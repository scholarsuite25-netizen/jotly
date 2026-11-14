"""Replaceable standard TTS adapter (Kokoro family) with deterministic CPU-safe stub.

Voice cloning is explicitly NOT part of this module (Phase 6 consent-gated,
VOICE_CLONING_ENABLED stays false). Only standard, non-cloned voices are supported.
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass, field
from typing import Optional

SUPPORTED_TTS_LANGUAGES: frozenset[str] = frozenset({"en", "es", "fr", "de", "it", "pt"})
SUPPORTED_OUTPUT_FORMATS: frozenset[str] = frozenset({"wav", "mp3", "ogg"})
SUPPORTED_SPEED_RANGE = (50, 200)


class StandardVoiceCatalogue:
    """Voice catalogue is standard (non-cloned) only; language coverage is explicit."""

    _VOICES: dict[str, dict[str, str]] = {
        "en": {"female_01": "Alloy", "male_01": "Echo"},
        "es": {"female_01": "Marisol"},
        "fr": {"female_01": "Camille"},
        "de": {"male_01": "Jonas"},
        "it": {"female_01": "Giulia"},
        "pt": {"male_01": "Rafael"},
    }

    @classmethod
    def voice_exists(cls, language_code: str, voice_id: str) -> bool:
        return voice_id in cls._VOICES.get(language_code, {})

    @classmethod
    def voice_name(cls, language_code: str, voice_id: str) -> str:
        return cls._VOICES.get(language_code, {}).get(voice_id, voice_id)


@dataclass(frozen=True)
class TtsChunkResult:
    chunk_index: int
    duration_ms: int
    wav_bytes: bytes


@dataclass(frozen=True)
class TtsResult:
    chunks: list[TtsChunkResult] = field(default_factory=list)
    tts_model_id: str = "stub-kokoro"
    tts_model_version: str = "1.0.0"
    voice_id: str = "female_01"


def chunk_text_for_speech(text: str, max_chars: int = 280) -> list[str]:
    """
    Chunks text at paragraph/sentence boundaries (never mid-word) so long
    documents synthesize reliably and chunks join cleanly.
    """
    if not text or not text.strip():
        return []
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    for para in paragraphs:
        if len(para) <= max_chars:
            chunks.append(para)
            continue
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", para) if s.strip()]
        current = ""
        for sentence in sentences:
            candidate = f"{current} {sentence}".strip()
            if len(candidate) <= max_chars:
                current = candidate
            else:
                if current:
                    chunks.append(current)
                current = sentence
        if current:
            chunks.append(current)
    return chunks


def _words_to_pcm16_samples(text: str, speed_percent: int) -> list[int]:
    """Deterministic waveform synthesis: word count drives amplitude pattern."""
    words = text.split()
    base_amplitude = 6000 + (len(words) % 7) * 900
    speed_factor = max(0.5, speed_percent / 100.0)
    samples_per_word = max(8, int(240 * speed_factor))
    samples: list[int] = []
    for word_index, word in enumerate(words):
        amplitude = base_amplitude + ((word_index * 37) % 1800)
        for sample_index in range(samples_per_word):
            phase = (sample_index / samples_per_word) * 3.14159
            value = int(amplitude * (0.6 + 0.4 * abs(phase - 1.57) / 1.57))
            if (word_index + sample_index) % 2:
                value = -value
            samples.append(max(-32768, min(32767, value)))
    return samples or [0]


def _build_wav_bytes(samples: list[int], sample_rate: int = 24000) -> bytes:
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
        sample_rate,
        sample_rate * 2,
        2,
        16,
        b"data",
        data_size,
    )
    return header + b"".join(struct.pack("<h", s) for s in samples)


class ReplaceableTtsAdapter:
    """Stable interface for standard TTS backends (Kokoro/CosyVoice plugged in later)."""

    tts_model_id: str = "stub-kokoro"
    tts_model_version: str = "1.0.0"

    def synthesize_chunk(
        self, *, text: str, language_code: str, voice_id: str, speed_percent: int
    ) -> TtsChunkResult:  # pragma: no cover - replaced by implementations
        raise NotImplementedError


class StubKokoroTtsAdapter(ReplaceableTtsAdapter):
    """Deterministic CPU-safe TTS adapter for CI/development without model weights."""

    tts_model_id = "stub-kokoro"
    tts_model_version = "1.0.0"

    def synthesize_chunk(
        self, *, text: str, language_code: str, voice_id: str, speed_percent: int
    ) -> TtsChunkResult:
        if not text.strip():
            raise ValueError("Chunk text must not be empty.")
        if not StandardVoiceCatalogue.voice_exists(language_code, voice_id):
            raise ValueError(
                f"Voice '{voice_id}' is not available for language '{language_code}'."
            )
        samples = _words_to_pcm16_samples(text, speed_percent)
        duration_ms = int(len(samples) / 24)  # 24kHz
        return TtsChunkResult(
            chunk_index=0,
            duration_ms=duration_ms,
            wav_bytes=_build_wav_bytes(samples),
        )


def get_default_tts_adapter() -> ReplaceableTtsAdapter:
    return StubKokoroTtsAdapter()


def apply_pronunciation_overrides(
    text: str, overrides: dict[str, str]
) -> str:
    """Applies organisation pronunciation dictionary entries before synthesis."""
    import re

    for word, phonetic_hint in overrides.items():
        if not word or not phonetic_hint:
            continue
        pattern = re.compile(r"\b" + re.escape(word) + r"\b", re.IGNORECASE)
        text = pattern.sub(phonetic_hint, text)
    return text


def join_chunks_with_normalisation(chunk_results: list[TtsChunkResult]) -> bytes:
    """
    Joins synthesized WAV chunks with loudness normalisation into one WAV asset.
    Peak-normalises the combined stream deterministically.
    """
    if not chunk_results:
        raise ValueError("No chunks to join.")

    all_samples: list[int] = []
    for chunk in chunk_results:
        wav_bytes = chunk.wav_bytes
        data_size = int.from_bytes(wav_bytes[40:44], "little")
        payload = wav_bytes[44 : 44 + data_size]
        for i in range(0, len(payload), 2):
            all_samples.append(int.from_bytes(payload[i : i + 2], "little", signed=True))

    peak = max((abs(s) for s in all_samples), default=1)
    target_peak = 26000
    if peak > 0 and peak != target_peak:
        scale = target_peak / peak
        all_samples = [
            max(-32768, min(32767, int(s * scale))) for s in all_samples
        ]

    return _build_wav_bytes(all_samples)
