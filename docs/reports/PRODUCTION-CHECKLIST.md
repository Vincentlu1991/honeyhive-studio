# Production Deployment Checklist

## Pre-launch (Development)
- [ ] Run health check: `scripts/health-check.ps1`
- [ ] Test with sample workflow
- [ ] Verify Ollama model is pulled: `ollama pull qwen2.5:14b-instruct`
- [ ] Test retry logic by temporarily stopping ComfyUI

## Launch Sequence
1. Start Ollama: `ollama serve`
2. Start ComfyUI
3. Run health check
4. Launch GUI: `streamlit run app_robust.py`

## Cost Optimization
- Use qwen2.5:7b for simple tasks
- Use qwen2.5:14b only for Supervisor/Prompt agents
- Set MAX_RENDER_RETRIES=2 (avoid excessive retries)
- Monitor VRAM with: `nvidia-smi -l 2`

## Common Issues & Fixes

### Ollama timeout
- Increase LOCAL_LLM_TIMEOUT_SECONDS in .env
- Check model size fits in memory
- Use smaller model if needed

### ComfyUI timeout
- Increase COMFYUI_TIMEOUT_SECONDS in .env
- Reduce workflow resolution/frames
- Check VRAM usage

### Workflow file not found
- Verify COMFYUI_WORKFLOW_PATH in .env
- Use absolute path if relative path fails

## Monitoring
- Check terminal logs for retry events
- Monitor exponential backoff behavior
- Track QA pass rate over time
