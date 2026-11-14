"""Phase 1 Secure Foundation schema and PostgreSQL Row-Level Security (RLS) baseline.

Revision ID: 0001_phase1_foundation
Revises: None
Create Date: 2026-11-13
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0001_phase1_foundation"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TENANT_ISOLATED_TABLES: tuple[str, ...] = (
    "workspaces",
    "departments",
    "roles",
    "user_roles",
    "invitations",
    "sessions",
    "audit_logs",
    "background_jobs",
)


def get_postgres_rls_upgrade_sql() -> list[str]:
    """Generate PostgreSQL Row-Level Security (RLS) DDL statements for all tenant tables."""
    statements: list[str] = [
        "ALTER TABLE organisations ENABLE ROW LEVEL SECURITY;",
        "ALTER TABLE organisations FORCE ROW LEVEL SECURITY;",
        (
            "CREATE POLICY tenant_isolation_organisations ON organisations "
            "USING (id::text = NULLIF(current_setting('app.current_organisation_id', true), '')) "
            "WITH CHECK (id::text = NULLIF(current_setting('app.current_organisation_id', true), ''));"
        ),
    ]
    for table in TENANT_ISOLATED_TABLES:
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


def get_postgres_rls_downgrade_sql() -> list[str]:
    """Generate reversible RLS policy drop statements."""
    statements: list[str] = [
        "DROP POLICY IF EXISTS tenant_isolation_organisations ON organisations;",
        "ALTER TABLE organisations DISABLE ROW LEVEL SECURITY;",
    ]
    for table in TENANT_ISOLATED_TABLES:
        statements.extend(
            [
                f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table};",
                f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;",
            ]
        )
    return statements


def upgrade() -> None:
    op.create_table(
        "organisations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("slug", sa.String(length=120), nullable=False, unique=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("retention_days", sa.Integer(), nullable=False, server_default="365"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("supabase_sub", sa.String(length=128), nullable=False, unique=True),
        sa.Column("email", sa.String(length=320), nullable=False, unique=True),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("mfa_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "permissions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("code", sa.String(length=100), nullable=False, unique=True),
        sa.Column("description", sa.String(length=255), nullable=False),
    )

    op.create_table(
        "workspaces",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "organisation_id",
            sa.String(length=36),
            sa.ForeignKey("organisations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_workspaces_org_id", "workspaces", ["organisation_id", "id"])

    op.create_table(
        "departments",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "organisation_id",
            sa.String(length=36),
            sa.ForeignKey("organisations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_departments_org_id", "departments", ["organisation_id", "id"])

    op.create_table(
        "roles",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "organisation_id",
            sa.String(length=36),
            sa.ForeignKey("organisations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_roles_org_code", "roles", ["organisation_id", "code"], unique=True)

    op.create_table(
        "role_permissions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "role_id",
            sa.String(length=36),
            sa.ForeignKey("roles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "permission_id",
            sa.String(length=36),
            sa.ForeignKey("permissions.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_role_permissions_unique", "role_permissions", ["role_id", "permission_id"], unique=True
    )

    op.create_table(
        "user_roles",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "organisation_id",
            sa.String(length=36),
            sa.ForeignKey("organisations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "role_id",
            sa.String(length=36),
            sa.ForeignKey("roles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_user_roles_org_user", "user_roles", ["organisation_id", "user_id"])

    op.create_table(
        "invitations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "organisation_id",
            sa.String(length=36),
            sa.ForeignKey("organisations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role_code", sa.String(length=80), nullable=False),
        sa.Column(
            "invited_by_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("email_provider", sa.String(length=32), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_invitations_org_email", "invitations", ["organisation_id", "email"])

    op.create_table(
        "sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "organisation_id",
            sa.String(length=36),
            sa.ForeignKey("organisations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("token_jti", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_sessions_org_user", "sessions", ["organisation_id", "user_id"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "organisation_id",
            sa.String(length=36),
            sa.ForeignKey("organisations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "actor_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("action", sa.String(length=120), nullable=False),
        sa.Column("resource_type", sa.String(length=80), nullable=False),
        sa.Column("resource_id", sa.String(length=64), nullable=False),
        sa.Column("result", sa.String(length=32), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("previous_hash", sa.String(length=64), nullable=False),
        sa.Column("entry_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_logs_org_created", "audit_logs", ["organisation_id", "created_at"])

    op.create_table(
        "background_jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "organisation_id",
            sa.String(length=36),
            sa.ForeignKey("organisations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("job_type", sa.String(length=80), nullable=False),
        sa.Column("source_entity_type", sa.String(length=80), nullable=False),
        sa.Column("source_entity_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("worker_version", sa.String(length=64), nullable=False, server_default="0.1.0"),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_background_jobs_org_idempotency",
        "background_jobs",
        ["organisation_id", "idempotency_key"],
        unique=True,
    )

    from alembic import context as _ctx
    if _ctx.is_offline_mode():
        for stmt in get_postgres_rls_upgrade_sql():
            op.execute(stmt)
    else:
        bind = op.get_bind()
        if bind.dialect.name == "postgresql":
            for stmt in get_postgres_rls_upgrade_sql():
                op.execute(stmt)


def downgrade() -> None:
    from alembic import context as _ctx
    if _ctx.is_offline_mode():
        for stmt in get_postgres_rls_downgrade_sql():
            op.execute(stmt)
    else:
        bind = op.get_bind()
        if bind.dialect.name == "postgresql":
            for stmt in get_postgres_rls_downgrade_sql():
                op.execute(stmt)

    op.drop_table("background_jobs")
    op.drop_table("audit_logs")
    op.drop_table("sessions")
    op.drop_table("invitations")
    op.drop_table("user_roles")
    op.drop_table("role_permissions")
    op.drop_table("roles")
    op.drop_table("departments")
    op.drop_table("workspaces")
    op.drop_table("permissions")
    op.drop_table("users")
    op.drop_table("organisations")
