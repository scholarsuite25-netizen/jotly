"""Transcript retrieval, segment editing with revision history, and export-ready data."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import TenantAccessContext, require_permission
from app.core.db import get_db, tenant_db_context
from app.core.errors import NexusAPIError
from app.models.foundation import utcnow
from app.models.meetings_media import MediaAsset, Meeting
from app.models.transcription import (
    SpeakerLabel,
    Transcript,
    TranscriptExport,
    TranscriptRevision,
    TranscriptSegment,
    TranscriptSpeaker,
)
from app.services.audit import record_audit_event
from app.workers.context import enqueue_tenant_job
from app.workers.transcription_worker import run_transcription_worker

router = APIRouter(prefix="/transcripts", tags=["transcriptions"])
media_router = APIRouter(tags=["transcriptions"])

MAX_UNDO_STACK = 100


class RequestTranscriptionBody(BaseModel):
    language_code: str = Field(default="en", min_length=2, max_length=16)
    enable_diarisation: bool = Field(default=False)


class EditSegmentBody(BaseModel):
    new_text: str = Field(min_length=0, max_length=20000)
    new_speaker_id: Optional[str] = Field(default=None, max_length=36)


class FindReplaceBody(BaseModel):
    find_text: str = Field(min_length=1, max_length=500)
    replace_text: str = Field(default="", max_length=500)
    case_sensitive: bool = Field(default=False)


class RelabelSpeakerBody(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)


def _segment_payload(seg: TranscriptSegment, speaker: Optional[TranscriptSpeaker]) -> dict:
    return {
        "id": seg.id,
        "sequence_number": seg.sequence_number,
        "start_ms": seg.start_ms,
        "end_ms": seg.end_ms,
        "original_asr_text": seg.original_asr_text,
        "current_text": seg.current_text,
        "confidence": seg.confidence,
        "speaker_id": seg.speaker_id,
        "speaker_display_name": speaker.display_name if speaker else None,
        "speaker_is_model_suggestion": seg.speaker_is_model_suggestion,
        "identity_verified": bool(speaker.identity_verified) if speaker else False,
        "is_edited": seg.is_edited,
        "updated_by_user_id": seg.updated_by_user_id,
    }


@router.post("/{meeting_id}/media/{media_asset_id}/transcriptions", status_code=status.HTTP_202_ACCEPTED)
def queue_transcription(
    meeting_id: str,
    media_asset_id: str,
    payload: RequestTranscriptionBody,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    ctx: TenantAccessContext = Depends(require_permission("transcript.edit")),
    db: Session = Depends(get_db),
) -> dict:
    """
    Queues an ASR transcription job for a validated media asset. Idempotent per
    (asset, language, diarisation) combination: replaying the request returns
    the existing transcript or job instead of duplicating work.
    """
    from app.services.asr_adapter import SUPPORTED_ASR_LANGUAGES

    if payload.language_code.lower() not in SUPPORTED_ASR_LANGUAGES:
        raise NexusAPIError(
            status_code=400,
            code="unsupported_language",
            message=f"Language '{payload.language_code}' is not on the supported ASR allowlist.",
        )

    with tenant_db_context(
        db, organisation_id=ctx.organisation.id, user_id=ctx.user.id
    ):
        meeting = db.scalars(
            select(Meeting).where(Meeting.id == meeting_id)
        ).first()
        if meeting is None:
            raise NexusAPIError(
                status_code=404,
                code="meeting_not_found",
                message="Meeting not found in the active organisation.",
            )

        asset = db.scalars(
            select(MediaAsset).where(
                MediaAsset.id == media_asset_id,
                MediaAsset.meeting_id == meeting_id,
            )
        ).first()
        if asset is None:
            raise NexusAPIError(
                status_code=404,
                code="media_asset_not_found",
                message="Media asset not found in the active organisation.",
            )
        if asset.status not in ("validated", "processed"):
            raise NexusAPIError(
                status_code=409,
                code="media_not_ready",
                message=f"Media asset status '{asset.status}' is not ready for transcription.",
            )

        lang = payload.language_code.lower()
        diarise = payload.enable_diarisation

        existing_transcript = db.scalars(
            select(Transcript).where(
                Transcript.organisation_id == ctx.organisation.id,
                Transcript.media_asset_id == asset.id,
                Transcript.language_code == lang,
                Transcript.diarisation_enabled == diarise,
            )
        ).first()
        if existing_transcript is not None:
            return {
                "transcript_id": existing_transcript.id,
                "meeting_id": existing_transcript.meeting_id,
                "media_asset_id": existing_transcript.media_asset_id,
                "job_id": existing_transcript.background_job_id,
                "status": existing_transcript.status,
                "idempotent_replay": True,
            }

        idem = (
            idempotency_key.strip()
            if idempotency_key and idempotency_key.strip()
            else f"transcribe:{asset.id}:{lang}:{diarise}"
        )
        bg_job = enqueue_tenant_job(
            db,
            organisation_id=ctx.organisation.id,
            actor_user_id=ctx.user.id,
            job_type="media.transcribe",
            source_entity_type="media_asset",
            source_entity_id=asset.id,
            idempotency_key=idem,
        )

        record_audit_event(
            db,
            organisation_id=ctx.organisation.id,
            actor_user_id=ctx.user.id,
            action="transcription.queue",
            resource_type="media_asset",
            resource_id=asset.id,
            result="succeeded",
            metadata={
                "meeting_id": meeting_id,
                "language_code": lang,
                "enable_diarisation": diarise,
                "job_id": bg_job.id,
            },
        )
        db.commit()

    # Execute synchronously in isolated worker tenant context (stub or real adapter).
    transcript = run_transcription_worker(
        db,
        background_job_id=bg_job.id,
        organisation_id=ctx.organisation.id,
        actor_user_id=ctx.user.id,
        language_code=lang,
        enable_diarisation=diarise,
    )
    db.refresh(transcript)

    return {
        "transcript_id": transcript.id,
        "meeting_id": transcript.meeting_id,
        "media_asset_id": transcript.media_asset_id,
        "job_id": bg_job.id,
        "status": transcript.status,
        "idempotent_replay": False,
    }


@router.get("/{transcript_id}")
def get_transcript(
    transcript_id: str,
    ctx: TenantAccessContext = Depends(require_permission("meeting.view")),
    db: Session = Depends(get_db),
) -> dict:
    """
    Fetches the authorised transcript with segments, speaker tracks (clearly marked
    as model suggestions where diarisation is enabled), and revision metadata.
    """
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

        speakers = {
            s.id: s
            for s in db.scalars(
                select(TranscriptSpeaker).where(
                    TranscriptSpeaker.transcript_id == transcript.id
                )
            ).all()
        }
        segments = list(
            db.scalars(
                select(TranscriptSegment)
                .where(TranscriptSegment.transcript_id == transcript.id)
                .order_by(TranscriptSegment.sequence_number.asc())
            ).all()
        )
        revisions = list(
            db.scalars(
                select(TranscriptRevision)
                .where(TranscriptRevision.transcript_id == transcript.id)
                .order_by(TranscriptRevision.revision_number.desc())
                .limit(50)
            ).all()
        )

        return {
            "id": transcript.id,
            "meeting_id": transcript.meeting_id,
            "media_asset_id": transcript.media_asset_id,
            "language_code": transcript.language_code,
            "detected_language": transcript.detected_language,
            "language_confidence": transcript.language_confidence,
            "asr_model_id": transcript.asr_model_id,
            "asr_model_version": transcript.asr_model_version,
            "diarisation_enabled": transcript.diarisation_enabled,
            "diarisation_model_id": transcript.diarisation_model_id,
            "status": transcript.status,
            "current_revision_number": transcript.current_revision_number,
            "speakers": [
                {
                    "id": s.id,
                    "speaker_key": s.speaker_key,
                    "display_name": s.display_name,
                    "is_model_suggestion": s.is_model_suggestion,
                    "identity_verified": s.identity_verified,
                }
                for s in speakers.values()
            ],
            "segments": [_segment_payload(seg, speakers.get(seg.speaker_id)) for seg in segments],
            "revisions": [
                {
                    "id": r.id,
                    "revision_number": r.revision_number,
                    "segment_id": r.segment_id,
                    "change_type": r.change_type,
                    "previous_text": r.previous_text,
                    "new_text": r.new_text,
                    "summary": r.summary,
                    "editor_user_id": r.editor_user_id,
                    "created_at": r.created_at.isoformat(),
                }
                for r in revisions
            ],
        }


@router.patch("/{transcript_id}/segments/{segment_id}")
def edit_transcript_segment(
    transcript_id: str,
    segment_id: str,
    payload: EditSegmentBody,
    ctx: TenantAccessContext = Depends(require_permission("transcript.edit")),
    db: Session = Depends(get_db),
) -> dict:
    """
    Edits a transcript segment with a mandatory revision record. The original
    ASR output (`original_asr_text`) is preserved immutably; human corrections
    are tracked in `current_text` and every change appends to `transcript_revisions`.
    """
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

        segment = db.scalars(
            select(TranscriptSegment).where(
                TranscriptSegment.id == segment_id,
                TranscriptSegment.transcript_id == transcript.id,
            )
        ).first()
        if segment is None:
            raise NexusAPIError(
                status_code=404,
                code="segment_not_found",
                message="Transcript segment not found in the active organisation.",
            )

        speaker = None
        if payload.new_speaker_id:
            speaker = db.scalars(
                select(TranscriptSpeaker).where(
                    TranscriptSpeaker.id == payload.new_speaker_id,
                    TranscriptSpeaker.transcript_id == transcript.id,
                )
            ).first()
            if speaker is None:
                raise NexusAPIError(
                    status_code=404,
                    code="speaker_not_found",
                    message="Speaker track not found in this transcript.",
                )

        previous_text = segment.current_text
        previous_speaker_id = segment.speaker_id
        new_text = payload.new_text

        text_changed = new_text != previous_text
        speaker_changed = (
            payload.new_speaker_id is not None
            and payload.new_speaker_id != previous_speaker_id
        )
        if not text_changed and not speaker_changed:
            return {
                "segment_id": segment.id,
                "current_text": segment.current_text,
                "is_edited": segment.is_edited,
                "revision_number": transcript.current_revision_number,
                "changed": False,
            }

        new_revision_number = transcript.current_revision_number + 1

        if text_changed:
            segment.current_text = new_text
            segment.is_edited = True
            segment.updated_by_user_id = ctx.user.id
        if speaker_changed and speaker is not None:
            segment.speaker_id = speaker.id
            segment.speaker_is_model_suggestion = False
            segment.updated_by_user_id = ctx.user.id

        transcript.current_revision_number = new_revision_number
        transcript.updated_at = utcnow()

        change_type = (
            "edit_and_relabel"
            if (text_changed and speaker_changed)
            else ("speaker_relabel" if speaker_changed else "text_edit")
        )
        summary_parts = []
        if text_changed:
            summary_parts.append("text edited")
        if speaker_changed:
            summary_parts.append("speaker relabelled")

        db.add(
            TranscriptRevision(
                organisation_id=ctx.organisation.id,
                transcript_id=transcript.id,
                segment_id=segment.id,
                revision_number=new_revision_number,
                change_type=change_type,
                previous_text=previous_text if text_changed else None,
                new_text=new_text if text_changed else None,
                previous_speaker_id=previous_speaker_id if speaker_changed else None,
                new_speaker_id=payload.new_speaker_id if speaker_changed else None,
                editor_user_id=ctx.user.id,
                summary=f"Segment {segment.sequence_number}: {', '.join(summary_parts)}",
            )
        )

        record_audit_event(
            db,
            organisation_id=ctx.organisation.id,
            actor_user_id=ctx.user.id,
            action="transcript.segment.edit",
            resource_type="transcript_segment",
            resource_id=segment.id,
            result="succeeded",
            metadata={
                "transcript_id": transcript.id,
                "revision_number": new_revision_number,
                "change_type": change_type,
            },
        )
        db.commit()
        db.refresh(segment)
        db.refresh(transcript)

        speaker_obj = (
            db.scalars(
                select(TranscriptSpeaker).where(TranscriptSpeaker.id == segment.speaker_id)
            ).first()
            if segment.speaker_id
            else None
        )

        return {
            "segment_id": segment.id,
            "current_text": segment.current_text,
            "original_asr_text": segment.original_asr_text,
            "is_edited": segment.is_edited,
            "speaker_id": segment.speaker_id,
            "speaker_display_name": speaker_obj.display_name if speaker_obj else None,
            "speaker_is_model_suggestion": segment.speaker_is_model_suggestion,
            "revision_number": transcript.current_revision_number,
            "changed": True,
        }


@router.post("/{transcript_id}/segments/{segment_id}/undo")
def undo_last_segment_edit(
    transcript_id: str,
    segment_id: str,
    ctx: TenantAccessContext = Depends(require_permission("transcript.edit")),
    db: Session = Depends(get_db),
) -> dict:
    """
    Undoes the most recent revision for a specific segment by restoring the
    previous text/speaker from `transcript_revisions` (stack-style undo).
    """
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

        segment = db.scalars(
            select(TranscriptSegment).where(
                TranscriptSegment.id == segment_id,
                TranscriptSegment.transcript_id == transcript.id,
            )
        ).first()
        if segment is None:
            raise NexusAPIError(
                status_code=404,
                code="segment_not_found",
                message="Transcript segment not found in the active organisation.",
            )

        last_revision = db.scalars(
            select(TranscriptRevision)
            .where(
                TranscriptRevision.transcript_id == transcript.id,
                TranscriptRevision.segment_id == segment.id,
            )
            .order_by(TranscriptRevision.revision_number.desc())
        ).first()

        if last_revision is None:
            raise NexusAPIError(
                status_code=409,
                code="no_revision_to_undo",
                message="No editable revision history exists for this segment.",
            )

        previous_text = (
            last_revision.previous_text
            if last_revision.previous_text is not None
            else segment.original_asr_text
        )
        previous_speaker_id = last_revision.previous_speaker_id

        segment.current_text = previous_text
        segment.speaker_id = previous_speaker_id
        segment.is_edited = previous_text != segment.original_asr_text
        segment.speaker_is_model_suggestion = previous_speaker_id is None
        segment.updated_by_user_id = ctx.user.id

        new_rev_num = transcript.current_revision_number + 1
        transcript.current_revision_number = new_rev_num
        transcript.updated_at = utcnow()

        db.add(
            TranscriptRevision(
                organisation_id=ctx.organisation.id,
                transcript_id=transcript.id,
                segment_id=segment.id,
                revision_number=new_rev_num,
                change_type="undo",
                previous_text=segment.current_text if not segment.is_edited else None,
                new_text=previous_text,
                previous_speaker_id=previous_speaker_id,
                new_speaker_id=previous_speaker_id,
                editor_user_id=ctx.user.id,
                summary=f"Undo of revision {last_revision.revision_number} on segment {segment.sequence_number}",
            )
        )

        record_audit_event(
            db,
            organisation_id=ctx.organisation.id,
            actor_user_id=ctx.user.id,
            action="transcript.segment.undo",
            resource_type="transcript_segment",
            resource_id=segment.id,
            result="succeeded",
            metadata={
                "transcript_id": transcript.id,
                "undone_revision": last_revision.revision_number,
                "new_revision_number": new_rev_num,
            },
        )
        db.commit()
        db.refresh(segment)
        db.refresh(transcript)

        return {
            "segment_id": segment.id,
            "current_text": segment.current_text,
            "original_asr_text": segment.original_asr_text,
            "is_edited": segment.is_edited,
            "revision_number": transcript.current_revision_number,
            "undone_revision_number": last_revision.revision_number,
        }


@router.post("/{transcript_id}/find-replace")
def find_replace_across_transcript(
    transcript_id: str,
    payload: FindReplaceBody,
    ctx: TenantAccessContext = Depends(require_permission("transcript.edit")),
    db: Session = Depends(get_db),
) -> dict:
    """
    Bulk find/replace across the transcript. Every replaced segment receives its own
    revision record; the replace count is capped to keep changes reviewable.
    """
    MAX_REPLACEMENTS = 500

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

        segments = list(
            db.scalars(
                select(TranscriptSegment)
                .where(TranscriptSegment.transcript_id == transcript.id)
                .order_by(TranscriptSegment.sequence_number.asc())
            ).all()
        )

        find_text = payload.find_text
        replace_text = payload.replace_text

        def _matches(haystack: str) -> bool:
            return (
                find_text in haystack
                if payload.case_sensitive
                else find_text.lower() in haystack.lower()
            )

        replacements: list[dict] = []
        new_rev_num = transcript.current_revision_number

        for seg in segments:
            if len(replacements) >= MAX_REPLACEMENTS:
                break
            if not _matches(seg.current_text):
                continue
            if payload.case_sensitive:
                new_value = seg.current_text.replace(find_text, replace_text)
            else:
                import re

                pattern = re.compile(re.escape(find_text), re.IGNORECASE)
                new_value = pattern.sub(replace_text, seg.current_text)

            if new_value == seg.current_text:
                continue

            previous_text = seg.current_text
            seg.current_text = new_value
            seg.is_edited = True
            seg.updated_by_user_id = ctx.user.id
            new_rev_num += 1

            db.add(
                TranscriptRevision(
                    organisation_id=ctx.organisation.id,
                    transcript_id=transcript.id,
                    segment_id=seg.id,
                    revision_number=new_rev_num,
                    change_type="find_replace",
                    previous_text=previous_text,
                    new_text=new_value,
                    editor_user_id=ctx.user.id,
                    summary=f"Find/replace '{find_text}' -> '{replace_text}' on segment {seg.sequence_number}",
                )
            )
            replacements.append(
                {
                    "segment_id": seg.id,
                    "sequence_number": seg.sequence_number,
                    "previous_text": previous_text,
                    "new_text": new_value,
                }
            )

        transcript.current_revision_number = new_rev_num
        transcript.updated_at = utcnow()

        record_audit_event(
            db,
            organisation_id=ctx.organisation.id,
            actor_user_id=ctx.user.id,
            action="transcript.find_replace",
            resource_type="transcript",
            resource_id=transcript.id,
            result="succeeded",
            metadata={
                "find_text": find_text,
                "replace_count": len(replacements),
                "case_sensitive": payload.case_sensitive,
            },
        )
        db.commit()
        db.refresh(transcript)

        return {
            "transcript_id": transcript.id,
            "replacement_count": len(replacements),
            "replacements": replacements,
            "revision_number": transcript.current_revision_number,
        }


@router.post("/{transcript_id}/speakers/{speaker_id}/relabel")
def relabel_speaker(
    transcript_id: str,
    speaker_id: str,
    payload: RelabelSpeakerBody,
    ctx: TenantAccessContext = Depends(require_permission("transcript.edit")),
    db: Session = Depends(get_db),
) -> dict:
    """
    Human correction of a diarisation-suggested speaker label. The relabelled
    speaker track is recorded in `speaker_labels` with source `human_correction`
    and keeps `identity_verified=False` (labels are never identity claims).
    """
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

        speaker = db.scalars(
            select(TranscriptSpeaker).where(
                TranscriptSpeaker.id == speaker_id,
                TranscriptSpeaker.transcript_id == transcript.id,
            )
        ).first()
        if speaker is None:
            raise NexusAPIError(
                status_code=404,
                code="speaker_not_found",
                message="Speaker track not found in this transcript.",
            )

        previous_name = speaker.display_name
        speaker.display_name = payload.display_name.strip()
        speaker.updated_at = utcnow()

        db.add(
            SpeakerLabel(
                organisation_id=ctx.organisation.id,
                transcript_id=transcript.id,
                speaker_id=speaker.id,
                previous_display_name=previous_name,
                new_display_name=speaker.display_name,
                changed_by_user_id=ctx.user.id,
                source="human_correction",
            )
        )

        record_audit_event(
            db,
            organisation_id=ctx.organisation.id,
            actor_user_id=ctx.user.id,
            action="transcript.speaker.relabel",
            resource_type="transcript_speaker",
            resource_id=speaker.id,
            result="succeeded",
            metadata={
                "transcript_id": transcript.id,
                "previous_name": previous_name,
                "new_name": speaker.display_name,
                "identity_verified": False,
            },
        )
        db.commit()
        db.refresh(speaker)

        return {
            "speaker_id": speaker.id,
            "display_name": speaker.display_name,
            "is_model_suggestion": speaker.is_model_suggestion,
            "identity_verified": speaker.identity_verified,
            "previous_display_name": previous_name,
        }


@router.get("/{transcript_id}/exports")
def list_transcript_exports(
    transcript_id: str,
    ctx: TenantAccessContext = Depends(require_permission("transcript.export")),
    db: Session = Depends(get_db),
) -> dict:
    """Returns export-ready transcript data (DOCX/PDF/SRT/VTT/TXT payloads for Phase 4)."""
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

        meeting = db.scalars(
            select(Meeting).where(Meeting.id == transcript.meeting_id)
        ).first()
        speakers = {
            s.id: s
            for s in db.scalars(
                select(TranscriptSpeaker).where(
                    TranscriptSpeaker.transcript_id == transcript.id
                )
            ).all()
        }
        segments = list(
            db.scalars(
                select(TranscriptSegment)
                .where(TranscriptSegment.transcript_id == transcript.id)
                .order_by(TranscriptSegment.sequence_number.asc())
            ).all()
        )
        exports = list(
            db.scalars(
                select(TranscriptExport).where(
                    TranscriptExport.transcript_id == transcript.id
                )
            ).all()
        )

        return {
            "transcript_id": transcript.id,
            "meeting_title": meeting.title if meeting else None,
            "language_code": transcript.language_code,
            "asr_model_id": transcript.asr_model_id,
            "asr_model_version": transcript.asr_model_version,
            "revision_number": transcript.current_revision_number,
            "speakers": [
                {
                    "id": s.id,
                    "speaker_key": s.speaker_key,
                    "display_name": s.display_name,
                    "is_model_suggestion": s.is_model_suggestion,
                    "identity_verified": s.identity_verified,
                }
                for s in speakers.values()
            ],
            "segments": [
                {
                    "sequence_number": seg.sequence_number,
                    "start_ms": seg.start_ms,
                    "end_ms": seg.end_ms,
                    "current_text": seg.current_text,
                    "original_asr_text": seg.original_asr_text,
                    "is_edited": seg.is_edited,
                    "speaker_display_name": (
                        speakers[seg.speaker_id].display_name if seg.speaker_id in speakers else None
                    ),
                }
                for seg in segments
            ],
            "previous_exports": [
                {
                    "id": e.id,
                    "format": e.format,
                    "revision_number": e.revision_number,
                    "created_at": e.created_at.isoformat(),
                }
                for e in exports
            ],
        }
