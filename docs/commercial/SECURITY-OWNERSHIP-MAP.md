# Security Ownership Map

This repository has no committed history yet, so a git-history ownership map cannot produce meaningful bus-factor data. The commercial ownership topology below is therefore based on current architecture and sensitive boundaries.

## Sensitive Components

| Area | Files | Commercial Risk | Suggested Owner |
| --- | --- | --- | --- |
| Upload handling | `agent-platform/app_robust.py` | malicious files, storage abuse, privacy | App Platform |
| Image analysis | `image_analysis_agent.py` | image metadata and user asset handling | AI Pipeline |
| Production planning | `production_planner_agent.py` | client-facing delivery logic | Product/AI Pipeline |
| Workflow injection | `builder_agent.py`, workflow JSON | workflow integrity, unsafe node use | AI Pipeline |
| ComfyUI API | `comfyui_client.py` | GPU job abuse, direct API exposure | Infrastructure |
| Local LLM API | `local_llm.py` | prompt privacy and prompt injection | AI Pipeline |
| Observability | `observability.py`, Sentry env vars | sensitive logs, production diagnostics | Infrastructure |
| Config/secrets | `.env`, `.env.example`, `config.py` | credential leakage and environment drift | Infrastructure |

## Bus-Factor Plan

Before commercial launch, create CODEOWNERS or an equivalent ownership table:

```text
/agent-platform/src/multi_agent_video/agents/ @ai-pipeline
/agent-platform/src/multi_agent_video/comfyui_client.py @infrastructure
/agent-platform/src/multi_agent_video/local_llm.py @ai-pipeline
/agent-platform/src/multi_agent_video/observability.py @infrastructure
/agent-platform/app_robust.py @app-platform
/workflow_*.json @ai-pipeline
/.env.example @infrastructure
```

## Required Review Rules

- Workflow JSON changes require AI Pipeline review.
- Upload/storage changes require App Platform and Infrastructure review.
- Any production deployment change requires Infrastructure review.
- Any rights/safety/business-delivery logic requires Product review.

## Next Step

After the first real commits, run the installed `security-ownership-map` skill against git history and compare the actual owners with this intended ownership map.
