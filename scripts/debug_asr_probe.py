import sys

sys.path.insert(0, "apps/api")
from app.services.asr_adapter import StubAsrAdapter, _estimate_duration_ms

wav = (
    b"RIFF" + (36 + 64).to_bytes(4, "little") + b"WAVEfmt " + (16).to_bytes(4, "little")
    + (1).to_bytes(2, "little") + (1).to_bytes(2, "little") + (16000).to_bytes(4, "little")
    + (32000).to_bytes(4, "little") + (2).to_bytes(2, "little") + (16).to_bytes(2, "little")
    + b"data" + (64).to_bytes(4, "little") + (b"\x01\x02" * 32)
)
print("len:", len(wav), "duration_ms:", _estimate_duration_ms(wav))
adapter = StubAsrAdapter()
result = adapter.transcribe(audio_bytes=wav, language_code="en", enable_diarisation=False)
print("segments:", len(result.segments), "model:", result.asr_model_id, "language:", result.detected_language)
for seg in result.segments:
    print(seg.sequence_number, seg.start_ms, seg.end_ms, repr(seg.text), seg.confidence, seg.speaker_key)
