# ChatGPT App Plan

## Archetype

Primary archetype: `interactive-decoupled`.

The future ChatGPT App should expose tool calls for planning, analyzing assets, starting jobs, checking status, and rendering a widget-based job dashboard. The video generation itself should stay behind a hosted API or worker queue.

## Tool Plan

| Tool | Purpose | Mutates State |
| --- | --- | --- |
| `analyze_reference_image` | Analyze an uploaded image and return production context | No |
| `plan_video_job` | Convert a creative brief into workflow, cost, risk, and shot plan | No |
| `create_video_job` | Submit a generation job to the platform queue | Yes |
| `get_video_job` | Fetch status, QA report, and output links | No |
| `revise_video_job` | Create a revision from feedback | Yes |

## Widget Plan

The widget should show:

- uploaded/reference image preview
- production plan
- job status timeline
- QA scores
- generated output links
- revision controls

## Production Requirements

- Public HTTPS MCP endpoint.
- Authentication and per-user asset isolation.
- S3-compatible storage for uploads and outputs.
- Queue-backed worker model.
- Sentry and metrics for tool failures.
- CSP allowlist for widget resources and API domains.

## Why Not Build It Yet

The current repo is a local-first Streamlit workstation app. A ChatGPT App should be added after the platform has:

- persistent job records
- a queue
- an API layer
- hosted asset storage
- auth

That sequence avoids wrapping a local-only prototype in a public interface too early.
