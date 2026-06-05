from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class ComfyUIClient:
    def __init__(self, base_url: str, timeout_seconds: int = 600, max_retries: int = 3) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.session = self._create_session(max_retries)

    def _create_session(self, max_retries: int) -> requests.Session:
        session = requests.Session()
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def health_check(self) -> bool:
        try:
            response = self.session.get(f"{self.base_url}/system_stats", timeout=5)
            return response.status_code == 200
        except Exception:
            return False

    def load_workflow(self, workflow_path: str) -> dict[str, Any]:
        path = Path(workflow_path)
        if not path.exists():
            raise FileNotFoundError(f"Workflow file not found: {workflow_path}")
        with path.open("r", encoding="utf-8-sig") as f:
            return json.load(f)

    def submit_prompt(self, workflow: dict[str, Any]) -> str:
        payload = {"prompt": workflow}
        try:
            response = self.session.post(f"{self.base_url}/prompt", json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()
            return str(data.get("prompt_id", ""))
        except Exception as e:
            print("\n=== ComfyUI Request Failed ===")
            print(f"Error: {e}")
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_detail = e.response.json()
                    print(f"ComfyUI Error: {json.dumps(error_detail, indent=2)}")
                except:
                    print(f"Response text: {e.response.text}")
            print("\nWorkflow nodes being submitted:")
            for node_id in sorted(workflow.keys()):
                node = workflow[node_id]
                print(f"  Node {node_id}: {node.get('class_type', 'Unknown')}")
            raise

    def get_history(self, prompt_id: str) -> dict[str, Any]:
        response = self.session.get(f"{self.base_url}/history/{prompt_id}", timeout=30)
        response.raise_for_status()
        return response.json()

    def get_object_info(self) -> dict[str, Any]:
        response = self.session.get(f"{self.base_url}/object_info", timeout=30)
        response.raise_for_status()
        return response.json()

    def get_ltx_dependency_diagnostics(self) -> dict[str, Any]:
        """Return detailed LTX dependency readiness and available option lists."""
        try:
            info = self.get_object_info()
        except Exception as e:
            return {
                "ready": False,
                "reason": f"failed_to_query_object_info: {e}",
                "gemma_options": [],
                "text_encoder_options": [],
            }

        def _extract_options(node_name: str, field_name: str) -> list[str]:
            raw = (
                info.get(node_name, {})
                .get("input", {})
                .get("required", {})
                .get(field_name, [[]])
            )
            if not isinstance(raw, list) or len(raw) == 0:
                return []
            first = raw[0]
            if not isinstance(first, list):
                return []
            return [str(item) for item in first if str(item).strip()]

        gemma_options = _extract_options("LTXVGemmaCLIPModelLoader", "gemma_path")
        text_encoder_options = _extract_options("LTXAVTextEncoderLoader", "text_encoder")

        ready = len(gemma_options) > 0 and len(text_encoder_options) > 0
        if ready:
            reason = "ok"
        else:
            reason = (
                "ltx_text_encoders_missing"
                f"(gemma={len(gemma_options)},text_encoder={len(text_encoder_options)})"
            )

        return {
            "ready": ready,
            "reason": reason,
            "gemma_options": gemma_options,
            "text_encoder_options": text_encoder_options,
        }

    def ltx_dependencies_ready(self) -> tuple[bool, str]:
        """Detect whether required LTX text encoders are available in ComfyUI."""
        diag = self.get_ltx_dependency_diagnostics()
        return bool(diag.get("ready", False)), str(diag.get("reason", "unknown"))

    def wait_for_completion(self, prompt_id: str) -> dict[str, Any]:
        start = time.time()
        poll_interval = 2.0
        max_interval = 10.0
        backoff_factor = 1.2
        
        while True:
            try:
                history = self.get_history(prompt_id)
                if prompt_id in history:
                    return history[prompt_id]
            except requests.RequestException as e:
                if time.time() - start > self.timeout_seconds:
                    elapsed = int(time.time() - start)
                    raise TimeoutError(
                        f"ComfyUI job timed out after {elapsed}s (limit={self.timeout_seconds}s): {prompt_id}. "
                        "Consider increasing COMFYUI_TIMEOUT_SECONDS or lowering resolution/frame count."
                    ) from e
            
            if time.time() - start > self.timeout_seconds:
                elapsed = int(time.time() - start)
                raise TimeoutError(
                    f"ComfyUI job timed out after {elapsed}s (limit={self.timeout_seconds}s): {prompt_id}. "
                    "Consider increasing COMFYUI_TIMEOUT_SECONDS or lowering resolution/frame count."
                )
            
            time.sleep(poll_interval)
            poll_interval = min(poll_interval * backoff_factor, max_interval)
