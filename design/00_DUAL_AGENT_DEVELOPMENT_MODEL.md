# NEXUS Dual-Agent Development Model

## Purpose
This document defines how OpenCode and Antigravity collaborate on one NEXUS Meeting Intelligence codebase. They are complementary development environments, not separate product teams or competing sources of truth.

## Operating model
- **OpenCode — primary implementation environment:** repository analysis, architecture implementation, database and API work, feature coding, debugging, automated tests, and technical documentation.
- **Antigravity — complementary design and engineering environment:** UI/UX exploration, visual refinement, implementation assistance, independent code review, browser-based validation where available, and test evidence.
- **GitHub — source of truth for code:** approved changes enter the shared repository through reviewed branches and pull requests.
- **Project documentation — source of truth for requirements and decisions:** the current specifications, decision log, and shared context govern both agents.

Either agent may lead a task when it is better suited to it. The role split is a default, not a technical restriction.

## Non-negotiable principles
1. One product, one approved architecture, one canonical database schema, and one shared backlog.
2. Read the relevant specifications and current project state before editing.
3. Never assume a feature, integration, environment variable, or test exists merely because a document describes it.
4. Do not silently change product requirements, data contracts, security boundaries, or approved decisions.
5. Use Git branches and commits to isolate work; avoid simultaneous edits to the same files.
6. Treat agent output as proposed code until tests, review, and acceptance checks pass.
7. Update documentation and decision records whenever approved behavior changes.
8. Protect credentials, user data, recordings, transcripts, and voice assets.

## Default division of work
| Workstream | Default lead | Supporting role |
|---|---|---|
| Repository inspection and implementation plan | OpenCode | Antigravity reviews |
| Product architecture and data contracts | OpenCode | Antigravity challenges assumptions |
| UI flows, interaction design, responsive polish | Antigravity | OpenCode implements/refactors |
| Database, RLS, APIs, integrations | OpenCode | Antigravity reviews |
| Feature implementation | OpenCode | Antigravity may implement assigned isolated tasks |
| Visual/browser QA | Antigravity | OpenCode fixes defects |
| Unit, integration and regression tests | OpenCode | Antigravity independently checks critical flows |
| Security and privacy review | Joint, independent passes | Both record findings |
| Release readiness | Joint | Human owner approves |

## Completion definition
A task is complete only when its acceptance criteria are met, relevant tests pass, security and privacy implications are addressed, documentation is updated, and the handover record identifies changed files, commit/branch, test evidence, known limitations, and next action.
