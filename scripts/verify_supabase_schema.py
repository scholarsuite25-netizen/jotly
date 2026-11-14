"""Locates the user's Supabase project pooler region and verifies the pasted schema."""

import socket
import sys

import psycopg

REF = "izxneacavxfcjklnsftd"
PASSWORD = "b7/guYHWkkT%WMW"
encoded = PASSWORD.replace("/", "%2F").replace("%", "%25")

REGIONS = [
    "us-east-1",
    "ap-south-1",
    "ap-southeast-1",
    "ap-southeast-2",
    "ap-northeast-1",
    "us-west-1",
    "us-east-2",
    "us-west-2",
    "sa-east-1",
    "eu-north-1",
    "eu-west-3",
    "eu-central-2",
    "ap-east-1",
    "ca-central-1",
    "ap-southeast-3",
    "ap-northeast-2",
]

PREFIXES = ["aws-0", "aws-1"]


def find_region() -> str | None:
    for region in REGIONS:
        for prefix in PREFIXES:
            host = f"{prefix}-{region}.pooler.supabase.com"
            try:
                socket.getaddrinfo(host, 5432, socket.AF_INET, socket.SOCK_STREAM)
            except OSError:
                continue
            for port in (5432, 6543):
                dsn = (
                    f"postgresql://postgres.{REF}:{encoded}@{host}:{port}/postgres"
                    f"?sslmode=require&connect_timeout=5"
                )
                try:
                    conn = psycopg.connect(dsn)
                except psycopg.OperationalError as exc:
                    message = str(exc)
                    if "enotfound" in message.lower():
                        # Pooler reached Supabase; project not hosted in this region.
                        break
                    if "authentication" in message.lower() or "password" in message.lower():
                        print(f"REGION {region} port {port}: reached project, auth error: {message[:120]}")
                        continue
                    print(f"REGION {region} port {port}: connect failed: {message[:90]}")
                    continue
                print(f"CONNECTED via {host}:{port}")
                conn.close()
                return f"{host}|{port}"
    return None


found = find_region()
if not found:
    print("NO REGION FOUND")
    sys.exit(2)

host, port = found.split("|")
DSN = (
    f"postgresql://postgres.{REF}:{encoded}@{host}:{port}/postgres"
    f"?sslmode=require&connect_timeout=10"
)

conn = psycopg.connect(DSN)
with conn.cursor() as cur:
    cur.execute(
        "SELECT count(*) FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
    )
    table_count = cur.fetchone()[0]
    cur.execute("SELECT version_num FROM alembic_version")
    version_row = cur.fetchone()
    cur.execute("SELECT count(*) FROM pg_policies WHERE schemaname = 'public'")
    policy_count = cur.fetchone()[0]
    cur.execute(
        "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class c "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relkind = 'r'"
    )
    tables = cur.fetchall()
    rls_incomplete = [t[0] for t in tables if not (t[1] and t[2])]
    total_tables = len(tables)

print(f"tables created:        {total_tables}")
print(f"migration version:     {version_row[0] if version_row else 'NONE'}")
print(f"RLS policies total:    {policy_count}")
print(f"tables without RLS:    {rls_incomplete if rls_incomplete else 'none'}")

ok = (
    total_tables >= 50
    and version_row is not None
    and version_row[0].startswith("0008")
    and policy_count >= 49
    and not rls_incomplete
)
print("VERDICT:", "SCHEMA APPLIED CORRECTLY" if ok else "ISSUES FOUND")
conn.close()
sys.exit(0 if ok else 1)
