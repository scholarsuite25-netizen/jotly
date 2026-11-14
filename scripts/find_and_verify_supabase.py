"""Tests each reachable regional pooler with the user's credentials to find their project."""

import sys

import psycopg

REF = "izxneacavxfcjklnsftd"
PASSWORD = "b7/guYHWkkT%WMW"
encoded = PASSWORD.replace("/", "%2F").replace("%", "%25")

HOSTS = [
    "aws-0-us-east-1.pooler.supabase.com",
    "aws-1-us-east-1.pooler.supabase.com",
    "aws-0-ap-south-1.pooler.supabase.com",
    "aws-1-ap-south-1.pooler.supabase.com",
    "aws-0-ap-southeast-1.pooler.supabase.com",
    "aws-1-ap-southeast-1.pooler.supabase.com",
    "aws-0-ap-southeast-2.pooler.supabase.com",
    "aws-1-ap-southeast-2.pooler.supabase.com",
    "aws-0-ap-northeast-1.pooler.supabase.com",
    "aws-1-ap-northeast-1.pooler.supabase.com",
    "aws-0-us-west-1.pooler.supabase.com",
    "aws-1-us-west-1.pooler.supabase.com",
    "aws-0-us-east-2.pooler.supabase.com",
    "aws-1-us-east-2.pooler.supabase.com",
    "aws-0-us-west-2.pooler.supabase.com",
    "aws-1-us-west-2.pooler.supabase.com",
    "aws-0-sa-east-1.pooler.supabase.com",
    "aws-1-sa-east-1.pooler.supabase.com",
    "aws-0-eu-north-1.pooler.supabase.com",
    "aws-1-eu-north-1.pooler.supabase.com",
    "aws-0-eu-west-3.pooler.supabase.com",
    "aws-1-eu-west-3.pooler.supabase.com",
    "aws-0-eu-central-2.pooler.supabase.com",
    "aws-1-eu-central-2.pooler.supabase.com",
    "aws-0-ap-east-1.pooler.supabase.com",
    "aws-0-ca-central-1.pooler.supabase.com",
    "aws-1-ca-central-1.pooler.supabase.com",
    "aws-0-ap-northeast-2.pooler.supabase.com",
    "aws-1-ap-northeast-2.pooler.supabase.com",
    "aws-0-eu-central-1.pooler.supabase.com",
    "aws-1-eu-central-1.pooler.supabase.com",
    "aws-0-eu-west-1.pooler.supabase.com",
    "aws-1-eu-west-1.pooler.supabase.com",
    "aws-0-eu-west-2.pooler.supabase.com",
    "aws-1-eu-west-2.pooler.supabase.com",
]

for host in HOSTS:
    dsn = (
        f"postgresql://postgres.{REF}:{encoded}@{host}:5432/postgres"
        f"?sslmode=require&connect_timeout=6"
    )
    try:
        conn = psycopg.connect(dsn)
    except psycopg.OperationalError as exc:
        print(f"{host}: {str(exc)[:110]}")
        continue
    print(f"SUCCESS: {host}")
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
    print(f"  tables: {tables} | version: {version_row[0] if version_row else 'NONE'} | policies: {policies} | no-RLS: {no_rls if no_rls else 'none'}")
    ok = tables >= 50 and version_row and version_row[0].startswith("0008") and policies >= 49 and not no_rls
    print("VERDICT:", "SCHEMA APPLIED CORRECTLY" if ok else "ISSUES FOUND")
    conn.close()
    sys.exit(0 if ok else 1)

print("\nNO PROJECT FOUND — credentials/region exhausted")
sys.exit(2)
