from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user
from app.core.exceptions import unauthorized
from app.core.security import hash_password, verify_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import ChangePasswordRequest

router = APIRouter(prefix="/account", tags=["account"])


@router.patch("/password", status_code=status.HTTP_200_OK)
async def change_password(
    body: ChangePasswordRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    db_user = await db.get(User, user.id)
    if not db_user or not verify_password(body.current_password, db_user.password_hash):
        raise unauthorized("Current password is incorrect")

    db_user.password_hash = hash_password(body.new_password)
    await db.commit()
    return Response(status_code=status.HTTP_200_OK)


@router.delete("", status_code=status.HTTP_200_OK)
async def delete_account(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    db_user = await db.get(User, user.id)
    if db_user:
        await db.delete(db_user)
        await db.commit()
    return Response(status_code=status.HTTP_200_OK)
