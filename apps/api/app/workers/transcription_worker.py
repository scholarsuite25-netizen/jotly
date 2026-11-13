"""ASR transcription worker with retry/idempotency and diarisation-suggestion handling."""

from __future__ import annotations

import json
import os
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.foundation import BackgroundJob, utcnow
from app.models.meetings_media import MediaAsset, MediaDerivative, MediaProcessingJob, Meeting
from app.models.transcription import (
    Transcript,
    TranscriptSegment,
    TranscriptSpeaker,
)
from app.services.asr_adapter import AsrAdapter, StubAsrAdapter, get_asr_adapter
from app.services.audit import record_audit_event
from app.workers.context import execute_job_in_tenant_context


def _default_asr_adapter() -> AsrAdapter:
    # CI/development default to the deterministic stub so tests never require
    # model weights or GPU hardware. Hostinger workers set ASR_ADAPTER=faster-whisper.
    if os.environ.get("ASR_ADAPTER"):
        return get_asr_adapter()
    return StubAsrAdapter()


def run_transcription_worker(
    db: Session,
    *,
    background_job_id: str,
    organisation_id: str,
    actor_user_id: str,
    language_code: str,
    enable_diarisation: bool = False,
    adapter: AsrAdapter | None = None,
) -> Transcript:
    """
    Executes ASR strictly inside `execute_job_in_tenant_context`:
    1. Loads the validated `MediaAsset` (preferring the normalised derivative bytes).
    2. Runs the replaceable ASR adapter with language selection.
    3. Persists the `Transcript`, `TranscriptSpeaker` tracks (diarisation is a
       model SUGGESTION with `identity_verified=False`) and timestamped segments.
    4. Never overwrites `original_asr_text`; human edits happen later via
       revision-tracked edits in the transcript editor.
    """
    asr = adapter or _default_asr_adapter()

    def _handler(session: Session, bg_job: BackgroundJob) -> Transcript:
        existing = session.scalars(
            select(Transcript).where(
                Transcript.organisation_id == organisation_id,
                Transcript.background_job_id == bg_job.id,
            )
        ).first()
        if existing is not None:
            # Idempotent replay: transcription already produced for this job.
            return existing

        asset = session.scalars(
            select(MediaAsset).where(MediaAsset.id == bg_job.source_entity_id)
        ).first()
        if asset is None:
            raise RuntimeError("Target MediaAsset not found in tenant context.")

        if asset.status not in ("validated", "processed"):
            raise RuntimeError(
                f"MediaAsset status '{asset.status}' is not ready for transcription."
            )

        # Prefer normalised derivative when available (16kHz mono PCM WAV).
        derivative = session.scalars(
            select(MediaDerivative).where(
                MediaDerivative.media_asset_id == asset.id
            ).order_by(MediaDerivative.created_at.asc())
        ).first()

        from app.services.storage_media import get_private_storage

        storage = get_private_storage()
        if derivative is not None:
            audio_bytes = storage.get_bytes(
                organisation_id=organisation_id,
                object_key=derivative.object_key,
            )
        else:
            audio_bytes = storage.get_bytes(
                organisation_id=organisation_id,
                object_key=asset.object_key,
            )

        bg_job.status = "running"
        bg_job.started_at = utcnow()
        session.flush()

        try:
            result = asr.transcribe(
                audio_bytes=audio_bytes,
                language_code=language_code,
                enable_diarisation=enable_diarisation,
            )

            transcript = Transcript(
                organisation_id=organisation_id,
                meeting_id=asset.meeting_id,
                media_asset_id=asset.id,
                background_job_id=bg_job.id,
                language_code=language_code,
                detected_language=result.detected_language,
                language_confidence=result.language_confidence,
                asr_model_id=result.asr_model_id,
                asr_model_version=result.asr_model_version,
                diarisation_enabled=result.diarisation_enabled,
                diarisation_model_id=result.diarisation_model_id,
                config_json=json.dumps(
                    {
                        "language_code": language_code,
                        "enable_diarisation": enable_diarisation,
                        "adapter": type(asr).__name__,
                    }
                ),
                status="completed",
                current_revision_number=1,
            )
            session.add(transcript)
            session.flush()

            speaker_tracks: dict[str, TranscriptSpeaker] = {}
            for seg in result.segments:
                speaker_id = None
                if seg.speaker_key:
                    track = speaker_tracks.get(seg.speaker_key)
                    if track is None:
                        track = TranscriptSpeaker(
                            organisation_id=organisation_id,
                            transcript_id=transcript.id,
                            speaker_key=seg.speaker_key,
                            display_name=f"Speaker {seg.speaker_key}",
                            # Diarisation is ALWAYS a model suggestion, never verified identity.
                            is_model_suggestion=True,
                            identity_verified=False,
                        )
                        session.add(track)
                        session.flush()
                        speaker_tracks[seg.speaker_key] = track
                    speaker_id = track.id

                session.add(
                    TranscriptSegment(
                        organisation_id=organisation_id,
                        transcript_id=transcript.id,
                        sequence_number=seg.sequence_number,
                        start_ms=seg.start_ms,
                        end_ms=seg.end_ms,
                        original_asr_text=seg.text,
                        current_text=seg.text,
                        confidence=seg.confidence,
                        speaker_id=speaker_id,
                        speaker_is_model_suggestion=bool(seg.speaker_key),
                        is_edited=False,
                    )
                )

            meeting = session.scalars(
                select(Meeting).where(Meeting.id == asset.meeting_id)
            ).first()
            if meeting is not None:
                meeting.recording_state = "transcribed"

            bg_job.status = "succeeded"
            bg_job.progress = 100
            bg_job.completed_at = utcnow()

            record_audit_event(
                session,
                organisation_id=organisation_id,
                actor_user_id=actor_user_id,
                action="transcription.complete",
                resource_type="transcript",
                resource_id=transcript.id,
                result="succeeded",
                metadata={
                    "meeting_id": asset.meeting_id,
                    "media_asset_id": asset.id,
                    "language_code": language_code,
                    "detected_language": result.detected_language,
                    "asr_model_id": result.asr_model_id,
                    "asr_model_version": result.asr_model_version,
                    "diarisation_enabled": result.diarisation_enabled,
                    "segment_count": len(result.segments),
                },
            )
            session.flush()
            return transcript
        except Exception as exc:
            bg_job.status = "failed"
            bg_job.retry_count += 1
            bg_job.error_code = "transcription_failed"
            bg_job.error_message = "Transcription processing failed safely."
            bg_job.completed_at = utcnow()
            session.flush()
            raise exc

    return execute_job_in_tenant_context(
        db,
        job_id=background_job_id,
        expected_organisation_id=organisation_id,
        handler=_handler,
    )
