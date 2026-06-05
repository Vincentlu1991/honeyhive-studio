# HoneyHive Studio Company Operations Platform

HoneyHive Studio 的本地优先公司管理与多 Agent 自动化平台。

本仓库不只是视频生成工具，而是一个公司级运营工程仓库，包含：
- 多 Agent 业务执行与编排系统（Supervisor / Story / Prompt / Builder / QA）
- 个人秘书与知识同步系统（文件、Telegram、Outlook 数据接入与分类）
- 项目管理资产（计划、报告、质量门、风险与安全文档）
- 可复用工作流与脚本体系（ComfyUI 工作流模板、自动化脚本、运维命令）

## Main Folders

- `agent-platform/` - 公司核心多 Agent 平台（Streamlit GUI、LangGraph pipeline、agents、tests、runtime scripts）。
- `personal-secretary/` - 个人秘书子系统（多源信息同步、自动分类、Dashboard）。
- `docs/` - 公司项目文档中心（规划、执行报告、指南、安全评估、商业化路线）。
- `scripts/` - 工作区级自动化脚本（质量门、上下文整理、知识流水线等）。
- Root `workflow_*.json` files - ComfyUI workflow templates kept at root for current environment compatibility.

## Company Scope (Current)

- 交付目标：构建可执行、可追踪、可复盘的公司级 AI 运营平台。
- 当前阶段：已完成首个基线版本落仓，并进入 GitHub 协作与里程碑推进阶段。
- 执行原则：本地优先、结构化交接、质量门先行、风险可回退。

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
