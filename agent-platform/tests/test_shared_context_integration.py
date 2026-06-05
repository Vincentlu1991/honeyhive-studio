import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from multi_agent_video.config import AppConfig
from multi_agent_video.graph import VideoPipeline


class MockComfyUIClient:
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
        return "mock-prompt-id"

    def wait_for_completion(self, prompt_id: str):
        return {
            "status": {
                "status_str": "success",
                "messages": [
                    ["execution_start", {"timestamp": 0}],
                    ["execution_success", {"timestamp": 35000}],
                ],
            },
            "outputs": {
                "8": {
                    "images": [{"filename": f"frame_{i:02d}.png"} for i in range(16)]
                }
            },
        }


def build_test_config() -> AppConfig:
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


def test_shared_context_injection_end_to_end() -> None:
    pipeline = VideoPipeline(config=build_test_config())
    pipeline.client = MockComfyUIClient()

    app = pipeline.build()
    result = app.invoke(
        {
            "user_brief": "make a cyberpunk portrait in rainy neon city",
            "seed": 42,
            "retry_count": 0,
            "workflow_path": "../workflow_sd15_simple.json",
            "evidence_documents": [
                {
                    "doc_id": "e1",
                    "title": "reference-note",
                    "source": "integration-test",
                    "text": "Character email a@b.com, keep black jacket, rainy neon reflections.",
                }
            ],
        }
    )

    assert "shared_context" in result
    assert result["shared_context"]["ranked_count"] >= 1
    assert result["shared_context"]["redaction_counts"].get("email", 0) == 1

    submitted = pipeline.client.last_prompt
    assert submitted is not None
    positive_text = submitted["2"]["inputs"]["text"].lower()
    assert "evidence grounded details" in positive_text
    assert "[email_redacted]" in positive_text


if __name__ == "__main__":
    test_shared_context_injection_end_to_end()
