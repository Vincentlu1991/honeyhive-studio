# Subagents Collaboration Guide

## Primary Session (Supervisor)
- Owns objective, scope, and release criteria.
- Delegates focused tasks and merges results.

## Specialist Subagents
- Debug subagent: isolate runtime/API failures.
- Test subagent: execute test/check commands and summarize failures.
- Docs subagent: align README, playbook, and examples with latest code.

## Hand-off Contract
- Input: target files, expected output, constraints.
- Output: changed files list, evidence, residual risks.

## Non-negotiables
- No destructive cleanup without explicit criteria.
- Keep changes minimal and traceable.
- Report assumptions when uncertain.
