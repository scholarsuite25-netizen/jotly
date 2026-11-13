from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import TenantAccessContext, require_permission
from app.core.db import get_db, tenant_db_context
from app.core.errors import NexusAPIError
from app.models.transcription import (
    Transcript,
    TranscriptExport,
    TranscriptSegment,
    TranscriptSpeaker,
)
from app.services.audit import record_audit_event

router = APIRouter(tags=["transcript-exports-evaluation"])

ALLOWED_EXPORT_FORMATS: frozenset[str] = frozenset({"txt", "srt", "vtt"})


def _format_timestamp_srt(total_ms: int) -> str:
    hours, remainder = divmod(total_ms, 3600000)
    minutes, remainder = divmod(remainder, 60000)
    seconds, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def _format_timestamp_vtt(total_ms: int) -> str:
    hours, remainder = divmod(total_ms, 3600000)
    minutes, remainder = divmod(remainder, 60000)
    seconds, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


class ExportRequest(BaseModel):
    format: str = Field(min_length=3, max_length=8)


@router.post("/transcripts/{transcript_id}/exports", status_code=status.HTTP_201_CREATED)
def export_transcript(
    transcript_id: str,
    payload: ExportRequest,
    ctx: TenantAccessContext = Depends(require_permission("transcript.export")),
    db: Session = Depends(get_db),
) -> dict:
    fmt = payload.format.lower()
    if fmt not in ALLOWED_EXPORT_FORMATS:
        raise NexusAPIError(
            status_code=415,
            code="unsupported_export_format",
            message=f"Export format must be one of {sorted(ALLOWED_EXPORT_FORMATS)}.",
        )

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
        speakers = {
            s.id: s
            for s in db.scalars(
                select(TranscriptSpeaker).where(
                    TranscriptSpeaker.transcript_id == transcript.id
                )
            ).all()
        }

        if fmt == "txt":
            lines = []
            for seg in segments:
                speaker_name = speakers[seg.speaker_id].display_name if seg.speaker_id in speakers else "Unknown"
                edited_marker = " (edited)" if seg.is_edited else ""
                lines.append(
                    f"[{seg.start_ms}ms -> {seg.end_ms}ms] {speaker_name}{edited_marker}: {seg.current_text}"
                )
            content = "\n".join(lines)
        elif fmt == "srt":
            lines = []
            for idx, seg in enumerate(segments, start=1):
                speaker_name = speakers[seg.speaker_id].display_name if seg.speaker_id in speakers else "Unknown"
                lines.append(str(idx))
                lines.append(
                    f"{_format_timestamp_srt(seg.start_ms)} --> {_format_timestamp_srt(seg.end_ms)}"
                )
                lines.append(f"{speaker_name}: {seg.current_text}")
                lines.append("")
            content = "\n".join(lines)
        else:
            lines = ["WEBVTT", ""]
            for seg in segments:
                speaker_name = speakers[seg.speaker_id].display_name if seg.speaker_id in speakers else "Unknown"
                lines.append(
                    f"{_format_timestamp_vtt(seg.start_ms)} --> {_format_timestamp_vtt(seg.end_ms)}"
                )
                lines.append(f"{speaker_name}: {seg.current_text}")
                lines.append("")
            content = "\n".join(lines)

        export_record = TranscriptExport(
            organisation_id=ctx.organisation.id,
            transcript_id=transcript.id,
            format=fmt,
            revision_number=transcript.current_revision_number,
            created_by_user_id=ctx.user.id,
        )
        db.add(export_record)
        db.flush()

        record_audit_event(
            db,
            organisation_id=ctx.organisation.id,
            actor_user_id=ctx.user.id,
            action="transcript.export",
            resource_type="transcript_export",
            resource_id=export_record.id,
            result="succeeded",
            metadata={
                "transcript_id": transcript.id,
                "format": fmt,
                "revision_number": transcript.current_revision_number,
                "segment_count": len(segments),
            },
        )
        db.commit()

        return {
            "export_id": export_record.id,
            "transcript_id": transcript.id,
            "format": fmt,
            "revision_number": transcript.current_revision_number,
            "content": content,
        }


class EvaluationRequest(BaseModel):
    reference_script: str = Field(min_length=1, max_length=5000)


@router.post("/transcripts/{transcript_id}/evaluation")
def evaluate_transcript_wer(
    transcript_id: str,
    payload: EvaluationRequest,
    ctx: TenantAccessContext = Depends(require_permission("transcript.export")),
    db: Session = Depends(get_db),
) -> dict:
    """
    Word Error Rate (WER) evaluation harness comparing the current transcript text
    against a supplied reference script. Reports substitutions, insertions, deletions,
    and accuracy, split per segment. Never claims universal accuracy.
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

        segments = list(
            db.scalars(
                select(TranscriptSegment)
                .where(TranscriptSegment.transcript_id == transcript.id)
                .order_by(TranscriptSegment.sequence_number.asc())
            ).all()
        )

        reference_words = payload.reference_script.lower().split()
        hypothesis_words = " ".join(
            seg.current_text for seg in segments
        ).lower().split()

        substitutions, insertions, deletions = _compute_edit_metrics(
            reference_words, hypothesis_words
        )
        total_reference = max(len(reference_words), 1)
        wer = round(
            (substitutions + insertions + deletions) / total_reference, 4
        )
        accuracy = round(max(0.0, 1.0 - wer), 4)

        segment_metrics = []
        for seg in segments:
            ref_words = seg.original_asr_text.lower().split()
            hyp_words = seg.current_text.lower().split()
            s, i, d = _compute_edit_metrics(ref_words, hyp_words)
            seg_total = max(len(ref_words), 1)
            segment_metrics.append(
                {
                    "segment_id": seg.id,
                    "sequence_number": seg.sequence_number,
                    "is_edited": seg.is_edited,
                    "substitutions": s,
                    "insertions": i,
                    "deletions": d,
                    "segment_wer": round((s + i + d) / seg_total, 4),
                }
            )

        record_audit_event(
            db,
            organisation_id=ctx.organisation.id,
            actor_user_id=ctx.user.id,
            action="transcript.evaluation.run",
            resource_type="transcript",
            resource_id=transcript.id,
            result="succeeded",
            metadata={
                "wer": wer,
                "reference_word_count": len(reference_words),
                "hypothesis_word_count": len(hypothesis_words),
            },
        )
        db.commit()

        return {
            "transcript_id": transcript.id,
            "asr_model_id": transcript.asr_model_id,
            "detected_language": transcript.detected_language,
            "reference_word_count": len(reference_words),
            "hypothesis_word_count": len(hypothesis_words),
            "substitutions": substitutions,
            "insertions": insertions,
            "deletions": deletions,
            "wer": wer,
            "accuracy": accuracy,
            "segments": segment_metrics,
            "disclaimer": (
                "WER is measured only on the supplied reference script for this transcript. "
                "Do not generalise accuracy across languages, accents, or meeting types."
            ),
        }


def _compute_edit_metrics(
    reference: list[str], hypothesis: list[str]
) -> tuple[int, int, int]:
    """Levenshtein-style word-level alignment returning (substitutions, insertions, deletions)."""
    import functools

    n, m = len(reference), len(hypothesis)

    @functools.lru_cache(maxsize=None)
    def dp(i: int, j: int) -> int:
        if i == n:
            return m - j
        if j == m:
            return n - i
        if reference[i] == hypothesis[j]:
            return dp(i + 1, j + 1)
        return 1 + min(dp(i + 1, j + 1), dp(i, j + 1), dp(i + 1, j))

    distance = dp(0, 0)
    i = j = 0
    sub = ins = dele = 0
    while i < n and j < m:
        if reference[i] == hypothesis[j]:
            i += 1
            j += 1
        elif dp(i + 1, j + 1) <= dp(i, j + 1) and dp(i + 1, j + 1) <= dp(i + 1, j):
            sub += 1
            i += 1
            j += 1
        elif dp(i, j + 1) <= dp(i + 1, j):
            ins += 1
            j += 1
        else:
            dele += 1
            i += 1
    dele += n - i
    ins += m - j
    return sub, ins, dele
