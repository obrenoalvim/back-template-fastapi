import uuid
from dataclasses import dataclass

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.exceptions import forbidden, unauthorized
from app.core.security import TokenType, decode_token
from app.models.user import Role

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class CurrentUser:
    id: uuid.UUID
    email: str
    role: str


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> CurrentUser:
    if credentials is None:
        raise unauthorized()
    try:
        payload = decode_token(credentials.credentials)
    except jwt.PyJWTError as exc:
        raise unauthorized() from exc

    if payload.get("type") != TokenType.ACCESS:
        raise unauthorized()

    return CurrentUser(id=uuid.UUID(payload["sub"]), email=payload["email"], role=payload["role"])


async def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if user.role != Role.ADMIN:
        raise forbidden()
    return user
