# Phase Prompt — Phase 3: Transcription (OpenCode Lead / Antigravity Review)

Implement transcription through a replaceable server-side ASR adapter, initially evaluating Whisper/faster-whisper.

Requirements:
- Supported format allowlist and media validation.
- Background jobs with progress, retry, idempotency, cancellation where safe.
- Language selection and recorded model/configuration metadata.
- Timestamped transcript segments and confidence metadata where available.
- Transcript editor with speaker labels, find/replace, undo, and revision history.
- Preserve original ASR output and human edits as separate revisions.
- Speaker diarisation is optional and must be labelled as model-suggested, not identity verification.
- Provide export-ready transcript data.

Create an evaluation harness using synthetic or explicitly authorised recordings. Measure WER by language, accent, noise, and meeting type. Do not claim perfect accuracy or universal language support.

Test long recordings, chunk boundaries, retries, duplicate job requests, tenant isolation, and failure recovery.
