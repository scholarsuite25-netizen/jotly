from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TenantScopedMixin
from app.models.foundation import new_uuid, utcnow


class Document(Base, TenantScopedMixin):
    __tablename__ = "documents"
    __table_args__ = (Index("ix_documents_org_type", "organisation_id", "document_type"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    document_type: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    uploaded_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    source_media_asset_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("media_assets.id", ondelete="RESTRICT"),
        nullable=True,
    )
    source_transcript_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("transcripts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class DocumentVersion(Base, TenantScopedMixin):
    __tablename__ = "document_versions"
    __table_args__ = (
        Index(
            "ix_document_versions_org_doc",
            "organisation_id",
            "document_id",
            "version_number",
            unique=True,
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source_object_key: Mapped[Optional[str]] = mapped_column(
        String(512), nullable=True
    )
    source_file_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source_mime_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    source_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source_sha256_checksum: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    extracted_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ocr_applied: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ocr_pages_detected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class DocumentTemplate(Base, TenantScopedMixin):
    __tablename__ = "document_templates"
    __table_args__ = (
        Index(
            "ix_document_templates_org_name",
            "organisation_id",
            "template_name",
            unique=True,
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    template_name: Mapped[str] = mapped_column(String(120), nullable=False)
    template_type: Mapped[str] = mapped_column(String(32), nullable=False, default="transcript")
    organisation_logo: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    brand_primary_color: Mapped[str] = mapped_column(
        String(16), nullable=False, default="#1F3A5F"
    )
    brand_secondary_color: Mapped[str] = mapped_column(
        String(16), nullable=False, default="#5A7C9F"
    )
    header_text: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    footer_text: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    include_page_numbers: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    confidentiality_label: Mapped[str] = mapped_column(
        String(64), nullable=False, default="Confidential"
    )
    created_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class DocumentExport(Base, TenantScopedMixin):
    __tablename__ = "document_exports"
    __table_args__ = (
        Index("ix_document_exports_org_doc", "organisation_id", "document_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    document_version_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("document_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    template_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("document_templates.id", ondelete="RESTRICT"),
        nullable=True,
    )
    export_format: Mapped[str] = mapped_column(String(16), nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class DocumentShare(Base, TenantScopedMixin):
    __tablename__ = "document_shares"
    __table_args__ = (
        Index("ix_document_shares_org_doc", "organisation_id", "document_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    shared_with_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    permission: Mapped[str] = mapped_column(String(32), nullable=False, default="view")
    granted_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
