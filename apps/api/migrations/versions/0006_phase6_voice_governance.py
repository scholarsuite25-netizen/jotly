"""Phase 6 Voice Governance: consents, profiles, samples, permissions, jobs, audit + RLS.

Revision ID: 0006_phase6_voice_governance
Revises: 0005_phase5_voice_studio
Create Date: 2026-11-14
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0006_phase6_voice_governance"
down_revision: Union[str, None] = "0005_phase5_voice_studio"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PHASE6_TENANT_TABLES: tuple[str, ...] = (
    "voice_consents",
    "voice_profiles",
    "voice_samples",
    "voice_permissions",
    "voice_jobs",
    "voice_audit_events",
)


def get_phase6_postgres_rls_upgrade_sql() -> list[str]:
    statements: list[str] = []
    for table in PHASE6_TENANT_TABLES:
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


def get_phase6_postgres_rls_downgrade_sql() -> list[str]:
    statements: list[str] = []
    for table in PHASE6_TENANT_TABLES:
        statements.extend(
            [
                f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table};",
                f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;",
            ]
        )
    return statements


def upgrade() -> None:
    op.create_table(
        "voice_consents",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "organisation_id",
            sa.String(length=36),
            sa.ForeignKey("organisations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "owner_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("consent_text_version", sa.String(length=32), nullable=False),
        sa.Column("permitted_uses", sa.Text(), nullable=False, server_default="internal_synthesis"),
        sa.Column("jurisdiction", sa.String(length=64), nullable=False, server_default="NG"),
        sa.Column("verification_method", sa.String(length=64), nullable=False, server_default="challenge_live_sample"),
        sa.Column("verification_reference", sa.String(length=128), nullable=False),
        sa.Column("verification_passed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_voice_consents_org_owner", "voice_consents", ["organisation_id", "owner_user_id"])

    op.create_table(
        "voice_profiles",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "organisation_id",
            sa.String(length=36),
            sa.ForeignKey("organisations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "owner_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "consent_record_id",
            sa.String(length=36),
            sa.ForeignKey("voice_consents.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("model_id", sa.String(length=120), nullable=False, server_default="stub-openvoice-v2"),
        sa.Column("model_version", sa.String(length=64), nullable=False, server_default="1.0.0"),
        sa.Column("public_gallery", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_voice_profiles_org_owner", "voice_profiles", ["organisation_id", "owner_user_id"])

    op.create_table(
        "voice_samples",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "organisation_id",
            sa.String(length=36),
            sa.ForeignKey("organisations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "voice_profile_id",
            sa.String(length=36),
            sa.ForeignKey("voice_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("object_key", sa.String(length=512), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("sha256_checksum", sa.String(length=64), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False, server_default="challenge_live_sample"),
        sa.Column("consent_scope", sa.String(length=64), nullable=False, server_default="internal_synthesis"),
        sa.Column("retention_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_voice_samples_org_profile", "voice_samples", ["organisation_id", "voice_profile_id"])

    op.create_table(
        "voice_permissions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "organisation_id",
            sa.String(length=36),
            sa.ForeignKey("organisations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "voice_profile_id",
            sa.String(length=36),
            sa.ForeignKey("voice_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "grantee_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("allowed_use", sa.String(length=64), nullable=False),
        sa.Column(
            "granted_by_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_voice_permissions_org_profile_grantee",
        "voice_permissions",
        ["organisation_id", "voice_profile_id", "grantee_user_id"],
        unique=True,
    )

    op.create_table(
        "voice_jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "organisation_id",
            sa.String(length=36),
            sa.ForeignKey("organisations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "voice_profile_id",
            sa.String(length=36),
            sa.ForeignKey("voice_profiles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "background_job_id",
            sa.String(length=36),
            sa.ForeignKey("background_jobs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "requester_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("text_sha256", sa.String(length=64), nullable=False),
        sa.Column("output_object_key", sa.String(length=512), nullable=True),
        sa.Column("disclosure_flag", sa.String(length=255), nullable=False, server_default="AI-generated voice clone"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_voice_jobs_org_profile", "voice_jobs", ["organisation_id", "voice_profile_id"])

    op.create_table(
        "voice_audit_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "organisation_id",
            sa.String(length=36),
            sa.ForeignKey("organisations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "voice_profile_id",
            sa.String(length=36),
            sa.ForeignKey("voice_profiles.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("voice_job_id", sa.String(length=36), nullable=True),
        sa.Column(
            "actor_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("result", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("permitted_ip_metadata", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_voice_audit_org_profile", "voice_audit_events", ["organisation_id", "voice_profile_id"])

    from alembic import context as _ctx
    if _ctx.is_offline_mode():
        for stmt in get_phase6_postgres_rls_upgrade_sql():
            op.execute(stmt)
    else:
        bind = op.get_bind()
        if bind.dialect.name == "postgresql":
            for stmt in get_phase6_postgres_rls_upgrade_sql():
                op.execute(stmt)


def downgrade() -> None:
    from alembic import context as _ctx
    if _ctx.is_offline_mode():
        for stmt in get_phase6_postgres_rls_downgrade_sql():
            op.execute(stmt)
    else:
        bind = op.get_bind()
        if bind.dialect.name == "postgresql":
            for stmt in get_phase6_postgres_rls_downgrade_sql():
                op.execute(stmt)

    op.drop_table("voice_audit_events")
    op.drop_table("voice_jobs")
    op.drop_table("voice_permissions")
    op.drop_table("voice_samples")
    op.drop_table("voice_profiles")
    op.drop_table("voice_consents")
