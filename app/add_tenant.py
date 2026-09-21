import argparse
import os
import re
import sys

import psycopg
from dotenv import load_dotenv

from app.db import get_connection

WHATSAPP_PREFIX = "whatsapp:"
WHATSAPP_NUMBER_PATTERN = re.compile(r"^whatsapp:\+[1-9][0-9]{6,14}$")


def normalise_number(number):
    """Strips spaces and adds the whatsapp: prefix if missing. Does not validate."""
    number = number.strip()
    if not number.startswith(WHATSAPP_PREFIX):
        number = WHATSAPP_PREFIX + number
    return number


def add_tenant(conn, name, number):
    """Inserts a tenant and returns its id. Raises ValueError with a readable message on bad input."""
    name = name.strip()
    if not name:
        raise ValueError("Tenant name must not be empty.")
    stored_number = normalise_number(number)
    if not WHATSAPP_NUMBER_PATTERN.match(stored_number):
        raise ValueError(
            f"'{number.strip()}' is not a valid WhatsApp number. "
            "Use the E.164 form with the leading '+', e.g. +14155238886 or whatsapp:+14155238886."
        )
    try:
        with conn.transaction():
            row = conn.execute(
                "INSERT INTO tenants (name, whatsapp_number) VALUES (%s, %s) RETURNING id",
                (name, stored_number),
            ).fetchone()
    except psycopg.errors.UniqueViolation:
        raise ValueError(f"A tenant with the number {stored_number} already exists.") from None
    return row[0]


def main(argv=None):
    parser = argparse.ArgumentParser(description="Add a tenant by name and WhatsApp number.")
    parser.add_argument("name", help='the tenant\'s name, e.g. "Kreavo Sandbox"')
    parser.add_argument("number", help="the WhatsApp number, with or without the whatsapp: prefix, e.g. +14155238886")
    args = parser.parse_args(argv)

    load_dotenv()
    if not os.environ.get("DATABASE_URL", "").strip():
        print("error: DATABASE_URL is not set. Add it to your .env and try again.", file=sys.stderr)
        return 1
    try:
        with get_connection() as conn:
            tenant_id = add_tenant(conn, args.name, args.number)
            print(f"Added tenant id={tenant_id} name={args.name.strip()!r} whatsapp_number={normalise_number(args.number)}")
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except psycopg.Error as e:
        print(f"error: could not add tenant: {str(e).strip()}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
