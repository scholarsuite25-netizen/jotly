"""Voice Studio router: speech projects, pronunciation dictionary, audio playback."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import TenantAccessContext, require_permission
from app.core.config import get_settings
from app.core.db import get_db, tenant_db_context
from app.core.errors import NexusAPIError
from app.models.documents import Document, DocumentVersion
from app.models.speech import (
    AudioAsset,
    AudioChapter,
    PronunciationEntry,
    SpeechChunk,
    SpeechProject,
)
from app.services.audit import record_audit_event
from app.services.storage_media import (
    create_signed_playback_url,
    get_private_storage,
    verify_signed_playback_signature,
)
from app.services.tts_adapter import (
    SUPPORTED_OUTPUT_FORMATS,
    SUPPORTED_SPEED_RANGE,
    SUPPORTED_TTS_LANGUAGES,
    StandardVoiceCatalogue,
    chunk_text_for_speech,
)
from app.workers.context import enqueue_tenant_job
from app.workers.speech_worker import run_speech_synthesis_worker

router = APIRouter(prefix="/speech-projects", tags=["voice-studio"])
audio_router = APIRouter(prefix="/audio", tags=["voice-studio"])


class CreateSpeechProjectBody(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    language_code: str = Field(default="en", max_length=16)
    voice_id: str = Field(min_length=1, max_length=64)
    speed_percent: int = Field(default=100, ge=SUPPORTED_SPEED_RANGE[0], le=SUPPORTED_SPEED_RANGE[1])
    output_format: str = Field(default="wav", max_length=8)
    text_content: str = Field(min_length=1, max_length=500000)
    add_chapters: bool = Field(default=True)
    source_document_id: Optional[str] = Field(default=None, max_length=36)


class PronunciationBody(BaseModel):
    word: str = Field(min_length=1, max_length=120)
    phonetic_hint: str = Field(min_length=1, max_length=255)
    language_code: str = Field(default="en", max_length=16)


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def create_speech_project(
    payload: CreateSpeechProjectBody,
    ctx: TenantAccessContext = Depends(require_permission("meeting.record")),
    db: Session = Depends(get_db),
) -> dict:
    """
    Creates a queued standard-voice speech project:
    validates language/voice/speed/output-format, requires reviewed text,
    chunks at paragraph/sentence boundaries, and queues idempotent synthesis.
    Voice cloning is NOT supported here (Phase 6 consent gate).
    """
    language = payload.language_code.lower()
    if language not in SUPPORTED_TTS_LANGUAGES:
        raise NexusAPIError(
            status_code=400,
            code="unsupported_language",
            message=f"Language '{payload.language_code}' is not in the supported TTS catalogue.",
        )
    if not StandardVoiceCatalogue.voice_exists(language, payload.voice_id):
        raise NexusAPIError(
            status_code=400,
            code="unknown_voice",
            message=f"Voice '{payload.voice_id}' is not available for language '{language}'.",
        )
    if payload.output_format.lower() not in SUPPORTED_OUTPUT_FORMATS:
        raise NexusAPIError(
            status_code=400,
            code="unsupported_output_format",
            message=f"Output format must be one of {sorted(SUPPORTED_OUTPUT_FORMATS)}.",
        )

    chunks = chunk_text_for_speech(payload.text_content)
    if not chunks:
        raise NexusAPIError(
            status_code=422,
            code="empty_text_content",
            message="Text content contains no synthesizable text.",
        )

    with tenant_db_context(
        db, organisation_id=ctx.organisation.id, user_id=ctx.user.id
    ):
        if payload.source_document_id:
            doc = db.scalars(
                select(Document).where(Document.id == payload.source_document_id)
            ).first()
            if doc is None:
                raise NexusAPIError(
                    status_code=404,
                    code="source_document_not_found",
                    message="Source document not found in the active organisation.",
                )

        existing = db.scalars(
            select(SpeechProject).where(
                SpeechProject.organisation_id == ctx.organisation.id,
                SpeechProject.title == payload.title.strip(),
                SpeechProject.language_code == language,
                SpeechProject.voice_id == payload.voice_id,
                SpeechProject.text_content == payload.text_content,
            )
        ).first()
        if existing is not None:
            asset = db.scalars(
                select(AudioAsset).where(
                    AudioAsset.speech_project_id == existing.id
                )
            ).first()
            return {
                "speech_project_id": existing.id,
                "status": existing.status,
                "chunk_count": existing.chunk_count,
                "audio_asset_id": asset.id if asset else None,
                "idempotent_replay": True,
            }

        project = SpeechProject(
            organisation_id=ctx.organisation.id,
            source_document_id=payload.source_document_id,
            title=payload.title.strip(),
            language_code=language,
            voice_id=payload.voice_id,
            speed_percent=payload.speed_percent,
            output_format=payload.output_format.lower(),
            text_content=payload.text_content,
            reviewed_by_user_id=ctx.user.id,
            status="queued",
            idempotency_key=f"speech:{ctx.organisation.id}:{hash((payload.title, language, payload.voice_id, payload.text_content))}",
            tts_model_id="stub-kokoro",
            chunk_count=len(chunks),
        )
        db.add(project)
        db.flush()

        for index, chunk_text in enumerate(chunks):
            db.add(
                SpeechChunk(
                    organisation_id=ctx.organisation.id,
                    speech_project_id=project.id,
                    chunk_index=index,
                    chunk_text=chunk_text,
                )
            )
        db.flush()

        bg_job = enqueue_tenant_job(
            db,
            organisation_id=ctx.organisation.id,
            actor_user_id=ctx.user.id,
            job_type="speech.synthesize",
            source_entity_type="speech_project",
            source_entity_id=project.id,
            idempotency_key=f"speech-synth:{project.id}",
        )

        record_audit_event(
            db,
            organisation_id=ctx.organisation.id,
            actor_user_id=ctx.user.id,
            action="speech.project.create",
            resource_type="speech_project",
            resource_id=project.id,
            result="succeeded",
            metadata={
                "language_code": language,
                "voice_id": payload.voice_id,
                "chunk_count": len(chunks),
                "standard_voice_only": True,
            },
        )
        db.commit()

    audio_asset = run_speech_synthesis_worker(
        db,
        background_job_id=bg_job.id,
        organisation_id=ctx.organisation.id,
        actor_user_id=ctx.user.id,
        language_code=language,
        voice_id=payload.voice_id,
        speed_percent=payload.speed_percent,
        output_format=payload.output_format.lower(),
        add_chapters=payload.add_chapters,
    )
    db.refresh(project)

    return {
        "speech_project_id": project.id,
        "job_id": bg_job.id,
        "audio_asset_id": audio_asset.id,
        "chunk_count": project.chunk_count,
        "duration_ms": audio_asset.duration_ms,
        "output_format": audio_asset.output_format,
        "synthetic_disclosure": audio_asset.synthetic_disclosure,
        "status": "completed",
        "idempotent_replay": False,
    }


@router.get("/{project_id}")
def get_speech_project(
    project_id: str,
    ctx: TenantAccessContext = Depends(require_permission("meeting.view")),
    db: Session = Depends(get_db),
) -> dict:
    with tenant_db_context(
        db, organisation_id=ctx.organisation.id, user_id=ctx.user.id
    ):
        project = db.scalars(
            select(SpeechProject).where(SpeechProject.id == project_id)
        ).first()
        if project is None:
            raise NexusAPIError(
                status_code=404,
                code="speech_project_not_found",
                message="Speech project not found in the active organisation.",
            )
        asset = db.scalars(
            select(AudioAsset).where(AudioAsset.speech_project_id == project.id)
        ).first()
        chapters = []
        if asset is not None:
            chapters = list(
                db.scalars(
                    select(AudioChapter)
                    .where(AudioChapter.audio_asset_id == asset.id)
                    .order_by(AudioChapter.chapter_index.asc())
                ).all()
            )
        return {
            "speech_project_id": project.id,
            "title": project.title,
            "language_code": project.language_code,
            "voice_id": project.voice_id,
            "speed_percent": project.speed_percent,
            "output_format": project.output_format,
            "status": project.status,
            "chunk_count": project.chunk_count,
            "tts_model_id": project.tts_model_id,
            "audio_asset": (
                {
                    "id": asset.id,
                    "duration_ms": asset.duration_ms,
                    "size_bytes": asset.size_bytes,
                    "sha256_checksum": asset.sha256_checksum,
                    "loudness_normalised": asset.loudness_normalised,
                    "synthetic_disclosure": asset.synthetic_disclosure,
                    "chapters": [
                        {
                            "chapter_index": ch.chapter_index,
                            "title": ch.title,
                            "start_ms": ch.start_ms,
                            "end_ms": ch.end_ms,
                        }
                        for ch in chapters
                    ],
                }
                if asset
                else None
            ),
        }


@audio_router.get("/{asset_id}/playback-url")
def get_audio_playback_url(
    asset_id: str,
    ctx: TenantAccessContext = Depends(require_permission("meeting.view")),
    db: Session = Depends(get_db),
) -> dict:
    with tenant_db_context(
        db, organisation_id=ctx.organisation.id, user_id=ctx.user.id
    ):
        asset = db.scalars(
            select(AudioAsset).where(AudioAsset.id == asset_id)
        ).first()
        if asset is None:
            raise NexusAPIError(
                status_code=404,
                code="audio_asset_not_found",
                message="Audio asset not found in the active organisation.",
            )
        signed = create_signed_playback_url(
            organisation_id=ctx.organisation.id, asset_id=asset.id
        )
        # Audio assets stream via the /audio router (Phase 5); rewrite path prefix.
        signed["url"] = signed["url"].replace("/media/", "/audio/")
        record_audit_event(
            db,
            organisation_id=ctx.organisation.id,
            actor_user_id=ctx.user.id,
            action="speech.playback.authorise",
            resource_type="audio_asset",
            resource_id=asset.id,
            result="succeeded",
            metadata={"expires_at": signed["expires_at"]},
        )
        db.commit()
        return {
            "asset_id": asset.id,
            "playback_url": signed["url"],
            "expires_at": signed["expires_at"],
            "synthetic_disclosure": asset.synthetic_disclosure,
        }


@audio_router.get("/{asset_id}/stream")
def stream_audio(
    asset_id: str,
    org_id: str,
    expires: int,
    signature: str,
    db: Session = Depends(get_db),
) -> dict:
    """Streams synthesized audio only with a valid short-lived signed URL."""
    verify_signed_playback_signature(
        organisation_id=org_id,
        asset_id=asset_id,
        expires=expires,
        signature=signature,
    )
    storage = get_private_storage()
    with tenant_db_context(db, organisation_id=org_id):
        asset = db.scalars(
            select(AudioAsset).where(AudioAsset.id == asset_id)
        ).first()
        if asset is None:
            raise NexusAPIError(
                status_code=404,
                code="audio_asset_not_found",
                message="Audio asset not found.",
            )
        from fastapi import Response

        raw_bytes = storage.get_bytes(
            organisation_id=org_id, object_key=asset.object_key
        )
        return Response(
            content=raw_bytes,
            media_type="audio/wav",
            headers={
                "Cache-Control": "private, no-store",
                "X-Synthetic-Audio-Disclosure": asset.synthetic_disclosure,
            },
        )


@router.post("/pronunciations", status_code=status.HTTP_201_CREATED)
def create_pronunciation_entry(
    payload: PronunciationBody,
    ctx: TenantAccessContext = Depends(require_permission("transcript.edit")),
    db: Session = Depends(get_db),
) -> dict:
    with tenant_db_context(
        db, organisation_id=ctx.organisation.id, user_id=ctx.user.id
    ):
        existing = db.scalars(
            select(PronunciationEntry).where(
                PronunciationEntry.organisation_id == ctx.organisation.id,
                PronunciationEntry.word == payload.word.strip().lower(),
            )
        ).first()
        if existing is not None:
            existing.phonetic_hint = payload.phonetic_hint.strip()
            db.commit()
            db.refresh(existing)
            return {
                "pronunciation_id": existing.id,
                "word": existing.word,
                "phonetic_hint": existing.phonetic_hint,
                "updated_existing": True,
            }

        entry = PronunciationEntry(
            organisation_id=ctx.organisation.id,
            word=payload.word.strip().lower(),
            phonetic_hint=payload.phonetic_hint.strip(),
            language_code=payload.language_code.lower(),
            created_by_user_id=ctx.user.id,
        )
        db.add(entry)
        db.flush()
        db.commit()
        db.refresh(entry)
        return {
            "pronunciation_id": entry.id,
            "word": entry.word,
            "phonetic_hint": entry.phonetic_hint,
            "updated_existing": False,
        }
