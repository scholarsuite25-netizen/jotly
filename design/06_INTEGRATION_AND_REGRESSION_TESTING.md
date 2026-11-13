# Integration and Regression Testing

## Purpose
Changes from either agent must be tested in the shared application context, not only in isolation.

## Minimum checks
Run the scripts that actually exist in the repository; do not invent command names. Typical checks may include:
- Formatting and lint.
- Static type checking.
- Unit tests for changed modules.
- Integration tests for APIs, database access, storage and background jobs.
- End-to-end tests for affected user journeys.
- Production build.
- Migration validation and rollback review where applicable.

## NEXUS critical regression areas
- Authentication, session lifecycle, account recovery and role permissions.
- Tenant/workspace boundaries and row-level security.
- Meeting creation, participant access and sharing permissions.
- Recording start/stop, upload, processing status and failure recovery.
- Recording consent, notice, consent records and restricted access.
- Transcription accuracy workflow, speaker attribution and transcript correction.
- Meeting summaries, action items, decisions and document export.
- Search/retrieval access controls and source traceability.
- Text-to-speech and any consent-governed voice features.
- Retention, export, deletion and audit events.
- Notifications, integrations, rate limits and background task retries.

## Test evidence record
For each task, record command, environment, date, pass/fail, and relevant output. Separate automated test results from manual checks. Never use production personal data in development tests; use synthetic or appropriately anonymized fixtures.

## Release gate
No release if there is a blocker/high security or privacy issue, a failed critical user journey, an unreviewed destructive migration, or missing evidence for a critical acceptance criterion.
