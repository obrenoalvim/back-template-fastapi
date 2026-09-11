[English](README.md) | Português

# back-template-fastapi

[![CI](https://github.com/obrenoalvim/back-template-fastapi/actions/workflows/ci.yml/badge.svg)](https://github.com/obrenoalvim/back-template-fastapi/actions/workflows/ci.yml) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Template de backend pronto para produção: FastAPI, Python 3.13, SQLAlchemy 2.0 assíncrono + Alembic + Postgres, auth JWT (access token + refresh token rotativo/revogável), rate limiting, logging estruturado e Docker, tudo integrado e testado de ponta a ponta. Irmão de `back-template-nest`, `back-template-laravel` e `back-template-spring`: mesmo contrato de endpoints e formato de erro, stack diferente.

## Conteúdo

- [Stack](#stack)
- [Estrutura do projeto](#estrutura-do-projeto)
- [Começando (Docker)](#começando-docker--recomendado)
- [Começando (sem Docker)](#começando-sem-docker)
- [Variáveis de ambiente](#variáveis-de-ambiente)
- [Auth](#auth)
- [Papéis (roles)](#papéis-roles)
- [Formato de erro](#formato-de-erro)
- [Banco de dados](#banco-de-dados)
- [Exemplo de recurso CRUD](#exemplo-de-recurso-crud)
- [Documentação da API](#documentação-da-api)
- [Testes](#testes)
- [CI/CD](#cicd)
- [Docker](#docker-1)
- [Scripts](#scripts)
- [Usando como template](#usando-como-template)
- [Notas de design e pegadinhas](#notas-de-design-e-pegadinhas)

## Stack

- [FastAPI](https://fastapi.tiangolo.com): assíncrono, validação de request/response com Pydantic v2, docs OpenAPI automáticas
- [uv](https://docs.astral.sh/uv): gerenciamento de dependências + versão do Python (sem precisar de pyenv/pip)
- [SQLAlchemy](https://www.sqlalchemy.org) 2.0 (assíncrono, `asyncpg`) + [Alembic](https://alembic.sqlalchemy.org): schema versionado em código, migrations commitadas no repo
- [Postgres](https://www.postgresql.org)
- Auth JWT ([PyJWT](https://pyjwt.readthedocs.io)): access token de curta duração + refresh token mais longo, rotacionado e persistido no servidor pra permitir revogação (`app/models/refresh_token.py`)
- [bcrypt](https://pypi.org/project/bcrypt): hash de senha
- [slowapi](https://github.com/laurentS/slowapi): rate limiting (5 req/min/IP em login/registro)
- Email via SMTP, com fallback no console em dev (`app/core/mail.py`); sem setup necessário pra testar o fluxo de auth localmente
- [structlog](https://www.structlog.org): logging estruturado, legível em dev, JSON em prod
- Formato consistente `{"error": {"code", "message", "details"}}` em todo endpoint (`app/core/exceptions.py`)
- [pytest](https://pytest.org) + [pytest-asyncio](https://pytest-asyncio.readthedocs.io) + [httpx](https://www.python-httpx.org): testes unitários + integração contra um Postgres real, sem mock de banco
- [ruff](https://docs.astral.sh/ruff): lint + format; [mypy](https://mypy-lang.org): checagem de tipos
- [pre-commit](https://pre-commit.com): ruff no commit
- Docker + docker-compose: app e Postgres containerizados, migrations rodam automaticamente ao subir o container
- GitHub Actions CI: lint/type-check/testes contra um Postgres real, build da imagem Docker
- `/health` pro healthcheck do Docker

## Estrutura do projeto

```
app/
  main.py                 # app FastAPI, middleware, exception handlers, inclusão de routers
  core/
    config.py              # Settings do pydantic-settings (validado por env)
    security.py             # hash de senha, encode/decode de JWT
    exceptions.py            # ApiException + handlers → formato {"error": {...}}
    logging.py                # config do structlog
    mail.py                    # envio SMTP, fallback console em dev
    rate_limit.py               # limiter do slowapi
  db/
    session.py                   # engine assíncrona + session factory
    base.py                       # Base declarativa
  models/                          # User, RefreshToken, Note (SQLAlchemy)
  schemas/                          # modelos Pydantic de request/response
  api/
    deps.py                          # get_current_user, require_admin
    routes/
      auth.py, account.py, admin.py, notes.py, health.py
alembic/
  versions/                          # migrations SQL geradas — commitar
tests/
  test_security.py                    # unitário: hash de senha, roundtrip de JWT
  test_auth_integration.py             # integração: fluxo completo de auth + notas, Postgres real
```

## Começando (Docker — recomendado)

```bash
cp .env.example .env
# gere um secret de verdade e coloque em .env como JWT_SECRET
python -c "import secrets; print(secrets.token_urlsafe(32))"

docker compose up -d --build
```

App: [http://localhost:8082](http://localhost:8082). O Postgres é exposto na porta `5459` do host por padrão (não `5432`, pra evitar conflito com um Postgres local). Migrations rodam automaticamente ao subir o container (`entrypoint.sh`).

## Começando (sem Docker)

Precisa de uma instância Postgres e do [uv](https://docs.astral.sh/uv/getting-started/installation/).

```bash
cp .env.example .env   # aponte DATABASE_URL pro seu próprio Postgres
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8082
```

## Variáveis de ambiente

Veja `.env.example` pra lista completa e comentada.

| Variável                          | Obrigatória | Propósito                                                          |
| ---------------------------------- | ----------- | ------------------------------------------------------------------ |
| `DATABASE_URL`                     | sim         | String de conexão do Postgres (driver asyncpg)                     |
| `JWT_SECRET`                       | sim         | ≥32 caracteres; assinatura dos tokens de access/refresh             |
| `DB_HOST_PORT/NAME/USER/PASSWORD`  | só Docker   | Padrões do `docker-compose.yml`, usados pra compor `DATABASE_URL`   |
| `ENVIRONMENT`                      | não         | `dev` (logs legíveis) ou qualquer outro valor (logs JSON); padrão `dev` |
| `LOG_LEVEL`                        | não         | nível do structlog; padrão `info`                                   |
| `CORS_ORIGINS`                     | não         | Origens separadas por vírgula autorizadas a chamar essa API pelo navegador (esse backend, diferente do `back-template-spring`, não tem par BFF; o `front-template-react` chama ele direto); padrão `http://localhost:5173` |
| `MAIL_HOST`/`MAIL_PORT`/`MAIL_USERNAME`/`MAIL_PASSWORD` | não | Envia email real via SMTP; sem `MAIL_HOST`, os emails são logados no console |

`app/core/config.py` valida essas variáveis com `pydantic-settings` na importação.

## Auth

`app/api/routes/auth.py` (todos `/auth/*`, públicos):

- `POST /auth/register`: 201, corpo vazio. 409 se o email já existe.
- `GET /auth/verify-email?token=...`: 200 vazio. 404 token inválido, 409 expirado.
- `POST /auth/login`: 200, `{accessToken, refreshToken}`. 401 credenciais inválidas ou email não verificado.
- `POST /auth/refresh`: rotaciona o refresh token (o antigo é apagado, um novo é emitido). 401 se inválido/expirado/revogado.
- `POST /auth/logout`: 200, idempotente.
- `POST /auth/forgot-password`: sempre 200 (sem vazamento de enumeração de usuário).
- `POST /auth/reset-password`: 200. 404/409 igual ao verify-email.
- `PATCH /account/password`, `DELETE /account` (`app/api/routes/account.py`): autenticados, `Authorization: Bearer <accessToken>`.
- Rate limit: 5 tentativas de registro/login por 60s por IP (`slowapi`, ver `app/core/rate_limit.py`).
- `get_current_user` de `app/api/deps.py` é a única dependency usada por toda rota protegida. Decodifica e valida o bearer token, sem duplicação por rota.

**Refresh tokens são persistidos**: diferente de um esquema JWT puramente stateless, o `jti` de cada refresh token fica salvo na tabela `refresh_tokens` (`app/models/refresh_token.py`) pra permitir revogação/rotação no servidor. Logout ou refresh apaga a linha antiga, então um refresh token roubado não pode ser reaproveitado depois da rotação.

## Papéis (roles)

Enum `Role` (`USER` | `ADMIN`, padrão `USER`) em `User.role` — nunca confie num role vindo do corpo da requisição. `GET /admin/users` (`app/api/routes/admin.py`) é o endpoint de referência admin-only, protegido pela dependency `require_admin` (construída sobre `get_current_user`, então é a mesma checagem de JWT mais uma verificação de role). Sem auto-promoção. Altere direto no banco pra testar localmente: `UPDATE users SET role = 'ADMIN' WHERE email = '...';`.

## Formato de erro

Toda resposta de erro — validação, auth, not-found, não tratado — tem o mesmo envelope, produzido pelos exception handlers em `app/core/exceptions.py`:

```json
{ "error": { "code": "VALIDATION_ERROR", "message": "Invalid request body", "details": ["email: value is not a valid email address"] } }
```

`code` é um de `VALIDATION_ERROR`, `UNAUTHORIZED`, `FORBIDDEN`, `NOT_FOUND`, `CONFLICT`, `RATE_LIMITED`, `INTERNAL_ERROR`. Bate de propósito com o formato usado por `back-template-spring`/`back-template-nest`/`back-template-laravel`, pra um template de front conseguir trocar de backend com o mínimo de mudança no tratamento de erro.

## Banco de dados

Schema fica em `app/models/` (SQLAlchemy). Depois de mudar um model:

```bash
uv run alembic revision --autogenerate -m "descreva a mudança"
uv run alembic upgrade head
```

As foreign keys de Note → User e RefreshToken → User usam `ondelete="CASCADE"`, então excluir uma conta limpa automaticamente suas notas e refresh tokens (ver [Notas de design](#notas-de-design-e-pegadinhas)).

## Exemplo de recurso CRUD

`/api/notes` (`app/api/routes/notes.py`) é uma implementação de referência completa: um request validado por Pydantic → um model SQLAlchemy pertencente ao usuário autenticado → uma resposta Pydantic com aliases em camelCase batendo com a convenção JSON do resto da família. Copie esse formato pra sua primeira feature de verdade, depois apague `/api/notes` (e o model `Note` + uma migration gerada removendo a tabela) quando não precisar mais da referência.

## Documentação da API

O FastAPI gera OpenAPI automaticamente — com o app rodando: UI interativa em `http://localhost:8082/docs` (Swagger) ou `http://localhost:8082/redoc`, spec bruta em `http://localhost:8082/openapi.json`. Nenhuma anotação extra necessária além dos schemas Pydantic já presentes em cada rota.

## Testes

- **Unitário** (`uv run pytest tests/test_security.py`): hash de senha e roundtrip de JWT, sem banco.
- **Integração** (`uv run pytest`): `tests/test_auth_integration.py` percorre o fluxo completo registro → verificação → login → CRUD de notas → refresh → exclusão de conta através do app ASGI (`httpx.ASGITransport`, sem precisar de servidor HTTP real) contra um Postgres real — sem mock de banco.
- **Guarda contra N+1** (`tests/test_admin_query_count.py`): `GET /admin/notes` (`list_notes_with_owners` em `app/api/routes/admin.py`) carrega o dono de cada nota com `joinedload(Note.owner)`, um único JOIN em SQL. O teste conta as queries de fato enviadas ao Postgres (via evento `before_cursor_execute` do SQLAlchemy, ver `tests/query_counter.py`) e garante que continua em exatamente 1, não importa quantas notas existam. `Note.owner` também é declarado `lazy="raise"`: qualquer código futuro que esquecer o `joinedload` e acessar `.owner` fora de uma query com eager load quebra na hora, com erro claro, em vez de virar 1+N queries silenciosamente em produção.
- O CI sobe um container de serviço Postgres e roda a suíte inteira contra ele.

## CI/CD

`.github/workflows/ci.yml` roda dois jobs a cada push/PR:

1. **build**: `uv sync`, `ruff check`, `ruff format --check`, `mypy`, `alembic upgrade head`, `pytest`, tudo rodando contra um container de serviço Postgres real
2. **docker**: builda a imagem Docker de produção (`docker/build-push-action`, sem push) pra pegar quebra no Dockerfile cedo

Dependabot (`.github/dependabot.yml`) checa uv (pyproject.toml/uv.lock), GitHub Actions e o Dockerfile semanalmente.

## Docker

- `Dockerfile`: multi-stage (`deps` → `runtime`), `python:3.13-slim`, `uv sync --frozen --no-dev` pra um install reproduzível, roda como usuário non-root.
- `entrypoint.sh`: roda `alembic upgrade head` e depois executa `uvicorn`, então `docker compose up` sempre inicia com o schema atualizado (igual o comportamento do Flyway-no-boot do `back-template-spring`).
- `docker-compose.yml`: `db` (Postgres 17, healthcheck via `pg_isready`, porta `5459` do host por padrão) e `app` (buildado do Dockerfile, healthcheck via `/health`, espera o `db` ficar saudável).

## Scripts

| Comando                                       | Propósito                          |
| ------------------------------------------------ | ------------------------------------ |
| `uv run uvicorn app.main:app --reload`            | Inicia o dev server                  |
| `uv run alembic revision --autogenerate -m …`     | Gera uma migration a partir dos models |
| `uv run alembic upgrade head`                     | Aplica migrations                    |
| `uv run pytest`                                    | Roda os testes                       |
| `uv run ruff check .`                              | Lint                                  |
| `uv run ruff format .`                              | Formata                              |
| `uv run mypy app`                                   | Checagem de tipos                    |
| `docker compose up -d --build`                       | Builda e sobe app + Postgres         |
| `docker compose down`                                 | Para                                  |

## Usando como template

1. Clique em "Use this template" no GitHub
2. Atualize o `name` em `pyproject.toml` e este README
3. `cp .env.example .env`, defina um `JWT_SECRET` de verdade
4. `docker compose up -d --build` (ou o caminho sem Docker acima)
5. Apague `/api/notes` depois de copiar o padrão pra sua primeira feature

## Notas de design e pegadinhas

- **`ondelete="CASCADE"` em toda FK pra `users`, não limpeza no nível da aplicação**: a primeira versão de `DELETE /account` deixava linhas órfãs em `notes`/`refresh_tokens` e o Postgres rejeitava o delete com `ForeignKeyViolationError`. Excluir um usuário precisa cascatear no nível do banco (`app/models/note.py`, `app/models/refresh_token.py`). "Apagar filhos primeiro" na aplicação é mais uma coisa pra esquecer quando uma tabela filha nova aparecer depois.
- **`Response(status_code=...)`, não `-> None`**: um endpoint tipado `-> None` ainda retorna um corpo JSON. O FastAPI serializa como o texto literal `null`, não um corpo vazio. Todo endpoint deste template que deveria ter corpo genuinamente vazio retorna `fastapi.Response(status_code=...)` explicitamente.
- **asyncpg e o `ProactorEventLoop` padrão do Windows não combinam**: o encerramento de conexão trava intermitentemente com `Event loop is closed` / `'NoneType' object has no attribute 'send'` no Windows a menos que a policy do event loop seja trocada pra `WindowsSelectorEventLoopPolicy` (`app/db/session.py`, protegido por `sys.platform == "win32"`). Não afeta Linux (CI, Docker, prod).
- **pytest-asyncio precisa de loop com escopo de sessão pra fixtures *e* testes**: a engine assíncrona do SQLAlchemy é um singleton em nível de módulo, atrelado a qualquer event loop que existia quando foi criada. O padrão do pytest-asyncio é um loop novo por teste, o que quebra as conexões do pool da engine no segundo teste. Tanto `asyncio_default_fixture_loop_scope = "session"` *quanto* `asyncio_default_test_loop_scope = "session"` são necessários em `pyproject.toml`. Só o escopo de fixture ainda quebra o segundo teste.
- **`Depends(...)` como argumento padrão não é bug**: a regra `B008` do `ruff` sinaliza isso por padrão, mas é o padrão documentado de injeção de dependência do FastAPI. Desabilitada no projeto inteiro em `pyproject.toml` em vez de `noqa` em cada rota.
- **`uv sync --no-install-project` no estágio `deps` do Dockerfile**: este app não é um pacote distribuível, então não há nada pra "instalar." Só as dependências precisam ir pro `.venv`. Pula um passo de auto-instalação sem sentido (e ocasionalmente frágil, dependendo do build backend).
