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

## Installing Requirements

1. Create a virtual environment: `python -m venv venv`
2. Activate it:
   - Windows (PowerShell): `.\venv\Scripts\Activate.ps1`
   - macOS/Linux: `source venv/bin/activate`
3. Install dependencies: `pip install -r requirements.txt`
4. Copy `.env.example` to `.env` and fill in your Twilio credentials (see Configuration below)
5. Start the service: `python app/app.py` — it will be available at http://127.0.0.1:5000

If a required setting is missing, the service refuses to start and names the setting.

## Health Check 
- The route to the health check is http://127.0.0.1:5000/health. Shows the health status plus its version number. 

## Configuration

Copy `.env.example` to `.env` and fill in the values.

- `TWILIO_ACCOUNT_SID` — identifies which account
- `TWILIO_AUTH_TOKEN` — proves you're allowed to use the account
- `TWILIO_SANDBOX_NUMBER` — the Twilio number replies are sent from, in E.164 format with the leading `+` (e.g. `+14155238886`). The code adds the `whatsapp:` prefix.

- `PORT` — optional; the port the service listens on. Defaults to 5000 if not set.

## Running the Tests

With the virtual environment activated:

    python -m pytest

This runs the full suite offline — no Twilio account, phone number, or network access required.