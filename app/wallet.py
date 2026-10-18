"""Wallet rules in one place (all amounts are taka, Decimal, 2 places).

Customer wallet
  * deposit request  -> admin approves -> balance goes up
  * booking          -> price is taken from the wallet at once; a cancelled booking is refunded
  * COD parcel       -> when delivered, the COD amount is credited to the customer's wallet
  * withdraw request -> amount is held (taken off the balance) straight away; a rejection gives it back

Rider wallet (same table, same user wallet)
  * commission is credited when a parcel is delivered
  * COD cash the rider collected is owed to ZENTO ("COD due") until the rider hands it in and an admin accepts it
  * a rider can only withdraw  balance - COD due  (the rest stays locked)
"""
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select

from app.models import Parcel, Rider, User, WalletRequest, WalletTransaction

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def q2(value) -> Decimal:
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def tk(value) -> str:
    return f"\u09F3{q2(value):,.2f}"  # taka sign


def lock_user(db, user_id: int) -> User:
    """Load a user row with a row lock (Postgres) so two requests cannot spend the same money."""
    user = db.scalar(select(User).where(User.id == user_id).with_for_update().execution_options(populate_existing=True))
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found.")
    return user


def ensure_funds(user: User, amount) -> None:
    amount, balance = q2(amount), q2(user.balance)
    if balance < amount:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Not enough wallet balance. This booking costs {tk(amount)} and your balance is {tk(balance)}. Deposit {tk(amount - balance)} or more first.",
        )


def post(db, user: User, kind: str, amount, note: str | None = None, parcel_id: int | None = None, request_id: int | None = None) -> WalletTransaction:
    """Apply one signed movement to the wallet and write it to the ledger. Never lets the balance go below zero."""
    amount = q2(amount)
    new_balance = q2(user.balance) + amount
    if new_balance < 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "Not enough wallet balance.")
    user.balance = new_balance
    txn = WalletTransaction(user_id=user.id, kind=kind, amount=amount, balance_after=new_balance,
                            note=(note or None) and note[:160], parcel_id=parcel_id, request_id=request_id)
    db.add(txn)
    return txn


# ---------------- COD owed by riders ----------------
def _rider_for(db, user_id: int) -> Rider | None:
    return db.scalar(select(Rider).where(Rider.user_id == user_id))


def cod_due(db, user_id: int) -> Decimal:
    """COD cash this rider collected on delivered parcels minus what an admin has accepted from them."""
    rider = _rider_for(db, user_id)
    if rider is None:
        return ZERO
    collected = db.scalar(select(func.coalesce(func.sum(Parcel.cod_amount), 0)).where(Parcel.rider_id == rider.id, Parcel.status == "delivered")) or 0
    handed_in = db.scalar(select(func.coalesce(func.sum(WalletRequest.amount), 0)).where(
        WalletRequest.user_id == user_id, WalletRequest.kind == "cod_deposit", WalletRequest.status == "approved")) or 0
    return max(ZERO, q2(collected) - q2(handed_in))


def cod_due_by_user(db) -> dict[int, Decimal]:
    """COD due for every rider that has a login (one pass, for the admin lists)."""
    collected = dict(db.execute(select(Rider.user_id, func.coalesce(func.sum(Parcel.cod_amount), 0))
                                .join(Parcel, Parcel.rider_id == Rider.id)
                                .where(Rider.user_id.is_not(None), Parcel.status == "delivered").group_by(Rider.user_id)).all())
    handed = dict(db.execute(select(WalletRequest.user_id, func.coalesce(func.sum(WalletRequest.amount), 0))
                             .where(WalletRequest.kind == "cod_deposit", WalletRequest.status == "approved").group_by(WalletRequest.user_id)).all())
    return {uid: max(ZERO, q2(c) - q2(handed.get(uid, 0))) for uid, c in collected.items()}


def pending_cod_deposits(db, user_id: int) -> Decimal:
    return q2(db.scalar(select(func.coalesce(func.sum(WalletRequest.amount), 0)).where(
        WalletRequest.user_id == user_id, WalletRequest.kind == "cod_deposit", WalletRequest.status == "pending")) or 0)


def withdrawable(db, user: User) -> Decimal:
    """What may be withdrawn now: the balance minus any COD the rider still owes."""
    return max(ZERO, q2(user.balance) - cod_due(db, user.id))


def snapshot(db, user: User) -> dict:
    due = cod_due(db, user.id)
    bal = q2(user.balance)
    return {"balance": str(bal), "cod_due": str(due), "withdrawable": str(max(ZERO, bal - due)), "locked": str(min(bal, due))}


# ---------------- parcel money events ----------------
def charge_booking(db, user: User, parcel: Parcel) -> None:
    post(db, user, "booking", -q2(parcel.price_total), note=f"Booking {parcel.tracking_number}", parcel_id=parcel.id)
    parcel.wallet_paid = True


def refund_booking(db, parcel: Parcel, reason: str = "Booking cancelled") -> None:
    """Give the booking fee back, once, for parcels that were paid from the wallet."""
    if not parcel.wallet_paid or parcel.refunded:
        return
    user = lock_user(db, parcel.user_id)
    post(db, user, "refund", q2(parcel.price_total), note=f"{reason} {parcel.tracking_number}", parcel_id=parcel.id)
    parcel.refunded = True


def settle_parcel_money(db, parcel: Parcel) -> None:
    """Call after a parcel becomes delivered (after settle_delivery): pays the rider commission and the COD amount, once each."""
    if parcel.rider_id and parcel.rider_commission is not None and not parcel.commission_paid:
        rider = db.get(Rider, parcel.rider_id)
        if rider is not None and rider.user_id:
            post(db, lock_user(db, rider.user_id), "commission", q2(parcel.rider_commission), note=f"Commission {parcel.tracking_number}", parcel_id=parcel.id)
            parcel.commission_paid = True
    if q2(parcel.cod_amount or 0) > 0 and not parcel.cod_credited:
        post(db, lock_user(db, parcel.user_id), "cod", q2(parcel.cod_amount), note=f"COD collected {parcel.tracking_number}", parcel_id=parcel.id)
        parcel.cod_credited = True
