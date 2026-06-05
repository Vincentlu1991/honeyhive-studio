# Commercialization Roadmap

## Positioning

Multi-Agent AI Video Generation Platform should be positioned as a local-first creative automation studio for image-to-video and prompt-to-video production. The strongest wedge is controlled, repeatable video generation for creators, agencies, and small studios that need predictable outputs instead of one-off prompt experiments.

## Applied Skills

- `jupyter-notebook`: created a quality evaluation notebook for reproducible prompt/workflow tests.
- `sentry`: added optional production error tracking via `SENTRY_DSN`.
- `security-ownership-map`: documented ownership and sensitive boundaries for commercial hardening.
- `render-deploy`: added a Render Blueprint for a hosted control-plane preview.
- `chatgpt-apps`: planned a future ChatGPT app surface.
- `pdf`: generated a partner/investor one-pager under `output/pdf/`.
- `figma-generate-design` and `figma-generate-library`: recommended next design-system workflow for a professional UI refresh.

## Product Tiers

| Tier | User | Value | Required Capabilities |
| --- | --- | --- | --- |
| Local Studio | Individual creator | Local GPU video generation with privacy | Streamlit GUI, local workflows, image upload |
| Agency Workbench | Small team | Repeatable client deliverables | project library, job history, presets, error tracking |
| Managed Control Plane | Studio/business | Remote orchestration over GPU workers | auth, queue, worker registration, billing hooks |
| ChatGPT App | ChatGPT users | Guided creative brief-to-video workflow | MCP tools, hosted API, secure asset handling |

## Agent Roadmap

Current agents:

- Supervisor Agent
- Image Analysis Agent
- Production Planner Agent
- Story Agent
- Prompt Agent
- Builder Agent
- QA Agent

Recommended next agents:

- Rights & Safety Agent: checks uploaded asset ownership, public-figure risk, brand/logo risk, and policy notes.
- Cost & Capacity Agent: estimates GPU minutes, queue time, retry budget, and output cost.
- Shot List Agent: converts a campaign brief into multiple shots with continuity notes.
- Delivery Agent: packages final MP4/GIF, prompt metadata, seed, workflow version, and license notes.
- Client Review Agent: summarizes output quality and creates human-readable revision instructions.

## Commercial Hardening Priorities

1. Add job records: prompt, seed, workflow, image hash, status, output path, failure reason.
2. Add a queue before ComfyUI calls to prevent concurrent GPU overload.
3. Add authentication before LAN/public use.
4. Add Sentry DSN in production for crash/failure telemetry.
5. Add workflow allowlisting and node schema validation.
6. Add a project/output library with reproducibility metadata.
7. Add rights/safety review before delivery.
8. Add evaluation notebook runs to compare workflow presets.

## Deployment Strategy

Render can host a lightweight control-plane preview, but GPU rendering should remain on local or dedicated GPU workers. The included `render.yaml` is best used for UI/control-plane demos, not full ComfyUI GPU rendering.

Recommended production split:

- Web control plane: Render/Fly/Container App.
- GPU workers: local workstation, RunPod, Lambda Labs, Vast.ai, or self-hosted ComfyUI.
- Storage: S3-compatible object storage for uploaded references and outputs.
- Observability: Sentry for app errors; metrics for render duration and failure rate.

## Next Build Slice

The next high-ROI engineering slice is a persistent Job model:

- `job_id`
- `created_at`
- `user_brief`
- `input_image_path`
- `image_hash`
- `workflow_path`
- `seed`
- `status`
- `render_job_id`
- `qa_report`
- `output_files`
- `error_summary`

This is the foundation for billing, team collaboration, retries, and client delivery.
