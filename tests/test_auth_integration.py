import uuid

from sqlalchemy import select

from app.core.security import hash_token
from app.db.session import async_session_factory
from app.models.user import User


def _capture_mail(sent: dict[str, str]):
    def _send(to: str, subject: str, body: str) -> None:
        sent["to"] = to
        sent["subject"] = subject
        sent["body"] = body

    return _send


async def _get_user(email: str) -> User:
    async with async_session_factory() as db:
        user = await db.scalar(select(User).where(User.email == email))
        assert user is not None
        return user


async def test_register_verify_login_notes_delete_flow(client, monkeypatch):
    email = f"pytest-{uuid.uuid4()}@example.com"
    password = "password123"

    sent: dict[str, str] = {}
    monkeypatch.setattr("app.api.routes.auth.send_mail", _capture_mail(sent))

    register = await client.post("/auth/register", json={"email": email, "password": password})
    assert register.status_code == 201
    assert register.content == b""

    duplicate = await client.post("/auth/register", json={"email": email, "password": password})
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "CONFLICT"

    login_unverified = await client.post("/auth/login", json={"email": email, "password": password})
    assert login_unverified.status_code == 401

    token = sent["body"].removeprefix("Verification token: ")
    user = await _get_user(email)
    assert user.verification_token == hash_token(token)
    assert user.verification_token != token

    verify_wrong = await client.get("/auth/verify-email", params={"token": "not-the-real-token"})
    assert verify_wrong.status_code == 404

    verify = await client.get("/auth/verify-email", params={"token": token})
    assert verify.status_code == 200

    login = await client.post("/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    tokens = login.json()
    access_token = tokens["accessToken"]
    headers = {"Authorization": f"Bearer {access_token}"}

    create_note = await client.post(
        "/api/notes", json={"title": "Hello", "content": "World"}, headers=headers
    )
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


async def test_forgot_password_reset_flow_hashes_token_at_rest(client, monkeypatch):
    email = f"pytest-{uuid.uuid4()}@example.com"
    await client.post("/auth/register", json={"email": email, "password": "password123"})

    sent: dict[str, str] = {}
    monkeypatch.setattr("app.api.routes.auth.send_mail", _capture_mail(sent))

    forgot = await client.post("/auth/forgot-password", json={"email": email})
    assert forgot.status_code == 200

    token = sent["body"].removeprefix("Reset token: ")
    user = await _get_user(email)
    assert user.reset_token == hash_token(token)
    assert user.reset_token != token

    reset_wrong = await client.post(
        "/auth/reset-password", json={"token": "not-the-real-token", "newPassword": "new-password123"}
    )
    assert reset_wrong.status_code == 404

    reset = await client.post("/auth/reset-password", json={"token": token, "newPassword": "new-password123"})
    assert reset.status_code == 200

    login_old = await client.post("/auth/login", json={"email": email, "password": "password123"})
    assert login_old.status_code == 401

    login_new = await client.post("/auth/login", json={"email": email, "password": "new-password123"})
    assert login_new.status_code == 401  # email never verified in this test
