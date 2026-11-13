# Development Handover Protocol

## When to hand over
Use a handover whenever OpenCode and Antigravity switch ownership, a task moves from design to implementation, implementation moves to review, or work pauses before completion.

## Handover packet
```md
# NEXUS Handover
Date/time:
From agent:
To agent:
Task / issue:
Branch and latest commit:
Objective and acceptance criteria:
Work completed:
Files changed:
Commands/tests run and exact results:
Screenshots or evidence:
Decisions made (with references):
Assumptions requiring owner approval:
Known defects and risks:
Uncommitted changes (must be disclosed):
Next exact action:
```

## Receiver checklist
1. Read the handover and referenced specifications.
2. Inspect branch, commit, working tree, and diff independently.
3. Re-run relevant checks when feasible.
4. Confirm the stated state before making further edits.
5. Ask for clarification if the handover omits a critical decision or leaves unclear ownership.

## No false completion
A handover saying “done” is not acceptance evidence. The receiver must verify the actual repository state and test results. Never discard uncommitted work or reset a branch without explicit authorization.
