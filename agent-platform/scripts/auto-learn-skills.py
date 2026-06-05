from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
AGENT_ROOT = ROOT / "agent-platform"
ROLE_CONFIG_PATH = AGENT_ROOT / "config" / "agent_roles.json"
WIKI_CONFIG_PATH = AGENT_ROOT / "config" / "wiki_knowledge_config.json"
AUTO_CONFIG_PATH = AGENT_ROOT / "config" / "auto_skill_learning_config.json"
WORKFLOW_MAPPING_PATH = AGENT_ROOT / "config" / "workflow_mappings.json"
INDEX_BUILDER_PATH = AGENT_ROOT / "scripts" / "build-knowledge-index.py"

DEFAULT_AUTO_CFG: dict[str, Any] = {
    "enabled": True,
    "max_chunks_per_staff": 10,
    "max_source_lines": 8,
    "github": {
        "enabled": True,
        "query": "comfyui workflow",
        "top_repos": 8,
        "min_stars": 100,
        "readme_max_chars": 2200,
        "request_timeout_seconds": 20,
    },
    "staff_focus_keywords": {},
}

VIDEO_TEAM = {
    "supervisor_video",
    "image",
    "production",
    "story",
    "prompt",
    "builder",
    "qa",
}

SOP_TEMPLATES: dict[str, list[str]] = {
    "builder": [
        "Parse request and resolve workflow mapping before touching nodes.",
        "Inject only mapped fields (prompt/seed/image/sampler), avoid unrelated node edits.",
        "Validate required node class_type and parameters before submit.",
        "Record changed_fields, assumptions, and retry_hint for handoff.",
        "On failure, prefer minimal rollback and deterministic retry path.",
    ],
    "prompt": [
        "Convert scene intent into positive/negative/motion prompt blocks.",
        "Enforce style and camera consistency across shots.",
        "Add anti-artifact negative constraints for temporal stability.",
        "Return structured prompt pack for downstream builder mapping.",
    ],
    "qa": [
        "Review output for identity drift, motion jitter, and artifact risks.",
        "Score pass/fail with explicit evidence and severity.",
        "Provide bounded retry suggestions and stop conditions.",
    ],
}

QUALITY_GATES: dict[str, list[str]] = {
    "builder": [
        "sampler_name must be dpmpp_2m",
        "scheduler must be karras",
        "workflow node mapping must match selected workflow",
        "handoff must include changed_fields/assumptions/retry_hint",
    ],
    "default": [
        "Output must be evidence-backed and reproducible",
        "Risk and fallback path must be explicit",
        "Handoff should be structured and actionable",
    ],
}


@dataclass
class Chunk:
    source_path: str
    source_type: str
    title: str
    text: str
    tags: list[str]
    staff_scopes: list[str]


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _load_auto_cfg() -> dict[str, Any]:
    raw = _read_json(AUTO_CONFIG_PATH, {})
    if not isinstance(raw, dict):
        raw = {}
    cfg = json.loads(json.dumps(DEFAULT_AUTO_CFG))
    cfg.update({k: v for k, v in raw.items() if k in cfg})
    if isinstance(raw.get("github"), dict):
        cfg["github"].update(raw["github"])
    if isinstance(raw.get("staff_focus_keywords"), dict):
        cfg["staff_focus_keywords"] = raw["staff_focus_keywords"]
    return cfg


def _ensure_index(wiki_cfg: dict[str, Any]) -> None:
    index_rel = str(wiki_cfg.get("index_path", "output/wiki/knowledge_index.json"))
    index_path = ROOT / index_rel
    if index_path.exists():
        return

    py_exe = AGENT_ROOT / ".venv" / "Scripts" / "python.exe"
    if not py_exe.exists():
        return
    if not INDEX_BUILDER_PATH.exists():
        return

    try:
        subprocess.run(
            [str(py_exe), str(INDEX_BUILDER_PATH)],
            cwd=str(AGENT_ROOT),
            check=False,
            capture_output=True,
            text=True,
            timeout=180,
        )
    except Exception:
        return


def _load_chunks(wiki_cfg: dict[str, Any]) -> list[Chunk]:
    index_rel = str(wiki_cfg.get("index_path", "output/wiki/knowledge_index.json"))
    index_path = ROOT / index_rel
    raw = _read_json(index_path, {})
    chunks_raw = raw.get("chunks", []) if isinstance(raw, dict) else []
    chunks: list[Chunk] = []
    for item in chunks_raw:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        chunks.append(
            Chunk(
                source_path=str(item.get("source_path", "")),
                source_type=str(item.get("source_type", "docs")),
                title=str(item.get("title", "Document")),
                text=text,
                tags=[str(x) for x in item.get("tags", []) if isinstance(x, (str, int, float))],
                staff_scopes=[str(x) for x in item.get("staff_scopes", []) if isinstance(x, str)],
            )
        )
    return chunks


def _workflow_chunks() -> list[Chunk]:
    raw = _read_json(WORKFLOW_MAPPING_PATH, {})
    workflows = raw.get("workflows", {}) if isinstance(raw, dict) else {}
    if not isinstance(workflows, dict):
        return []

    result: list[Chunk] = []
    for wf_key, wf in workflows.items():
        if not isinstance(wf, dict):
            continue
        desc = str(wf.get("description", "")).strip()
        file_path = str(wf.get("file_path", "")).strip()
        params = wf.get("parameters", {}) if isinstance(wf.get("parameters"), dict) else {}
        mapping = wf.get("node_mapping", {}) if isinstance(wf.get("node_mapping"), dict) else {}
        tags = [str(x) for x in wf.get("tags", []) if isinstance(x, str)]
        text = "\n".join(
            [
                f"workflow: {wf_key}",
                f"description: {desc}",
                f"file_path: {file_path}",
                "parameters: " + json.dumps(params, ensure_ascii=False),
                "node_mapping: " + json.dumps(mapping, ensure_ascii=False),
            ]
        )
        result.append(
            Chunk(
                source_path=f"agent-platform/config/workflow_mappings.json::{wf_key}",
                source_type="workflow_config",
                title=f"workflow {wf_key}",
                text=text,
                tags=tags + ["workflow", "comfyui"],
                staff_scopes=["builder", "production", "prompt", "qa", "supervisor_video"],
            )
        )
    return result


def _http_json(url: str, token: str, timeout_seconds: int) -> dict[str, Any]:
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "HoneyHive-AutoSkillLearner")
    req.add_header("Accept", "application/vnd.github+json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")

    with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:  # nosec B310
        payload = resp.read().decode("utf-8", errors="ignore")
        return json.loads(payload)


def _github_chunks(auto_cfg: dict[str, Any]) -> list[Chunk]:
    gh = auto_cfg.get("github", {}) if isinstance(auto_cfg.get("github"), dict) else {}
    if not bool(gh.get("enabled", True)):
        return []

    query = str(gh.get("query", "comfyui workflow")).strip() or "comfyui workflow"
    top_repos = max(1, int(gh.get("top_repos", 8)))
    min_stars = max(0, int(gh.get("min_stars", 100)))
    readme_max_chars = max(300, int(gh.get("readme_max_chars", 2200)))
    timeout_seconds = max(5, int(gh.get("request_timeout_seconds", 20)))
    token = ""
    # Priority: explicit env vars.
    for env_name in ("GITHUB_TOKEN", "GH_TOKEN"):
        val = str(os.environ.get(env_name, "")).strip()
        if val:
            token = val
            break

    q = urllib.parse.quote_plus(query)
    search_url = (
        "https://api.github.com/search/repositories"
        f"?q={q}&sort=stars&order=desc&per_page={top_repos}"
    )

    try:
        search = _http_json(search_url, token, timeout_seconds)
    except Exception:
        return []

    items = search.get("items", []) if isinstance(search, dict) else []
    if not isinstance(items, list):
        return []

    chunks: list[Chunk] = []
    for repo in items:
        if not isinstance(repo, dict):
            continue
        stars = int(repo.get("stargazers_count", 0) or 0)
        if stars < min_stars:
            continue

        full_name = str(repo.get("full_name", "")).strip()
        if not full_name:
            continue

        description = str(repo.get("description", "")).strip()
        html_url = str(repo.get("html_url", "")).strip()
        readme_text = ""

        try:
            readme_api = f"https://api.github.com/repos/{full_name}/readme"
            readme_json = _http_json(readme_api, token, timeout_seconds)
            content = str(readme_json.get("content", "")) if isinstance(readme_json, dict) else ""
            encoding = str(readme_json.get("encoding", "")) if isinstance(readme_json, dict) else ""
            if content and encoding == "base64":
                readme_text = base64.b64decode(content).decode("utf-8", errors="ignore")
        except Exception:
            readme_text = ""

        readme_text = " ".join(readme_text.split())[:readme_max_chars]
        text = "\n".join(
            [
                f"repo: {full_name}",
                f"stars: {stars}",
                f"url: {html_url}",
                f"description: {description}",
                f"readme_excerpt: {readme_text}",
            ]
        )
        chunks.append(
            Chunk(
                source_path=html_url or full_name,
                source_type="github_comfyui",
                title=f"GitHub {full_name}",
                text=text,
                tags=["github", "comfyui", "workflow", "popular"],
                staff_scopes=["builder", "production", "prompt", "qa", "supervisor_video"],
            )
        )
    return chunks


def _keywords_for_staff(staff_key: str, role_name: str, auto_cfg: dict[str, Any]) -> list[str]:
    user_map = auto_cfg.get("staff_focus_keywords", {}) if isinstance(auto_cfg.get("staff_focus_keywords"), dict) else {}
    user_values = user_map.get(staff_key, [])
    keywords: list[str] = []
    if isinstance(user_values, list):
        keywords.extend(str(x).strip().lower() for x in user_values if str(x).strip())

    fallback = [staff_key.lower()] + [x.strip().lower() for x in role_name.replace("(", " ").replace(")", " ").replace("Agent", "").split() if x.strip()]
    for token in fallback:
        if token and token not in keywords:
            keywords.append(token)
    return keywords


def _score_chunk(chunk: Chunk, staff_key: str, keywords: list[str]) -> float:
    text = (chunk.text + "\n" + " ".join(chunk.tags)).lower()
    kw_hits = sum(1 for kw in keywords if kw and kw in text)
    score = kw_hits / max(len(keywords), 1)

    if staff_key in chunk.staff_scopes:
        score += 0.9
    if chunk.source_type == "skills":
        score += 0.2
    if chunk.source_type == "project_context":
        score += 0.1

    if staff_key in VIDEO_TEAM:
        if "comfyui" in text:
            score += 0.25
        if chunk.source_type in {"workflow_config", "github_comfyui"}:
            score += 0.35
    return score


def _extract_bullets(chunks: list[tuple[float, Chunk]], max_items: int = 8) -> list[str]:
    bullets: list[str] = []
    seen: set[str] = set()
    for _, chunk in chunks:
        text = " ".join(chunk.text.split())
        if not text:
            continue
        segments = re.split(r"[。！？!?.;；]\s*", text)
        for seg in segments:
            sentence = seg.strip(" -\t")
            if len(sentence) < 36:
                continue
            if len(sentence) > 180:
                sentence = sentence[:180].rstrip() + "..."
            if sentence in seen:
                continue
            seen.add(sentence)
            bullets.append(sentence)
            if len(bullets) >= max_items:
                break
        if len(bullets) >= max_items:
            break
    return bullets


def _role_quality_gates(staff_key: str) -> list[str]:
    if staff_key in QUALITY_GATES:
        return QUALITY_GATES[staff_key]
    return QUALITY_GATES["default"]


def _role_steps(staff_key: str, role_name: str) -> list[str]:
    if staff_key in SOP_TEMPLATES:
        return SOP_TEMPLATES[staff_key]
    return [
        f"Clarify objective and constraints for {role_name}.",
        "Retrieve evidence from indexed docs and skills before acting.",
        "Produce structured handoff with assumptions and risks.",
        "Validate output quality and define retry/fallback criteria.",
    ]


def _render_skill_markdown(
    staff_key: str,
    role_name: str,
    role_summary: str,
    skill_file_name: str,
    ranked_chunks: list[tuple[float, Chunk]],
    auto_cfg: dict[str, Any],
) -> str:
    now = datetime.now(timezone.utc).isoformat()
    max_source_lines = max(3, int(auto_cfg.get("max_source_lines", 8)))

    bullets = _extract_bullets(ranked_chunks, max_items=8)
    if not bullets:
        bullets = ["No strong evidence chunks were found; keep previous role routine and rebuild index."]

    lines: list[str] = []
    lines.append(f"# {role_name} 自动学习 Skill")
    lines.append("")
    lines.append("## 元信息")
    lines.append(f"- staff_key: {staff_key}")
    lines.append(f"- role: {role_name}")
    lines.append(f"- file: {skill_file_name}")
    lines.append(f"- generated_at_utc: {now}")
    lines.append("")
    lines.append("## 角色目标")
    lines.append(f"- {role_summary or 'Deliver stable, structured, and evidence-backed output.'}")
    lines.append("")
    lines.append("## 自动学习提炼")
    for bullet in bullets:
        lines.append(f"- {bullet}")
    lines.append("")
    lines.append("## 标准执行流程")
    for idx, step in enumerate(_role_steps(staff_key, role_name), start=1):
        lines.append(f"{idx}. {step}")
    lines.append("")
    lines.append("## 质量门")
    for gate in _role_quality_gates(staff_key):
        lines.append(f"- {gate}")
    lines.append("")
    lines.append("## 学习证据")
    for score, chunk in ranked_chunks[:max_source_lines]:
        snippet = " ".join(chunk.text.split())[:180]
        lines.append(
            f"- [{chunk.source_type}] {chunk.title} | score={score:.3f} | source={chunk.source_path}"
        )
        lines.append(f"  - snippet: {snippet}")

    return "\n".join(lines).strip() + "\n"


def main() -> int:
    auto_cfg = _load_auto_cfg()
    if not bool(auto_cfg.get("enabled", True)):
        print("Auto skill learning disabled by config.")
        return 0

    role_cfg = _read_json(ROLE_CONFIG_PATH, {})
    if not isinstance(role_cfg, dict):
        print("Invalid role config")
        return 1

    skill_files = role_cfg.get("staff_skill_files", {})
    role_map = role_cfg.get("staff_role_by_key", {})
    role_summaries = role_cfg.get("agent_role_summaries", {})

    if not isinstance(skill_files, dict) or not skill_files:
        print("No staff_skill_files mapping found")
        return 1

    wiki_cfg = _read_json(WIKI_CONFIG_PATH, {})
    if not isinstance(wiki_cfg, dict):
        wiki_cfg = {}

    _ensure_index(wiki_cfg)

    chunks = _load_chunks(wiki_cfg)
    chunks.extend(_workflow_chunks())

    gh_chunks = _github_chunks(auto_cfg)
    chunks.extend(gh_chunks)

    skills_dir = ROOT / "output" / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)

    max_chunks_per_staff = max(4, int(auto_cfg.get("max_chunks_per_staff", 10)))

    updated = 0
    for staff_key, file_name in skill_files.items():
        if not isinstance(staff_key, str) or not isinstance(file_name, str):
            continue

        role_name = str(role_map.get(staff_key, staff_key)) if isinstance(role_map, dict) else staff_key
        role_summary = str(role_summaries.get(role_name, "")) if isinstance(role_summaries, dict) else ""
        keywords = _keywords_for_staff(staff_key, role_name, auto_cfg)

        ranked: list[tuple[float, Chunk]] = []
        self_skill_source = f"output/skills/{file_name}".replace("\\", "/")
        for chunk in chunks:
            src_norm = chunk.source_path.replace("\\", "/")
            if src_norm.endswith(self_skill_source):
                continue
            score = _score_chunk(chunk, staff_key, keywords)
            if score <= 0:
                continue
            ranked.append((score, chunk))

        ranked.sort(key=lambda x: x[0], reverse=True)
        top = ranked[:max_chunks_per_staff]

        markdown = _render_skill_markdown(
            staff_key=staff_key,
            role_name=role_name,
            role_summary=role_summary,
            skill_file_name=file_name,
            ranked_chunks=top,
            auto_cfg=auto_cfg,
        )

        out_path = skills_dir / file_name
        out_path.write_text(markdown, encoding="utf-8")
        updated += 1

    print(f"Auto-learned staff skills updated: {updated}")
    print(f"GitHub comfyui chunks used: {len(gh_chunks)}")
    print(f"Output dir: {skills_dir.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
