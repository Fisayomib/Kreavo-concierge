import psycopg
import pytest

from app.add_tenant import add_tenant
from app.db import get_connection
from app.setup_db import apply_schema

SEEDED_NUMBER = "whatsapp:+14155238886"  # inserted by the clean_db fixture in conftest.py
NEW_NUMBER = "+15550001111"


def stored_number(tenant_id):
    with get_connection() as conn:
        return conn.execute("SELECT whatsapp_number FROM tenants WHERE id = %s", (tenant_id,)).fetchone()[0]


# ---------- database rule on the number's format ----------

def test_number_without_prefix_is_rejected_by_the_database():
    with pytest.raises(psycopg.errors.CheckViolation, match="tenants_whatsapp_number_format"):
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO tenants (name, whatsapp_number) VALUES (%s, %s)",
                ("No Prefix", "+14155238886"),
            )


# ---------- add_tenant ----------

def test_add_tenant_adds_the_prefix_when_missing():
    with get_connection() as conn:
        tenant_id = add_tenant(conn, "New Tenant", NEW_NUMBER)
    assert stored_number(tenant_id) == "whatsapp:+15550001111"


def test_add_tenant_keeps_an_existing_prefix_unchanged():
    with get_connection() as conn:
        tenant_id = add_tenant(conn, "New Tenant", "whatsapp:+15550001111")
    assert stored_number(tenant_id) == "whatsapp:+15550001111"


def test_add_tenant_strips_surrounding_spaces():
    with get_connection() as conn:
        tenant_id = add_tenant(conn, "  New Tenant  ", "  +15550001111  ")
    assert stored_number(tenant_id) == "whatsapp:+15550001111"


@pytest.mark.parametrize("bad_number", ["12345", "whatsapp:14155238886", "abc"])
def test_add_tenant_rejects_a_malformed_number(bad_number):
    with get_connection() as conn:
        with pytest.raises(ValueError, match="not a valid WhatsApp number"):
            add_tenant(conn, "Bad Number", bad_number)
        count = conn.execute("SELECT count(*) FROM tenants").fetchone()[0]
    assert count == 1  # only the seeded tenant


def test_add_tenant_rejects_a_number_that_already_belongs_to_a_tenant():
    with get_connection() as conn:
        with pytest.raises(ValueError, match="already exists"):
            add_tenant(conn, "Duplicate", SEEDED_NUMBER)
        # the connection is still usable after the rejected insert
        count = conn.execute("SELECT count(*) FROM tenants").fetchone()[0]
    assert count == 1


def test_add_tenant_rejects_a_duplicate_given_without_the_prefix():
    with get_connection() as conn:
        with pytest.raises(ValueError, match="already exists"):
            add_tenant(conn, "Duplicate", "+14155238886")


# ---------- database rule on reply_status ----------

def test_unknown_reply_status_is_rejected_by_the_database():
    with pytest.raises(psycopg.errors.CheckViolation, match="turns_reply_status_values"):
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO turns (tenant_id, message_sid, customer_number, role, body, num_media, reply_status)
                VALUES (1, 'SM001', 'whatsapp:+2340000000000', 'customer', 'hello', 0, 'banana')
                """
            )


def test_reply_status_allows_null_for_untracked_turns():
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO turns (tenant_id, message_sid, customer_number, role, body, num_media)
            VALUES (1, 'SM001', 'whatsapp:+2340000000000', 'assistant', 'hello', 0)
            """
        )
        status = conn.execute("SELECT reply_status FROM turns WHERE message_sid = 'SM001'").fetchone()[0]
    assert status is None


# ---------- apply_schema ----------

def test_apply_schema_can_run_twice_in_a_row():
    for _ in range(2):
        with get_connection() as conn:
            apply_schema(conn)
    with get_connection() as conn:
        constraints = conn.execute(
            """
            SELECT count(*) FROM pg_constraint
            WHERE conname IN ('tenants_whatsapp_number_format', 'turns_reply_status_values')
            """
        ).fetchone()[0]
    assert constraints == 2
