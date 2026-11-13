# Phase Prompt — Phase 5: Standard Voice Studio and TTS (OpenCode Lead / Antigravity Review)

Implement document-to-speech using standard, non-cloned voices first.

Requirements:
- User uploads DOCX/PDF/TXT or pastes text.
- Extract text and require review before synthesis.
- Provide supported language/voice selection, pronunciation entries, and speed.
- Chunk at paragraph/sentence boundaries.
- Queue long synthesis jobs; make them resumable and idempotent.
- Normalize loudness, join chunks, optionally add chapter markers.
- Export configured WAV/MP3/OGG formats.
- Player supports pause, seek, speed, skip intervals, and chapters where available.
- Store model ID/version, voice ID, settings, output metadata, and audit event.
- Label generated speech appropriately.

Do not enable voice cloning in this phase. Test pronunciation, intelligibility, naturalness, chunk continuity, long-document completion, and download metadata.
