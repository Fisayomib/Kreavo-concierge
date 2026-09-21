-- Safe to run any number of times.

CREATE TABLE IF NOT EXISTS tenants (
    id              BIGSERIAL PRIMARY KEY,
    name            TEXT NOT NULL,
    whatsapp_number TEXT NOT NULL UNIQUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT tenants_whatsapp_number_format
        CHECK (whatsapp_number ~ '^whatsapp:\+[1-9][0-9]{6,14}$')
);

CREATE TABLE IF NOT EXISTS turns (
    id              BIGSERIAL PRIMARY KEY,
    tenant_id       BIGINT NOT NULL REFERENCES tenants(id),
    message_sid     TEXT NOT NULL UNIQUE,
    customer_number TEXT NOT NULL,
    role            TEXT NOT NULL CHECK (role IN ('customer', 'assistant')),
    body            TEXT NOT NULL DEFAULT '',
    num_media       INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Stamped on the first line of the webhook, before any database work. Conversation order is (received_at, id).
    received_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- NULL means no reply is tracked: assistant turns, and customer turns stored before this column existed.
    reply_status    TEXT,
    CONSTRAINT turns_reply_status_values
        CHECK (reply_status IN ('pending', 'sent', 'failed'))
);

-- Messages whose To number matched no tenant. Deliberately references neither tenants nor turns:
-- they belong to no tenant and must never appear in any tenant's conversation.
CREATE TABLE IF NOT EXISTS unrecognised_messages (
    id              BIGSERIAL PRIMARY KEY,
    message_sid     TEXT NOT NULL UNIQUE,
    to_number       TEXT NOT NULL,
    from_number     TEXT NOT NULL,
    body            TEXT NOT NULL DEFAULT '',
    num_media       INTEGER NOT NULL DEFAULT 0,
    received_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- CREATE TABLE IF NOT EXISTS does not add the constraint to a tenants table that
-- already existed, and Postgres has no ADD CONSTRAINT IF NOT EXISTS, so check first.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'tenants_whatsapp_number_format'
          AND conrelid = 'tenants'::regclass
    ) THEN
        ALTER TABLE tenants
            ADD CONSTRAINT tenants_whatsapp_number_format
            CHECK (whatsapp_number ~ '^whatsapp:\+[1-9][0-9]{6,14}$');
    END IF;
END
$$;

-- turns tables created before reply_status existed need the column and its constraint added.
ALTER TABLE turns ADD COLUMN IF NOT EXISTS reply_status TEXT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'turns_reply_status_values'
          AND conrelid = 'turns'::regclass
    ) THEN
        ALTER TABLE turns
            ADD CONSTRAINT turns_reply_status_values
            CHECK (reply_status IN ('pending', 'sent', 'failed'));
    END IF;
END
$$;

-- turns tables created before received_at existed: add it, backfill from created_at, then tighten.
ALTER TABLE turns ADD COLUMN IF NOT EXISTS received_at TIMESTAMPTZ;
UPDATE turns SET received_at = created_at WHERE received_at IS NULL;
ALTER TABLE turns ALTER COLUMN received_at SET DEFAULT now();
ALTER TABLE turns ALTER COLUMN received_at SET NOT NULL;

-- Reading one customer's conversation for one tenant, in order.
CREATE INDEX IF NOT EXISTS turns_conversation_order ON turns (tenant_id, customer_number, received_at, id);
