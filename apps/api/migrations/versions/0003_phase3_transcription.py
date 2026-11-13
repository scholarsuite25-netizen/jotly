"""Phase 3 Transcription, Diarisation Suggestions, and Revision History schema + PostgreSQL RLS.

Revision ID: 0003_phase3_transcription
Revises: 0002_phase2_recording_media
Create Date: 2026-11-13
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0003_phase3_transcription"
down_revision: Union[str, None] = "0002_phase2_recording_media"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PHASE3_TENANT_TABLES: tuple[str, ...] = (
    "transcripts",
    "transcript_speakers",
    "speaker_labels",
    "transcript_segments",
    "transcript_revisions",
    "transcript_exports",
)


def get_phase3_postgres_rls_upgrade_sql() -> list[str]:
    statements: list[str] = []
    for table in PHASE3_TENANT_TABLES:
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


def get_phase3_postgres_rls_downgrade_sql() -> list[str]:
    statements: list[str] = []
    for table in PHASE3_TENANT_TABLES:
        statements.extend(
            [
                f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table};",
                f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;",
            ]
        )
    return statements


def upgrade() -> None:
    op.create_table(
        "transcripts",
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
        sa.Column("language_code", sa.String(length=16), nullable=False, server_default="en"),
        sa.Column("detected_language", sa.String(length=16), nullable=False, server_default="en"),
        sa.Column("language_confidence", sa.Float(), nullable=False, server_default="0.95"),
        sa.Column(
            "asr_model_id",
            sa.String(length=120),
            nullable=False,
            server_default="faster-whisper-large-v3",
        ),
        sa.Column("asr_model_version", sa.String(length=64), nullable=False, server_default="1.0.3"),
        sa.Column("diarisation_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("diarisation_model_id", sa.String(length=120), nullable=True),
        sa.Column("config_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="completed"),
        sa.Column("current_revision_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_transcripts_org_meeting", "transcripts", ["organisation_id", "meeting_id"])
    op.create_index("ix_transcripts_org_media", "transcripts", ["organisation_id", "media_asset_id"])

    op.create_table(
        "transcript_speakers",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "organisation_id",
            sa.String(length=36),
            sa.ForeignKey("organisations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "transcript_id",
            sa.String(length=36),
            sa.ForeignKey("transcripts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("speaker_key", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("is_model_suggestion", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("identity_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_transcript_speakers_org_tx_key",
        "transcript_speakers",
        ["organisation_id", "transcript_id", "speaker_key"],
        unique=True,
    )

    op.create_table(
        "speaker_labels",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "organisation_id",
            sa.String(length=36),
            sa.ForeignKey("organisations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "transcript_id",
            sa.String(length=36),
            sa.ForeignKey("transcripts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "speaker_id",
            sa.String(length=36),
            sa.ForeignKey("transcript_speakers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("previous_display_name", sa.String(length=120), nullable=True),
        sa.Column("new_display_name", sa.String(length=120), nullable=False),
        sa.Column(
            "changed_by_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="model_suggestion"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_speaker_labels_org_tx", "speaker_labels", ["organisation_id", "transcript_id"])

    op.create_table(
        "transcript_segments",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "organisation_id",
            sa.String(length=36),
            sa.ForeignKey("organisations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "transcript_id",
            sa.String(length=36),
            sa.ForeignKey("transcripts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=False),
        sa.Column("original_asr_text", sa.Text(), nullable=False),
        sa.Column("current_text", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.9"),
        sa.Column(
            "speaker_id",
            sa.String(length=36),
            sa.ForeignKey("transcript_speakers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "speaker_is_model_suggestion",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("is_edited", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "updated_by_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_transcript_segments_org_tx_seq",
        "transcript_segments",
        ["organisation_id", "transcript_id", "sequence_number"],
        unique=True,
    )

    op.create_table(
        "transcript_revisions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "organisation_id",
            sa.String(length=36),
            sa.ForeignKey("organisations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "transcript_id",
            sa.String(length=36),
            sa.ForeignKey("transcripts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "segment_id",
            sa.String(length=36),
            sa.ForeignKey("transcript_segments.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("change_type", sa.String(length=32), nullable=False),
        sa.Column("previous_text", sa.Text(), nullable=True),
        sa.Column("new_text", sa.Text(), nullable=True),
        sa.Column("previous_speaker_id", sa.String(length=36), nullable=True),
        sa.Column("new_speaker_id", sa.String(length=36), nullable=True),
        sa.Column(
            "editor_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("summary", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_transcript_revisions_org_tx_rev",
        "transcript_revisions",
        ["organisation_id", "transcript_id", "revision_number"],
    )

    op.create_table(
        "transcript_exports",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "organisation_id",
            sa.String(length=36),
            sa.ForeignKey("organisations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "transcript_id",
            sa.String(length=36),
            sa.ForeignKey("transcripts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("format", sa.String(length=16), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column(
            "created_by_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_transcript_exports_org_tx", "transcript_exports", ["organisation_id", "transcript_id"])

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for stmt in get_phase3_postgres_rls_upgrade_sql():
            op.execute(stmt)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for stmt in get_phase3_postgres_rls_downgrade_sql():
            op.execute(stmt)

    op.drop_table("transcript_exports")
    op.drop_table("transcript_revisions")
    op.drop_table("transcript_segments")
    op.drop_table("speaker_labels")
    op.drop_table("transcript_speakers")
    op.drop_table("transcripts")
