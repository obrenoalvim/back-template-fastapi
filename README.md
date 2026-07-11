English | [Português](README.pt.md)

# back-template-fastapi

Production-ready backend base template: FastAPI, Python 3.13, async SQLAlchemy 2.0 + Alembic + Postgres, JWT auth (access + rotating/revocable refresh tokens), rate limiting, structured logging, and Docker — all pre-wired and tested end to end. Sibling of `back-template-nest`, `back-template-laravel`, and `back-template-spring`: same endpoint contract and error shape, different stack.

## Contents

- [Stack](#stack)
- [Project structure](#project-structure)
- [Getting started (Docker)](#getting-started-docker--recommended)
- [Getting started (without Docker)](#getting-started-without-docker)
- [Environment variables](#environment-variables)
- [Auth](#auth)
- [Roles](#roles)
- [Error shape](#error-shape)
- [Database](#database)
- [Example CRUD resource](#example-crud-resource)
- [API docs](#api-docs)
- [Testing](#testing)
- [CI/CD](#cicd)
- [Docker](#docker-1)
- [Scripts](#scripts)
- [Using this as a template](#using-this-as-a-template)
- [Design notes and gotchas](#design-notes-and-gotchas)

## Stack

- [FastAPI](https://fastapi.tiangolo.com) — async, Pydantic v2 request/response validation, auto OpenAPI docs
- [uv](https://docs.astral.sh/uv) — dependency management + Python version management (no pyenv/pip needed)
- [SQLAlchemy](https://www.sqlalchemy.org) 2.0 (async, `asyncpg`) + [Alembic](https://alembic.sqlalchemy.org) — schema versioned in code, migrations committed to the repo
- [Postgres](https://www.postgresql.org)
- JWT auth ([PyJWT](https://pyjwt.readthedocs.io)) — short-lived access token + longer-lived refresh token, rotated and persisted server-side for revocation (`app/models/refresh_token.py`)
- [bcrypt](https://pypi.org/project/bcrypt) — password hashing
- [slowapi](https://github.com/laurentS/slowapi) — rate limiting (5 req/min/IP on login/register)
- Mail via SMTP, with a console fallback in dev (`app/core/mail.py`) — no setup required to try the auth flow locally
- [structlog](https://www.structlog.org) — structured logging, pretty in dev, JSON in prod
- Consistent `{"error": {"code", "message", "details"}}` shape across every endpoint (`app/core/exceptions.py`)
- [pytest](https://pytest.org) + [pytest-asyncio](https://pytest-asyncio.readthedocs.io) + [httpx](https://www.python-httpx.org) — unit + integration tests against a real Postgres, no mocked DB
- [ruff](https://docs.astral.sh/ruff) — lint + format; [mypy](https://mypy-lang.org) — type checking
- [pre-commit](https://pre-commit.com) — ruff on commit
- Docker + docker-compose — app and Postgres both containerized, migrations run automatically on container start
- GitHub Actions CI — lint/type-check/test against a real Postgres service container, Docker image build
- `/health` for the Docker healthcheck

## Project structure

```
app/
  main.py                 # FastAPI app, middleware, exception handlers, router includes
  core/
    config.py              # pydantic-settings Settings (env-validated)
    security.py             # password hashing, JWT encode/decode
    exceptions.py            # ApiException + handlers → {"error": {...}} shape
    logging.py                # structlog config
    mail.py                    # SMTP send, console fallback in dev
    rate_limit.py               # slowapi limiter
  db/
    session.py                   # async engine + session factory
    base.py                       # declarative Base
  models/                          # User, RefreshToken, Note (SQLAlchemy)
  schemas/                          # Pydantic request/response models
  api/
    deps.py                          # get_current_user, require_admin
    routes/
      auth.py, account.py, admin.py, notes.py, health.py
alembic/
  versions/                          # generated SQL migrations — commit these
tests/
  test_security.py                    # unit: password hash, JWT roundtrip
  test_auth_integration.py             # integration: full auth + notes flow, real Postgres
```

## Getting started (Docker — recommended)

```bash
cp .env.example .env
# generate a real secret and drop it into .env as JWT_SECRET
python -c "import secrets; print(secrets.token_urlsafe(32))"

docker compose up -d --build
```

App: [http://localhost:8082](http://localhost:8082). Postgres is exposed on host port `5459` by default (not `5432`, to avoid clashing with a local Postgres install). Migrations run automatically on container start (`entrypoint.sh`).

## Getting started (without Docker)

Requires a Postgres instance and [uv](https://docs.astral.sh/uv/getting-started/installation/).

```bash
cp .env.example .env   # point DATABASE_URL at your own Postgres
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8082
```

## Environment variables

See `.env.example` for the full, commented list.

| Variable                          | Required    | Purpose                                                          |
| ---------------------------------- | ----------- | ------------------------------------------------------------------ |
| `DATABASE_URL`                     | yes         | Postgres connection string (asyncpg driver)                         |
| `JWT_SECRET`                       | yes         | ≥32 chars; access/refresh token signing                             |
| `DB_HOST_PORT/NAME/USER/PASSWORD`  | Docker only | `docker-compose.yml` defaults, used to compose `DATABASE_URL`       |
| `ENVIRONMENT`                      | no          | `dev` (pretty logs) or anything else (JSON logs); default `dev`     |
| `LOG_LEVEL`                        | no          | structlog level; default `info`                                     |
| `CORS_ORIGINS`                     | no          | Comma-separated origins allowed to call this API from the browser (this backend, unlike `back-template-spring`, has no BFF pairing — `front-template-react` calls it directly); default `http://localhost:5173` |
| `MAIL_HOST`/`MAIL_PORT`/`MAIL_USERNAME`/`MAIL_PASSWORD` | no | Sends real email via SMTP; without `MAIL_HOST`, emails are logged to console instead |

`app/core/config.py` validates these with `pydantic-settings` at import time.

## Auth

`app/api/routes/auth.py` (all `/auth/*`, public):

- `POST /auth/register` — 201, empty body. 409 if email taken.
- `GET /auth/verify-email?token=...` — 200 empty. 404 invalid token, 409 expired.
- `POST /auth/login` — 200, `{accessToken, refreshToken}`. 401 invalid credentials or unverified email.
- `POST /auth/refresh` — rotates the refresh token (old one deleted, new one issued). 401 if invalid/expired/revoked.
- `POST /auth/logout` — 200, idempotent.
- `POST /auth/forgot-password` — always 200 (no user-enumeration leak).
- `POST /auth/reset-password` — 200. 404/409 like verify-email.
- `PATCH /account/password`, `DELETE /account` (`app/api/routes/account.py`) — authenticated, `Authorization: Bearer <accessToken>`.
- Rate limited: 5 register/login attempts per 60s per IP (`slowapi`, see `app/core/rate_limit.py`).
- `app/api/deps.py`'s `get_current_user` is the single dependency every protected route uses — decodes and validates the bearer token, no per-route duplication.

**Refresh tokens are persisted**: unlike a purely stateless JWT scheme, each refresh token's `jti` is stored in the `refresh_tokens` table (`app/models/refresh_token.py`) so it can be revoked/rotated server-side — logging out or refreshing deletes the old row, so a stolen refresh token can't be replayed after rotation.

## Roles

`Role` enum (`USER` | `ADMIN`, default `USER`) on `User.role` — never trust a role from a request body. `GET /admin/users` (`app/api/routes/admin.py`) is the reference admin-only endpoint, guarded by the `require_admin` dependency (built on top of `get_current_user`, so it's the same JWT check plus a role assertion). No self-serve promotion — flip it directly in the DB for local testing: `UPDATE users SET role = 'ADMIN' WHERE email = '...';`.

## Error shape

Every error response — validation, auth, not-found, unhandled — has the same envelope, produced by exception handlers in `app/core/exceptions.py`:

```json
{ "error": { "code": "VALIDATION_ERROR", "message": "Invalid request body", "details": ["email: value is not a valid email address"] } }
```

`code` is one of `VALIDATION_ERROR`, `UNAUTHORIZED`, `FORBIDDEN`, `NOT_FOUND`, `CONFLICT`, `RATE_LIMITED`, `INTERNAL_ERROR` — deliberately matching the shape used by `back-template-spring`/`back-template-nest`/`back-template-laravel`, so a front-end template can swap backends with minimal changes to its error-handling code.

## Database

Schema lives in `app/models/` (SQLAlchemy). After changing a model:

```bash
uv run alembic revision --autogenerate -m "describe the change"
uv run alembic upgrade head
```

Note → User and RefreshToken → User foreign keys use `ondelete="CASCADE"`, so deleting an account cleans up its notes and refresh tokens automatically (see [Design notes](#design-notes-and-gotchas)).

## Example CRUD resource

`/api/notes` (`app/api/routes/notes.py`) is a full reference implementation: a Pydantic-validated request → a SQLAlchemy model owned by the authenticated user → a Pydantic response with camelCase aliases matching the rest of the family's JSON convention. Copy this shape for your first real feature, then delete `/api/notes` (and the `Note` model + a generated migration dropping the table) once you don't need the reference.

## API docs

FastAPI generates OpenAPI automatically — with the app running: interactive UI at `http://localhost:8082/docs` (Swagger) or `http://localhost:8082/redoc`, raw spec at `http://localhost:8082/openapi.json`. No extra annotation needed beyond the Pydantic schemas already on each route.

## Testing

- **Unit** (`uv run pytest tests/test_security.py`): password hashing and JWT roundtrip, no DB.
- **Integration** (`uv run pytest`): `tests/test_auth_integration.py` drives the full register → verify → login → notes CRUD → refresh → delete-account flow through the ASGI app (`httpx.ASGITransport`, no real HTTP server needed) against a real Postgres — no mocked DB.
- CI spins up a Postgres service container and runs the whole suite against it.

## CI/CD

`.github/workflows/ci.yml` runs two jobs on every push/PR:

1. **build** — `uv sync`, `ruff check`, `ruff format --check`, `mypy`, `alembic upgrade head`, `pytest` — all against a real Postgres service container
2. **docker** — builds the production Docker image (`docker/build-push-action`, no push) to catch Dockerfile breakage early

Dependabot (`.github/dependabot.yml`) checks uv (pyproject.toml/uv.lock), GitHub Actions, and the Dockerfile weekly.

## Docker

- `Dockerfile` — multi-stage (`deps` → `runtime`), `python:3.13-slim`, `uv sync --frozen --no-dev` for a reproducible install, runs as a non-root user.
- `entrypoint.sh` — runs `alembic upgrade head` then execs `uvicorn`, so `docker compose up` always starts against an up-to-date schema (matches `back-template-spring`'s Flyway-on-boot behavior).
- `docker-compose.yml` — `db` (Postgres 17, healthchecked via `pg_isready`, host port `5459` by default) and `app` (built from the Dockerfile, healthchecked via `/health`, waits for `db` to be healthy).

## Scripts

| Command                                    | Purpose                          |
| -------------------------------------------- | ----------------------------------- |
| `uv run uvicorn app.main:app --reload`        | Start dev server                    |
| `uv run alembic revision --autogenerate -m …` | Generate a migration from models    |
| `uv run alembic upgrade head`                 | Apply migrations                    |
| `uv run pytest`                                | Run tests                           |
| `uv run ruff check .`                          | Lint                                 |
| `uv run ruff format .`                          | Format                               |
| `uv run mypy app`                               | Type-check                           |
| `docker compose up -d --build`                   | Build and start app + Postgres      |
| `docker compose down`                             | Stop                                 |

## Using this as a template

1. Click "Use this template" on GitHub
2. Update `pyproject.toml`'s `name` and this README
3. `cp .env.example .env`, set a real `JWT_SECRET`
4. `docker compose up -d --build` (or the no-Docker path above)
5. Delete `/api/notes` once you've copied its pattern for your own first feature

## Design notes and gotchas

- **`ondelete="CASCADE"` on every FK to `users`, not app-level cleanup**: the first cut of `DELETE /account` left orphaned `notes`/`refresh_tokens` rows and Postgres rejected the delete with a `ForeignKeyViolationError`. Deleting a user needs to cascade at the DB level (`app/models/note.py`, `app/models/refresh_token.py`) — app-level "delete children first" is one more thing to forget when a new child table shows up later.
- **`Response(status_code=...)`, not `-> None`**: an endpoint typed `-> None` still returns a JSON body — FastAPI serializes it as the literal text `null`, not an empty body. Every endpoint in this template that should have a genuinely empty body returns `fastapi.Response(status_code=...)` explicitly instead.
- **asyncpg + Windows' default `ProactorEventLoop` don't mix**: connection teardown intermittently crashes with `Event loop is closed` / `'NoneType' object has no attribute 'send'` on Windows unless the event loop policy is switched to `WindowsSelectorEventLoopPolicy` (`app/db/session.py`, guarded by `sys.platform == "win32"`). Doesn't affect Linux (CI, Docker, prod).
- **pytest-asyncio needs a session-scoped loop for both fixtures *and* tests**: the SQLAlchemy async engine is a module-level singleton bound to whichever event loop existed when it was created. pytest-asyncio's default is a fresh loop per test, which breaks the engine's pooled connections on the second test. Both `asyncio_default_fixture_loop_scope = "session"` *and* `asyncio_default_test_loop_scope = "session"` are needed in `pyproject.toml` — setting only the fixture scope still crashes the second test.
- **`Depends(...)` as a default argument isn't a bug**: `ruff`'s `B008` rule flags it by default, but it's FastAPI's documented dependency-injection pattern. Disabled project-wide in `pyproject.toml` rather than `noqa`-ing every route.
- **`uv sync --no-install-project` in the Dockerfile's `deps` stage**: this app isn't a distributable package, so there's nothing to "install" — only its dependencies need to land in `.venv`. Skips a pointless (and occasionally fragile, depending on build backend) self-install step.
