import os
import psycopg


def get_connection():
    database_url = os.environ.get("DATABASE_URL", "").strip()
    return psycopg.connect(database_url)


def find_tenant_id(conn, whatsapp_number):
    row = conn.execute(
        "SELECT id FROM tenants WHERE whatsapp_number = %s",
        (whatsapp_number,),
    ).fetchone()
    if row is None:
        return None
    return row[0]


def record_inbound_turn(conn, tenant_id, message_sid, customer_number, body, num_media, received_at):
    row = conn.execute(
        """
        INSERT INTO turns (tenant_id, message_sid, customer_number, role, body, num_media, reply_status, received_at)
        VALUES (%s, %s, %s, 'customer', %s, %s, 'pending', %s)
        ON CONFLICT (message_sid) DO NOTHING
        RETURNING id
        """,
        (tenant_id, message_sid, customer_number, body, num_media, received_at),
    ).fetchone()
    return row is not None


def get_conversation(conn, tenant_id, customer_number):
    # The only place conversation order is defined: when we received the webhook, then id to break ties.
    return conn.execute(
        """
        SELECT message_sid, role, body, num_media, received_at
        FROM turns
        WHERE tenant_id = %s AND customer_number = %s
        ORDER BY received_at, id
        """,
        (tenant_id, customer_number),
    ).fetchall()


def set_reply_status(conn, message_sid, status):
    if status not in ("sent", "failed"):
        raise ValueError(f"reply_status must be 'sent' or 'failed', got '{status}'")
    conn.execute(
        "UPDATE turns SET reply_status = %s WHERE message_sid = %s",
        (status, message_sid),
    )


def record_unrecognised_message(conn, message_sid, to_number, from_number, body, num_media, received_at):
    row = conn.execute(
        """
        INSERT INTO unrecognised_messages (message_sid, to_number, from_number, body, num_media, received_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (message_sid) DO NOTHING
        RETURNING id
        """,
        (message_sid, to_number, from_number, body, num_media, received_at),
    ).fetchone()
    return row is not None
