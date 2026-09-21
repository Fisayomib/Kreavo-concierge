"""Create or update the database tables.

Run from the project root:
    python -m app.setup_db          # applies db/schema.sql to DATABASE_URL
    python -m app.setup_db --test   # applies it to TEST_DATABASE_URL instead
"""
import argparse
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "db" / "schema.sql"


def apply_schema(conn):
    """Runs db/schema.sql on the given connection. Safe to call repeatedly."""
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    conn.execute(sql)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Create or update the database tables from db/schema.sql.")
    parser.add_argument("--test", action="store_true", help="use TEST_DATABASE_URL instead of DATABASE_URL")
    args = parser.parse_args(argv)

    load_dotenv()
    setting = "TEST_DATABASE_URL" if args.test else "DATABASE_URL"
    database_url = os.environ.get(setting, "").strip()
    if not database_url:
        print(f"error: {setting} is not set. Add it to your .env and try again.", file=sys.stderr)
        return 1

    try:
        with psycopg.connect(database_url) as conn:
            apply_schema(conn)
            print(f"Schema applied to database '{conn.info.dbname}' on {conn.info.host}:{conn.info.port} ({setting})")
    except psycopg.Error as e:
        print(f"error: could not set up {setting}: {str(e).strip()}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
