# Mobile Tracker API

The backend currently provides account authentication and connection/sharing-consent APIs. It does **not** collect or expose GPS locations, app-usage history, restriction attempts, or account deletion. Deploying this backend does not enable those frontend features.

## Production safeguards

- Production startup requires `APP_ENV=production`, an explicitly configured JWT signing key of at least 32 bytes, and PostgreSQL.
- Database tables are managed through Alembic migrations; the API never creates or changes tables on startup.
- Login attempts are counted per normalized username and client IP in PostgreSQL, shared across workers, and limited to five attempts per 15 minutes by default. The combined identifier is stored only as a keyed digest. A successful login clears that bucket's counter.
- `/health` executes `SELECT 1` and returns HTTP 503 when the database is unavailable.
- The Docker image runs as a non-root user. Compose binds the API to localhost; put it behind a TLS-enabled reverse proxy or deploy it behind a platform ingress that provides HTTPS. Do not expose the plain HTTP container port directly to the public internet.
- Configure database backup retention and periodically verify a restore. The Compose volume provides persistence, not a backup.

Also configure request/IP rate limiting at the trusted ingress. When behind a proxy, configure Uvicorn's `FORWARDED_ALLOW_IPS` to the actual proxy addresses so the app receives the correct client IP; do not trust forwarded headers from arbitrary clients or set the trusted list to `*`.

## Docker Compose deployment

Use Docker Engine with the Compose plugin. From PowerShell:

```powershell
Set-Location C:\Users\ayush\Desktop\development\mobile_tracker_app\backend
Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Put the first generated value in `JWT_SECRET_KEY`, the second in `POSTGRES_PASSWORD`, then edit `.env`. Keep `.env` private; it is excluded from version control. The generated password uses URL-safe characters so it can be used in the Compose PostgreSQL URL without extra encoding.

```powershell
docker compose up --build -d
docker compose ps
curl.exe http://127.0.0.1:8000/health
docker compose logs --tail 100 api migrate
```

The migration service runs `alembic upgrade head` before the API starts. Configure TLS and the public HTTPS domain at your reverse proxy/platform ingress, then set the Android app's API base URL to that HTTPS address. Set `API_PORT` in `.env` to change the host-side loopback port.

Equivalent Ubuntu/WSL2 commands:

```bash
cd /path/to/mobile_tracker_app/backend
cp .env.example .env
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
# Put those values in JWT_SECRET_KEY and POSTGRES_PASSWORD in .env.
docker compose up --build -d
docker compose ps
curl --fail http://127.0.0.1:8000/health
docker compose logs --tail 100 api migrate
```

To stop without deleting database data, run `docker compose down`. **Do not** run `docker compose down --volumes` unless you intend to permanently delete the PostgreSQL data.

For managed production hosting, use a persistent managed PostgreSQL database, set `APP_ENV`, `JWT_SECRET_KEY`, and `DATABASE_URL` as platform secrets, execute `alembic upgrade head` as a one-off release step, and deploy the container behind the platform's HTTPS ingress. Keep `DATABASE_URL` in SQLAlchemy's `postgresql+psycopg://` format or a standard `postgresql://` URL. Database TLS settings should follow the selected provider's requirements.

## Migrations

Fresh databases:

```bash
alembic upgrade head
```

For local PowerShell with a virtual environment, activate it first and set `DATABASE_URL` to the intended database before running the command. Do not run a migration against production until a database backup exists and the migration has been reviewed.

The checked-in `mobile_tracker.db` predates Alembic. To retain it, back it up, confirm its schema matches revision `0001_initial`, set `DATABASE_URL=sqlite:///./mobile_tracker.db`, then run:

```bash
alembic stamp 0001_initial
alembic upgrade head
```

Do not stamp a database with unknown or mismatched schema. Fresh production deployments should use PostgreSQL and `alembic upgrade head`.

## Local development

Python 3.11+ is supported. Install requirements and initialize the local SQLite schema with Alembic:

```powershell
Set-Location C:\Users\ayush\Desktop\development\mobile_tracker_app\backend
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:APP_ENV = "development"
$env:DATABASE_URL = "sqlite:///./mobile_tracker.db"
alembic upgrade head
uvicorn app.main:app --reload
```

The development environment generates an ephemeral JWT key when none is set; tokens become invalid when the process restarts. Production never generates a key. Run the backend unit tests with:

```powershell
python -m unittest discover -s tests -v
```

## API endpoints currently implemented

- `POST /api/auth/signup`
- `POST /api/auth/login`
- `GET /api/auth/me`
- `GET /api/connections` and username search/request/accept/reject/disconnect endpoints
- `GET` and `PATCH /api/connections/{connection_id}/permissions`
- `GET /health`

Location, activity, restricted-app, account-deletion, and persistent push/background monitoring endpoints are not implemented. Sharing permissions default to off. Each account controls only sharing of its own data.
