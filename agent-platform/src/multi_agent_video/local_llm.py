from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


@dataclass
class LocalLLMConfig:
    provider: str
    base_url: str
    model: str
    timeout_seconds: int = 120
    max_retries: int = 2


class LocalLLM:
    """Production-grade local LLM wrapper with retry and fallback. Current provider: Ollama."""

    def __init__(self, config: LocalLLMConfig) -> None:
        self.config = config
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        session = requests.Session()
        retry_strategy = Retry(
            total=self.config.max_retries,
            backoff_factor=2,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["POST"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def health_check(self) -> bool:
        try:
            response = self.session.get(f"{self.config.base_url.rstrip('/')}/api/tags", timeout=5)
            return response.status_code == 200
        except Exception:
            return False

    def chat(self, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> str:
        if self.config.provider.lower() != "ollama":
            raise ValueError(f"Unsupported local LLM provider: {self.config.provider}")

        endpoint = f"{self.config.base_url.rstrip('/')}/api/chat"
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_ctx": 4096,
            },
        }

        try:
            response = self.session.post(endpoint, json=payload, timeout=self.config.timeout_seconds)
            response.raise_for_status()
            data = response.json()
            return str(data.get("message", {}).get("content", "")).strip()
        except requests.RequestException as e:
            raise RuntimeError(f"Ollama API call failed: {e}") from e


def extract_json_object(text: str) -> dict[str, Any] | None:
    """Try parsing whole text as JSON, then fallback to first {...} block."""
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        chunk = text[start : end + 1]
        try:
            data = json.loads(chunk)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            return None
    return None
