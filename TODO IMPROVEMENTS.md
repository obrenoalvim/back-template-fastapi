# TODO Improvements

### Hash email-verification and password-reset tokens at rest
- **Category:** Bug (security)
- **What:** `User.verification_token` and `User.reset_token` are stored as the raw `secrets.token_urlsafe(32)` value, unlike `RefreshToken.jti` which is a non-secret lookup key. Anyone with read access to the `users` table (a DB leak, a backup, a careless admin query) can immediately take over any account mid-flow by using the token directly, no cracking needed.
- **Where:** `app/api/routes/auth.py` (`register`, `forgot_password`, `verify_email`, `reset_password`), `app/models/user.py`
- **Why:** Bearer secrets shouldn't be stored in plaintext, same principle already applied correctly to password hashing.
- **Risk:** Low to change (hash on write with e.g. `hashlib.sha256`, compare hashed on lookup), but touches the auth flow tests.
- **Effort:** Low

### Expired refresh_tokens rows are never cleaned up
- **What:** Rows in `refresh_tokens` are only deleted on logout or rotation. A user who never logs out or refreshes (e.g. abandons the session) leaves a row that outlives its own `expires_at` forever.
- **Where:** `app/models/refresh_token.py`, `app/api/routes/auth.py`
- **Why:** Unbounded table growth over the life of a real deployment; not a correctness bug (expired tokens are still rejected on use) but worth a periodic sweep.
- **Risk:** Low — additive only (a scheduled job or a `DELETE ... WHERE expires_at < now()` on some cadence).
- **Effort:** Low
