"""Phase 5 Voice Studio: speech projects, chunks, audio assets, chapters, pronunciation + RLS.

Revision ID: 0005_phase5_voice_studio
Revises: 0004_phase4_document_studio
Create Date: 2026-11-13
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0005_phase5_voice_studio"
down_revision: Union[str, None] = "0004_phase4_document_studio"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PHASE5_TENANT_TABLES: tuple[str, ...] = (
    "speech_projects",
    "speech_chunks",
    "audio_assets",
    "audio_chapters",
    "pronunciation_entries",
)


def get_phase5_postgres_rls_upgrade_sql() -> list[str]:
    statements: list[str] = []
    for table in PHASE5_TENANT_TABLES:
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


def get_phase5_postgres_rls_downgrade_sql() -> list[str]:
    statements: list[str] = []
    for table in PHASE5_TENANT_TABLES:
        statements.extend(
            [
                f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table};",
                f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;",
            ]
        )
    return statements


def upgrade() -> None:
    op.create_table(
        "speech_projects",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "organisation_id",
            sa.String(length=36),
            sa.ForeignKey("organisations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "source_document_id",
            sa.String(length=36),
            sa.ForeignKey("documents.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "source_document_version_id",
            sa.String(length=36),
            sa.ForeignKey("document_versions.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("language_code", sa.String(length=16), nullable=False, server_default="en"),
        sa.Column("voice_id", sa.String(length=64), nullable=False),
        sa.Column("speed_percent", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("output_format", sa.String(length=16), nullable=False, server_default="wav"),
        sa.Column("text_content", sa.Text(), nullable=False),
        sa.Column(
            "reviewed_by_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("tts_model_id", sa.String(length=120), nullable=False, server_default="stub-kokoro"),
        sa.Column("tts_model_version", sa.String(length=64), nullable=False, server_default="1.0.0"),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_speech_projects_org_idem",
        "speech_projects",
        ["organisation_id", "idempotency_key"],
        unique=True,
    )

    op.create_table(
        "speech_chunks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "organisation_id",
            sa.String(length=36),
            sa.ForeignKey("organisations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "speech_project_id",
            sa.String(length=36),
            sa.ForeignKey("speech_projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("pronunciation_overrides_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("object_key", sa.String(length=512), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_speech_chunks_org_project_idx",
        "speech_chunks",
        ["organisation_id", "speech_project_id", "chunk_index"],
        unique=True,
    )

    op.create_table(
        "audio_assets",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "organisation_id",
            sa.String(length=36),
            sa.ForeignKey("organisations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "speech_project_id",
            sa.String(length=36),
            sa.ForeignKey("speech_projects.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("object_key", sa.String(length=512), nullable=False, unique=True),
        sa.Column("output_format", sa.String(length=16), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256_checksum", sa.String(length=64), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("loudness_normalised", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "synthetic_disclosure",
            sa.String(length=255),
            nullable=False,
            server_default="AI-generated speech",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audio_assets_org_project", "audio_assets", ["organisation_id", "speech_project_id"])

    op.create_table(
        "audio_chapters",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "organisation_id",
            sa.String(length=36),
            sa.ForeignKey("organisations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "audio_asset_id",
            sa.String(length=36),
            sa.ForeignKey("audio_assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chapter_index", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=False),
    )
    op.create_index(
        "ix_audio_chapters_org_asset",
        "audio_chapters",
        ["organisation_id", "audio_asset_id", "chapter_index"],
        unique=True,
    )

    op.create_table(
        "pronunciation_entries",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "organisation_id",
            sa.String(length=36),
            sa.ForeignKey("organisations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("word", sa.String(length=120), nullable=False),
        sa.Column("phonetic_hint", sa.String(length=255), nullable=False),
        sa.Column("language_code", sa.String(length=16), nullable=False, server_default="en"),
        sa.Column(
            "created_by_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_pronunciation_entries_org_word",
        "pronunciation_entries",
        ["organisation_id", "word"],
        unique=True,
    )

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for stmt in get_phase5_postgres_rls_upgrade_sql():
            op.execute(stmt)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for stmt in get_phase5_postgres_rls_downgrade_sql():
            op.execute(stmt)

    op.drop_table("pronunciation_entries")
    op.drop_table("audio_chapters")
    op.drop_table("audio_assets")
    op.drop_table("speech_chunks")
    op.drop_table("speech_projects")
