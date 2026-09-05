import uuid

from app.api.routes.admin import list_notes_with_owners
from app.core.security import hash_password
from app.db.session import async_session_factory, engine
from app.models.note import Note
from app.models.user import User
from tests.query_counter import count_queries


async def test_list_notes_with_owners_runs_one_query_regardless_of_row_count():
    async with async_session_factory() as db:
        owner = User(email=f"pytest-{uuid.uuid4()}@example.com", password_hash=hash_password("password123"))
        db.add(owner)
        await db.flush()

        notes = [Note(owner_id=owner.id, title=f"Note {i}", content="body") for i in range(4)]
        db.add_all(notes)
        await db.commit()

        try:
            with count_queries(engine) as counter:
                result = await list_notes_with_owners(db)

            assert len(result) >= 4
            assert all(n.owner.email == owner.email for n in result if n.owner_id == owner.id)
            assert counter.count == 1
        finally:
            for note in notes:
                await db.delete(note)
            await db.delete(owner)
            await db.commit()
