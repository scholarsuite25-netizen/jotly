"""Phase 7 Meeting Intelligence: summaries, decisions, action items, evidence links + RLS.

Revision ID: 0007_phase7_meeting_intelligence
Revises: 0006_phase6_voice_governance
Create Date: 2026-11-14
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0007_phase7_meeting_intelligence"
down_revision: Union[str, None] = "0006_phase6_voice_governance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PHASE7_TENANT_TABLES: tuple[str, ...] = (
    "meeting_summaries",
    "decisions",
    "action_items",
    "ai_questions",
    "ai_answers",
    "evidence_links",
    "ai_job_logs",
)


def get_phase7_postgres_rls_upgrade_sql() -> list[str]:
    statements: list[str] = []
    for table in PHASE7_TENANT_TABLES:
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


def get_phase7_postgres_rls_downgrade_sql() -> list[str]:
    statements: list[str] = []
    for table in PHASE7_TENANT_TABLES:
        statements.extend(
            [
                f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table};",
                f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;",
            ]
        )
    return statements


def upgrade() -> None:
    op.create_table(
        "meeting_summaries",
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
            "transcript_id",
            sa.String(length=36),
            sa.ForeignKey("transcripts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "background_job_id",
            sa.String(length=36),
            sa.ForeignKey("background_jobs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=32), nullable=False, server_default="summary"),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column("llm_model_id", sa.String(length=120), nullable=False, server_default="stub-llm"),
        sa.Column("llm_model_version", sa.String(length=64), nullable=False, server_default="1.0.0"),
        sa.Column("prompt_template_version", sa.String(length=64), nullable=False, server_default="summary-v1"),
        sa.Column("is_ai_interpretation", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("review_status", sa.String(length=32), nullable=False, server_default="pending_review"),
        sa.Column(
            "reviewed_by_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_meeting_summaries_org_meeting", "meeting_summaries", ["organisation_id", "meeting_id"])

    op.create_table(
        "decisions",
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
            "summary_id",
            sa.String(length=36),
            sa.ForeignKey("meeting_summaries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("decision_text", sa.Text(), nullable=False),
        sa.Column("is_ai_interpretation", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_decisions_org_meeting", "decisions", ["organisation_id", "meeting_id"])

    op.create_table(
        "action_items",
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
            "summary_id",
            sa.String(length=36),
            sa.ForeignKey("meeting_summaries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("action_text", sa.Text(), nullable=False),
        sa.Column("owner_hint", sa.String(length=255), nullable=True),
        sa.Column("due_hint", sa.String(length=64), nullable=True),
        sa.Column("is_ai_interpretation", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_action_items_org_meeting", "action_items", ["organisation_id", "meeting_id"])

    op.create_table(
        "ai_questions",
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
            nullable=True,
        ),
        sa.Column(
            "asked_by_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ai_questions_org_meeting", "ai_questions", ["organisation_id", "meeting_id"])

    op.create_table(
        "ai_answers",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "organisation_id",
            sa.String(length=36),
            sa.ForeignKey("organisations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "question_id",
            sa.String(length=36),
            sa.ForeignKey("ai_questions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("answer_text", sa.Text(), nullable=False),
        sa.Column("abstained", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_ai_interpretation", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("llm_model_id", sa.String(length=120), nullable=False, server_default="stub-llm"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ai_answers_org_question", "ai_answers", ["organisation_id", "question_id"])

    op.create_table(
        "evidence_links",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "organisation_id",
            sa.String(length=36),
            sa.ForeignKey("organisations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "summary_id",
            sa.String(length=36),
            sa.ForeignKey("meeting_summaries.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "answer_id",
            sa.String(length=36),
            sa.ForeignKey("ai_answers.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "decision_id",
            sa.String(length=36),
            sa.ForeignKey("decisions.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "action_item_id",
            sa.String(length=36),
            sa.ForeignKey("action_items.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "transcript_id",
            sa.String(length=36),
            sa.ForeignKey("transcripts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "segment_id",
            sa.String(length=36),
            sa.ForeignKey("transcript_segments.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=False),
        sa.Column("evidence_kind", sa.String(length=32), nullable=False, server_default="quote"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_evidence_links_org_summary", "evidence_links", ["organisation_id", "summary_id"])

    op.create_table(
        "ai_job_logs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "organisation_id",
            sa.String(length=36),
            sa.ForeignKey("organisations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "background_job_id",
            sa.String(length=36),
            sa.ForeignKey("background_jobs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("job_kind", sa.String(length=32), nullable=False),
        sa.Column("llm_model_id", sa.String(length=120), nullable=False),
        sa.Column("prompt_template_version", sa.String(length=64), nullable=False),
        sa.Column("retrieved_segment_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("permission_filter_applied", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("injection_attempts_detected", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ai_job_logs_org_job", "ai_job_logs", ["organisation_id", "background_job_id"])

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for stmt in get_phase7_postgres_rls_upgrade_sql():
            op.execute(stmt)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for stmt in get_phase7_postgres_rls_downgrade_sql():
            op.execute(stmt)

    op.drop_table("ai_job_logs")
    op.drop_table("evidence_links")
    op.drop_table("ai_answers")
    op.drop_table("ai_questions")
    op.drop_table("action_items")
    op.drop_table("decisions")
    op.drop_table("meeting_summaries")
