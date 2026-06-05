import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

_THIS_DIR = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(_THIS_DIR, "..", "src"))
sys.path.insert(0, os.path.join(_THIS_DIR, "..", "..", "personal-secretary", "src"))

from multi_agent_video.config import AppConfig
from multi_agent_video.graph import VideoPipeline
from personal_secretary.shared_capabilities_adapter import SecretarySharedCapabilitiesAdapter


class _FakeHermes:
    def run_prompt(self, prompt: str, **kwargs) -> str:
        return "ok"


class _MockComfyUIClient:
    def __init__(self) -> None:
        self.last_prompt = None

    def get_ltx_dependency_diagnostics(self):
        return {
            "ready": True,
            "reason": "ok",
            "gemma_options": ["mock-gemma"],
            "text_encoder_options": ["mock-text-encoder"],
        }

    def load_workflow(self, workflow_path: str):
        return {
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},
            "3": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},
            "4": {"class_type": "KSampler", "inputs": {"seed": 1}},
        }

    def submit_prompt(self, workflow):
        self.last_prompt = workflow
        return "bridge-prompt-id"

    def wait_for_completion(self, prompt_id: str):
        return {
            "status": {
                "status_str": "success",
                "messages": [
                    ["execution_start", {"timestamp": 0}],
                    ["execution_success", {"timestamp": 33000}],
                ],
            },
            "outputs": {
                "8": {
                    "images": [{"filename": f"frame_{i:02d}.png"} for i in range(16)]
                }
            },
        }


def _build_test_config() -> AppConfig:
    return AppConfig(
        comfyui_base_url="http://127.0.0.1:8188",
        comfyui_workflow_path="../workflow_sd15_simple.json",
        fallback_workflow_path="../workflow_sd15_simple.json",
        enable_workflow_fallback=True,
        comfyui_timeout_seconds=10,
        max_render_retries=1,
        strict_zero_retry=True,
        enable_local_llm=False,
        local_llm_provider="ollama",
        local_llm_base_url="http://127.0.0.1:11434",
        local_llm_model="qwen2.5:7b-instruct",
        local_llm_timeout_seconds=10,
        output_dir="E:/AI/outputs",
        cache_dir="E:/AI/cache",
        comfyui_path="E:/AI/ComfyUI_windows_portable",
        sentry_dsn="",
        sentry_environment="local",
        app_release="test",
        enable_online_research=False,
        online_research_base_url="https://api.openalex.org",
        online_research_timeout_seconds=5,
        online_research_max_results=3,
        enable_shared_context_injection=True,
        shared_context_top_k=3,
        enable_debug_workflow_dump=False,
    )


def test_cross_system_shared_context_bridge() -> None:
    adapter = SecretarySharedCapabilitiesAdapter(_FakeHermes())
    read_result = adapter.read_documents(
        [
            {
                "doc_id": "sec-1",
                "title": "secretary-report",
                "source": "secretary",
                "text": "Contact a@b.com. Character keeps black jacket in rainy neon city.",
            }
        ]
    )

    pipeline = VideoPipeline(config=_build_test_config())
    pipeline.client = _MockComfyUIClient()
    app = pipeline.build()

    result = app.invoke(
        {
            "user_brief": "generate rainy neon city portrait with black jacket",
            "seed": 7,
            "retry_count": 0,
            "workflow_path": "../workflow_sd15_simple.json",
            "evidence_documents": read_result.docs,
        }
    )

    assert result.get("shared_context", {}).get("ranked_count", 0) >= 1
    email_redactions = result.get("shared_context", {}).get("redaction_counts", {}).get("email", 0)
    assert email_redactions in (0, 1)

    submitted = pipeline.client.last_prompt
    assert submitted is not None
    positive = submitted["2"]["inputs"]["text"].lower()
    assert "evidence grounded details" in positive
    assert "[email_redacted]" in positive


if __name__ == "__main__":
    test_cross_system_shared_context_bridge()
