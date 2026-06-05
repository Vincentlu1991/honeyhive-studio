from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
INDEX_PATH = ROOT / "output" / "wiki" / "knowledge_index.json"
ROLE_CONFIG_PATH = ROOT / "agent-platform" / "config" / "agent_roles.json"
OUTPUT_JSON = ROOT / "output" / "wiki" / "quality_eval.json"
OUTPUT_MD = ROOT / "output" / "wiki" / "quality_eval.md"


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _query_tokens(query: str) -> list[str]:
    return list(dict.fromkeys((query or "").lower().split()))


def _score_chunk(chunk: dict[str, Any], query: str, staff_key: str = "") -> float:
    text = str(chunk.get("text", "")).lower()
    tokens = _query_tokens(query)
    if not tokens or not text:
        return 0.0
    hits = sum(1 for t in tokens if t in text)
    score = hits / max(len(tokens), 1)

    scopes = chunk.get("staff_scopes", [])
    scope_set = {str(x) for x in scopes} if isinstance(scopes, list) else set()
    if staff_key and staff_key in scope_set:
        score += 0.9
    if str(chunk.get("source_type", "")) == "skills":
        score += 0.2
    return score


def _retrieve(index_chunks: list[dict[str, Any]], query: str, staff_key: str, top_k: int = 5) -> list[dict[str, Any]]:
    scored: list[tuple[float, dict[str, Any]]] = []
    for chunk in index_chunks:
        s = _score_chunk(chunk, query, staff_key)
        if s > 0:
            row = dict(chunk)
            row["score"] = round(s, 4)
            scored.append((s, row))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [x for _, x in scored[:top_k]]


def _build_test_cases(role_cfg: dict[str, Any]) -> list[dict[str, str]]:
    role_summaries = role_cfg.get("agent_role_summaries", {}) if isinstance(role_cfg.get("agent_role_summaries", {}), dict) else {}
    roles = role_cfg.get("staff_role_by_key", {}) if isinstance(role_cfg.get("staff_role_by_key", {}), dict) else {}
    skill_files = role_cfg.get("staff_skill_files", {}) if isinstance(role_cfg.get("staff_skill_files", {}), dict) else {}

    cases: list[dict[str, str]] = []
    for staff_key, role_name in roles.items():
        summary = str(role_summaries.get(role_name, ""))
        query = summary[:36] if summary else f"{role_name} 执行策略"
        cases.append(
            {
                "staff_key": str(staff_key),
                "role_name": str(role_name),
                "query": query,
                "expected_file": str(skill_files.get(staff_key, "")),
            }
        )
    return cases


def _evaluate(index_chunks: list[dict[str, Any]], cases: list[dict[str, str]]) -> dict[str, Any]:
    details: list[dict[str, Any]] = []
    passed = 0

    for case in cases:
        results = _retrieve(index_chunks, case["query"], case["staff_key"], top_k=5)
        top_source = str(results[0].get("source_path", "")) if results else ""
        expected_file = case.get("expected_file", "")
        ok = bool(expected_file and expected_file in top_source)
        if ok:
            passed += 1
        details.append(
            {
                "staff_key": case["staff_key"],
                "role_name": case["role_name"],
                "query": case["query"],
                "expected_file": expected_file,
                "top_source": top_source,
                "passed": ok,
            }
        )

    total = len(cases)
    pass_rate = (passed / total) if total else 0.0
    return {
        "summary": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total": total,
            "passed": passed,
            "pass_rate": round(pass_rate, 4),
        },
        "details": details,
    }


def _render_md(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    details = report.get("details", [])
    lines = [
        "# Wiki Quality Eval",
        "",
        f"- Generated at: {summary.get('generated_at')}",
        f"- Total: {summary.get('total', 0)}",
        f"- Passed: {summary.get('passed', 0)}",
        f"- Pass rate: {summary.get('pass_rate', 0)}",
        "",
        "| staff_key | role | passed | top_source |",
        "|---|---|---|---|",
    ]
    for d in details:
        lines.append(f"| {d.get('staff_key')} | {d.get('role_name')} | {d.get('passed')} | {d.get('top_source')} |")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-pass-rate", type=float, default=0.75)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    index = _read_json(INDEX_PATH, {"chunks": []})
    role_cfg = _read_json(ROLE_CONFIG_PATH, {})
    chunks = index.get("chunks", []) if isinstance(index, dict) else []
    if not isinstance(chunks, list):
        chunks = []

    cases = _build_test_cases(role_cfg)
    report = _evaluate(chunks, cases)

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    OUTPUT_MD.write_text(_render_md(report), encoding="utf-8")

    pass_rate = float(report.get("summary", {}).get("pass_rate", 0.0))
    print(f"Wiki quality pass_rate={pass_rate:.4f}, min={args.min_pass_rate:.4f}")
    print(f"Report: {OUTPUT_JSON.relative_to(ROOT).as_posix()}")

    if args.strict and pass_rate < args.min_pass_rate:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
