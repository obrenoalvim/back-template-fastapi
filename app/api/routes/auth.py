import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import conflict, not_found, unauthorized
from app.core.mail import send_mail
from app.core.rate_limit import limiter
from app.core.security import (
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.session import get_db
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])

TOKEN_TTL = timedelta(hours=1)


@router.post("/register", status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register(request: Request, body: RegisterRequest, db: AsyncSession = Depends(get_db)) -> Response:
    existing = await db.scalar(select(User).where(User.email == body.email))
    if existing:
        raise conflict("Email already registered")

    token = secrets.token_urlsafe(32)
    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        verification_token=token,
        verification_token_expires_at=datetime.now(timezone.utc) + TOKEN_TTL,
    )
    db.add(user)
    await db.commit()

    send_mail(body.email, "Verify your email", f"Verification token: {token}")
    return Response(status_code=status.HTTP_201_CREATED)


@router.get("/verify-email", status_code=status.HTTP_200_OK)
async def verify_email(token: str, db: AsyncSession = Depends(get_db)) -> Response:
    user = await db.scalar(select(User).where(User.verification_token == token))
    if not user:
        raise not_found("Invalid verification token")
    if user.verification_token_expires_at and user.verification_token_expires_at < datetime.now(timezone.utc):
        raise conflict("Verification token expired")

    user.email_verified = True
    user.verification_token = None
    user.verification_token_expires_at = None
    await db.commit()
    return Response(status_code=status.HTTP_200_OK)


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(request: Request, body: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    user = await db.scalar(select(User).where(User.email == body.email))
    if not user or not verify_password(body.password, user.password_hash):
        raise unauthorized("Invalid email or password")
    if not user.email_verified:
        raise unauthorized("Email not verified")

    return await _issue_tokens(db, user)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    try:
        payload = decode_token(body.refresh_token)
    except jwt.PyJWTError as exc:
        raise unauthorized("Invalid or expired refresh token") from exc

    if payload.get("type") != TokenType.REFRESH:
        raise unauthorized("Invalid or expired refresh token")

    stored = await db.scalar(select(RefreshToken).where(RefreshToken.jti == payload["jti"]))
    if not stored or stored.expires_at < datetime.now(timezone.utc):
        raise unauthorized("Invalid or expired refresh token")

    user = await db.get(User, uuid.UUID(payload["sub"]))
    if not user:
        raise unauthorized("Invalid or expired refresh token")

    await db.delete(stored)
    return await _issue_tokens(db, user)


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(body: LogoutRequest, db: AsyncSession = Depends(get_db)) -> Response:
    try:
        payload = decode_token(body.refresh_token)
    except jwt.PyJWTError:
        return Response(status_code=status.HTTP_200_OK)
    await db.execute(delete(RefreshToken).where(RefreshToken.jti == payload.get("jti")))
    await db.commit()
    return Response(status_code=status.HTTP_200_OK)


@router.post("/forgot-password", status_code=status.HTTP_200_OK)
async def forgot_password(body: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)) -> Response:
    user = await db.scalar(select(User).where(User.email == body.email))
    if user:
        token = secrets.token_urlsafe(32)
        user.reset_token = token
        user.reset_token_expires_at = datetime.now(timezone.utc) + TOKEN_TTL
        await db.commit()
        send_mail(body.email, "Reset your password", f"Reset token: {token}")
    # Always 200 — no user-enumeration leak, same response whether or not the email exists.
    return Response(status_code=status.HTTP_200_OK)


@router.post("/reset-password", status_code=status.HTTP_200_OK)
async def reset_password(body: ResetPasswordRequest, db: AsyncSession = Depends(get_db)) -> Response:
    user = await db.scalar(select(User).where(User.reset_token == body.token))
    if not user:
        raise not_found("Invalid reset token")
    if user.reset_token_expires_at and user.reset_token_expires_at < datetime.now(timezone.utc):
        raise conflict("Reset token expired")

    user.password_hash = hash_password(body.new_password)
    user.reset_token = None
    user.reset_token_expires_at = None
    await db.commit()
    return Response(status_code=status.HTTP_200_OK)


async def _issue_tokens(db: AsyncSession, user: User) -> TokenResponse:
    access_token = create_access_token(str(user.id), user.email, user.role)
    refresh_token, jti, expires_at = create_refresh_token(str(user.id))
    db.add(RefreshToken(user_id=user.id, jti=jti, expires_at=expires_at))
    await db.commit()
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)
