# Multi-Agent AI Video Generation Platform

Local-first multi-agent video generation project using Streamlit, LangGraph, Ollama, and ComfyUI.

## Main Folders

- `agent-platform/` - Python application, Streamlit GUI, LangGraph pipeline, agents, tests, and runtime scripts.
- `personal-secretary/` - Hermes-based personal file secretary (Telegram + Outlook + folder ingestion, auto classification, dashboard).
- `docs/` - Planning notes, reports, guides, research, ComfyUI notes, and security reviews.
- `scripts/` - Workspace-level helper scripts.
- Root `workflow_*.json` files - ComfyUI workflow templates kept at the root to preserve current `.env` paths.

## Common Commands

```powershell
cd "C:\Users\User\OneDrive\文档\New project\agent-platform"
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = "src"
streamlit run app_robust.py
```

Run basic agent checks:

```powershell
cd "C:\Users\User\OneDrive\文档\New project\agent-platform"
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -B tests\test_agents.py
```

Build LLM Wiki index:

```powershell
cd "C:\Users\User\OneDrive\文档\New project\agent-platform"
.\.venv\Scripts\python.exe scripts\build-knowledge-index.py
```

Knowledge config and outputs:

- `agent-platform/config/wiki_knowledge_config.json`
- `output/wiki/knowledge_index.json`
- `output/wiki/knowledge_state.json`

## Image-To-Video Flow

The Streamlit GUI supports optional reference image upload. Uploaded images are saved into the configured ComfyUI `input` folder, analyzed by `ImageAnalysisAgent`, and injected into `LoadImage` node `1` when the LTXV image-to-video workflow is selected.

Default image-to-video workflow:

```text
workflow_ltxv_img2video_test.json
```

## Security Notes

This project is currently safest as a local-only tool. Keep Streamlit, Ollama, and ComfyUI bound to localhost unless authentication, rate limiting, and workflow validation are added.

Security reports:

- `docs/security/agent-platform-threat-model.md`
- `docs/security/security-best-practices-report.md`

Commercialization docs:

- `docs/commercial/COMMERCIALIZATION-ROADMAP.md`
- `docs/commercial/RENDER-DEPLOYMENT-PLAN.md`
- `docs/commercial/CHATGPT-APP-PLAN.md`
- `docs/commercial/SECURITY-OWNERSHIP-MAP.md`

Generated commercial artifacts:

- `output/jupyter-notebook/video-workflow-quality-evaluation.ipynb`
- `output/pdf/multi-agent-video-commercial-one-pager.pdf`
