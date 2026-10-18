# ZENTO COURIER: Phase 1

Courier delivery web app: public website, customer accounts, parcel booking with server-side pricing, public shipment tracking and a customer dashboard.

**Stack:** FastAPI + SQLAlchemy 2 + Alembic + PostgreSQL (Supabase-ready) on the back end; plain HTML, CSS and vanilla JavaScript (ES modules) on the front end. No Node.js is needed to run anything. FastAPI serves the API under `/api` and the static site from `frontend/`, so one process is enough.

**Admin panel:** served at `/admin`. **Rider app:** served at `/rider` (phone-first). **Wallet, COD and payouts:** built (see *Wallet and Cash on Delivery* below). **Android apps:** see `android/README.md`. **Not built yet:** online payment gateway (deposits are checked by an admin), editable pricing rules.

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
| `CURRENCY` | no | Default `BDT`. All prices are shown with the taka sign |
| `WALLET_MIN_DEPOSIT`, `WALLET_MIN_WITHDRAW` | no | Smallest deposit (default 50) and withdrawal (default 100), in taka |
| `PAY_BKASH`, `PAY_NAGAD`, `PAY_ROCKET`, `PAY_BANK` | no | Where customers send deposit money. Shown on the wallet page; empty = hidden |
| `CORS_ORIGINS` | no | Comma-separated. Only needed if the frontend is hosted on a different origin |
| `RIDER_COMMISSION_RATE` | no | Share of the parcel price a rider earns on delivery, default `0.20` |
| `RIDER_DAILY_GOAL` | no | Daily earnings goal shown in the rider app, default `2000` |

## Admin panel (`/admin`)

Dark dashboard for staff: dashboard, parcels (status updates, rider and courier assignment, CSV export), bookings (create on behalf of a customer), customers (add, suspend), riders, courier providers, delivery pricing (read-only view and calculator), service areas, reports, notifications and settings.

1. Set `ADMIN_EMAIL` and `ADMIN_PASSWORD` (8+ characters, letters and numbers) on the host. On every start the app creates that account, or promotes it if the email is already registered (its password is not changed). Alternatively promote an existing account by SQL: `UPDATE users SET is_admin = true WHERE email = 'you@example.com';`
2. Deploy (the Dockerfile runs `alembic upgrade head`, which adds migration `0002`), then open `https://<your-site>/admin` and sign in.
3. Everything the panel does goes through `/api/admin/*`, which returns 403 for non-admin accounts.

Notes: *Recent Activities* and *Notifications* combine new bookings, new customers and staff actions. The Live Tracking map is an illustration of the route between the two cities; the app stores no GPS coordinates. Service areas are informational and are not enforced when customers book.

## Rider app (`/rider`)

1. **Apply:** a rider opens `/rider`, taps *Apply as rider* and sends name, phone, city, vehicle, own photo, NID or passport (type, number, photo), email and password. The photos are resized in the browser and stored in the database (`rider_documents`); only admins can read them. The application starts as **pending** and the rider can sign in but cannot work yet.
2. **Approve:** in `/admin` open *Riders*, press *Review* on a pending application, check the photo and ID, then *Approve rider* or *Reject* with a reason. A rejected application can still be approved later.
3. **Assign:** in a parcel's detail window the admin picks an approved rider. The rider gets the parcel under *New Requests* and must **accept or reject** it. A rejection sends the parcel back to the admin queue (the admin sees who rejected it and why). Until the rider accepts, the rider sees addresses but no names or phone numbers.
4. **Deliver:** after accepting, the rider moves the parcel *Confirm Pickup -> Start Delivery -> Mark Delivered*. Each step is added to the customer's tracking timeline.
5. **Commission:** when the parcel is delivered (by the rider or by an admin) the rider earns `RIDER_COMMISSION_RATE` of the parcel price (default `0.20` = 20%), stored on the parcel as `rider_commission`. The wallet shows the total earned, today's earnings against `RIDER_DAILY_GOAL` (default 2000) and the delivery streak.

Riders added by hand with *Add Rider* have no login; they are approved straight away and assigned without the accept/reject step, as before.

## Wallet and Cash on Delivery

All money is in taka (the taka sign in the apps; `Tk` in PDFs because the PDF fonts have no taka glyph).

**Customer**
* **Deposit:** the customer sends money to your bKash/Nagad/Rocket/bank number (set `PAY_*`), then submits amount + TrxID on *Wallet*. Nothing is added until an admin approves it in `/admin` -> *Wallet* -> *Deposits*. The same TrxID cannot be used twice.
* **Booking:** the price is taken from the wallet when the parcel is booked. Not enough balance = no booking, with a message saying how much to deposit. Cancelling (customer, or admin) refunds the price once.
* **Cash on Delivery:** the customer can enter a COD amount when booking. The rider collects it from the receiver; when the parcel is *delivered* the amount is credited to the customer's wallet.
* **Withdraw:** the amount leaves the balance at once (on hold). The admin sends the money and presses *Mark paid*, or rejects it and the money returns.

**Rider**
* Commission (default 20%) is credited to the rider's wallet on delivery.
* **COD rule:** COD cash a rider collected is owed to ZENTO. The rider can only withdraw `balance - COD owed`. Example: owes 500 COD, wallet 1000 -> can withdraw 500, the other 500 is locked until the rider hands in the cash and an admin accepts it (rider *Wallet* tab -> *Hand in COD*, or admin *Wallet* -> *Receive COD*).

**Admin** (`/admin` -> *Wallet*): money in wallets, COD cash with riders, approve/reject deposits, withdrawals and COD hand-ins, wallet list with history, manual adjustments (always with a written reason; they appear in the user's history).

Every balance change is a line in `wallet_transactions`; booking, refund, commission and COD are paid once only (flags on the parcel). Balances are locked per user (`SELECT ... FOR UPDATE`) so two requests cannot spend the same money. Run `alembic upgrade head` (migration `0004`) after deploying.

New API: `/api/wallet` (overview), `/api/wallet/transactions`, `POST /api/wallet/deposit|withdraw|cod-deposit`, and `/api/admin/wallet/*`.

## Android apps

Three apps (website, admin, rider) are built by GitHub Actions: see `android/README.md`.

## Parcel PDF

Customers (*My parcels* -> *Details* -> *Download PDF*) and admins (parcel window -> *PDF*) can download a PDF with the tracking number and barcode, sender, recipient, shipment details, price breakdown and tracking history. The admin copy also shows the customer account, rider contact and rider commission. The PDF fonts are Latin only: Bengali or other scripts print as `?` (supporting them needs a font plus a text-shaping library).

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
| `GET /api/parcels/{id}/pdf` | yes | Download your own parcel as a PDF |
| `POST /api/rider/apply` | no | Rider application (name, phone, city, photo, NID/passport, email, password) |
| `GET /api/rider/me` | rider | Own profile and application status (works while pending/rejected) |
| `GET /api/rider/dashboard`, `/parcels?tab=requests\|active\|history`, `/earnings` | approved rider | Wallet, requests, active order, history, commission |
| `POST /api/rider/parcels/{id}/respond` | approved rider | `accept` or `reject` an assigned parcel |
| `POST /api/rider/parcels/{id}/status` | approved rider | `picked_up` -> `out_for_delivery` -> `delivered` |
| `/api/admin/*` | admin | Dashboard, parcels (+ `/parcels/{id}/pdf`), bookings, customers, riders (+ `approve`, `reject`, `documents/{photo\|id_document}`), providers, areas, pricing, reports, notifications |

Validation errors return `422` as `{"detail": "...", "errors": [{"field": "...", "message": "..."}]}`; the frontend maps `field` to the input.

## Pricing rules (`app/pricing.py`)

Chargeable weight is the larger of actual and volumetric weight (L x W x H / 5000), rounded up to 0.5 kg. Each zone has a base fee covering the first kilogram plus a per-kg rate after that (local 80 + 15/kg, regional 120 + 20/kg, national 150 + 25/kg, in taka). Express is x1.5 and same-day (local zone only) x2.2. Fragile handling is a flat 20. Insurance is 1.5% of declared value, minimum 10. Limits: 30 kg, 150 cm per side, 100000 declared value. **These rates are placeholders; change the constants at the top of `app/pricing.py` and the tests accordingly.**

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

## Verification status (rider panel and PDF)

Executed in a sandbox without network access (FastAPI, SQLAlchemy and Alembic could not be installed there): the PDF builder (customer and admin copies generated and read back), image validation and commission rounding, all Python files compile, the rider app and the admin *Riders* page were driven in headless Chromium against a throwaway mock API (apply with a field error, pending screen, sign in, accept, pickup, delivery, earnings, profile, review and approve with ID photos; no script errors, no horizontal overflow on a 390 px phone).

**Not executed:** the real API routes, migration `0003` and `tests/test_rider.py` (written against the real routes). Run `pytest` after deploying; any failure there is a real defect to fix.

## Verification status (phase 1)

What was actually executed when this was built (in a sandbox with no network, so the Python dependencies could not be installed):

* Pricing, tracking-number, password-hash, JWT and rate-limiter tests: **16 passed** (run with a stubbed settings module).
* Frontend: full browser flow in headless Chromium at desktop and mobile widths (register, live quote, booking with a field error, public tracking, dashboard, cancel, sign out/in) against a throwaway stand-in API that reused the real pricing code. No page errors, no horizontal overflow.
* All Python files compile and all JavaScript passes a syntax check.

**Not executed:** the FastAPI app, SQLAlchemy models, the Alembic migration and the pytest suites that depend on them (`test_auth`, `test_parcels`, `test_tracking`, `test_migrations`), and anything against real PostgreSQL or Supabase. Run `pytest` first; if anything fails, that is a genuine defect to fix before relying on the app.

## Deploying (Render, Railway, Fly.io, any Docker host)

This is a Python server, not a static site: it will NOT work on GitHub Pages, Netlify static hosting or Vercel static hosting.

1. Create a web service from this repo using the included `Dockerfile` (it runs `alembic upgrade head`, then starts uvicorn on `$PORT`).
2. Set these environment variables on the host (the app exits at startup without the first two):
   - `DATABASE_URL`: use the Supabase **session pooler** string (port 5432, `?sslmode=require`). The "direct connection" host is IPv6-only and fails on many hosts.
   - `SECRET_KEY`: 32+ random characters.
   - `ENVIRONMENT=production`
3. Check `https://<your-site>/api/health`. It should return `{"status":"ok"}`.

No Docker? Use build command `pip install -r requirements.txt` and start command
`alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips='*'`.
