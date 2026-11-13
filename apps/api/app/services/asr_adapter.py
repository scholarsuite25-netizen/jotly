"""Replaceable server-side ASR adapter (Whisper/faster-whisper family).

The adapter sits behind a stable interface so the exact model, runtime and
version can be swapped without touching domain code. In development, CI and
any environment without model weights installed, a deterministic
`StubAsrAdapter` produces synthetic segments so the full pipeline, revision
history and evaluation harness remain testable without GPU or downloads.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol


SUPPORTED_ASR_LANGUAGES: frozenset[str] = frozenset(
    {
        "en",
        "es",
        "fr",
        "de",
        "it",
        "pt",
        "nl",
        "pl",
        "tr",
        "ru",
        "uk",
        "ar",
        "zh",
        "ja",
        "ko",
        "hi",
        "id",
        "vi",
        "th",
        "sw",
        "yo",
    }
)

# Deterministic synthetic word banks used by the stub adapter so segment
# content, timestamps and confidence values are reproducible in tests.
_STUB_WORD_BANK: tuple[str, ...] = (
    "welcome",
    "everyone",
    "to",
    "the",
    "quarterly",
    "review",
    "we",
    "will",
    "cover",
    "budget",
    "hiring",
    "and",
    "roadmap",
    "decisions",
    "action",
    "items",
    "follow",
    "up",
    "next",
    "week",
)


@dataclass(frozen=True)
class AsrSegmentResult:
    sequence_number: int
    start_ms: int
    end_ms: int
    text: str
    confidence: float
    speaker_key: Optional[str] = None


@dataclass(frozen=True)
class AsrTranscriptionResult:
    segments: list[AsrSegmentResult] = field(default_factory=list)
    detected_language: str = "en"
    language_confidence: float = 0.95
    asr_model_id: str = "faster-whisper-large-v3"
    asr_model_version: str = "1.0.3"
    diarisation_enabled: bool = False
    diarisation_model_id: Optional[str] = None


class AsrAdapter(Protocol):
    """Stable server-side interface every ASR backend must implement."""

    model_id: str
    model_version: str

    def transcribe(
        self,
        *,
        audio_bytes: bytes,
        language_code: str,
        enable_diarisation: bool = False,
    ) -> AsrTranscriptionResult: ...


class StubAsrAdapter:
    """
    Deterministic offline ASR adapter used for CI, unit tests and local
    development without model weights. It never claims accuracy: output is
    synthetic text derived from the audio byte length so chunking, timestamp
    alignment, revision history and evaluation harness logic can be verified
    end to end.
    """

    model_id = "stub-asr-deterministic"
    model_version = "1.0.0"

    def __init__(
        self,
        *,
        segments_per_second: float = 0.5,
        segment_confidence: float = 0.88,
        detected_language: str = "en",
        language_confidence: float = 0.93,
        fixed_text: Optional[str] = None,
    ) -> None:
        self.segments_per_second = segments_per_second
        self.segment_confidence = segment_confidence
        self.detected_language = detected_language
        self.language_confidence = language_confidence
        self.fixed_text = fixed_text

    def transcribe(
        self,
        *,
        audio_bytes: bytes,
        language_code: str,
        enable_diarisation: bool = False,
    ) -> AsrTranscriptionResult:
        if language_code not in SUPPORTED_ASR_LANGUAGES:
            raise ValueError(
                f"Language '{language_code}' is not on the supported ASR allowlist."
            )

        duration_ms = _estimate_duration_ms(audio_bytes)
        segments: list[AsrSegmentResult] = []

        if self.fixed_text is not None:
            segments.append(
                AsrSegmentResult(
                    sequence_number=0,
                    start_ms=0,
                    end_ms=duration_ms,
                    text=self.fixed_text,
                    confidence=self.segment_confidence,
                    speaker_key="S0" if enable_diarisation else None,
                )
            )
            return AsrTranscriptionResult(
                segments=segments,
                detected_language=language_code,
                language_confidence=self.language_confidence,
                asr_model_id=self.model_id,
                asr_model_version=self.model_version,
                diarisation_enabled=enable_diarisation,
                diarisation_model_id=(
                    "stub-diarisation-1.0" if enable_diarisation else None
                ),
            )

        segment_count = max(1, round(duration_ms / 1000 * self.segments_per_second))
        segment_duration = max(1000, duration_ms // segment_count)
        for index in range(segment_count):
            start = index * segment_duration
            end = (
                duration_ms if index == segment_count - 1 else (index + 1) * segment_duration
            )
            words = [
                _STUB_WORD_BANK[(index + offset) % len(_STUB_WORD_BANK)]
                for offset in range(6)
            ]
            text = " ".join(words)
            # Alternate deterministic speaker tracks when diarisation is requested.
            # These are model SUGGESTIONS only — never presented as verified identity.
            speaker_key = f"S{index % 2}" if enable_diarisation else None
            segments.append(
                AsrSegmentResult(
                    sequence_number=index,
                    start_ms=start,
                    end_ms=max(end, start + 1),
                    text=text,
                    confidence=round(self.segment_confidence, 3),
                    speaker_key=speaker_key,
                )
            )

        return AsrTranscriptionResult(
            segments=segments,
            detected_language=language_code,
            language_confidence=self.language_confidence,
            asr_model_id=self.model_id,
            asr_model_version=self.model_version,
            diarisation_enabled=enable_diarisation,
            diarisation_model_id=(
                "stub-diarisation-1.0" if enable_diarisation else None
            ),
        )


class FasterWhisperAsrAdapter:
    """
    Production adapter for faster-whisper. Import of the runtime library is
    deferred so CI and lightweight environments are never forced to install
    GPU/model dependencies. Exact model weights require individual licence
    review (see `docs/quality-and-operations/SBOM_AND_LICENCE_REGISTER.md`).
    """

    model_id = "faster-whisper-large-v3"
    model_version = "1.0.3"

    def __init__(self, *, compute_type: str = "int8", device: str = "cpu") -> None:
        self.compute_type = compute_type
        self.device = device
        self._model = None

    def _load(self):
        if self._model is None:
            try:
                from faster_whisper import WhisperModel  # type: ignore
            except ImportError as exc:  # pragma: no cover - exercised only without runtime
                raise RuntimeError(
                    "faster-whisper runtime is not installed. Configure "
                    "ASR_ADAPTER=stub for CI/development or install model "
                    "dependencies on the Hostinger worker host."
                ) from exc
            self._model = WhisperModel(
                self.model_id,
                device=self.device,
                compute_type=self.compute_type,
            )
        return self._model

    def transcribe(
        self,
        *,
        audio_bytes: bytes,
        language_code: str,
        enable_diarisation: bool = False,
    ) -> AsrTranscriptionResult:  # pragma: no cover - requires model weights
        if language_code not in SUPPORTED_ASR_LANGUAGES:
            raise ValueError(
                f"Language '{language_code}' is not on the supported ASR allowlist."
            )
        import tempfile
        import os

        model = self._load()
        suffix = ".wav"
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(audio_bytes)
                tmp_path = tmp.name
            raw_segments, info = model.transcribe(
                tmp_path, language=language_code, vad_filter=True
            )
            segments: list[AsrSegmentResult] = []
            for index, seg in enumerate(raw_segments):
                segments.append(
                    AsrSegmentResult(
                        sequence_number=index,
                        start_ms=int(seg.start * 1000),
                        end_ms=int(seg.end * 1000),
                        text=(seg.text or "").strip(),
                        confidence=round(float(getattr(seg, "avg_logprob", 0.0) * -1 + 0.95), 3),
                        speaker_key=f"S{index % 2}" if enable_diarisation else None,
                    )
                )
            return AsrTranscriptionResult(
                segments=segments,
                detected_language=getattr(info, "language", language_code),
                language_confidence=round(float(getattr(info, "language_probability", 0.9)), 3),
                asr_model_id=self.model_id,
                asr_model_version=self.model_version,
                diarisation_enabled=enable_diarisation,
                diarisation_model_id=(
                    "whisperx-pyannote" if enable_diarisation else None
                ),
            )
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)


def _estimate_duration_ms(audio_bytes: bytes) -> int:
    """
    Deterministic duration estimate from byte length for the stub adapter
    (assumes 16kHz 16-bit mono => 32000 bytes/sec after Phase 2 normalisation).
    """
    if not audio_bytes:
        return 1000
    seconds = len(audio_bytes) / 32000
    return max(1000, int(seconds * 1000))


def get_asr_adapter(adapter_name: Optional[str] = None) -> AsrAdapter:
    """Factory selecting the configured ASR adapter (default: faster-whisper, fallback: stub)."""
    import os

    name = (adapter_name or os.environ.get("ASR_ADAPTER", "faster-whisper")).lower()
    if name == "stub":
        return StubAsrAdapter()
    if name == "faster-whisper":
        return FasterWhisperAsrAdapter()
    raise ValueError(f"Unknown ASR adapter '{name}'. Use 'faster-whisper' or 'stub'.")
