"""Phase 2 Recording and Media schema and PostgreSQL Row-Level Security (RLS) policies.

Revision ID: 0002_phase2_recording_media
Revises: 0001_phase1_foundation
Create Date: 2026-11-13
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0002_phase2_recording_media"
down_revision: Union[str, None] = "0001_phase1_foundation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PHASE2_TENANT_TABLES: tuple[str, ...] = (
    "meetings",
    "meeting_participants",
    "media_upload_sessions",
    "media_chunks",
    "media_assets",
    "media_derivatives",
    "media_processing_jobs",
)


def get_phase2_postgres_rls_upgrade_sql() -> list[str]:
    statements: list[str] = []
    for table in PHASE2_TENANT_TABLES:
        statements.extend(
            [
                f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;",
                f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;",
                (
                    f"CREATE POLICY tenant_isolation_{table} ON {table} "
                    f"USING (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), '')) "
                    f"WITH CHECK (organisation_id::text = NULLIF(current_setting('app.current_organisation_id', true), ''));"
                ),
            ]
        )
    return statements


def get_phase2_postgres_rls_downgrade_sql() -> list[str]:
    statements: list[str] = []
    for table in PHASE2_TENANT_TABLES:
        statements.extend(
            [
                f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table};",
                f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;",
            ]
        )
    return statements


def upgrade() -> None:
    op.create_table(
        "meetings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "organisation_id",
            sa.String(length=36),
            sa.ForeignKey("organisations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            sa.String(length=36),
            sa.ForeignKey("workspaces.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "department_id",
            sa.String(length=36),
            sa.ForeignKey("departments.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "host_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("agenda", sa.Text(), nullable=True),
        sa.Column("scheduled_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scheduled_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("visibility", sa.String(length=32), nullable=False, server_default="workspace"),
        sa.Column("recording_state", sa.String(length=32), nullable=False, server_default="idle"),
        sa.Column("notice_version", sa.String(length=32), nullable=True),
        sa.Column("notice_confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "notice_confirmed_by_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_meetings_org_workspace", "meetings", ["organisation_id", "workspace_id"])

    op.create_table(
        "meeting_participants",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "organisation_id",
            sa.String(length=36),
            sa.ForeignKey("organisations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "meeting_id",
            sa.String(length=36),
            sa.ForeignKey("meetings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False, server_default="attendee"),
        sa.Column("consent_status", sa.String(length=32), nullable=False, server_default="notified"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_meeting_participants_org_meeting",
        "meeting_participants",
        ["organisation_id", "meeting_id"],
    )

    op.create_table(
        "media_upload_sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "organisation_id",
            sa.String(length=36),
            sa.ForeignKey("organisations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "meeting_id",
            sa.String(length=36),
            sa.ForeignKey("meetings.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "initiated_by_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("declared_size_bytes", sa.Integer(), nullable=False),
        sa.Column("chunk_size_bytes", sa.Integer(), nullable=False),
        sa.Column("total_chunks", sa.Integer(), nullable=False),
        sa.Column("expected_sha256", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="initiated"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_media_upload_sessions_org_idem",
        "media_upload_sessions",
        ["organisation_id", "idempotency_key"],
        unique=True,
    )

    op.create_table(
        "media_chunks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "organisation_id",
            sa.String(length=36),
            sa.ForeignKey("organisations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "upload_session_id",
            sa.String(length=36),
            sa.ForeignKey("media_upload_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256_checksum", sa.String(length=64), nullable=False),
        sa.Column("object_key", sa.String(length=512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_media_chunks_session_idx",
        "media_chunks",
        ["organisation_id", "upload_session_id", "chunk_index"],
        unique=True,
    )

    op.create_table(
        "media_assets",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "organisation_id",
            sa.String(length=36),
            sa.ForeignKey("organisations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "meeting_id",
            sa.String(length=36),
            sa.ForeignKey("meetings.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "upload_session_id",
            sa.String(length=36),
            sa.ForeignKey("media_upload_sessions.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "uploaded_by_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("object_key", sa.String(length=512), nullable=False, unique=True),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256_checksum", sa.String(length=64), nullable=False),
        sa.Column("codec", sa.String(length=64), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("sample_rate_hz", sa.Integer(), nullable=True),
        sa.Column("channels", sa.Integer(), nullable=True),
        sa.Column("encryption_alg", sa.String(length=32), nullable=False, server_default="AES-256-GCM"),
        sa.Column("retention_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="uploaded"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_media_assets_org_meeting", "media_assets", ["organisation_id", "meeting_id"])

    op.create_table(
        "media_derivatives",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "organisation_id",
            sa.String(length=36),
            sa.ForeignKey("organisations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "media_asset_id",
            sa.String(length=36),
            sa.ForeignKey("media_assets.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "meeting_id",
            sa.String(length=36),
            sa.ForeignKey("meetings.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("object_key", sa.String(length=512), nullable=False, unique=True),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256_checksum", sa.String(length=64), nullable=False),
        sa.Column("processing_version", sa.String(length=32), nullable=False, server_default="ffmpeg-norm-1.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_media_derivatives_org_asset",
        "media_derivatives",
        ["organisation_id", "media_asset_id"],
    )

    op.create_table(
        "media_processing_jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "organisation_id",
            sa.String(length=36),
            sa.ForeignKey("organisations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "media_asset_id",
            sa.String(length=36),
            sa.ForeignKey("media_assets.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "background_job_id",
            sa.String(length=36),
            sa.ForeignKey("background_jobs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("stage", sa.String(length=64), nullable=False, server_default="validate_and_normalise"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("details_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_media_proc_jobs_org_asset",
        "media_processing_jobs",
        ["organisation_id", "media_asset_id"],
    )

    from alembic import context as _ctx
    if _ctx.is_offline_mode():
        for stmt in get_phase2_postgres_rls_upgrade_sql():
            op.execute(stmt)
    else:
        bind = op.get_bind()
        if bind.dialect.name == "postgresql":
            for stmt in get_phase2_postgres_rls_upgrade_sql():
                op.execute(stmt)


def downgrade() -> None:
    from alembic import context as _ctx
    if _ctx.is_offline_mode():
        for stmt in get_phase2_postgres_rls_downgrade_sql():
            op.execute(stmt)
    else:
        bind = op.get_bind()
        if bind.dialect.name == "postgresql":
            for stmt in get_phase2_postgres_rls_downgrade_sql():
                op.execute(stmt)

    op.drop_table("media_processing_jobs")
    op.drop_table("media_derivatives")
    op.drop_table("media_assets")
    op.drop_table("media_chunks")
    op.drop_table("media_upload_sessions")
    op.drop_table("meeting_participants")
    op.drop_table("meetings")
