"""Verifies the schema via the discovered pooler host using raw keyword-arg connection
(no URL encoding of the password)."""

import sys

import psycopg

HOST = "aws-1-eu-central-1.pooler.supabase.com"
REF = "izxneacavxfcjklnsftd"
PASSWORD = "b7/guYHWkkT%WMW"

conn = psycopg.connect(
    host=HOST,
    port=5432,
    dbname="postgres",
    user=f"postgres.{REF}",
    password=PASSWORD,
    sslmode="require",
    connect_timeout=10,
)
print("CONNECTED OK")

with conn.cursor() as cur:
    cur.execute(
        "SELECT count(*) FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
    )
    tables = cur.fetchone()[0]
    cur.execute("SELECT version_num FROM alembic_version")
    version_row = cur.fetchone()
    cur.execute("SELECT count(*) FROM pg_policies WHERE schemaname = 'public'")
    policies = cur.fetchone()[0]
    cur.execute(
        "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class c "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relkind = 'r'"
    )
    rows = cur.fetchall()
    no_rls = [r[0] for r in rows if not (r[1] and r[2])]

print(f"tables: {tables} | version: {version_row[0] if version_row else 'NONE'} | policies: {policies}")
print(f"tables without RLS enabled+forced: {no_rls if no_rls else 'none'}")

ok = (
    tables >= 50
    and version_row is not None
    and version_row[0].startswith("0008")
    and policies >= 49
    and not no_rls
)
print("VERDICT:", "SCHEMA APPLIED CORRECTLY" if ok else "ISSUES FOUND")
conn.close()
sys.exit(0 if ok else 1)
