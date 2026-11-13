# Antigravity Prompt — Phase 2: Recording and Media

Implement browser microphone recording and media management only after Phase 1 acceptance.

Requirements:
- Meeting creation with title, date/time, agenda, attendees, workspace, visibility.
- Recording notice and consent reminder before capture.
- Start/pause/resume/stop, input selection, level meter, elapsed time, clear state.
- Chunked resumable upload to private object storage.
- Validate file type, size, signature, quota, and checksum.
- Preserve original media separately from derivatives.
- Media metadata, playback, retention metadata, and audit events.
- Recovery after network interruption and safe warning before navigation away.
- Asynchronous media validation/normalisation worker.
- Tenant-aware limits and bounded queues.

Tests: interrupted upload, duplicate chunks, invalid file type, oversized file, checksum mismatch, permission denial, cross-tenant access, and playback URL expiry.

Do not implement desktop/system-audio capture in this phase.
