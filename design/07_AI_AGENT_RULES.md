# AI Agent Rules

## Required behavior for OpenCode and Antigravity
1. Start with repository reconnaissance. Identify framework, package manager, scripts, environment requirements, current branch, existing modules, and test coverage.
2. Read this file, `README.md`, `design/04_SHARED_PROJECT_CONTEXT.md`, and the relevant specifications before implementation.
3. Produce a short plan before broad or cross-cutting changes.
4. Ask for owner input where a missing decision affects product policy, privacy, consent, billing, retention, or external commitments.
5. Reuse established components, services, types and data contracts. Search before creating a new implementation.
6. Make the smallest coherent change that meets the task.
7. Never claim completion, deployment, test success, or security compliance without evidence.
8. Report limitations honestly, including tests that could not be run.
9. Keep user-facing content, logs and telemetry free of secrets and unnecessary sensitive meeting content.
10. Do not commit secrets, private keys, service-role credentials, tokens, or real user recordings/transcripts.

## Prohibited shortcuts
- Disabling RLS or authorization to make a feature work.
- Trusting client-supplied tenant IDs or role claims without server-side authorization.
- Logging raw audio, transcripts, access tokens, or voice samples unnecessarily.
- Bypassing recording notice/consent or voice authorization checks.
- Adding unapproved third-party services or sending user content to them without documenting data flow and approval.
- Marking placeholder, mocked, or demo behavior as production-ready.
- Replacing an existing subsystem without migration, compatibility and rollback analysis.

## Required final report
Summarize objective, implementation, files changed, tests actually run, results, security/privacy considerations, known gaps, branch/commit, and recommended next task.
