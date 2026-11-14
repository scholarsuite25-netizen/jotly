"""Phase 4 Document Studio: documents, versions, templates, exports, shares + PostgreSQL RLS.

Revision ID: 0004_phase4_document_studio
Revises: 0003_phase3_transcription
Create Date: 2026-11-13
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0004_phase4_document_studio"
down_revision: Union[str, None] = "0003_phase3_transcription"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PHASE4_TENANT_TABLES: tuple[str, ...] = (
    "documents",
    "document_versions",
    "document_templates",
    "document_exports",
    "document_shares",
)


def get_phase4_postgres_rls_upgrade_sql() -> list[str]:
    statements: list[str] = []
    for table in PHASE4_TENANT_TABLES:
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


def get_phase4_postgres_rls_downgrade_sql() -> list[str]:
    statements: list[str] = []
    for table in PHASE4_TENANT_TABLES:
        statements.extend(
            [
                f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table};",
                f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;",
            ]
        )
    return statements


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "organisation_id",
            sa.String(length=36),
            sa.ForeignKey("organisations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("document_type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column(
            "uploaded_by_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "source_media_asset_id",
            sa.String(length=36),
            sa.ForeignKey("media_assets.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "source_transcript_id",
            sa.String(length=36),
            sa.ForeignKey("transcripts.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_documents_org_type", "documents", ["organisation_id", "document_type"])

    op.create_table(
        "document_versions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "organisation_id",
            sa.String(length=36),
            sa.ForeignKey("organisations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            sa.String(length=36),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("source_object_key", sa.String(length=512), nullable=True),
        sa.Column("source_file_name", sa.String(length=255), nullable=True),
        sa.Column("source_mime_type", sa.String(length=100), nullable=True),
        sa.Column("source_size_bytes", sa.Integer(), nullable=True),
        sa.Column("source_sha256_checksum", sa.String(length=64), nullable=True),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("ocr_applied", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("ocr_pages_detected", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_document_versions_org_doc",
        "document_versions",
        ["organisation_id", "document_id", "version_number"],
        unique=True,
    )

    op.create_table(
        "document_templates",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "organisation_id",
            sa.String(length=36),
            sa.ForeignKey("organisations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("template_name", sa.String(length=120), nullable=False),
        sa.Column("template_type", sa.String(length=32), nullable=False, server_default="transcript"),
        sa.Column("organisation_logo", sa.Text(), nullable=True),
        sa.Column("brand_primary_color", sa.String(length=16), nullable=False, server_default="#1F3A5F"),
        sa.Column("brand_secondary_color", sa.String(length=16), nullable=False, server_default="#5A7C9F"),
        sa.Column("header_text", sa.String(length=255), nullable=True),
        sa.Column("footer_text", sa.String(length=255), nullable=True),
        sa.Column("include_page_numbers", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("confidentiality_label", sa.String(length=64), nullable=False, server_default="Confidential"),
        sa.Column(
            "created_by_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_document_templates_org_name",
        "document_templates",
        ["organisation_id", "template_name"],
        unique=True,
    )

    op.create_table(
        "document_exports",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "organisation_id",
            sa.String(length=36),
            sa.ForeignKey("organisations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            sa.String(length=36),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_version_id",
            sa.String(length=36),
            sa.ForeignKey("document_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "template_id",
            sa.String(length=36),
            sa.ForeignKey("document_templates.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("export_format", sa.String(length=16), nullable=False),
        sa.Column("object_key", sa.String(length=512), nullable=False, unique=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256_checksum", sa.String(length=64), nullable=False),
        sa.Column(
            "created_by_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_document_exports_org_doc", "document_exports", ["organisation_id", "document_id"])

    op.create_table(
        "document_shares",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "organisation_id",
            sa.String(length=36),
            sa.ForeignKey("organisations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            sa.String(length=36),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "shared_with_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("permission", sa.String(length=32), nullable=False, server_default="view"),
        sa.Column(
            "granted_by_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_document_shares_org_doc", "document_shares", ["organisation_id", "document_id"])

    from alembic import context as _ctx
    if _ctx.is_offline_mode():
        for stmt in get_phase4_postgres_rls_upgrade_sql():
            op.execute(stmt)
    else:
        bind = op.get_bind()
        if bind.dialect.name == "postgresql":
            for stmt in get_phase4_postgres_rls_upgrade_sql():
                op.execute(stmt)


def downgrade() -> None:
    from alembic import context as _ctx
    if _ctx.is_offline_mode():
        for stmt in get_phase4_postgres_rls_downgrade_sql():
            op.execute(stmt)
    else:
        bind = op.get_bind()
        if bind.dialect.name == "postgresql":
            for stmt in get_phase4_postgres_rls_downgrade_sql():
                op.execute(stmt)

    op.drop_table("document_shares")
    op.drop_table("document_exports")
    op.drop_table("document_templates")
    op.drop_table("document_versions")
    op.drop_table("documents")
