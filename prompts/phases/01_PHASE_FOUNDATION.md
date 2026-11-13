# Antigravity Prompt — Phase 1: Secure Foundation

Read the NEXUS documentation before coding. Inspect the current repository and report planned file changes first.

Implement only:
- project foundation and local development configuration
- database connection and migration framework
- authentication scaffolding using the selected OIDC approach
- organisation, workspace, membership, role, permission models
- server-side authorisation middleware/dependencies
- PostgreSQL tenant isolation/RLS baseline
- audit event service and sensitive-action event model
- automated tests for cross-tenant denial

Rules:
- Never trust organisation IDs supplied by the browser.
- Resolve tenant membership from authenticated server-side context.
- Test guessed IDs, direct API calls, and background-job tenant context.
- Do not add recording, transcription, TTS, or voice cloning in this phase.
- Do not add secrets to source control.
- Use migrations; do not mutate production schema manually.

Exit report must include changed files, migrations, tests, cross-tenant negative test evidence, remaining risks, and next phase recommendation.
