# Kreavo Concierge

A multi-tenant WhatsApp assistant for small businesses.

## Stack

- Python / Flask
- Twilio (WhatsApp API)
- Anthropic Claude API
- PostgreSQL

## What it does

Each client gets isolated conversation history, their own knowledge base,
and a hard monthly token budget.

## v1 goals

- [ ] Survive duplicate webhook deliveries (idempotency)
- [ ] Handle model calls asynchronously without timing out Twilio
- [ ] Per-tenant data isolation
- [ ] Per-client token cost caps
- [ ] Structured logging good enough to debug a complaint from three days ago
- [ ] A way to measure whether answers are correct, not just returned

## Status

In development.

## Setup

Everything below is run from the project root, in this order.

### 1. Install requirements

1. Create a virtual environment: `python -m venv venv`
2. Activate it:
   - Windows (PowerShell): `.\venv\Scripts\Activate.ps1`
   - macOS/Linux: `source venv/bin/activate`
3. Install dependencies: `pip install -r requirements.txt`

### 2. Configure

Copy `.env.example` to `.env` and fill in the values (see Configuration below for what each one means).

`DATABASE_URL` and `TEST_DATABASE_URL` need the password of your local Postgres user. If the password contains special characters, URL-encode them (for example `@` becomes `%40`, `#` becomes `%23`), otherwise the connection string won't parse.

### 3. Create the databases (once)

You need a local PostgreSQL server. Open `psql` as the `postgres` user and create the two databases: one for the app, one that the tests are allowed to wipe.

    psql -U postgres
    CREATE DATABASE kreavo;
    CREATE DATABASE kreavo_test;
    \q

### 4. Create the tables

    python -m app.setup_db
    python -m app.setup_db --test

The first applies `db/schema.sql` to `DATABASE_URL`, the second to `TEST_DATABASE_URL`. Both print which database they set up. The script is safe to run again whenever `db/schema.sql` changes.

### 5. Add the first tenant

    python -m app.add_tenant "Kreavo Sandbox" +14155238886

The number is the Twilio WhatsApp number this tenant receives messages on. Give it with or without the `whatsapp:` prefix; the command normalises it and stores `whatsapp:+14155238886`, which is exactly how Twilio sends it in the webhook's `To` field. A number that is badly formatted, or already belongs to a tenant, is refused with a one-line error.

### 6. Start the app

    python -m app.app

It will be available at http://127.0.0.1:5000. Run it as a module, not as a file: `app.py` imports from `app.db`, which only resolves when Python starts from the project root, so `python app/app.py` will fail with an import error.

If a required setting is missing, the service refuses to start and names the setting.

### 7. Run the tests

    pytest

The suite runs offline against `TEST_DATABASE_URL` — no Twilio account or network access required. It creates the tables itself and wipes the test database before every test, so it refuses to run if `TEST_DATABASE_URL` is unset or the same as `DATABASE_URL`.

## Health Check 
- The route to the health check is http://127.0.0.1:5000/health. Shows the health status plus its version number. 

## Configuration

Copy `.env.example` to `.env` and fill in the values.

- `TWILIO_ACCOUNT_SID` — identifies which account
- `TWILIO_AUTH_TOKEN` — proves you're allowed to use the account
- `TWILIO_SANDBOX_NUMBER` — the Twilio number replies are sent from, in E.164 format with the leading `+` (e.g. `+14155238886`). The code adds the `whatsapp:` prefix.

- `PORT` — optional; the port the service listens on. Defaults to 5000 if not set.
- `DATABASE_URL` — the app's Postgres connection string, e.g. `postgresql://postgres:YOUR_PASSWORD@localhost:5432/kreavo`. URL-encode special characters in the password (`@` → `%40`).
- `TEST_DATABASE_URL` — same form, pointing at the separate `kreavo_test` database. The tests wipe it.

## Running the Tests

With the virtual environment activated and `TEST_DATABASE_URL` set (see Setup):

    pytest

This runs the full suite offline — no Twilio account, phone number, or network access required.