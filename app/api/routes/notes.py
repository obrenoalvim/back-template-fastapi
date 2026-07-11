import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user
from app.core.exceptions import not_found
from app.db.session import get_db
from app.models.note import Note
from app.schemas.note import NoteRequest, NoteResponse

router = APIRouter(prefix="/api/notes", tags=["notes"])


async def _get_owned_note(db: AsyncSession, note_id: uuid.UUID, owner_id: uuid.UUID) -> Note:
    note = await db.scalar(select(Note).where(Note.id == note_id, Note.owner_id == owner_id))
    if not note:
        raise not_found("Note not found")
    return note


@router.post("", response_model=NoteResponse, status_code=status.HTTP_201_CREATED)
async def create_note(
    body: NoteRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Note:
    note = Note(owner_id=user.id, title=body.title, content=body.content)
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return note


@router.get("", response_model=list[NoteResponse])
async def list_notes(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Note]:
    result = await db.scalars(select(Note).where(Note.owner_id == user.id))
    return list(result.all())


@router.get("/{note_id}", response_model=NoteResponse)
async def get_note(
    note_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Note:
    return await _get_owned_note(db, note_id, user.id)


@router.put("/{note_id}", response_model=NoteResponse)
async def update_note(
    note_id: uuid.UUID,
    body: NoteRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Note:
    note = await _get_owned_note(db, note_id, user.id)
    note.title = body.title
    note.content = body.content
    await db.commit()
    await db.refresh(note)
    return note


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(
    note_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    note = await _get_owned_note(db, note_id, user.id)
    await db.delete(note)
    await db.commit()
