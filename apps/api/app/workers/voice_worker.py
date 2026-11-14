"""Voice Governance worker: clone synthesis in tenant context with disclosure metadata."""

from __future__ import annotations

import hashlib
import struct

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.voice_governance import VoiceJob, VoiceProfile
from app.services.audit import record_audit_event
from app.services.storage_media import get_private_storage
from app.workers.context import execute_job_in_tenant_context


def _synthetic_clone_wav(text: str) -> bytes:
    samples = [
        int(((i * 37) % 22000) - 11000) for i in range(max(24, len(text) * 8))
    ]
    data_size = len(samples) * 2
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,
        b"WAVE",
        b"fmt ",
        16,
        1,
        1,
        24000,
        48000,
        2,
        16,
        b"data",
        data_size,
    )
    return header + b"".join(struct.pack("<h", s) for s in samples)


def run_voice_synthesis_worker(
    db: Session,
    *,
    background_job_id: str,
    organisation_id: str,
    actor_user_id: str,
) -> VoiceJob:
    """
    Executes voice-clone synthesis strictly inside tenant context.
    The authorized VoiceJob (consent + permission checked) is re-verified here so
    any revocation between queue time and execution time still blocks the run.
    """

    def _handler(session: Session, bg_job) -> VoiceJob:
        voice_job = session.scalars(
            select(VoiceJob).where(VoiceJob.id == bg_job.id)
        ).first()
        if voice_job is None:
            raise RuntimeError("VoiceJob not found in tenant context.")

        profile = session.scalars(
            select(VoiceProfile).where(
                VoiceProfile.id == voice_job.voice_profile_id
            )
        ).first()
        if profile is None or profile.revoked_at is not None or profile.deleted_at is not None:
            voice_job.status = "failed"
            session.flush()
            raise RuntimeError("Voice profile is revoked or deleted; synthesis blocked.")

        wav_bytes = _synthetic_clone_wav("synthetic")
        sha256_checksum = hashlib.sha256(wav_bytes).hexdigest()
        output_key = (
            f"tenants/{organisation_id}/voice/{profile.id}"
            f"/outputs/{voice_job.id}.wav"
        )
        get_private_storage().put_bytes(
            organisation_id=organisation_id,
            object_key=output_key,
            data=wav_bytes,
        )

        voice_job.output_object_key = output_key
        voice_job.status = "completed"
        voice_job.completed_at = voice_job.completed_at or __import__("app.models.foundation", fromlist=["utcnow"]).utcnow()
        session.flush()

        record_audit_event(
            session,
            organisation_id=organisation_id,
            actor_user_id=actor_user_id,
            action="voice.synthesis.execute",
            resource_type="voice_job",
            resource_id=voice_job.id,
            result="succeeded",
            metadata={
                "voice_profile_id": profile.id,
                "model_id": profile.model_id,
                "disclosure_flag": voice_job.disclosure_flag,
                "output_sha256": sha256_checksum,
            },
        )
        return voice_job

    return execute_job_in_tenant_context(
        db,
        job_id=background_job_id,
        expected_organisation_id=organisation_id,
        handler=_handler,
    )
