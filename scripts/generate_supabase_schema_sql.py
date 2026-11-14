"""Generates the full PostgreSQL schema SQL (all migrations, including RLS policies)
into infra/sql/supabase_schema.sql for pasting into the Supabase SQL Editor."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_DIR = ROOT / "apps" / "api"
OUT = ROOT / "infra" / "sql" / "supabase_schema.sql"

# Offline mode never connects; the URL only selects the PostgreSQL dialect.
os.environ["DATABASE_URL"] = "postgresql://offline:offline@localhost:5432/offline"

result = subprocess.run(
    [sys.executable, "-m", "alembic", "upgrade", "head", "--sql"],
    cwd=API_DIR,
    capture_output=True,
    text=True,
    env={**os.environ},
)

if result.returncode != 0:
    print(result.stdout[-3000:])
    print(result.stderr[-3000:])
    raise SystemExit(f"alembic offline generation failed: {result.returncode}")

sql = result.stdout
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(sql, encoding="utf-8", newline="\n")

checks = {
    "CREATE TABLE meetings": "CREATE TABLE meetings" in sql,
    "RLS enabled on media_assets": "ALTER TABLE media_assets ENABLE ROW LEVEL SECURITY" in sql,
    "RLS forced on voice_profiles": "ALTER TABLE voice_profiles FORCE ROW LEVEL SECURITY" in sql,
    "tenant policy on transcript_segments": "CREATE POLICY tenant_isolation_transcript_segments" in sql,
    "background_jobs table": "CREATE TABLE background_jobs" in sql,
}
print(f"written: {OUT} ({len(sql)} chars)")
for name, ok in checks.items():
    print(f"  {'OK ' if ok else 'MISS'} {name}")
if not all(checks.values()):
    raise SystemExit("generated SQL failed verification")
print("verification passed")
