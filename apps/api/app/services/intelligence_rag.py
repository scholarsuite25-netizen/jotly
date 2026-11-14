"""Permission-filtered retrieval + grounded generation service (Phase 7 RAG)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.transcription import Transcript, TranscriptSegment


INJECTION_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"ignore (all|any|previous|prior) instructions", re.IGNORECASE),
    re.compile(r"disregard (the )?(system|above|previous) (prompt|message|instructions)", re.IGNORECASE),
    re.compile(r"you are now (an?|the) (admin|administrator|root|system)", re.IGNORECASE),
    re.compile(r"reveal (all|the) (secrets|credentials|tokens|passwords)", re.IGNORECASE),
    re.compile(r"run (this|the following) (sql|command|script)", re.IGNORECASE),
    re.compile(r"drop table|delete from users|grant all privileges", re.IGNORECASE),
    re.compile(r"reveal the administrator password", re.IGNORECASE),
)


def detect_prompt_injection(text: str) -> list[str]:
    """Detects transcript-embedded instruction attempts; content is untrusted data, never instructions."""
    return [p.pattern for p in INJECTION_PATTERNS if p.search(text or "")]


@dataclass(frozen=True)
class RetrievedSegment:
    segment_id: str
    transcript_id: str
    sequence_number: int
    start_ms: int
    end_ms: int
    text: str
    speaker_display_name: Optional[str] = None


@dataclass(frozen=True)
class RetrievalResult:
    segments: list[RetrievedSegment] = field(default_factory=list)
    permission_filter_applied: bool = True
    retrieved_segment_count: int = 0


def permission_filtered_retrieval(
    db: Session,
    *,
    organisation_id: str,
    transcript_ids: Optional[list[str]] = None,
    query_text: str = "",
    max_segments: int = 50,
) -> RetrievalResult:
    """
    Permission-filtered retrieval BEFORE any content reaches the model:
    all segments are loaded strictly inside the tenant RLS context so unauthorised
    cross-tenant content can never be retrieved for generation.
    """
    stmt = select(Transcript).where(Transcript.organisation_id == organisation_id)
    if transcript_ids:
        stmt = stmt.where(Transcript.id.in_(transcript_ids))
    transcripts = list(db.scalars(stmt).all())
    transcript_by_id = {t.id: t for t in transcripts}

    segments: list[RetrievedSegment] = []
    query_terms = [t for t in (query_text or "").lower().split() if len(t) > 2]

    for transcript_id, transcript in transcript_by_id.items():
        rows = list(
            db.scalars(
                select(TranscriptSegment)
                .where(TranscriptSegment.transcript_id == transcript_id)
                .order_by(TranscriptSegment.sequence_number.asc())
            ).all()
        )
        for seg in rows:
            text = seg.current_text or seg.original_asr_text
            if query_terms and not any(term in text.lower() for term in query_terms):
                continue
            segments.append(
                RetrievedSegment(
                    segment_id=seg.id,
                    transcript_id=transcript_id,
                    sequence_number=seg.sequence_number,
                    start_ms=seg.start_ms,
                    end_ms=seg.end_ms,
                    text=text,
                )
            )
            if len(segments) >= max_segments:
                break
        if len(segments) >= max_segments:
            break

    return RetrievalResult(
        segments=segments,
        permission_filter_applied=True,
        retrieved_segment_count=len(segments),
    )


def generate_summary_from_evidence(
    retrieval: RetrievalResult,
    *,
    meeting_title: str,
) -> str:
    """
    Deterministic extractive summary generated ONLY from retrieved evidence.
    Every sentence cites [segment seq @ timestamp]; nothing is invented.
    """
    if not retrieval.segments:
        return (
            f"Summary of '{meeting_title}': No supporting transcript evidence was "
            "retrieved, so no summary claims can be made."
        )
    lines = [f"Summary of '{meeting_title}' (AI interpretation — requires human review):"]
    for seg in retrieval.segments[:10]:
        timestamp = f"{seg.start_ms // 60000:02d}:{(seg.start_ms % 60000) // 1000:02d}"
        lines.append(f"- [segment {seg.sequence_number} @ {timestamp}] {seg.text}")
    return "\n".join(lines)


def answer_question_from_evidence(
    retrieval: RetrievalResult,
    *,
    question: str,
) -> tuple[str, bool, list[RetrievedSegment]]:
    """
    Grounded Q&A: answer ONLY when supporting evidence exists, otherwise abstain.
    Returns (answer_text, abstained, supporting_segments).
    """
    question_terms = [t for t in question.lower().split() if len(t) > 2]
    # Require meaningful term coverage so unrelated fragments cannot fabricate support.
    supporting = []
    for seg in retrieval.segments:
        lowered = seg.text.lower()
        matched = sum(1 for term in question_terms if term in lowered)
        if len(question_terms) <= 1:
            if matched >= 1:
                supporting.append(seg)
        elif matched >= max(1, (len(question_terms) + 1) // 2):
            supporting.append(seg)
    if not supporting:
        return (
            "The system cannot find supporting evidence in the authorised meeting "
            "records for this question.",
            True,
            [],
        )

    citations = "; ".join(
        f"[segment {seg.sequence_number} @ {seg.start_ms // 60000:02d}:"
        f"{(seg.start_ms % 60000) // 1000:02d}]"
        for seg in supporting[:5]
    )
    answer = (
        f"Based on retrieved transcript evidence {citations}: "
        + " ".join(seg.text for seg in supporting[:3])
        + " (AI interpretation — verify against cited segments.)"
    )
    return answer, False, supporting


def extract_decisions_and_actions(
    retrieval: RetrievalResult,
) -> tuple[list[tuple[str, RetrievedSegment]], list[tuple[str, Optional[str], Optional[str], RetrievedSegment]]]:
    """
    Extracts decision/action candidates ONLY from evidence-bearing segments.
    Owner/deadline hints are returned only when explicitly supported by the text.
    """
    decisions: list[tuple[str, RetrievedSegment]] = []
    actions: list[tuple[str, Optional[str], Optional[str], RetrievedSegment]] = []

    decision_pattern = re.compile(
        r"\b(?:we (?:have )?decided|agreed|approved|it was decided)\b(.*)", re.IGNORECASE
    )
    action_pattern = re.compile(
        r"\b(\w+)\s+will\s+([^.;!?]+)", re.IGNORECASE
    )
    deadline_pattern = re.compile(
        r"\bby\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday|tomorrow|next week|eod)\b",
        re.IGNORECASE,
    )

    for seg in retrieval.segments:
        decision_match = decision_pattern.search(seg.text)
        if decision_match:
            decisions.append((seg.text, seg))
        action_match = action_pattern.search(seg.text)
        if action_match:
            owner = action_match.group(1).title()
            action_text = f"{owner} will {action_match.group(2).strip()}"
            deadline_match = deadline_pattern.search(seg.text)
            due_hint = deadline_match.group(1).title() if deadline_match else None
            actions.append((action_text, owner, due_hint, seg))

    return decisions, actions
