import hashlib
import hmac
import os

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .database import get_db
from .models import ActivityLog, User


class NotAuthenticated(Exception):
    pass


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return f"pbkdf2${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt, digest = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000)
        return hmac.compare_digest(dk.hex(), digest)
    except Exception:
        return False


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    uid = request.session.get("uid")
    user = db.get(User, uid) if uid else None
    if not user or user.status != "active":
        request.session.clear()
        raise NotAuthenticated()
    return user


def require_role(*roles):
    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="You do not have permission for this action.")
        return user
    return dep


def log(db: Session, user, action: str, description: str = ""):
    db.add(ActivityLog(user_id=getattr(user, "id", None), action=action, description=description))
    db.commit()
