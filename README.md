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
