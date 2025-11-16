# TaskUp API

FastAPI backend that powers TaskUp's task management and multi-device sync. It exposes authentication, device registration, CRUD for tasks, and dedicated sync endpoints that read/write MariaDB using the schema in `db/schema.sql`.

## Requirements

- Python 3.11+
- MariaDB / MySQL instance with the `taskup` schema loaded via `db/schema.sql`
- Recommended virtual environment (venv or Conda)

## Quickstart

```bash
python -m venv .venv
. .venv/Scripts/activate  # PowerShell: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
# Update .env with TASKUP_DATABASE_URL and TASKUP_JWT_SECRET_KEY
uvicorn main:app --reload --port 8000
```

Environment variables (`.env` supported) prefix `TASKUP_`. Key values:

- `TASKUP_DATABASE_URL` – e.g. `mysql+pymysql://user:password@localhost:3306/taskup`
- `TASKUP_JWT_SECRET_KEY` – random string for JWT signing
- `TASKUP_ACCESS_TOKEN_EXPIRES_MINUTES` (optional)
- `TASKUP_REFRESH_TOKEN_EXPIRES_DAYS` (optional)
- `TASKUP_GOOGLE_CLIENT_IDS` – comma-separated OAuth client IDs that are allowed when calling `/auth/google`

### Google OAuth

Client apps (Flutter PWA/mobile) can pass the Google ID token they already obtained on the device to `POST /auth/google`. The backend verifies the token against the configured client IDs, ensures the email is verified, auto-creates the user record on first login, and responds with the standard TaskUp access/refresh tokens. Leave `TASKUP_GOOGLE_CLIENT_IDS` empty to disable the route.

## Endpoint Overview

| Method | Path | Purpose |
| ------ | ---- | ------- |
| `POST /auth/register` | Create user and return tokens |
| `POST /auth/login` | Issue tokens for existing user |
| `POST /auth/google` | Exchange a Google ID token for TaskUp tokens |
| `POST /auth/refresh` | Exchange refresh token for new access token |
| `GET /auth/me` | Return profile for current user |
| `POST /devices` | Register/update a device for the logged-in user |
| `GET /devices` | List registered devices plus their last change id |
| `GET /tasks` | List current tasks (filters for `since_version`, `only_active`) |
| `POST /tasks` | Create a task (optionally include `X-Device-UUID` header) |
| `PUT /tasks/{id}` | Update a task |
| `DELETE /tasks/{id}` | Soft-delete/Archive a task |
| `POST /sync/push` | Submit batched changes from a device |
| `POST /sync/pull` | Request change log entries after a cursor |

### Sync flow tips

1. Register/login to obtain bearer token and register the device via `POST /devices`.
2. Use the returned `last_change_id` to seed the device cursor.
3. Push offline changes with `POST /sync/push` (`client_change_id` keeps responses aligned, and server echoes any new task IDs).
4. Pull updates with `POST /sync/pull` providing the last applied change id; response includes outstanding operations.
5. Task CRUD endpoints also accept an `X-Device-UUID` header so manual edits continue the change log.

## Testing health

```bash
uvicorn main:app --reload
# or run FastAPI's built-in docs at http://localhost:8000/docs
```

The OpenAPI schema documents bodies for every route, making it easier to wire your Flutter client or automated tests.
