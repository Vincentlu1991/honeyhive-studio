# Project Folder Organization Report (2026-06-03)

## Scope
- Safe, non-breaking organization for the root workspace.
- Keep all workflow files at root because current code and tests reference `../workflow_*.json`.

## Actions Completed
1. Cleaned transient cache directories at workspace root (`__pycache__` if present).
2. Preserved runtime-critical root workflow templates to avoid path regressions.
3. Added custom agent/prompt governance under `.github/agents` and `.github/prompts`.

## Current Root Layout Guidance
- Keep at root:
  - `workflow_*.json`
  - `ltx_example_t2v.json`
  - `CLAUDE.md`
  - `README.md`
- Keep application code in:
  - `agent-platform/`
  - `personal-secretary/`
- Keep docs and reports in:
  - `docs/`
  - `reports/`

## Why No Workflow Relocation
- Multiple files reference root workflow paths directly, including:
  - app runtime defaults
  - config mappings
  - tests
  - setup scripts
- Relocating now would require broad path migration and retesting.

## Next Suggested Step (Optional)
- If you want full structural migration, do it in a dedicated refactor branch with path rewrite + test matrix verification.
