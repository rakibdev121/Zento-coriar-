# ZENTO COURIER: Phase 1

Courier delivery web app: public website, customer accounts, parcel booking with server-side pricing, public shipment tracking and a customer dashboard.

**Stack:** FastAPI + SQLAlchemy 2 + Alembic + PostgreSQL (Supabase-ready) on the back end; plain HTML, CSS and vanilla JavaScript (ES modules) on the front end. No Node.js is needed to run anything. FastAPI serves the API under `/api` and the static site from `frontend/`, so one process is enough.

**Not in Phase 1:** admin panel, rider panel, payments, notifications, status updates by staff. Until those exist, parcels stay `booked` unless the customer cancels them.

## Quick start

Requires Python 3.11+ and a PostgreSQL database.

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

cp .env.example .env                                    # then edit .env (never commit it)
python -c "import secrets; print(secrets.token_urlsafe(48))"   # paste the output as SECRET_KEY

docker compose up -d                                    # local Postgres (skip if using Supabase)
alembic upgrade head                                    # create the tables
uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000>. Interactive API docs (non-production only): <http://127.0.0.1:8000/api/docs>.

## Using Supabase PostgreSQL

1. In the Supabase dashboard open **Connect** and copy a Postgres connection string.
2. Put it in `.env` as `DATABASE_URL`. Plain `postgresql://` or `postgres://` URLs are accepted and rewritten to the `psycopg` driver. Add `?sslmode=require`. URL-encode special characters in the password (`@` becomes `%40`).
3. Use the **direct connection** or **session pooler** (port 5432) for `alembic upgrade head`. The **transaction pooler** (port 6543) also works for the running app; the code disables prepared statements automatically when it sees `:6543`.
4. Run `alembic upgrade head` against that URL. The service-role key and anon key are not used; this app talks to Postgres directly, so do not put those in `.env`.

Supabase enables Row Level Security on tables created through its dashboard. Tables created by Alembic over a direct connection are not exposed through Supabase's REST API unless you grant that, which is what you want here because all access goes through this API.

## Configuration

| Variable | Required | Notes |
|---|---|---|
| `DATABASE_URL` | yes | SQLAlchemy URL, see above |
| `SECRET_KEY` | yes | 32+ characters; signs login tokens. The app refuses to start without it |
| `ENVIRONMENT` | no | `development` (default) or `production`. Production hides `/api/docs` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | no | Default 720 (12 h) |
| `CURRENCY` | no | ISO code shown in prices, default `USD` |
| `CORS_ORIGINS` | no | Comma-separated. Only needed if the frontend is hosted on a different origin |

## Tests

```bash
pytest
```

Tests use an in-memory SQLite database, so no Postgres is needed. They cover pricing rules, password hashing, JWTs, the login rate limiter, tracking numbers, registration/login validation, booking, ownership isolation between customers, cancellation, the dashboard summary, public tracking privacy and an Alembic upgrade/downgrade round trip.

## API overview

| Method and path | Auth | Purpose |
|---|---|---|
| `POST /api/auth/register` | no | Create account, returns token |
| `POST /api/auth/login` | no | Sign in (5 failures per IP and email, then a 15 minute lockout) |
| `GET /api/auth/me` | yes | Current user |
| `GET /api/pricing/options` | no | Zones, services, limits, currency |
| `POST /api/pricing/quote` | no | Price a parcel |
| `POST /api/parcels` | yes | Book a parcel (price recomputed on the server) |
| `GET /api/parcels` | yes | List own parcels, `page`, `page_size`, `status` |
| `GET /api/parcels/{id}` | yes | Own parcel with timeline |
| `POST /api/parcels/{id}/cancel` | yes | Cancel while still `booked` |
| `GET /api/dashboard/summary` | yes | Counts, total spent, recent parcels |
| `GET /api/track/{tracking_number}` | no | Public tracking: cities, status, timeline. No names, phones or street addresses |
| `GET /api/health` | no | Database connectivity check |

Validation errors return `422` as `{"detail": "...", "errors": [{"field": "...", "message": "..."}]}`; the frontend maps `field` to the input.

## Pricing rules (`app/pricing.py`)

Chargeable weight is the larger of actual and volumetric weight (L x W x H / 5000), rounded up to 0.5 kg. Each zone has a base fee covering the first kilogram plus a per-kg rate after that (local 5.00 + 1.00/kg, regional 8.00 + 1.50/kg, national 12.00 + 2.25/kg). Express is x1.5 and same-day (local zone only) x2.2. Fragile handling is a flat 2.00. Insurance is 1.5% of declared value, minimum 1.00. Limits: 30 kg, 150 cm per side, 5000 declared value. **These rates are placeholders; change the constants at the top of `app/pricing.py` and the tests accordingly.**

## Project layout

```
app/            FastAPI app: config, database, models, schemas, security, pricing, routers/
alembic/        Migrations (0001_initial creates users, parcels, tracking_events)
frontend/       Static site: HTML pages, css/style.css, js/ (ES modules)
tests/          pytest suite
```

## Security notes

* `.env` is git-ignored; only `.env.example` (no secrets) is committed.
* Passwords are hashed with scrypt and per-user salts. Unknown emails take the same time as wrong passwords.
* Login tokens are JWTs kept in `localStorage`. All user-supplied text is rendered with `textContent` (no `innerHTML`), which is what makes this acceptable, but an HttpOnly cookie with CSRF protection would be the stronger choice if you later add third-party scripts.
* The login rate limiter is in-memory and per process. Use a shared store such as Redis if you run several workers.
* Users can only read or cancel their own parcels; other users' IDs return 404.

## Verification status

What was actually executed when this was built (in a sandbox with no network, so the Python dependencies could not be installed):

* Pricing, tracking-number, password-hash, JWT and rate-limiter tests: **16 passed** (run with a stubbed settings module).
* Frontend: full browser flow in headless Chromium at desktop and mobile widths (register, live quote, booking with a field error, public tracking, dashboard, cancel, sign out/in) against a throwaway stand-in API that reused the real pricing code. No page errors, no horizontal overflow.
* All Python files compile and all JavaScript passes a syntax check.

**Not executed:** the FastAPI app, SQLAlchemy models, the Alembic migration and the pytest suites that depend on them (`test_auth`, `test_parcels`, `test_tracking`, `test_migrations`), and anything against real PostgreSQL or Supabase. Run `pytest` first; if anything fails, that is a genuine defect to fix before relying on the app.
