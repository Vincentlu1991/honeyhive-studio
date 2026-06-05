from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from personal_secretary.hermes_client import HermesClient


@dataclass
class _Chunk:
    chunk_id: str
    file_name: str
    local_path: str
    file_type: str
    text: str
    score: float = 0.0


class DocumentReaderAgent:
    """High-precision document reading agent with evidence-first outputs."""

    _SENSITIVE_PATTERNS = {
        "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
        "phone": re.compile(r"\b(?:\+?\d{1,3}[-\s]?)?(?:\d[-\s]?){7,14}\b"),
        "card_like": re.compile(r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b"),
    }

    def __init__(self, hermes: HermesClient) -> None:
        self.hermes = hermes

    def run(
        self,
        objective: str,
        files: list[dict[str, Any]],
        backend: str,
        ollama_base_url: str,
        ollama_model: str,
        temperature: float,
        max_context_chars: int,
    ) -> dict[str, Any]:
        format_counter: Counter[str] = Counter()
        text_ready_count = 0
        image_file_count = 0
        redaction_counter: Counter[str] = Counter()
        chunks: list[_Chunk] = []
        uncertainties: list[str] = []

        for idx, row in enumerate(files, start=1):
            file_name = str(row.get("file_name", ""))
            local_path = str(row.get("local_path", ""))
            ext = Path(file_name).suffix.lower()
            file_type = self._infer_file_type(ext)
            format_counter[file_type] += 1
            if file_type == "image":
                image_file_count += 1

            extracted = str(row.get("extracted_text", "") or "")
            redacted_text, redactions = self._mask_sensitive(extracted)
            for k, v in redactions.items():
                redaction_counter[k] += v

            if redacted_text.strip():
                text_ready_count += 1
            else:
                uncertainties.append(f"{file_name}: no extracted text, manual check may be required")

            base = (
                f"File: {file_name}\n"
                f"Type: {file_type}\n"
                f"Project: {row.get('project', 'general')}\n"
                f"Category: {row.get('category', 'general')}\n"
                f"Path: {local_path}\n"
            )
            text_source = (base + "\n" + redacted_text).strip()
            for c_idx, text_chunk in enumerate(self._chunk_text(text_source), start=1):
                chunks.append(
                    _Chunk(
                        chunk_id=f"C{idx}_{c_idx}",
                        file_name=file_name,
                        local_path=local_path,
                        file_type=file_type,
                        text=text_chunk,
                    )
                )

        ranked = self._rank_chunks(objective, chunks)
        top_chunks = ranked[: min(18, len(ranked))]
        evidence_files = self._build_evidence(top_chunks)
        conflicts = self._detect_conflicts(top_chunks)
        confidence = self._estimate_confidence(
            total_files=len(files),
            text_ready_count=text_ready_count,
            top_chunks=top_chunks,
        )

        context_blocks = []
        for c in top_chunks:
            context_blocks.append(f"[{c.chunk_id}]\n{c.text[:1200]}")
        context = "\n\n---\n\n".join(context_blocks)[:max_context_chars]

        summary_prompt = (
            "You are Document Reader Agent.\n"
            "Task: build a precise, evidence-backed summary for multi-format files.\n"
            "Required sections:\n"
            "1) Key facts\n"
            "2) Quantitative findings\n"
            "3) Risks and uncertainties\n"
            "4) Action items\n"
            "5) Evidence references (must cite chunk IDs like [C1_2])\n"
            "If image OCR is weak or absent, explicitly mark manual verification items.\n"
            f"Objective: {objective}"
        )

        summary = self.hermes.answer(
            question=summary_prompt,
            context=context,
            backend=backend,
            ollama_base_url=ollama_base_url,
            ollama_model=ollama_model,
            temperature=temperature,
            timeout_seconds=180,
        )

        return {
            "file_count": len(files),
            "text_ready_count": text_ready_count,
            "image_file_count": image_file_count,
            "format_breakdown": dict(format_counter.most_common()),
            "retrieval_chunks": len(top_chunks),
            "confidence": confidence,
            "conflicts": conflicts,
            "uncertainties": uncertainties[:12],
            "redaction_counts": dict(redaction_counter),
            "evidence_files": evidence_files,
            "summary": summary,
        }

    @staticmethod
    def _infer_file_type(ext: str) -> str:
        if ext in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"}:
            return "image"
        if ext in {".doc", ".docx"}:
            return "word"
        if ext == ".pdf":
            return "pdf"
        if ext in {".csv", ".xls", ".xlsx"}:
            return "table"
        if ext in {".ppt", ".pptx"}:
            return "slides"
        return "text"

    @classmethod
    def _mask_sensitive(cls, text: str) -> tuple[str, dict[str, int]]:
        redaction_counts: dict[str, int] = {}
        masked = text
        for key, pattern in cls._SENSITIVE_PATTERNS.items():
            found = pattern.findall(masked)
            if found:
                redaction_counts[key] = len(found)
                masked = pattern.sub(f"[{key}_redacted]", masked)
        return masked, redaction_counts

    @staticmethod
    def _chunk_text(text: str, size: int = 900, overlap: int = 120) -> list[str]:
        if not text:
            return []
        chunks: list[str] = []
        start = 0
        while start < len(text):
            end = min(len(text), start + size)
            chunks.append(text[start:end])
            if end >= len(text):
                break
            start = max(0, end - overlap)
        return chunks

    @staticmethod
    def _tokenize_query(text: str) -> list[str]:
        raw = (text or "").lower()
        tokens = set(re.findall(r"[a-z0-9_]{2,}|[\u4e00-\u9fff]{2,}", raw))
        extra: set[str] = set()
        for t in tokens:
            if re.fullmatch(r"[\u4e00-\u9fff]{2,}", t):
                for i in range(len(t) - 1):
                    extra.add(t[i : i + 2])
        tokens.update(extra)
        return sorted(tokens, key=len, reverse=True)

    def _rank_chunks(self, objective: str, chunks: list[_Chunk]) -> list[_Chunk]:
        tokens = self._tokenize_query(objective)
        if not tokens:
            tokens = ["summary", "risk", "action", "数据", "总结"]

        for c in chunks:
            text_lower = c.text.lower()
            token_hits = sum(1 for t in tokens if t in text_lower)
            structure_bonus = 1.0 if any(k in text_lower for k in ["sheet:", "page", "[image_meta]"]) else 0.0
            numeric_bonus = 1.0 if re.search(r"\b\d+(?:\.\d+)?\b", text_lower) else 0.0
            c.score = token_hits * 2.0 + structure_bonus + numeric_bonus

        return sorted(chunks, key=lambda x: x.score, reverse=True)

    @staticmethod
    def _build_evidence(chunks: list[_Chunk]) -> list[dict[str, str]]:
        seen: set[str] = set()
        evidence: list[dict[str, str]] = []
        for c in chunks:
            key = f"{c.file_name}|{c.local_path}"
            if key in seen:
                continue
            seen.add(key)
            evidence.append(
                {
                    "citation": c.chunk_id,
                    "file": c.file_name,
                    "type": c.file_type,
                    "path": c.local_path,
                    "snippet": c.text[:220].replace("\n", " "),
                }
            )
            if len(evidence) >= 12:
                break
        return evidence

    @staticmethod
    def _detect_conflicts(chunks: list[_Chunk]) -> list[str]:
        amounts: list[float] = []
        for c in chunks:
            for m in re.findall(r"\b\d+(?:\.\d{1,2})?\b", c.text[:1200]):
                try:
                    val = float(m)
                except ValueError:
                    continue
                if 1 <= val <= 1_000_000:
                    amounts.append(val)

        if not amounts:
            return []

        distinct = sorted(set(round(x, 2) for x in amounts))
        if len(distinct) >= 8:
            return ["High numeric variability detected across evidence chunks; verify totals before final decision."]
        return []

    @staticmethod
    def _estimate_confidence(total_files: int, text_ready_count: int, top_chunks: list[_Chunk]) -> float:
        if total_files <= 0:
            return 0.0
        coverage = text_ready_count / total_files
        avg_score = 0.0
        if top_chunks:
            avg_score = sum(c.score for c in top_chunks) / len(top_chunks)
        normalized_score = min(1.0, avg_score / 8.0)
        return round((coverage * 0.7 + normalized_score * 0.3), 3)
