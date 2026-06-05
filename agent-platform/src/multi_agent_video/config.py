from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass
class AppConfig:
    comfyui_base_url: str
    comfyui_workflow_path: str
    fallback_workflow_path: str
    enable_workflow_fallback: bool
    comfyui_timeout_seconds: int
    max_render_retries: int
    strict_zero_retry: bool
    enable_local_llm: bool
    local_llm_provider: str
    local_llm_base_url: str
    local_llm_model: str
    local_llm_timeout_seconds: int
    output_dir: str
    cache_dir: str
    comfyui_path: str
    sentry_dsn: str
    sentry_environment: str
    app_release: str
    enable_online_research: bool
    online_research_base_url: str
    online_research_timeout_seconds: int
    online_research_max_results: int
    enable_shared_context_injection: bool = False
    shared_context_top_k: int = 5
    enable_debug_workflow_dump: bool = False



def load_config() -> AppConfig:
    load_dotenv()

    enable_local_llm = os.getenv("ENABLE_LOCAL_LLM", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    enable_online_research = os.getenv("ENABLE_ONLINE_RESEARCH", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    enable_workflow_fallback = os.getenv("ENABLE_WORKFLOW_FALLBACK", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    strict_zero_retry = os.getenv("STRICT_ZERO_RETRY", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    return AppConfig(
        comfyui_base_url=os.getenv("COMFYUI_BASE_URL", "http://127.0.0.1:8188"),
        comfyui_workflow_path=os.getenv("COMFYUI_WORKFLOW_PATH", "../workflow_ltxv_img2video_test.json"),
        fallback_workflow_path=os.getenv("FALLBACK_WORKFLOW_PATH", "../workflow_sd15_i2v_realistic.json"),
        enable_workflow_fallback=enable_workflow_fallback,
        comfyui_timeout_seconds=int(os.getenv("COMFYUI_TIMEOUT_SECONDS", "600")),
        max_render_retries=int(os.getenv("MAX_RENDER_RETRIES", "2")),
        strict_zero_retry=strict_zero_retry,
        enable_local_llm=enable_local_llm,
        local_llm_provider=os.getenv("LOCAL_LLM_PROVIDER", "ollama"),
        local_llm_base_url=os.getenv("LOCAL_LLM_BASE_URL", "http://127.0.0.1:11434"),
        local_llm_model=os.getenv("LOCAL_LLM_MODEL", "qwen2.5:7b-instruct"),
        local_llm_timeout_seconds=int(os.getenv("LOCAL_LLM_TIMEOUT_SECONDS", "120")),
        output_dir=os.getenv("OUTPUT_DIR", "E:/AI/outputs"),
        cache_dir=os.getenv("CACHE_DIR", "E:/AI/cache"),
        comfyui_path=os.getenv("COMFYUI_PATH", "E:/AI/ComfyUI_windows_portable"),
        sentry_dsn=os.getenv("SENTRY_DSN", ""),
        sentry_environment=os.getenv("SENTRY_ENVIRONMENT", "local"),
        app_release=os.getenv("APP_RELEASE", "multi-agent-video@0.1.0"),
        enable_online_research=enable_online_research,
        online_research_base_url=os.getenv("ONLINE_RESEARCH_BASE_URL", "https://api.openalex.org"),
        online_research_timeout_seconds=int(os.getenv("ONLINE_RESEARCH_TIMEOUT_SECONDS", "5")),
        online_research_max_results=int(os.getenv("ONLINE_RESEARCH_MAX_RESULTS", "3")),
        enable_shared_context_injection=os.getenv("ENABLE_SHARED_CONTEXT_INJECTION", "false").strip().lower() in {"1", "true", "yes", "on"},
        shared_context_top_k=max(1, int(os.getenv("SHARED_CONTEXT_TOP_K", "5"))),
        enable_debug_workflow_dump=os.getenv("ENABLE_DEBUG_WORKFLOW_DUMP", "false").strip().lower() in {"1", "true", "yes", "on"},
    )
