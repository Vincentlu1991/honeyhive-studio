import os
import sys
from tempfile import TemporaryDirectory

from PIL import Image

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

    def ltx_dependencies_ready(self):
        return True, "ok"

    def get_ltx_dependency_diagnostics(self):
        return {
            "ready": True,
            "reason": "ok",
            "gemma_options": ["mock-gemma"],
            "text_encoder_options": ["mock-text-encoder"],
        }

    def load_workflow(self, workflow_path: str):
        if "sd15_simple" in str(workflow_path):
            return {
                "2": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},
                "3": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},
                "4": {"class_type": "KSampler", "inputs": {"seed": 1}},
            }

        return {
            "1": {"class_type": "LoadImage", "inputs": {"image": "old.png"}},
            "3": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},
            "4": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},
            "6": {"class_type": "KSampler", "inputs": {"seed": 1}},
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
                    ["execution_success", {"timestamp": 40000}],
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
        enable_local_llm=True,
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
    )


def test_pipeline_smoke() -> None:
    print("=" * 60)
    print("Running E2E Smoke Test (Mock ComfyUI)")
    print("=" * 60)

    pipeline = VideoPipeline(config=build_test_config())
    pipeline.client = MockComfyUIClient()

    app = pipeline.build()
    result = app.invoke(
        {
            "user_brief": "cyberpunk girl in rainy night",
            "seed": 42,
            "retry_count": 0,
            "workflow_path": "../workflow_sd15_simple.json",
        }
    )

    assert result["render_job_id"] == "mock-prompt-id"
    assert result["render_status"] == "completed"
    assert result["qa_report"]["passed"] is True
    assert result["qa_report"]["face"] >= 6
    assert result["qa_report"]["motion"] >= 6

    submitted = pipeline.client.last_prompt
    assert submitted is not None
    assert submitted["2"]["inputs"]["text"]
    assert submitted["3"]["inputs"]["text"]
    assert submitted["4"]["inputs"]["seed"] == 42

    print("E2E smoke test passed. ✓")


def test_pipeline_smoke_uploaded_image_identity_lock() -> None:
    print("=" * 60)
    print("Running E2E Smoke Test (Uploaded Image Identity Lock)")
    print("=" * 60)

    pipeline = VideoPipeline(config=build_test_config())
    pipeline.client = MockComfyUIClient()

    app = pipeline.build()
    with TemporaryDirectory() as tmp:
        image_path = os.path.join(tmp, "person.png")
        Image.new("RGB", (320, 320), color=(160, 120, 100)).save(image_path)

        _ = app.invoke(
            {
                "user_brief": "make the person smile and wave slowly",
                "input_image_path": image_path,
                "seed": 9,
                "retry_count": 0,
                "workflow_path": "../workflow_ltxv_img2video_test.json",
            }
        )

    submitted = pipeline.client.last_prompt
    assert submitted is not None
    pos_text = submitted["3"]["inputs"]["text"].lower()
    neg_text = submitted["4"]["inputs"]["text"].lower()

    assert (
        "same person as uploaded reference photo" in pos_text
        or "keep facial identity" in pos_text
    )
    assert "identity drift" in neg_text
    print("Uploaded-image identity lock test passed. ✓")


if __name__ == "__main__":
    try:
        test_pipeline_smoke()
        test_pipeline_smoke_uploaded_image_identity_lock()
    except Exception as exc:
        print(f"E2E smoke test failed: {exc}")
        raise
