from app.core.security import (
    TokenType,
    create_access_token,
    decode_token,
    hash_password,
    hash_token,
    verify_password,
)


def test_password_hash_roundtrip():
    hashed = hash_password("correct-horse-battery-staple")
    assert hashed != "correct-horse-battery-staple"
    assert verify_password("correct-horse-battery-staple", hashed)
    assert not verify_password("wrong-password", hashed)


def test_hash_token_is_deterministic_and_not_reversible_to_input():
    token = "abc123-verification-token"
    hashed = hash_token(token)

    assert hashed != token
    assert hash_token(token) == hashed  # same input always hashes the same, for DB lookup
    assert hash_token("a-different-token") != hashed


def test_access_token_roundtrip():
    token = create_access_token(user_id="11111111-1111-1111-1111-111111111111", email="a@b.com", role="USER")
    payload = decode_token(token)

    assert payload["sub"] == "11111111-1111-1111-1111-111111111111"
    assert payload["email"] == "a@b.com"
    assert payload["role"] == "USER"
    assert payload["type"] == TokenType.ACCESS
