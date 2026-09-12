# TODO Improvements

### Expired refresh_tokens rows are never cleaned up
- **What:** Rows in `refresh_tokens` are only deleted on logout or rotation. A user who never logs out or refreshes (e.g. abandons the session) leaves a row that outlives its own `expires_at` forever.
- **Where:** `app/models/refresh_token.py`, `app/api/routes/auth.py`
- **Why:** Unbounded table growth over the life of a real deployment; not a correctness bug (expired tokens are still rejected on use) but worth a periodic sweep.
- **Risk:** Low — additive only (a scheduled job or a `DELETE ... WHERE expires_at < now()` on some cadence).
- **Effort:** Low
