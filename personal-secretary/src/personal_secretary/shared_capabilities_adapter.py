from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from personal_secretary.hermes_client import HermesClient


@dataclass
class SharedCapabilityError:
    code: str
    message: str
    retryable: bool = False
    reference_id: str = ""


@dataclass
class ReadDocumentsResult:
    docs: list[dict[str, Any]]
    redaction_counts: dict[str, int]
    errors: list[SharedCapabilityError]


@dataclass
class RankContextResult:
    contexts: list[dict[str, Any]]
    errors: list[SharedCapabilityError]


@dataclass
class LLMFallbackResult:
    text: str
    provider_used: str
    errors: list[SharedCapabilityError]


@dataclass
class MarkdownReportResult:
    markdown: str
    errors: list[SharedCapabilityError]


class SecretarySharedCapabilitiesAdapter:
    """Secretary-side implementation of shared capability contracts.

    This adapter mirrors the same four interfaces used by video pipeline integration:
    read_documents, rank_context, run_local_llm_with_fallback, build_markdown_report.
    """

    _SENSITIVE_PATTERNS = {
        "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
        "phone": re.compile(r"\b(?:\+?\d{1,3}[-\s]?)?(?:\d[-\s]?){7,14}\b"),
        "card_like": re.compile(r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b"),
    }

    def __init__(self, hermes: HermesClient) -> None:
        self._hermes = hermes

    def read_documents(self, docs: list[dict[str, Any]]) -> ReadDocumentsResult:
        redaction_counts: dict[str, int] = {}
        normalized_docs: list[dict[str, Any]] = []
        errors: list[SharedCapabilityError] = []

        for idx, row in enumerate(docs, start=1):
            doc_id = str(row.get("doc_id") or f"doc_{idx}")
            text = str(row.get("text") or row.get("extracted_text") or "")
            if not text.strip():
                errors.append(
                    SharedCapabilityError(
                        code="doc_empty_text",
                        message=f"Document {doc_id} has empty text.",
                        retryable=False,
                        reference_id=doc_id,
                    )
                )

            masked = text
            for key, pattern in self._SENSITIVE_PATTERNS.items():
                found = pattern.findall(masked)
                if found:
                    redaction_counts[key] = redaction_counts.get(key, 0) + len(found)
                    masked = pattern.sub(f"[{key}_redacted]", masked)

            normalized_docs.append(
                {
                    "doc_id": doc_id,
                    "title": str(row.get("title") or row.get("file_name") or doc_id),
                    "source": str(row.get("source") or ""),
                    "text": masked,
                }
            )

        return ReadDocumentsResult(
            docs=normalized_docs,
            redaction_counts=redaction_counts,
            errors=errors,
        )

    def rank_context(self, query: str, docs: list[dict[str, Any]], top_k: int = 5) -> RankContextResult:
        tokens = self._tokenize(query)
        scored: list[tuple[float, dict[str, Any]]] = []

        for row in docs:
            text = str(row.get("text") or "").lower()
            hits = sum(1 for token in tokens if token in text)
            numeric_bonus = 1.0 if re.search(r"\b\d+(?:\.\d+)?\b", text) else 0.0
            score = hits * 2.0 + numeric_bonus
            if score <= 0:
                continue
            scored.append((score, row))

        scored.sort(key=lambda x: x[0], reverse=True)
        contexts: list[dict[str, Any]] = []
        for i, (score, row) in enumerate(scored[: max(1, top_k)], start=1):
            contexts.append(
                {
                    "rank": i,
                    "score": round(float(score), 3),
                    "doc_id": str(row.get("doc_id") or ""),
                    "title": str(row.get("title") or ""),
                    "snippet": str(row.get("text") or "")[:600],
                }
            )

        return RankContextResult(contexts=contexts, errors=[])

    def run_local_llm_with_fallback(
        self,
        system_prompt: str,
        user_prompt: str,
        fallback_text: str,
        backend: str = "auto",
        ollama_base_url: str = "http://127.0.0.1:11434",
        ollama_model: str = "qwen2.5:7b-instruct",
        temperature: float = 0.2,
        timeout_seconds: int = 180,
    ) -> LLMFallbackResult:
        errors: list[SharedCapabilityError] = []
        try:
            prompt = f"System:\n{system_prompt}\n\nUser:\n{user_prompt}"
            text = self._hermes.run_prompt(
                prompt=prompt,
                backend=backend,
                ollama_base_url=ollama_base_url,
                ollama_model=ollama_model,
                temperature=temperature,
                timeout_seconds=timeout_seconds,
            )
            if text and not text.startswith("[ollama_error]") and not text.startswith("[hermes_error]"):
                return LLMFallbackResult(text=text.strip(), provider_used=backend or "auto", errors=[])
        except Exception as exc:
            errors.append(
                SharedCapabilityError(
                    code="secretary_llm_failed",
                    message=str(exc),
                    retryable=True,
                )
            )

        return LLMFallbackResult(
            text=fallback_text,
            provider_used="fallback_text",
            errors=errors,
        )

    def build_markdown_report(self, title: str, sections: list[dict[str, Any]]) -> MarkdownReportResult:
        lines = [f"# {title}", ""]
        for section in sections:
            heading = str(section.get("heading") or "Section")
            body = str(section.get("body") or "").strip()
            lines.append(f"## {heading}")
            lines.append(body if body else "- (empty)")
            lines.append("")
        return MarkdownReportResult(markdown="\n".join(lines).strip() + "\n", errors=[])

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        raw = (text or "").lower()
        tokens = set(re.findall(r"[a-z0-9_]{2,}|[\u4e00-\u9fff]{2,}", raw))
        return sorted(tokens, key=len, reverse=True)
