from __future__ import annotations

import os
import subprocess
from pathlib import Path

import requests

from personal_secretary.config import SecretaryConfig


class HermesClient:
    def __init__(self, config: SecretaryConfig) -> None:
        self.config = config

    def summarize(self, title: str, text: str) -> str:
        prompt = (
            "You are a personal secretary assistant. "
            "Summarize this file into: key points, action items, possible tags, and one-line conclusion.\n\n"
            f"Title: {title}\n"
            f"Content:\n{text[:12000]}"
        )
        return self.run_prompt(prompt)

    def answer(
        self,
        question: str,
        context: str,
        backend: str = "auto",
        ollama_base_url: str = "http://127.0.0.1:11434",
        ollama_model: str = "qwen2.5:7b-instruct",
        temperature: float = 0.2,
        timeout_seconds: int = 180,
    ) -> str:
        prompt = (
            "You are Lu Weixiong's project manager and executive secretary. "
            "Reply naturally in Chinese like a real human on chat, not like a stiff template. "
            "First infer the user's actual intent, then use only the most relevant context to analyze, summarize evidence, and answer. "
            "If the evidence is insufficient, say clearly what is known, what is uncertain, and what should be checked next.\n\n"
            f"Question:\n{question}\n\n"
            f"Context:\n{context[:16000]}"
        )
        return self.run_prompt(
            prompt,
            backend=backend,
            ollama_base_url=ollama_base_url,
            ollama_model=ollama_model,
            temperature=temperature,
            timeout_seconds=timeout_seconds,
        )

    def run_prompt(
        self,
        prompt: str,
        backend: str = "auto",
        ollama_base_url: str = "http://127.0.0.1:11434",
        ollama_model: str = "qwen2.5:7b-instruct",
        temperature: float = 0.2,
        timeout_seconds: int = 180,
    ) -> str:
        backend_normalized = (backend or "auto").strip().lower()

        if backend_normalized == "ollama":
            output = self._run_ollama(
                prompt=prompt,
                base_url=ollama_base_url,
                model=ollama_model,
                temperature=temperature,
                timeout_seconds=timeout_seconds,
            )
            return output or self._fallback_summary(prompt)

        if backend_normalized == "hermes":
            output = self._run_hermes(prompt=prompt, timeout_seconds=timeout_seconds)
            return output or self._fallback_summary(prompt)

        hermes_output = self._run_hermes(prompt=prompt, timeout_seconds=timeout_seconds)
        if hermes_output:
            return hermes_output

        ollama_output = self._run_ollama(
            prompt=prompt,
            base_url=ollama_base_url,
            model=ollama_model,
            temperature=temperature,
            timeout_seconds=timeout_seconds,
        )
        if ollama_output:
            return ollama_output

        return self._fallback_summary(prompt)

    def _run_hermes(self, prompt: str, timeout_seconds: int) -> str:
        exe = self._find_exe()
        if not exe:
            return ""

        try:
            completed = subprocess.run(
                [str(exe), "-z", prompt],
                check=False,
                capture_output=True,
                text=False,
                timeout=timeout_seconds,
            )
            output = self._decode_output(completed.stdout).strip()
            if output:
                return output
            if completed.stderr:
                return f"[hermes_error] {self._decode_output(completed.stderr).strip()}"
            return ""
        except Exception:
            return ""

    def _run_ollama(
        self,
        prompt: str,
        base_url: str,
        model: str,
        temperature: float,
        timeout_seconds: int,
    ) -> str:
        endpoint = f"{base_url.rstrip('/')}/api/chat"
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are Lu Weixiong's project manager and executive secretary. "
                        "Answer naturally in Chinese, stay evidence-based, and avoid robotic phrasing."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_ctx": 4096,
            },
        }
        try:
            response = requests.post(endpoint, json=payload, timeout=timeout_seconds)
            response.raise_for_status()
            data = response.json()
            return str(data.get("message", {}).get("content", "")).strip()
        except Exception as exc:
            return f"[ollama_error] {exc}"

    def _find_exe(self) -> Path | None:
        if self.config.hermes_exe:
            p = Path(self.config.hermes_exe)
            if p.exists():
                return p

        default = Path(os.getenv("LOCALAPPDATA", "")) / "hermes" / "hermes-agent" / "venv" / "Scripts" / "hermes.exe"
        if default.exists():
            return default
        return None

    @staticmethod
    def _decode_output(data: bytes | str | None) -> str:
        if data is None:
            return ""
        if isinstance(data, str):
            return data
        for enc in ("utf-8", "gbk"):
            try:
                return data.decode(enc)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="replace")

    @staticmethod
    def _fallback_summary(text: str) -> str:
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        preview = "\n".join(lines[:8])
        return (
            "Hermes unavailable. Fallback summary:\n"
            f"- Approx length: {len(text)} chars\n"
            "- Preview:\n"
            f"{preview}"
        )
