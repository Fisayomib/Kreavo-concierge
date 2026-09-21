import os
import pytest
from dotenv import load_dotenv

os.environ.setdefault("TWILIO_ACCOUNT_SID", "test-sid")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "test-token")
os.environ.setdefault("TWILIO_SANDBOX_NUMBER", "+15550000000")

load_dotenv()

test_db = os.environ.get("TEST_DATABASE_URL", "").strip()
if not test_db:
    raise RuntimeError("TEST_DATABASE_URL is not set. Tests wipe their database, so they refuse to run without their own.")
if test_db == os.environ.get("DATABASE_URL", "").strip():
    raise RuntimeError("TEST_DATABASE_URL must not be the same as DATABASE_URL. Tests would wipe your real data.")
os.environ["DATABASE_URL"] = test_db

TEST_TENANT_NUMBER = "whatsapp:+14155238886"


@pytest.fixture(autouse=True)
def clean_db():
    from app.db import get_connection
    with get_connection() as conn:
        conn.execute("TRUNCATE turns, tenants RESTART IDENTITY")
        conn.execute(
            "INSERT INTO tenants (name, whatsapp_number) VALUES (%s, %s)",
            ("Test Tenant", TEST_TENANT_NUMBER),
        )
    yield