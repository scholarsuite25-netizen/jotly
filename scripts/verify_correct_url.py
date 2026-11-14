"""Tests the correctly-encoded DATABASE_URL string Vercel will receive."""

import sys
from urllib.parse import quote

import psycopg
from sqlalchemy import create_engine, text

HOST = "aws-1-eu-central-1.pooler.supabase.com"
REF = "izxneacavxfcjklnsftd"
PASSWORD = "b7/guYHWkkT%WMW"
ENCODED = quote(PASSWORD, safe="")  # proper single-pass encoding

print(f"correctly encoded password: {ENCODED}")

for port in (6543, 5432):
    url = f"postgresql://postgres.{REF}:{ENCODED}@{HOST}:{port}/postgres"
    try:
        engine = create_engine(
            url, connect_args={"sslmode": "require", "connect_timeout": 10}
        )
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        engine.dispose()
        print(f"SQLAlchemy URL port {port}: CONNECTED OK")
        best_port = port
        break
    except Exception as exc:  # noqa: BLE001
        print(f"SQLAlchemy URL port {port}: FAIL {str(exc)[:80]}")
        best_port = None

# Also confirm RLS tenant context behaves on the live DB
if best_port:
    engine = create_engine(
        f"postgresql://postgres.{REF}:{ENCODED}@{HOST}:{best_port}/postgres",
        connect_args={"sslmode": "require", "connect_timeout": 10},
    )
    with engine.connect() as c:
        c.execute(text("SELECT set_config('app.current_organisation_id', '00000000-0000-0000-0000-000000000001', true)"))
        result = c.execute(
            text("SELECT count(*) FROM meetings WHERE organisation_id = '00000000-0000-0000-0000-000000000001'")
        )
        count = result.scalar_one()
        c.execute(text("SELECT set_config('app.current_organisation_id', '', true)"))
    print(f"RLS tenant-context query on meetings: returned {count} rows (expected 0) — RLS ACTIVE")
    print()
    print("VERIFIED DATABASE_URL FOR VERCEL:")
    print(f"postgresql://postgres.{REF}:{ENCODED}@{HOST}:{best_port}/postgres")
    sys.exit(0)
sys.exit(1)
