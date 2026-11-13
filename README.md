# NEXUS Meeting Intelligence — OpenCode Project Kit

This is a Markdown-only project documentation kit organised for use in an existing OpenCode repository. It contains no application source code, binary assets, environment files or runtime configuration.

## OpenCode quick start
1. Extract this kit.
2. Copy the contents of `NEXUS_OPENCODE_PROJECT_KIT/` into the root of your NEXUS application repository. Merge folders if they already exist; do not overwrite application files.
3. Ensure `AGENTS.md` is at the repository root. OpenCode uses it as the main project instruction file.
4. Open the repository in OpenCode and ask it to **inspect the repository only**. It must read `AGENTS.md` and the linked specifications, then return a gap analysis and phased implementation plan without changing code.
5. After reviewing the plan, approve one phase at a time using the relevant prompt in `prompts/phases/`.
6. Use `prompts/antigravity/MASTER_ANTIGRAVITY_PROMPT.md` when assigning independent design/review work to Antigravity.

## If folder upload is failing
You do not need to upload the entire folder as a chat attachment. Put the extracted Markdown files directly into your local project repository. If the interface accepts only one file, start by adding the standalone root `AGENTS.md`; then add the rest of the kit to the repository using your computer's file manager. The ZIP is simply a convenient transfer package.

## Folder structure
```text
NEXUS_OPENCODE_PROJECT_KIT/
├── AGENTS.md                 # OpenCode auto-read project instructions
├── README.md                 # Setup and navigation
├── docs/                     # Product and engineering specifications
│   ├── product/
│   ├── architecture/
│   ├── data-and-api/
│   ├── security-and-privacy/
│   ├── ai-and-media/
│   └── quality-and-operations/
├── design/                   # OpenCode + Antigravity collaboration rules
└── prompts/                  # Master and phase-specific prompts
    ├── opencode/
    ├── antigravity/
    └── phases/
```

## Operating model
OpenCode is the default primary implementation agent. Antigravity supports product/design exploration, visual QA and independent review. Either may be assigned a task explicitly. Git branches and pull requests coordinate work; never allow both agents to edit the same files concurrently.

## Important product safeguards
- NEXUS is a standalone multi-tenant product.
- Tenant isolation and server-side authorization are mandatory.
- Recordings, transcripts and voice assets are sensitive data.
- Voice cloning stays disabled until every documented consent, verification, licensing, revocation, security and abuse-prevention gate is approved and tested.
- The kit is a specification, not evidence that the application has been implemented or tested.
