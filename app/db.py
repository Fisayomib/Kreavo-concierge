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


def record_inbound_turn(conn, tenant_id, message_sid, customer_number, body, num_media):
    row = conn.execute(
        """
        INSERT INTO turns (tenant_id, message_sid, customer_number, role, body, num_media, reply_status)
        VALUES (%s, %s, %s, 'customer', %s, %s, 'pending')
        ON CONFLICT (message_sid) DO NOTHING
        RETURNING id
        """,
        (tenant_id, message_sid, customer_number, body, num_media),
    ).fetchone()
    return row is not None


def set_reply_status(conn, message_sid, status):
    if status not in ("sent", "failed"):
        raise ValueError(f"reply_status must be 'sent' or 'failed', got '{status}'")
    conn.execute(
        "UPDATE turns SET reply_status = %s WHERE message_sid = %s",
        (status, message_sid),
    )
