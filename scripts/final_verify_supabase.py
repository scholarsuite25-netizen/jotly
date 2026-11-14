"""Final verification: full table list + tests the exact SQLAlchemy URL Vercel will use."""

import sys

import psycopg
from sqlalchemy import create_engine, text

HOST = "aws-1-eu-central-1.pooler.supabase.com"
REF = "izxneacavxfcjklnsftd"
PASSWORD = "b7/guYHWkkT%WMW"

TENANT_TABLES = {
    "organisations", "workspaces", "departments", "roles", "user_roles", "invitations",
    "sessions", "audit_logs", "background_jobs", "meetings", "meeting_participants",
    "media_upload_sessions", "media_chunks", "media_assets", "media_derivatives",
    "media_processing_jobs", "transcripts", "transcript_speakers", "speaker_labels",
    "transcript_segments", "transcript_revisions", "transcript_exports", "documents",
    "document_versions", "document_templates", "document_exports", "document_shares",
    "speech_projects", "speech_chunks", "audio_assets", "audio_chapters",
    "pronunciation_entries", "voice_consents", "voice_profiles", "voice_samples",
    "voice_permissions", "voice_jobs", "voice_audit_events", "meeting_summaries",
    "decisions", "action_items", "ai_questions", "ai_answers", "evidence_links",
    "ai_job_logs", "meeting_comments", "share_grants", "notifications",
    "approval_workflows", "action_assignments", "integration_events",
}
GLOBAL_TABLES = {"alembic_version", "permissions", "role_permissions", "users"}

# --- Part 1: full schema state via psycopg kwargs ---
conn = psycopg.connect(
    host=HOST, port=5432, dbname="postgres",
    user=f"postgres.{REF}", password=PASSWORD, sslmode="require", connect_timeout=10,
)
with conn.cursor() as cur:
    cur.execute(
        "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class c "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relkind = 'r' ORDER BY relname"
    )
    rows = cur.fetchall()
tenant_missing_rls = sorted(r[0] for r in rows if r[0] in TENANT_TABLES and not (r[1] and r[2]))
unexpected = sorted(r[0] for r in rows if r[0] not in TENANT_TABLES and r[0] not in GLOBAL_TABLES)
conn.close()

print(f"total tables:          {len(rows)}")
print(f"tenant tables w/ RLS:  {len([r for r in rows if r[0] in TENANT_TABLES and r[1] and r[2]])} / {len(TENANT_TABLES)}")
print(f"tenant tables MISSING RLS: {tenant_missing_rls if tenant_missing_rls else 'none'}")
print(f"unexpected extra tables:   {unexpected if unexpected else 'none'}")
print(f"global (by design, no RLS): {sorted(r[0] for r in rows if r[0] in GLOBAL_TABLES)}")

# --- Part 2: exact SQLAlchemy URL the Vercel backend will use ---
engine = create_engine(
    "postgresql://postgres."
    f"{REF}:{PASSWORD.replace('/', '%2F').replace('%', '%25')}@{HOST}:6543/postgres",
    connect_args={"sslmode": "require", "connect_timeout": 10},
)
try:
    with engine.connect() as c:
        c.execute(text("SELECT 1"))
        c.execute(text("SELECT set_config('app.current_organisation_id', 'test', true)"))
        c.execute(text("SELECT set_config('app.current_organisation_id', '', true)"))
    print("SQLAlchemy pooler URL (transaction mode, port 6543): CONNECTED OK")
    url_ok = True
except Exception as exc:  # noqa: BLE001
    print(f"SQLAlchemy URL test FAILED: {exc}")
    url_ok = False

ok = not tenant_missing_rls and not unexpected and url_ok
print("FINAL VERDICT:", "SCHEMA APPLIED CORRECTLY" if ok else "ISSUES FOUND")
sys.exit(0 if ok else 1)
