# Agent Task Allocation

## Work allocation protocol
Every task must have one **accountable lead agent** and, where useful, one **review agent**. Do not assign both agents to modify the same files concurrently.

## Task classes
- **Architecture / schema / security boundary:** OpenCode drafts the change and rationale; Antigravity performs a challenge review before implementation or before merge.
- **UI / UX / visual system:** Antigravity may lead design exploration and produce a clear component/interaction specification; OpenCode integrates it into the canonical application and verifies behavior.
- **Backend / database / integration:** OpenCode leads; Antigravity reviews user flows, failure states, and visible behavior.
- **Independent review:** Reviewer inspects the diff and running feature without rewriting the lead's work unless assigned a separate fix branch.
- **Release / migration:** OpenCode prepares; both agents review; human owner authorizes production deployment.

## Task ticket template
```md
## Task
## User/business outcome
## Scope and explicit non-goals
## Relevant specification files
## Lead agent
## Review agent
## Files or modules expected to change
## Acceptance criteria
## Security/privacy considerations
## Required tests
## Dependencies and blockers
## Handover evidence
```

## Rules
- Split large tasks into small, independently testable slices.
- Assign exclusive file/module ownership for parallel work.
- If the task changes shared types, database schema, auth, permissions, or API contracts, pause parallel feature work until the contract is agreed.
- Do not let either agent invent product requirements to fill a gap. Record an assumption and request owner validation where needed.
