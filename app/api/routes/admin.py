from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.api.deps import CurrentUser, require_admin
from app.db.session import get_db
from app.models.note import Note
from app.models.user import User
from app.schemas.note import NoteWithOwnerResponse
from app.schemas.user import UserSummaryResponse

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=list[UserSummaryResponse])
async def list_users(
    _: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[User]:
    result = await db.scalars(select(User))
    return list(result.all())


async def list_notes_with_owners(db: AsyncSession) -> list[Note]:
    # joinedload -> a single SQL JOIN no matter how many notes exist. Regression
    # guard: tests/test_admin_query_count.py asserts this stays exactly 1 query.
    result = await db.scalars(select(Note).options(joinedload(Note.owner)))
    return list(result.all())


@router.get("/notes", response_model=list[NoteWithOwnerResponse])
async def list_notes(
    _: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[NoteWithOwnerResponse]:
    notes = await list_notes_with_owners(db)
    return [NoteWithOwnerResponse(id=n.id, title=n.title, owner_email=n.owner.email) for n in notes]
