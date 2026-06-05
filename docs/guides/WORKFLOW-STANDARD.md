# Workflow Standard (Industrial)

## Plan Mode (Before Coding)
- Read relevant files and current architecture.
- List risks: compatibility, VRAM budget, regression.
- Define minimal change scope and verification steps.
- Only then implement.

## Compact Mode (After Major Steps)
- Save decisions, assumptions, unresolved issues.
- Save modified files and rollback strategy.
- Save next 3 actionable steps.

## Definition of Done
- Feature behavior validated.
- No new errors from static checks.
- Docs updated for changed workflow.
- Repro command is included.

## Cost Control Rules
- Prefer qwen2.5:7b or 14b local model first.
- Use heavier local model only for planning/review calls.
- Keep render retries bounded by MAX_RENDER_RETRIES.
- Cache prompt packs and workflow mappings when possible.
