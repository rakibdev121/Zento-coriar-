"""Wallet API for signed-in users (customers and riders share it): /api/wallet/*.

Deposits and rider COD hand-overs are requests an admin approves (see routers/admin_wallet.py). Withdrawals hold the money
at once; the admin pays it out (or rejects it and the money comes back).
"""
import re
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field, StringConstraints, field_validator, model_validator
from sqlalchemy import func, select

from app import wallet
from app.config import get_settings
from app.deps import CurrentUser, DbSession
from app.models import Rider, WalletRequest, WalletTransaction
from app.rider_logic import aware

router = APIRouter(prefix="/wallet", tags=["wallet"])

Method = Literal["bkash", "nagad", "rocket", "bank", "cash"]
MOBILE_METHODS = ("bkash", "nagad", "rocket")
_BD_MOBILE = re.compile(r"^(?:\+?88)?01[3-9]\d{8}$")


def iso(dt):
    return aware(dt).isoformat() if dt else None


class MoneyRequest(BaseModel):
    amount: Annotated[Decimal, Field(gt=0, le=1_000_000, max_digits=10, decimal_places=2)]
    method: Method
    account: Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=40)]
    reference: Annotated[str, StringConstraints(strip_whitespace=True, max_length=60)] | None = None

    @model_validator(mode="after")
    def _check(self):
        if self.method in MOBILE_METHODS:
            digits = re.sub(r"[\s\-]", "", self.account)
            if not _BD_MOBILE.match(digits):
                raise ValueError("Enter a valid mobile number, for example 01712345678.")
            self.account = digits
        return self


def _request_out(r: WalletRequest) -> dict:
    return {"id": r.id, "kind": r.kind, "amount": str(r.amount), "method": r.method, "account": r.account, "reference": r.reference,
            "status": r.status, "admin_note": r.admin_note, "created_at": iso(r.created_at), "reviewed_at": iso(r.reviewed_at)}


def _txn_out(t: WalletTransaction) -> dict:
    return {"id": t.id, "kind": t.kind, "amount": str(t.amount), "balance_after": str(t.balance_after), "note": t.note, "created_at": iso(t.created_at)}


def _is_rider(db, user) -> bool:
    return db.scalar(select(Rider.id).where(Rider.user_id == user.id)) is not None


def _field_error(field: str, message: str) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, message)


@router.get("")
def overview(db: DbSession, user: CurrentUser):
    s = get_settings()
    requests = db.scalars(select(WalletRequest).where(WalletRequest.user_id == user.id).order_by(WalletRequest.created_at.desc(), WalletRequest.id.desc()).limit(30)).all()
    txns = db.scalars(select(WalletTransaction).where(WalletTransaction.user_id == user.id).order_by(WalletTransaction.id.desc()).limit(30)).all()
    rider = _is_rider(db, user)
    return {
        "currency": s.currency, "is_rider": rider, **wallet.snapshot(db, user),
        "pending_cod_deposit": str(wallet.pending_cod_deposits(db, user.id)),
        "min_deposit": str(s.wallet_min_deposit), "min_withdraw": str(s.wallet_min_withdraw),
        "pay_to": {"bkash": s.pay_bkash, "nagad": s.pay_nagad, "rocket": s.pay_rocket, "bank": s.pay_bank},
        "transactions": [_txn_out(t) for t in txns], "requests": [_request_out(r) for r in requests],
    }


@router.get("/transactions")
def transactions(db: DbSession, user: CurrentUser, page: Annotated[int, Query(ge=1)] = 1, page_size: Annotated[int, Query(ge=1, le=50)] = 20):
    total = db.scalar(select(func.count()).select_from(WalletTransaction).where(WalletTransaction.user_id == user.id)) or 0
    rows = db.scalars(select(WalletTransaction).where(WalletTransaction.user_id == user.id).order_by(WalletTransaction.id.desc())
                      .offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [_txn_out(t) for t in rows], "total": total, "page": page, "page_size": page_size}


@router.post("/deposit", status_code=status.HTTP_201_CREATED)
def deposit(payload: MoneyRequest, db: DbSession, user: CurrentUser):
    """Customer says "I sent Tk X by bKash, TrxID ..."; an admin checks it and approves."""
    s = get_settings()
    if payload.amount < s.wallet_min_deposit:
        raise _field_error("amount", f"The smallest deposit is {wallet.tk(s.wallet_min_deposit)}.")
    if payload.method == "cash":
        raise HTTPException(status.HTTP_409_CONFLICT, "Choose bKash, Nagad, Rocket or Bank for a deposit.")
    if not payload.reference or len(payload.reference) < 6:
        raise HTTPException(status.HTTP_409_CONFLICT, "Enter the transaction ID (TrxID) of your payment.")
    dup = db.scalar(select(WalletRequest.id).where(WalletRequest.kind == "deposit", WalletRequest.status != "rejected",
                                                   func.lower(WalletRequest.reference) == payload.reference.lower()))
    if dup:
        raise HTTPException(status.HTTP_409_CONFLICT, "This transaction ID was already submitted.")
    req = WalletRequest(user_id=user.id, kind="deposit", amount=wallet.q2(payload.amount), method=payload.method, account=payload.account, reference=payload.reference)
    db.add(req)
    db.commit()
    db.refresh(req)
    return _request_out(req)


@router.post("/withdraw", status_code=status.HTTP_201_CREATED)
def withdraw(payload: MoneyRequest, db: DbSession, user: CurrentUser):
    """The amount leaves the balance immediately (held). Riders can only take out balance minus the COD they still owe."""
    s = get_settings()
    if payload.method == "cash":
        raise HTTPException(status.HTTP_409_CONFLICT, "Choose bKash, Nagad, Rocket or Bank for a withdrawal.")
    amount = wallet.q2(payload.amount)
    if amount < s.wallet_min_withdraw:
        raise HTTPException(status.HTTP_409_CONFLICT, f"The smallest withdrawal is {wallet.tk(s.wallet_min_withdraw)}.")
    locked_user = wallet.lock_user(db, user.id)
    due = wallet.cod_due(db, locked_user.id)
    free = max(wallet.ZERO, wallet.q2(locked_user.balance) - due)
    if amount > free:
        if due > 0:
            raise HTTPException(status.HTTP_409_CONFLICT,
                                f"Withdrawal is locked until you hand in your COD cash. You owe {wallet.tk(due)}; you can withdraw up to {wallet.tk(free)} now.")
        raise HTTPException(status.HTTP_409_CONFLICT, f"Not enough balance. You can withdraw up to {wallet.tk(free)}.")
    req = WalletRequest(user_id=user.id, kind="withdraw", amount=amount, method=payload.method, account=payload.account, reference=payload.reference or None)
    db.add(req)
    db.flush()
    wallet.post(db, locked_user, "withdrawal", -amount, note=f"Withdrawal to {payload.method} {payload.account}", request_id=req.id)
    db.commit()
    db.refresh(req)
    return _request_out(req)


@router.post("/cod-deposit", status_code=status.HTTP_201_CREATED)
def cod_deposit(payload: MoneyRequest, db: DbSession, user: CurrentUser):
    """A rider reports that COD cash was handed in (or sent by bKash etc.). It counts once an admin accepts it."""
    if not _is_rider(db, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only riders can deposit COD cash.")
    due = wallet.cod_due(db, user.id)
    open_amount = due - wallet.pending_cod_deposits(db, user.id)
    amount = wallet.q2(payload.amount)
    if due <= 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "You have no COD cash to hand in.")
    if amount > open_amount:
        raise HTTPException(status.HTTP_409_CONFLICT, f"You can hand in at most {wallet.tk(max(wallet.ZERO, open_amount))} (COD due {wallet.tk(due)}, some is already waiting for approval).")
    if payload.method != "cash" and (not payload.reference or len(payload.reference) < 6):
        raise HTTPException(status.HTTP_409_CONFLICT, "Enter the transaction ID of your payment.")
    req = WalletRequest(user_id=user.id, kind="cod_deposit", amount=amount, method=payload.method, account=payload.account, reference=payload.reference or None)
    db.add(req)
    db.commit()
    db.refresh(req)
    return _request_out(req)
