"""Document Studio router: ingest, DOCX/PDF/TXT export generation, template management."""

from __future__ import annotations

import hashlib
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Header, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import TenantAccessContext, require_permission
from app.core.config import get_settings
from app.core.db import get_db, tenant_db_context
from app.core.errors import NexusAPIError
from app.models.documents import (
    Document,
    DocumentExport,
    DocumentShare,
    DocumentTemplate,
    DocumentVersion,
)
from app.models.foundation import utcnow
from app.models.meetings_media import MediaAsset
from app.models.transcription import Transcript, TranscriptSegment, TranscriptSpeaker
from app.services.audit import record_audit_event
from app.services.document_ingest import ALLOWED_DOCUMENT_MIME_TYPES, ingest_document_bytes
from app.services.document_renderer import (
    render_transcript_docx,
    render_transcript_pdf,
    render_transcript_txt,
)
from app.services.storage_media import get_private_storage

router = APIRouter(prefix="/documents", tags=["documents"])
transcript_ingest_router = APIRouter(tags=["documents"])

ALLOWED_EXPORT_FORMATS: frozenset[str] = frozenset({"docx", "pdf", "txt"})


class IngestDocumentBody(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    document_type: str = Field(default="ingested", max_length=32)
    mime_type: str = Field(min_length=3, max_length=100)
    content_base64: str = Field(min_length=1)
    file_name: str = Field(min_length=1, max_length=255)


class ExportDocumentBody(BaseModel):
    export_format: str = Field(min_length=3, max_length=8)
    template_id: Optional[str] = Field(default=None, max_length=36)


class TemplateBody(BaseModel):
    template_name: str = Field(min_length=1, max_length=120)
    template_type: str = Field(default="transcript", max_length=32)
    organisation_logo: Optional[str] = Field(default=None, max_length=500000)
    brand_primary_color: str = Field(default="#1F3A5F", max_length=16)
    brand_secondary_color: str = Field(default="#5A7C9F", max_length=16)
    header_text: Optional[str] = Field(default=None, max_length=255)
    footer_text: Optional[str] = Field(default=None, max_length=255)
    include_page_numbers: bool = Field(default=True)
    confidentiality_label: str = Field(default="Confidential", max_length=64)


def _load_transcript_segments(
    db: Session, transcript_id: str
) -> tuple[list[TranscriptSegment], dict[str, TranscriptSpeaker]]:
    segments = list(
        db.scalars(
            select(TranscriptSegment)
            .where(TranscriptSegment.transcript_id == transcript_id)
            .order_by(TranscriptSegment.sequence_number.asc())
        ).all()
    )
    speakers = {
        s.id: s
        for s in db.scalars(
            select(TranscriptSpeaker).where(
                TranscriptSpeaker.transcript_id == transcript_id
            )
        ).all()
    }
    return segments, speakers


@transcript_ingest_router.post(
    "/transcripts/{transcript_id}/documents",
    status_code=status.HTTP_201_CREATED,
)
def create_document_from_transcript(
    transcript_id: str,
    ctx: TenantAccessContext = Depends(require_permission("transcript.export")),
    db: Session = Depends(get_db),
) -> dict:
    """Creates a versioned document record with retained source linkage to the transcript."""
    with tenant_db_context(
        db, organisation_id=ctx.organisation.id, user_id=ctx.user.id
    ):
        transcript = db.scalars(
            select(Transcript).where(Transcript.id == transcript_id)
        ).first()
        if transcript is None:
            raise NexusAPIError(
                status_code=404,
                code="transcript_not_found",
                message="Transcript not found in the active organisation.",
            )

        document = Document(
            organisation_id=ctx.organisation.id,
            document_type="transcript",
            title=f"Transcript Document {transcript.meeting_id[:8]}",
            uploaded_by_user_id=ctx.user.id,
            source_transcript_id=transcript.id,
            source_media_asset_id=transcript.media_asset_id,
            status="draft",
        )
        db.add(document)
        db.flush()

        version = DocumentVersion(
            organisation_id=ctx.organisation.id,
            document_id=document.id,
            version_number=1,
        )
        db.add(version)
        db.flush()

        record_audit_event(
            db,
            organisation_id=ctx.organisation.id,
            actor_user_id=ctx.user.id,
            action="document.create_from_transcript",
            resource_type="document",
            resource_id=document.id,
            result="succeeded",
            metadata={
                "transcript_id": transcript.id,
                "version_number": version.version_number,
            },
        )
        db.commit()
        db.refresh(document)
        db.refresh(version)

        return {
            "document_id": document.id,
            "document_version_id": version.id,
            "version_number": version.version_number,
            "document_type": document.document_type,
            "source_transcript_id": document.source_transcript_id,
            "status": document.status,
        }


@router.post("/ingest", status_code=status.HTTP_202_ACCEPTED)
def ingest_document(
    payload: IngestDocumentBody,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    ctx: TenantAccessContext = Depends(require_permission("document.share")),
    db: Session = Depends(get_db),
) -> dict:
    """
    Ingests DOCX/PDF/TXT uploads:
    validates MIME allowlist + size, extracts text with paragraph/heading/table preservation,
    detects scanned PDF pages and routes them through the OCR warning path,
    and treats uploads strictly as untrusted data (no macro/script/link execution).
    """
    import base64

    try:
        payload_bytes = base64.b64decode(payload.content_base64, validate=True)
    except Exception as exc:
        raise NexusAPIError(
            status_code=400,
            code="invalid_document_encoding",
            message="Document payload must be valid base64.",
        ) from exc

    ingest = ingest_document_bytes(
        file_name=payload.file_name,
        mime_type=payload.mime_type,
        payload=payload_bytes,
    )

    settings = get_settings()
    storage = get_private_storage()
    declared_sha256 = hashlib.sha256(payload_bytes).hexdigest()

    with tenant_db_context(
        db, organisation_id=ctx.organisation.id, user_id=ctx.user.id
    ):
        document = Document(
            organisation_id=ctx.organisation.id,
            document_type=payload.document_type,
            title=payload.title.strip(),
            uploaded_by_user_id=ctx.user.id,
            status="ingested",
        )
        db.add(document)
        db.flush()

        source_key = (
            f"tenants/{ctx.organisation.id}/documents/{document.id}"
            f"/source/{payload.file_name}"
        )
        storage.put_bytes(
            organisation_id=ctx.organisation.id,
            object_key=source_key,
            data=payload_bytes,
        )

        version = DocumentVersion(
            organisation_id=ctx.organisation.id,
            document_id=document.id,
            version_number=1,
            source_object_key=source_key,
            source_file_name=payload.file_name,
            source_mime_type=payload.mime_type,
            source_size_bytes=len(payload_bytes),
            source_sha256_checksum=declared_sha256,
            extracted_text=ingest.extracted_text,
            ocr_applied=ingest.ocr_applied,
            ocr_pages_detected=ingest.ocr_pages_detected,
        )
        db.add(version)
        db.flush()

        record_audit_event(
            db,
            organisation_id=ctx.organisation.id,
            actor_user_id=ctx.user.id,
            action="document.ingest",
            resource_type="document",
            resource_id=document.id,
            result="succeeded",
            metadata={
                "mime_type": payload.mime_type,
                "size_bytes": len(payload_bytes),
                "sha256_checksum": declared_sha256,
                "ocr_applied": ingest.ocr_applied,
                "ocr_pages_detected": ingest.ocr_pages_detected,
                "paragraph_count": ingest.paragraph_count,
            },
        )
        db.commit()
        db.refresh(document)
        db.refresh(version)

        return {
            "document_id": document.id,
            "document_version_id": version.id,
            "status": document.status,
            "extracted_text_preview": ingest.extracted_text[:500],
            "paragraph_count": ingest.paragraph_count,
            "ocr_applied": ingest.ocr_applied,
            "ocr_pages_detected": ingest.ocr_pages_detected,
            "ocr_review_warning": (
                "Scanned pages detected: extracted text may be incomplete and requires human review before use."
                if ingest.ocr_applied
                else None
            ),
        }


@router.post("/{document_id}/export")
def export_document(
    document_id: str,
    payload: ExportDocumentBody,
    ctx: TenantAccessContext = Depends(require_permission("transcript.export")),
    db: Session = Depends(get_db),
) -> dict:
    """
    Generates a branded DOCX/PDF/TXT export for a document versioned with source linkage.
    Template supplies logo, brand colours, headers/footers, page numbering, and
    confidentiality labels. Output objects are stored privately with checksums.
    """
    fmt = payload.export_format.lower()
    if fmt not in ALLOWED_EXPORT_FORMATS:
        raise NexusAPIError(
            status_code=415,
            code="unsupported_export_format",
            message=f"Export format must be one of {sorted(ALLOWED_EXPORT_FORMATS)}.",
        )

    storage = get_private_storage()
    with tenant_db_context(
        db, organisation_id=ctx.organisation.id, user_id=ctx.user.id
    ):
        document = db.scalars(
            select(Document).where(Document.id == document_id)
        ).first()
        if document is None:
            raise NexusAPIError(
                status_code=404,
                code="document_not_found",
                message="Document not found in the active organisation.",
            )

        version = db.scalars(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document.id)
            .order_by(DocumentVersion.version_number.desc())
        ).first()
        if version is None:
            raise NexusAPIError(
                status_code=404,
                code="document_version_not_found",
                message="Document version not found.",
            )

        template = None
        if payload.template_id:
            template = db.scalars(
                select(DocumentTemplate).where(
                    DocumentTemplate.id == payload.template_id
                )
            ).first()
            if template is None or template.organisation_id != ctx.organisation.id:
                raise NexusAPIError(
                    status_code=404,
                    code="template_not_found",
                    message="Document template not found in the active organisation.",
                )

        segments: list[TranscriptSegment] = []
        speakers: dict[str, TranscriptSpeaker] = {}
        if document.source_transcript_id:
            segments, speakers = _load_transcript_segments(db, document.source_transcript_id)

        document_meta = {
            "source_metadata": (
                f"Transcript {document.source_transcript_id}"
                if document.source_transcript_id
                else version.source_file_name or "Uploaded document"
            )
        }

        render_kwargs = {
            "title": document.title,
            "segments": segments,
            "speakers": speakers,
            "template": template,
            "document_meta": document_meta,
        }
        if fmt == "docx":
            rendered = render_transcript_docx(**render_kwargs)
        elif fmt == "pdf":
            rendered = render_transcript_pdf(**render_kwargs)
        else:
            rendered = render_transcript_txt(**render_kwargs)

        object_key = (
            f"tenants/{ctx.organisation.id}/documents/{document.id}"
            f"/exports/{version.version_number}/{rendered.file_name}"
        )
        storage.put_bytes(
            organisation_id=ctx.organisation.id,
            object_key=object_key,
            data=rendered.content,
        )

        sha256_checksum = hashlib.sha256(rendered.content).hexdigest()
        export_record = DocumentExport(
            organisation_id=ctx.organisation.id,
            document_id=document.id,
            document_version_id=version.id,
            template_id=template.id if template else None,
            export_format=fmt,
            object_key=object_key,
            size_bytes=len(rendered.content),
            sha256_checksum=sha256_checksum,
            created_by_user_id=ctx.user.id,
        )
        db.add(export_record)
        db.flush()

        record_audit_event(
            db,
            organisation_id=ctx.organisation.id,
            actor_user_id=ctx.user.id,
            action="document.export",
            resource_type="document_export",
            resource_id=export_record.id,
            result="succeeded",
            metadata={
                "document_id": document.id,
                "format": fmt,
                "size_bytes": len(rendered.content),
                "template_id": template.id if template else None,
            },
        )
        db.commit()
        db.refresh(export_record)

        return {
            "export_id": export_record.id,
            "document_id": document.id,
            "format": fmt,
            "object_key": object_key,
            "size_bytes": len(rendered.content),
            "sha256_checksum": sha256_checksum,
            "template_id": template.id if template else None,
            "page_count": rendered.page_count,
        }


@router.get("/{document_id}/exports")
def list_document_exports(
    document_id: str,
    ctx: TenantAccessContext = Depends(require_permission("meeting.view")),
    db: Session = Depends(get_db),
) -> dict:
    with tenant_db_context(
        db, organisation_id=ctx.organisation.id, user_id=ctx.user.id
    ):
        document = db.scalars(
            select(Document).where(Document.id == document_id)
        ).first()
        if document is None:
            raise NexusAPIError(
                status_code=404,
                code="document_not_found",
                message="Document not found in the active organisation.",
            )
        exports = list(
            db.scalars(
                select(DocumentExport).where(
                    DocumentExport.document_id == document.id
                )
            ).all()
        )
        return {
            "document_id": document.id,
            "items": [
                {
                    "id": e.id,
                    "export_format": e.export_format,
                    "size_bytes": e.size_bytes,
                    "sha256_checksum": e.sha256_checksum,
                    "template_id": e.template_id,
                    "created_at": e.created_at.isoformat(),
                }
                for e in exports
            ],
        }


@router.post("/templates", status_code=status.HTTP_201_CREATED)
def create_template(
    payload: TemplateBody,
    ctx: TenantAccessContext = Depends(require_permission("tenant.admin")),
    db: Session = Depends(get_db),
) -> dict:
    with tenant_db_context(
        db, organisation_id=ctx.organisation.id, user_id=ctx.user.id
    ):
        existing = db.scalars(
            select(DocumentTemplate).where(
                DocumentTemplate.organisation_id == ctx.organisation.id,
                DocumentTemplate.template_name == payload.template_name,
            )
        ).first()
        if existing is not None:
            raise NexusAPIError(
                status_code=409,
                code="template_name_exists",
                message=f"Template '{payload.template_name}' already exists.",
            )

        template = DocumentTemplate(
            organisation_id=ctx.organisation.id,
            template_name=payload.template_name.strip(),
            template_type=payload.template_type,
            organisation_logo=payload.organisation_logo,
            brand_primary_color=payload.brand_primary_color,
            brand_secondary_color=payload.brand_secondary_color,
            header_text=payload.header_text,
            footer_text=payload.footer_text,
            include_page_numbers=payload.include_page_numbers,
            confidentiality_label=payload.confidentiality_label.strip(),
            created_by_user_id=ctx.user.id,
        )
        db.add(template)
        db.flush()

        record_audit_event(
            db,
            organisation_id=ctx.organisation.id,
            actor_user_id=ctx.user.id,
            action="document.template.create",
            resource_type="document_template",
            resource_id=template.id,
            result="succeeded",
            metadata={"template_name": template.template_name},
        )
        db.commit()
        db.refresh(template)

        return {
            "template_id": template.id,
            "template_name": template.template_name,
            "template_type": template.template_type,
            "brand_primary_color": template.brand_primary_color,
            "confidentiality_label": template.confidentiality_label,
        }


@router.get("/templates")
def list_templates(
    ctx: TenantAccessContext = Depends(require_permission("meeting.view")),
    db: Session = Depends(get_db),
) -> dict:
    with tenant_db_context(
        db, organisation_id=ctx.organisation.id, user_id=ctx.user.id
    ):
        templates = list(
            db.scalars(
                select(DocumentTemplate).order_by(
                    DocumentTemplate.created_at.asc()
                )
            ).all()
        )
        return {
            "items": [
                {
                    "id": t.id,
                    "template_name": t.template_name,
                    "template_type": t.template_type,
                    "brand_primary_color": t.brand_primary_color,
                    "header_text": t.header_text,
                    "footer_text": t.footer_text,
                    "confidentiality_label": t.confidentiality_label,
                }
                for t in templates
            ]
        }
