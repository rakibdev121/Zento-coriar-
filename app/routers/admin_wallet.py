"""Admin side of the wallet: approve or reject deposits, withdrawals and rider COD hand-overs, adjust balances, see totals.

/api/admin/wallet/*  (admins only)
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import func, or_, select

from app import wallet
from app.config import get_settings
from app.deps import CurrentAdmin, DbSession
from app.models import ActivityLog, Rider, User, WalletRequest, WalletTransaction
from app.routers.wallet import _request_out, _txn_out, iso

router = APIRouter(prefix="/admin/wallet", tags=["admin-wallet"])


def _log(db, title: str, detail: str) -> None:
    db.add(ActivityLog(kind="wallet", title=title, detail=detail[:160]))


def _req_row(r: WalletRequest) -> dict:
    return {**_request_out(r), "user": {"id": r.user.id, "full_name": r.user.full_name, "email": r.user.email, "phone": r.user.phone}}


@router.get("/summary")
def summary(db: DbSession, admin: CurrentAdmin):
    def total(*conds):
        return wallet.q2(db.scalar(select(func.coalesce(func.sum(WalletTransaction.amount), 0)).where(*conds)) or 0)

    def req_sum(kind, st):
        return wallet.q2(db.scalar(select(func.coalesce(func.sum(WalletRequest.amount), 0)).where(WalletRequest.kind == kind, WalletRequest.status == st)) or 0)

    pending = dict(db.execute(select(WalletRequest.kind, func.count()).where(WalletRequest.status == "pending").group_by(WalletRequest.kind)).all())
    in_wallets = wallet.q2(db.scalar(select(func.coalesce(func.sum(User.balance), 0)).where(User.is_admin.is_(False))) or 0)
    cod_out = sum(wallet.cod_due_by_user(db).values(), Decimal("0"))
    return {
        "currency": get_settings().currency,
        "in_wallets": str(in_wallets),  # money ZENTO owes to customers and riders
        "deposits_approved": str(req_sum("deposit", "approved")),
        "withdrawals_paid": str(req_sum("withdraw", "approved")),
        "booking_income": str(-total(WalletTransaction.kind == "booking") - total(WalletTransaction.kind == "refund")),
        "commissions_paid": str(total(WalletTransaction.kind == "commission")),
        "cod_with_riders": str(wallet.q2(cod_out)),
        "pending": {"deposit": pending.get("deposit", 0), "withdraw": pending.get("withdraw", 0), "cod_deposit": pending.get("cod_deposit", 0)},
    }


@router.get("/requests")
def list_requests(
    db: DbSession, admin: CurrentAdmin,
    kind: Annotated[Literal["deposit", "withdraw", "cod_deposit"] | None, Query()] = None,
    status_filter: Annotated[Literal["pending", "approved", "rejected"] | None, Query(alias="status")] = "pending",
    page: Annotated[int, Query(ge=1)] = 1, page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    conds = []
    if kind:
        conds.append(WalletRequest.kind == kind)
    if status_filter:
        conds.append(WalletRequest.status == status_filter)
    total = db.scalar(select(func.count()).select_from(WalletRequest).where(*conds)) or 0
    rows = db.scalars(select(WalletRequest).where(*conds).order_by(WalletRequest.created_at.desc(), WalletRequest.id.desc())
                      .offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [_req_row(r) for r in rows], "total": total, "page": page, "page_size": page_size}


def _pending_request(db, request_id: int) -> WalletRequest:
    r = db.scalar(select(WalletRequest).where(WalletRequest.id == request_id).with_for_update(of=WalletRequest))
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Request not found.")
    if r.status != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, f"This request was already {r.status}.")
    return r


@router.post("/requests/{request_id}/approve")
def approve(request_id: int, db: DbSession, admin: CurrentAdmin):
    r = _pending_request(db, request_id)
    if r.kind == "deposit":
        wallet.post(db, wallet.lock_user(db, r.user_id), "deposit", r.amount, note=f"Deposit via {r.method} {r.reference or ''}".strip(), request_id=r.id)
    elif r.kind == "cod_deposit":
        due = wallet.cod_due(db, r.user_id)
        if wallet.q2(r.amount) > due:
            raise HTTPException(status.HTTP_409_CONFLICT, f"The rider only owes {wallet.tk(due)}. Reject this request or ask for the right amount.")
    # withdraw: the money was already held when the rider/customer asked; approving means "paid out".
    r.status, r.reviewed_at = "approved", datetime.now(timezone.utc)
    _log(db, {"deposit": "Deposit Approved", "withdraw": "Withdrawal Paid", "cod_deposit": "COD Accepted"}[r.kind], f"{r.user.full_name} · {wallet.tk(r.amount)}")
    db.commit()
    db.refresh(r)
    return _req_row(r)


class RejectIn(BaseModel):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=255)]


@router.post("/requests/{request_id}/reject")
def reject(request_id: int, payload: RejectIn, db: DbSession, admin: CurrentAdmin):
    r = _pending_request(db, request_id)
    if r.kind == "withdraw":  # give the held money back
        wallet.post(db, wallet.lock_user(db, r.user_id), "withdrawal_refund", r.amount, note="Withdrawal rejected, money returned", request_id=r.id)
    r.status, r.admin_note, r.reviewed_at = "rejected", payload.reason, datetime.now(timezone.utc)
    _log(db, "Wallet Request Rejected", f"{r.user.full_name} · {r.kind} · {wallet.tk(r.amount)}")
    db.commit()
    db.refresh(r)
    return _req_row(r)


@router.get("/users")
def list_users(db: DbSession, admin: CurrentAdmin, q: str | None = None, role: Annotated[Literal["all", "rider", "customer"], Query()] = "all",
               page: Annotated[int, Query(ge=1)] = 1, page_size: Annotated[int, Query(ge=1, le=100)] = 20):
    conds = [User.is_admin.is_(False)]
    rider_user_ids = select(Rider.user_id).where(Rider.user_id.is_not(None))
    if role == "rider":
        conds.append(User.id.in_(rider_user_ids))
    elif role == "customer":
        conds.append(User.id.not_in(rider_user_ids))
    if q and q.strip():
        like = f"%{q.strip().lower()}%"
        conds.append(or_(func.lower(User.full_name).like(like), func.lower(User.email).like(like), User.phone.like(like)))
    total = db.scalar(select(func.count()).select_from(User).where(*conds)) or 0
    users = db.scalars(select(User).where(*conds).order_by(User.balance.desc(), User.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    due = wallet.cod_due_by_user(db)
    riders = {uid for (uid,) in db.execute(select(Rider.user_id).where(Rider.user_id.is_not(None)))}
    return {"items": [{"id": u.id, "full_name": u.full_name, "email": u.email, "phone": u.phone, "balance": str(wallet.q2(u.balance)),
                       "is_rider": u.id in riders, "cod_due": str(due.get(u.id, wallet.ZERO))} for u in users],
            "total": total, "page": page, "page_size": page_size}


@router.get("/users/{user_id}/transactions")
def user_transactions(user_id: int, db: DbSession, admin: CurrentAdmin, page: Annotated[int, Query(ge=1)] = 1, page_size: Annotated[int, Query(ge=1, le=100)] = 30):
    if db.get(User, user_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found.")
    total = db.scalar(select(func.count()).select_from(WalletTransaction).where(WalletTransaction.user_id == user_id)) or 0
    rows = db.scalars(select(WalletTransaction).where(WalletTransaction.user_id == user_id).order_by(WalletTransaction.id.desc())
                      .offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [_txn_out(t) for t in rows], "total": total, "page": page, "page_size": page_size}


class AdjustIn(BaseModel):
    amount: Annotated[Decimal, Field(max_digits=10, decimal_places=2)]  # + adds, - removes
    note: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=140)]


@router.post("/users/{user_id}/adjust")
def adjust(user_id: int, payload: AdjustIn, db: DbSession, admin: CurrentAdmin):
    """Manual correction (for example crediting a rider's old commission). Always needs a written reason."""
    if payload.amount == 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Enter an amount other than zero.")
    user = wallet.lock_user(db, user_id)
    if user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin accounts have no wallet.")
    wallet.post(db, user, "adjustment", payload.amount, note=f"Admin: {payload.note}")
    _log(db, "Wallet Adjusted", f"{user.full_name} · {wallet.tk(payload.amount)} · {payload.note}")
    db.commit()
    return {"id": user.id, **wallet.snapshot(db, user)}


class CodReceiveIn(BaseModel):
    amount: Annotated[Decimal, Field(gt=0, max_digits=10, decimal_places=2)]


@router.post("/riders/{user_id}/cod-receive", status_code=status.HTTP_201_CREATED)
def cod_receive(user_id: int, payload: CodReceiveIn, db: DbSession, admin: CurrentAdmin):
    """The rider handed cash to the office: record it and accept it in one step."""
    user = db.get(User, user_id)
    if user is None or db.scalar(select(Rider.id).where(Rider.user_id == user_id)) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rider not found.")
    due, amount = wallet.cod_due(db, user_id), wallet.q2(payload.amount)
    if amount > due:
        raise HTTPException(status.HTTP_409_CONFLICT, f"This rider only owes {wallet.tk(due)}.")
    now = datetime.now(timezone.utc)
    r = WalletRequest(user_id=user_id, kind="cod_deposit", amount=amount, method="cash", account="office", status="approved", reviewed_at=now)
    db.add(r)
    _log(db, "COD Accepted", f"{user.full_name} · {wallet.tk(amount)}")
    db.commit()
    db.refresh(r)
    return _req_row(r)
