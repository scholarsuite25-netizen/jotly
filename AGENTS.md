# AGENTS.md — NEXUS Meeting Intelligence

This file is the repository-level operating guide for OpenCode and any coding agent that reads `AGENTS.md`. Treat the Markdown specifications in this kit as the approved product source of truth.

## Role and first action
You are the primary implementation agent by default. Antigravity is the complementary design, visual QA and independent review agent. Before changing anything, inspect the repository, branch, working tree, framework, package manager, scripts, database, migrations, authentication, storage, tests and deployment setup. Read `README.md`, the relevant files under `docs/`, `design/00_DUAL_AGENT_DEVELOPMENT_MODEL.md`, `design/04_SHARED_PROJECT_CONTEXT.md`, `design/07_AI_AGENT_RULES.md`, and the relevant phase prompt.

Your first response must be a repository assessment and phased implementation plan. State explicitly that no files were changed. Do not modify code until the owner approves the plan, unless implementation has been explicitly authorised.

## Product and architecture constraints
- NEXUS Meeting Intelligence is a standalone multi-tenant enterprise product, not a module of Nexus Business Suite ERP.
- Follow `docs/product/PRODUCT_REQUIREMENTS.md`, `docs/architecture/SYSTEM_ARCHITECTURE.md`, `docs/data-and-api/`, and the security/privacy specifications.
- Do not silently invent product policies, vendors, frameworks, APIs, costs or data flows. Record unresolved decisions in `docs/architecture/DECISION_LOG.md`.
- Preserve existing working code and conventions. Do not create duplicate authentication, tenant, storage, transcription, AI, document or voice subsystems.
- Enforce organisation/tenant isolation at API, database, storage, search, cache, queues and AI retrieval layers. Never rely on frontend-only authorization.
- Treat recordings, transcripts, meeting documents and voice assets as sensitive. Minimise collection, access, retention and logging. Do not train on customer recordings by default.
- Voice cloning and identity-replicating features must remain disabled until consent, identity/authority verification, licensing, revocation, security and abuse-prevention gates are approved and tested. A recording agreement is not permission to clone a voice.
- Never expose secrets, model credentials, unrestricted storage URLs, arbitrary SQL or shell access to the browser or an AI model. Never commit secrets or real user content.

## Implementation discipline
- Work in small, task-specific changes on a dedicated Git branch. Do not edit the same files concurrently with Antigravity.
- Use the existing stack and package manager unless an approved decision changes them. Treat technology choices in the architecture as candidates where the specification says they require evaluation.
- Make migrations reviewable and reversible where practical. Validate tenant policies, permissions, error handling, retries, accessibility and responsive states.
- Run the repository's actual format, lint, type, unit, integration, end-to-end and build checks as applicable. Report exact commands and outcomes; never claim a test passed unless it ran successfully.
- Update documentation and decision records when approved requirements or architecture change.

## Collaboration
- GitHub and the shared repository are the code source of truth. Approved specifications and decision records are the product source of truth.
- Use separate branches and pull requests for agent work. Do not allow simultaneous edits to the same files or shared working tree.
- Before handover, disclose changed files, branch/commit, tests, risks and unresolved issues. Follow `design/05_DEVELOPMENT_HANDOVER_PROTOCOL.md`.
- Request Antigravity to perform independent review or visual validation; do not ask it to overwrite active OpenCode work.

## Required completion report
For every implementation task report: summary; changed files; branch and commit; tests actually run and results; security/privacy review; assumptions; limitations; handover notes; next recommended task.

## Specification map
- Product: `docs/product/`
- Architecture and decisions: `docs/architecture/`
- Data and APIs: `docs/data-and-api/`
- Security and privacy: `docs/security-and-privacy/`
- AI, audio and media: `docs/ai-and-media/`
- Testing and operations: `docs/quality-and-operations/`
- Dual-agent collaboration: `design/`
- Agent and phase prompts: `prompts/`
