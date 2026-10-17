from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.deps import CurrentUser, DbSession
from app.models import User
from app.schemas import LoginRequest, RegisterRequest, TokenOut, UserOut
from app.security import DUMMY_HASH, create_access_token, hash_password, login_limiter, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: DbSession):
    exists = db.scalar(select(User.id).where(User.email == payload.email))
    conflict = HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists. Sign in instead.")
    if exists:
        raise conflict
    user = User(
        full_name=payload.full_name, email=payload.email, phone=payload.phone, password_hash=hash_password(payload.password)
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:  # concurrent registration with the same email
        db.rollback()
        raise conflict
    db.refresh(user)
    return TokenOut(access_token=create_access_token(user.id), user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenOut)
def login(payload: LoginRequest, request: Request, db: DbSession):
    client_ip = request.client.host if request.client else "unknown"
    key = f"{client_ip}:{payload.email}"
    wait = login_limiter.retry_after(key)
    if wait:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Too many failed sign-in attempts. Try again in {max(1, wait // 60)} minute(s).",
            headers={"Retry-After": str(wait)},
        )
    user = db.scalar(select(User).where(User.email == payload.email))
    password_ok = verify_password(payload.password, user.password_hash if user else DUMMY_HASH)
    if not user or not password_ok or not user.is_active:
        login_limiter.record_failure(key)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password.", headers={"WWW-Authenticate": "Bearer"})
    login_limiter.reset(key)
    return TokenOut(access_token=create_access_token(user.id), user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser):
    return user
