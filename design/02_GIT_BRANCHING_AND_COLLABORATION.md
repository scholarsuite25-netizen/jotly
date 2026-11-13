# Git Branching and Collaboration

## Repository workflow
Use GitHub as the canonical code history. Recommended lightweight model:
- `main`: protected, releasable code only.
- `develop` (optional): shared integration branch if the project needs a staging lane.
- `feat/<short-task>`: isolated feature work.
- `fix/<short-task>`: isolated bug fixes.
- `docs/<short-task>`: documentation-only changes.
- `chore/<short-task>`: tooling, dependencies, or maintenance.

For a small team, feature branches can target `main` directly if branch protection and CI checks are configured. Do not maintain `develop` merely for ceremony.

## Required workflow
1. Pull the latest base branch before starting.
2. Create a task-specific branch.
3. Confirm the working tree and files being changed.
4. Implement only the assigned scope.
5. Run formatting, lint, type checks, relevant tests, and build checks.
6. Review the diff for unrelated edits, secrets, generated noise, and accidental data changes.
7. Commit with a clear message and push the branch.
8. Open a pull request with summary, tests, screenshots where relevant, risks, and migration notes.
9. Obtain review and resolve conflicts deliberately.
10. Merge only after required checks pass and an authorized owner approves.

## Parallel-work safeguards
- Never have both agents editing the same branch or working tree at the same time.
- Use separate branches or separate worktrees for concurrent tasks.
- Agree shared interfaces before parallel implementation.
- Avoid two migrations that modify the same tables or constraints.
- Rebase/merge frequently enough to surface conflicts early, but do not overwrite another agent's uncommitted work.
- Never use force-push on shared branches without explicit owner approval.

## Pull request checklist
- [ ] Scope matches the task.
- [ ] Acceptance criteria are demonstrated.
- [ ] Tests and build pass.
- [ ] Database migration is reviewed and safe to apply.
- [ ] RLS/auth/authorization implications are reviewed.
- [ ] No secrets or private data are committed.
- [ ] Accessibility and responsive behavior are checked for UI changes.
- [ ] Documentation and decision records are updated.
- [ ] Rollback or recovery approach is stated for risky changes.
