"""Voice Studio (standard TTS) worker: chunk synthesis, chapter markers, asset assembly."""

from __future__ import annotations

import hashlib
import json
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.speech import (
    AudioAsset,
    AudioChapter,
    PronunciationEntry,
    SpeechChunk,
    SpeechProject,
)
from app.services.audit import record_audit_event
from app.services.tts_adapter import (
    TtsChunkResult,
    apply_pronunciation_overrides,
    get_default_tts_adapter,
    join_chunks_with_normalisation,
)
from app.services.storage_media import get_private_storage
from app.workers.context import execute_job_in_tenant_context


def run_speech_synthesis_worker(
    db: Session,
    *,
    background_job_id: str,
    organisation_id: str,
    actor_user_id: str,
    language_code: str,
    voice_id: str,
    speed_percent: int,
    output_format: str = "wav",
    add_chapters: bool = True,
) -> AudioAsset:
    """
    Executes document-to-speech synthesis strictly inside tenant context:
    1. Reads reviewed text from SpeechProject.
    2. Synthesizes each chunk through the replaceable TTS adapter (pronunciation-aware).
    3. Joins chunks with loudness normalisation into one AudioAsset.
    4. Writes chapter markers per chunk for player navigation.
    Every output is labelled AI-generated with model/voice provenance recorded.
    """

    def _handler(session: Session, bg_job) -> AudioAsset:
        project = session.scalars(
            select(SpeechProject).where(SpeechProject.id == bg_job.source_entity_id)
        ).first()
        if project is None:
            raise RuntimeError("SpeechProject not found in tenant context.")

        existing_asset = session.scalars(
            select(AudioAsset).where(AudioAsset.speech_project_id == project.id)
        ).first()
        if existing_asset is not None:
            return existing_asset

        pronunciation = {
            e.word: e.phonetic_hint
            for e in session.scalars(
                select(PronunciationEntry).where(
                    PronunciationEntry.organisation_id == organisation_id
                )
            ).all()
        }

        chunks = list(
            session.scalars(
                select(SpeechChunk)
                .where(SpeechChunk.speech_project_id == project.id)
                .order_by(SpeechChunk.chunk_index.asc())
            ).all()
        )

        adapter = get_default_tts_adapter()
        chunk_results: list[TtsChunkResult] = []
        for chunk in chunks:
            overrides = json.loads(chunk.pronunciation_overrides_json or "{}")
            merged = {**pronunciation, **overrides}
            effective_text = apply_pronunciation_overrides(chunk.chunk_text, merged)
            result = adapter.synthesize_chunk(
                text=effective_text,
                language_code=language_code,
                voice_id=voice_id,
                speed_percent=speed_percent,
            )
            chunk_results.append(
                TtsChunkResult(
                    chunk_index=chunk.chunk_index,
                    duration_ms=result.duration_ms,
                    wav_bytes=result.wav_bytes,
                )
            )
            chunk.object_key = (
                f"tenants/{organisation_id}/speech/{project.id}"
                f"/chunks/{chunk.chunk_index:04d}.wav"
            )
            chunk.duration_ms = result.duration_ms
            session.flush()

        joined = join_chunks_with_normalisation(chunk_results)
        sha256_checksum = hashlib.sha256(joined).hexdigest()
        total_duration_ms = sum(c.duration_ms for c in chunk_results)

        storage = get_private_storage()
        object_key = (
            f"tenants/{organisation_id}/speech/{project.id}"
            f"/assets/synthesized.{output_format}"
        )
        storage.put_bytes(
            organisation_id=organisation_id,
            object_key=object_key,
            data=joined,
        )

        audio_asset = AudioAsset(
            organisation_id=organisation_id,
            speech_project_id=project.id,
            object_key=object_key,
            output_format=output_format,
            size_bytes=len(joined),
            sha256_checksum=sha256_checksum,
            duration_ms=total_duration_ms,
            loudness_normalised=True,
            synthetic_disclosure="AI-generated speech (standard voice)",
        )
        session.add(audio_asset)
        session.flush()

        if add_chapters:
            cursor = 0
            for index, chunk_result in enumerate(chunk_results):
                session.add(
                    AudioChapter(
                        organisation_id=organisation_id,
                        audio_asset_id=audio_asset.id,
                        chapter_index=index,
                        title=f"Chapter {index + 1}",
                        start_ms=cursor,
                        end_ms=cursor + chunk_result.duration_ms,
                    )
                )
                cursor += chunk_result.duration_ms

        project.status = "completed"
        project.chunk_count = len(chunk_results)
        session.flush()

        record_audit_event(
            session,
            organisation_id=organisation_id,
            actor_user_id=actor_user_id,
            action="speech.synthesize",
            resource_type="audio_asset",
            resource_id=audio_asset.id,
            result="succeeded",
            metadata={
                "speech_project_id": project.id,
                "tts_model_id": adapter.tts_model_id,
                "voice_id": voice_id,
                "language_code": language_code,
                "chunk_count": len(chunk_results),
                "duration_ms": total_duration_ms,
                "synthetic_disclosure": audio_asset.synthetic_disclosure,
            },
        )
        return audio_asset

    return execute_job_in_tenant_context(
        db,
        job_id=background_job_id,
        expected_organisation_id=organisation_id,
        handler=_handler,
    )
