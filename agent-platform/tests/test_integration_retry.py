"""
Integration test: QA fail → retry → success workflow
Tests that the retry branch of the graph correctly increments retry_count
and reflows through builder/render/qa without infinite loop.
"""
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from multi_agent_video.config import AppConfig
from multi_agent_video.graph import VideoPipeline


class MockComfyUIClientWithFailThenPass:
    """Mock that fails once (QA reject), then passes on retry"""
    def __init__(self) -> None:
        self.call_count = 0
        self.submitted_seeds = []

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
        return {
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},
            "3": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},
            "4": {"class_type": "KSampler", "inputs": {"seed": 1}},
        }

    def submit_prompt(self, workflow):
        self.call_count += 1
        seed = workflow["4"]["inputs"]["seed"]
        self.submitted_seeds.append(seed)
        return f"mock-prompt-id-{self.call_count}"

    def wait_for_completion(self, prompt_id: str):
        """Simulate QA failure on first call, success on second"""
        is_first_call = (self.call_count == 1)
        
        if is_first_call:
            # First render: simulate incomplete/low-quality result
            return {
                "status": {
                    "status_str": "success",
                    "messages": [
                        ["execution_start", {"timestamp": 0}],
                        ["execution_success", {"timestamp": 5000}],  # Very fast = likely failed
                    ],
                },
                "outputs": {
                    "8": {
                        "images": [{"filename": f"frame_{i:02d}.png"} for i in range(8)]  # Only 8 frames
                    }
                },
            }
        else:
            # Retry: proper quality result
            return {
                "status": {
                    "status_str": "success",
                    "messages": [
                        ["execution_start", {"timestamp": 0}],
                        ["execution_success", {"timestamp": 40000}],  # Proper render time
                    ],
                },
                "outputs": {
                    "8": {
                        "images": [{"filename": f"frame_{i:02d}.png"} for i in range(16)]  # Full 16 frames
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
        max_render_retries=2,  # Allow retries
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


def test_retry_branch_integration() -> None:
    print("=" * 70)
    print("Integration Test: QA Fail → Retry → Success")
    print("=" * 70)

    pipeline = VideoPipeline(config=build_test_config())
    mock_client = MockComfyUIClientWithFailThenPass()
    pipeline.client = mock_client

    app = pipeline.build()

    result = app.invoke(
        {
            "user_brief": "simple test scene",
            "seed": 100,
            "retry_count": 0,
            "workflow_path": "../workflow_sd15_simple.json",
        }
    )

    print(f"\n📊 Retry Statistics:")
    print(f"  Total submit calls: {mock_client.call_count}")
    print(f"  Seeds submitted: {mock_client.submitted_seeds}")
    print(f"  Final retry_count: {result['retry_count']}")
    print(f"  Final QA status: passed={result['qa_report']['passed']}")
    print(f"  Face score: {result['qa_report']['face']}")
    print(f"  Motion score: {result['qa_report']['motion']}")
    print(f"  Artifact score: {result['qa_report']['artifact']}")

    # Assertions
    assert mock_client.call_count == 2, f"Expected 2 submit calls, got {mock_client.call_count}"
    assert len(mock_client.submitted_seeds) == 2, f"Expected 2 seeds, got {len(mock_client.submitted_seeds)}"
    
    # First seed = base seed (100)
    # Second seed = base seed + retry_count (100 + 1)
    assert mock_client.submitted_seeds[0] == 100, f"First seed should be 100, got {mock_client.submitted_seeds[0]}"
    assert mock_client.submitted_seeds[1] == 101, f"Second seed should be 101 (100+1), got {mock_client.submitted_seeds[1]}"
    
    # Final result should pass after retry
    assert result["qa_report"]["passed"] is True, "Expected QA to pass after retry"
    assert result["retry_count"] == 1, f"Expected retry_count=1, got {result['retry_count']}"

    print("\n✅ Retry branch integration test passed!")
    print("   - QA correctly rejected incomplete render on first attempt")
    print("   - Retry correctly incremented seed (100 → 101)")
    print("   - Second render passed QA with 16 full frames")


if __name__ == "__main__":
    try:
        test_retry_branch_integration()
    except AssertionError as e:
        print(f"\n❌ Test assertion failed: {e}")
        sys.exit(1)
    except Exception as exc:
        print(f"\n❌ Test failed with exception: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
