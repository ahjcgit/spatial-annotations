import hashlib
import secrets
from datetime import timedelta
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from .models import SessionToken, User, utcnow

hasher = PasswordHasher()
DUMMY_HASH = hasher.hash(secrets.token_urlsafe(32))
bearer = HTTPBearer(auto_error=False)


def db_session(request: Request):
    with request.app.state.session_factory() as db:
        yield db


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def check_password(encoded, password):
    try:
        return hasher.verify(encoded, password)
    except (VerificationError, InvalidHashError):
        return False


def issue_token(db, user, ttl_hours):
    raw = secrets.token_urlsafe(32)
    expiration = utcnow() + timedelta(hours=ttl_hours)
    db.add(SessionToken(token_hash=digest(raw), user_id=user.id, expires_at=expiration))
    db.commit()
    return {"access_token": raw, "expires_at": expiration, "user": user}


def optional_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db=Depends(db_session)):
    if credentials is None:
        return None
    token = db.scalar(select(SessionToken).where(SessionToken.token_hash == digest(credentials.credentials), SessionToken.expires_at > utcnow()))
    if not token:
        raise HTTPException(401, "Invalid or expired session", headers={"WWW-Authenticate": "Bearer"})
    return db.get(User, token.user_id)


def require_user(user=Depends(optional_user)):
    if user is None:
        raise HTTPException(401, "Authentication required", headers={"WWW-Authenticate": "Bearer"})
    return user
