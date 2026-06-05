from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
INDEX_PATH = ROOT / "output" / "wiki" / "knowledge_index.json"
ROLE_CONFIG_PATH = ROOT / "agent-platform" / "config" / "agent_roles.json"
OUTPUT_MD = ROOT / "docs" / "reports" / "knowledge-role-coverage.md"


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _load_role_config() -> dict[str, Any]:
    return _read_json(ROLE_CONFIG_PATH, {})


def _load_index() -> dict[str, Any]:
    return _read_json(INDEX_PATH, {"meta": {"chunk_count": 0}, "chunks": []})


def _status(own_skill_chunks: int, docs_chunks: int) -> str:
    if own_skill_chunks >= 2 and docs_chunks >= 8:
        return "good"
    if own_skill_chunks >= 1 and docs_chunks >= 4:
        return "warn"
    return "weak"


def _build_rows(index: dict[str, Any], role_cfg: dict[str, Any]) -> list[dict[str, Any]]:
    chunks = index.get("chunks", [])
    if not isinstance(chunks, list):
        chunks = []

    labels = role_cfg.get("staff_labels", {}) if isinstance(role_cfg.get("staff_labels", {}), dict) else {}
    roles = role_cfg.get("staff_role_by_key", {}) if isinstance(role_cfg.get("staff_role_by_key", {}), dict) else {}
    skill_files = role_cfg.get("staff_skill_files", {}) if isinstance(role_cfg.get("staff_skill_files", {}), dict) else {}

    rows: list[dict[str, Any]] = []
    for staff_key, role_name in roles.items():
        if not isinstance(staff_key, str):
            continue
        mapped_file = str(skill_files.get(staff_key, ""))

        own_skill_chunks = 0
        docs_chunks = 0
        skill_chunks_total = 0

        for chunk in chunks:
            if not isinstance(chunk, dict):
                continue
            source_type = str(chunk.get("source_type", ""))
            source_path = str(chunk.get("source_path", ""))
            scopes = chunk.get("staff_scopes", [])
            scopes_set = {str(x) for x in scopes} if isinstance(scopes, list) else set()

            if source_type == "skills":
                skill_chunks_total += 1
                if staff_key in scopes_set:
                    own_skill_chunks += 1
            if source_type == "docs" and staff_key in scopes_set:
                docs_chunks += 1

            # docs 默认不带 scope，这里用文件名匹配兜底统计“技能文件是否入库”
            if mapped_file and mapped_file in source_path and source_type == "skills":
                own_skill_chunks = max(own_skill_chunks, 1)

        rows.append(
            {
                "staff_key": staff_key,
                "label": str(labels.get(staff_key, staff_key)),
                "role": str(role_name),
                "own_skill_chunks": own_skill_chunks,
                "docs_chunks": docs_chunks,
                "status": _status(own_skill_chunks, docs_chunks),
            }
        )

    rows.sort(key=lambda r: r["staff_key"])
    return rows


def _render_markdown(index: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    built_at = datetime.now(timezone.utc).isoformat()
    chunk_count = int(index.get("meta", {}).get("chunk_count", 0)) if isinstance(index.get("meta", {}), dict) else 0

    good = sum(1 for r in rows if r["status"] == "good")
    warn = sum(1 for r in rows if r["status"] == "warn")
    weak = sum(1 for r in rows if r["status"] == "weak")

    lines = [
        "# Knowledge Role Coverage Report",
        "",
        f"- Generated at: {built_at}",
        f"- Index chunks: {chunk_count}",
        f"- Roles: {len(rows)} (good={good}, warn={warn}, weak={weak})",
        "",
        "| staff_key | label | role | own_skill_chunks | docs_chunks | status |",
        "|---|---|---|---:|---:|---|",
    ]

    for row in rows:
        lines.append(
            f"| {row['staff_key']} | {row['label']} | {row['role']} | {row['own_skill_chunks']} | {row['docs_chunks']} | {row['status']} |"
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "- good: 角色技能块和文档块覆盖较完整",
            "- warn: 覆盖基本可用，但建议补文档或技能细化",
            "- weak: 覆盖薄弱，优先补充角色知识",
        ]
    )

    return "\n".join(lines)


def main() -> int:
    index = _load_index()
    role_cfg = _load_role_config()
    rows = _build_rows(index, role_cfg)
    OUTPUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_MD.write_text(_render_markdown(index, rows), encoding="utf-8")
    print(f"Coverage report written: {OUTPUT_MD.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
