CREATE TABLE IF NOT EXISTS tenants (
    id              BIGSERIAL PRIMARY KEY,
    name            TEXT NOT NULL,
    whatsapp_number TEXT NOT NULL UNIQUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS turns (
    id              BIGSERIAL PRIMARY KEY,
    tenant_id       BIGINT NOT NULL REFERENCES tenants(id),
    message_sid     TEXT NOT NULL UNIQUE,
    customer_number TEXT NOT NULL,
    role            TEXT NOT NULL CHECK (role IN ('customer', 'assistant')),
    body            TEXT NOT NULL DEFAULT '',
    num_media       INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);