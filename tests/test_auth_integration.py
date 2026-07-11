import uuid

from sqlalchemy import select

from app.db.session import async_session_factory
from app.models.user import User


async def _verification_token(email: str) -> str:
    async with async_session_factory() as db:
        user = await db.scalar(select(User).where(User.email == email))
        assert user is not None
        assert user.verification_token is not None
        return user.verification_token


async def test_register_verify_login_notes_delete_flow(client):
    email = f"pytest-{uuid.uuid4()}@example.com"
    password = "password123"

    register = await client.post("/auth/register", json={"email": email, "password": password})
    assert register.status_code == 201
    assert register.content == b""

    duplicate = await client.post("/auth/register", json={"email": email, "password": password})
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "CONFLICT"

    login_unverified = await client.post("/auth/login", json={"email": email, "password": password})
    assert login_unverified.status_code == 401

    token = await _verification_token(email)
    verify = await client.get("/auth/verify-email", params={"token": token})
    assert verify.status_code == 200

    login = await client.post("/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    tokens = login.json()
    access_token = tokens["accessToken"]
    headers = {"Authorization": f"Bearer {access_token}"}

    create_note = await client.post("/api/notes", json={"title": "Hello", "content": "World"}, headers=headers)
    assert create_note.status_code == 201
    note_id = create_note.json()["id"]

    list_notes = await client.get("/api/notes", headers=headers)
    assert list_notes.status_code == 200
    assert any(n["id"] == note_id for n in list_notes.json())

    update_note = await client.put(
        f"/api/notes/{note_id}", json={"title": "Updated", "content": "World"}, headers=headers
    )
    assert update_note.status_code == 200
    assert update_note.json()["title"] == "Updated"

    delete_note = await client.delete(f"/api/notes/{note_id}", headers=headers)
    assert delete_note.status_code == 204

    admin_forbidden = await client.get("/admin/users", headers=headers)
    assert admin_forbidden.status_code == 403

    refresh = await client.post("/auth/refresh", json={"refreshToken": tokens["refreshToken"]})
    assert refresh.status_code == 200

    delete_account = await client.delete("/account", headers=headers)
    assert delete_account.status_code == 200


async def test_login_with_wrong_password_is_unauthorized(client):
    email = f"pytest-{uuid.uuid4()}@example.com"
    await client.post("/auth/register", json={"email": email, "password": "password123"})

    response = await client.post("/auth/login", json={"email": email, "password": "wrong-password"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"
