"""Isolates: port 5432 vs 6543, and kwargs vs URL-encoded password."""

import sys

import psycopg
from sqlalchemy import create_engine, text

HOST = "aws-1-eu-central-1.pooler.supabase.com"
REF = "izxneacavxfcjklnsftd"
PASSWORD = "b7/guYHWkkT%WMW"
ENCODED = PASSWORD.replace("/", "%2F").replace("%", "%25")


def psycopg_test(port: int, password: str, label: str) -> bool:
    try:
        conn = psycopg.connect(
            host=HOST, port=port, dbname="postgres",
            user=f"postgres.{REF}", password=password,
            sslmode="require", connect_timeout=10,
        )
        conn.close()
        print(f"OK    psycopg kwargs {label}")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL  psycopg kwargs {label}: {str(exc)[:100]}")
        return False


def sqlalchemy_test(port: int, url_password: str, label: str) -> bool:
    try:
        engine = create_engine(
            f"postgresql://postgres.{REF}:{url_password}@{HOST}:{port}/postgres",
            connect_args={"sslmode": "require", "connect_timeout": 10},
        )
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        engine.dispose()
        print(f"OK    SQLAlchemy {label}")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL  SQLAlchemy {label}: {str(exc)[:100]}")
        return False


r1 = psycopg_test(6543, PASSWORD, "port 6543, raw password")
r2 = sqlalchemy_test(6543, ENCODED, "port 6543, encoded URL password")
r3 = sqlalchemy_test(5432, ENCODED, "port 5432, encoded URL password")
r4 = psycopg_test(5432, PASSWORD, "port 5432, raw password (control)")

print()
if r2:
    print("USE FOR VERCEL DATABASE_URL: postgresql://postgres." + REF + f":{ENCODED}@{HOST}:6543/postgres")
elif r3:
    print("USE FOR VERCEL DATABASE_URL: postgresql://postgres." + REF + f":{ENCODED}@{HOST}:5432/postgres")
elif r1:
    print("USE: raw-password kwargs connection on 6543 works; env URL must avoid percent-encoding")
elif r4:
    print("USE FOR VERCEL DATABASE_URL: session pooler port 5432")
sys.exit(0)
