# Security Best Practices Report

## Executive Summary

This Python/Streamlit project is in a reasonable local-first prototype state, but it should not be exposed to a network without adding authentication, job controls, workflow validation, and safer debug behavior. The most important improvements are keeping local services bound to localhost, constraining workflow files, limiting prompt/render inputs, and avoiding runtime dependency installation.

## High Severity

### SBP-001: No authentication or job throttling for expensive render actions

Impact: If Streamlit is exposed on LAN or the internet, any reachable user can trigger GPU-heavy ComfyUI renders.

Evidence:

- `agent-platform/app_robust.py` exposes render execution through `st.button(...)`.
- `agent-platform/src/multi_agent_video/graph.py` submits jobs to ComfyUI and waits up to the configured timeout.

Recommendation:

- Keep Streamlit bound to localhost during development.
- Before any shared deployment, add authentication and authorization.
- Add max prompt length, max concurrent render jobs, cooldowns, and per-session limits.

### SBP-002: ComfyUI direct exposure would bypass app checks

Impact: If `127.0.0.1:8188` is changed to a LAN/public binding, attackers can submit jobs directly to ComfyUI.

Evidence:

- `COMFYUI_BASE_URL=http://127.0.0.1:8188` in `.env.example`.
- `ComfyUIClient.submit_prompt` posts raw workflow payloads to `/prompt`.

Recommendation:

- Document localhost-only ComfyUI as a security requirement.
- Add startup checks that warn when `COMFYUI_BASE_URL` is not localhost.
- Use firewall rules or reverse proxy authentication before network exposure.

## Medium Severity

### SBP-003: Workflow path is configurable without directory allowlist

Evidence:

- `AppConfig.comfyui_workflow_path` is read from environment.
- `ComfyUIClient.load_workflow` opens the configured path and parses JSON.

Recommendation:

- Store approved workflows under a known directory.
- Resolve paths and reject files outside that directory.
- Validate workflow shape and expected node IDs before submission.

### SBP-004: Debug and error details may leak local paths

Evidence:

- `app_robust.py` displays `traceback.format_exc()` in the UI.
- `ComfyUIClient.submit_prompt` prints submitted node classes on failures.

Recommendation:

- Add `DEBUG=false` by default.
- Show friendly errors to users and write full traces only to local logs.

### SBP-005: Runtime dependency installation in video script

Evidence:

- `agent-platform/scripts/create_video.py` installs `moviepy` at runtime when missing.

Recommendation:

- Add `moviepy` as an optional documented dependency or fail with an install instruction.
- Avoid automatic package installation inside runtime scripts.

## Low Severity

### SBP-006: Windows console encoding breaks tests

Evidence:

- Direct test execution failed when printing checkmark/cross characters under GBK.

Recommendation:

- Reconfigure stdout/stderr to UTF-8 in scripts or use ASCII-only status text.
- Keep source files UTF-8 and configure editors consistently.

### SBP-007: Generated cache and environment files need git hygiene

Evidence:

- `.venv`, `__pycache__`, and `.env` exist inside the project tree.
- No `.gitignore` existed before this review.

Recommendation:

- Keep `.venv`, `.env`, `__pycache__`, outputs, and generated media out of git.
- Keep `.env.example` committed as the safe template.

## Suggested Fix Order

1. Add `.gitignore` and remove generated cache files from the working tree.
2. Keep ComfyUI/Ollama localhost-only and document that requirement.
3. Add workflow directory allowlisting and schema checks.
4. Add debug-mode gating around traceback output.
5. Replace runtime `pip install` in `create_video.py` with a clear error message.
