"""FastAPI dependencies (M4): repository access, auth, and role enforcement."""

from __future__ import annotations

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .db import Repository
from .entities import User, UserRole
from .security import decode_token
from .state import get_repo

_bearer = HTTPBearer(auto_error=True)


def repo_dependency() -> Repository:
    return get_repo()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    repo: Repository = Depends(repo_dependency),
) -> User:
    try:
        payload = decode_token(credentials.credentials)
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    user = repo.get_user(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown user")
    return user


def require_role(*roles: UserRole):
    """Dependency factory that allows only the given roles."""

    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return user

    return checker
