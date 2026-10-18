"""Create or promote the first admin from ADMIN_EMAIL / ADMIN_PASSWORD (runs at startup, safe to repeat)."""
import logging

from sqlalchemy import select

from app.config import get_settings
from app.database import SessionLocal
from app.models import User
from app.security import hash_password

log = logging.getLogger("zento")


def ensure_admin() -> None:
    s = get_settings()
    email = s.admin_email.strip().lower()
    if not email:
        return
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            if len(s.admin_password) < 8:
                log.warning("ADMIN_PASSWORD must be at least 8 characters; admin %s not created.", email)
                return
            db.add(User(full_name=s.admin_name.strip() or "Admin", email=email, phone="+000 000 0000",
                        password_hash=hash_password(s.admin_password), is_admin=True))
            log.info("Created admin account %s", email)
        elif not user.is_admin or not user.is_active:
            user.is_admin, user.is_active = True, True  # promote an existing account; its password is untouched
            log.info("Promoted %s to admin", email)
        db.commit()
