# Render Deployment Plan

## Current Blueprint

`render.yaml` has been added for a lightweight Streamlit control-plane preview:

- root directory: `agent-platform`
- runtime: Python
- start command: Streamlit on `$PORT`
- local LLM disabled by default
- ComfyUI URL must be supplied in Render Dashboard
- Sentry DSN is optional and marked as a secret

## Important Constraint

Render free web services are not a GPU rendering environment. This Blueprint is for a hosted control-plane demo only. Full commercial deployment should separate web orchestration from GPU rendering.

## Recommended Architecture

```text
Browser / ChatGPT App
-> Hosted control plane
-> Job queue
-> GPU worker running ComfyUI
-> Object storage
-> QA and delivery metadata
```

## Before Deployment

The repo currently has no Git remote. Render Blueprint deployment requires the repo to be pushed to GitHub, GitLab, or Bitbucket.

Checklist:

1. Create a GitHub repo.
2. Push this project.
3. Set `COMFYUI_BASE_URL` to a reachable worker endpoint.
4. Set `SENTRY_DSN` if production observability is desired.
5. Validate that the hosted control plane can reach the worker.

## Env Vars

| Key | Required | Notes |
| --- | --- | --- |
| `PYTHONPATH` | yes | `src` |
| `ENABLE_LOCAL_LLM` | yes | false for hosted control plane preview |
| `COMFYUI_BASE_URL` | yes for rendering | Set in Dashboard |
| `SENTRY_DSN` | optional | Set in Dashboard |
| `SENTRY_ENVIRONMENT` | yes | production |
