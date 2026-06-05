from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import traceback
import uuid
import html
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests
import streamlit as st

from multi_agent_video.chat_hub import create_runtime
from multi_agent_video.config import load_config
from multi_agent_video.models import SceneSpec
from multi_agent_video.observability import capture_exception, init_observability

I2V_WORKFLOW_PATH = Path(__file__).resolve().parent.parent / "workflow_ltxv_img2video_test.json"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALLOWED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
SECRETARY_ROOT = PROJECT_ROOT / "personal-secretary"
SECRETARY_DB_PATH = SECRETARY_ROOT / "data" / "secretary.db"
SECRETARY_DASHBOARD_PORT = 8503
SECRETARY_DASHBOARD_URL = f"http://127.0.0.1:{SECRETARY_DASHBOARD_PORT}"
TELEGRAM_BOT_SCRIPT_PATH = SECRETARY_ROOT / "run_telegram_bot.py"
AGENT_MEMORY_PATH = PROJECT_ROOT / "output" / "agent-memory" / "honeyhive_agent_memory.json"
AGENT_MEMORY_MAX_TURNS = 30
AGENT_MEMORY_CONTEXT_TURNS = 6
AGENT_MEMORY_MAX_FACTS = 20
AGENT_MEMORY_SUMMARY_MAX_CHARS = 900
AGENT_MEMORY_RECENCY_DAYS = 14
# Hermes-inspired: skills system (auto-generated reusable procedures)
SKILLS_DIR = PROJECT_ROOT / "output" / "skills"
SKILLS_MAX_INJECT = 3          # max skills to inject per prompt
# Hermes-inspired: project context file (shapes every conversation)
PROJECT_CONTEXT_FILE = PROJECT_ROOT / "CLAUDE.md"
PROJECT_CONTEXT_MAX_CHARS = 800
WIKI_CONFIG_PATH = PROJECT_ROOT / "agent-platform" / "config" / "wiki_knowledge_config.json"
WIKI_DEFAULT_INDEX_PATH = PROJECT_ROOT / "output" / "wiki" / "knowledge_index.json"
WIKI_DEFAULT_STATE_PATH = PROJECT_ROOT / "output" / "wiki" / "knowledge_state.json"
WIKI_BUILD_SCRIPT_PATH = PROJECT_ROOT / "agent-platform" / "scripts" / "build-knowledge-index.py"
AUTO_SKILL_LEARN_SCRIPT_PATH = PROJECT_ROOT / "agent-platform" / "scripts" / "auto-learn-skills.py"
BOSS_MEETING_ATTACHMENTS_DIR = PROJECT_ROOT / "output" / "boss-meeting-attachments"
AGENT_ROLE_CONFIG_PATH = PROJECT_ROOT / "agent-platform" / "config" / "agent_roles.json"
SUPERVISOR_RESPONSE_MAX_RETRIES = 2

DEFAULT_AGENT_ROLE_SUMMARIES: dict[str, str] = {
    "Supervisor Agent": "负责统筹全局、拆解任务、协调员工、控制成本和风险。",
    "Supervisor Agent (Video)": "负责视频项目的总调度，协调剧情、提示词、工作流和质检。",
    "Supervisor Agent (Secretary)": "负责秘书项目的总调度，统筹检索、精读、文件处理和报告输出。",
    "Image Analysis Agent": "负责读取上传图片，提炼画面主体、构图、光线、风格和可注入的生成线索。",
    "Production Planner Agent": "负责把需求转成可执行的制作计划，明确顺序、资源、风险和回退方案。",
    "Story Agent": "负责把创意需求整理成适合视频生成的场景结构，输出 scene、action、mood。",
    "Prompt Agent": "负责把场景结构转成高质量提示词，并结合风格、镜头和动作约束优化表达。",
    "Builder Agent": "负责把提示词和场景映射到 ComfyUI 工作流节点，处理参考图、seed 和注入策略。",
    "QA Agent": "负责检查生成结果的画面质量、人物一致性、动作稳定性和可重试项。",
    "Retriever Agent": "负责从本地知识库和文件中检索相关信息，提供证据和上下文。",
    "Document Reader Agent": "负责多格式文档精读、证据提取、冲突检测和关键信息归纳。",
    "FileOps Agent": "负责文件整理、路径处理、归档和基础文件操作。",
    "Finance Agent": "负责费用、预算、投入产出和成本分析。",
    "Learning Agent": "负责学习规划、技能补齐和知识路线设计。",
    "Business Plan Agent": "负责商业计划梳理、方案结构和落地节奏设计。",
    "Report Agent": "负责把过程、结果和风险整理成清晰报告。",
    "QA Agent (Secretary)": "负责秘书项目的结果校验、遗漏检查和输出质量控制。",
}

DEFAULT_STAFF_ROLE_BY_KEY: dict[str, str] = {
    "supervisor_video": "Supervisor Agent (Video)",
    "image": "Image Analysis Agent",
    "production": "Production Planner Agent",
    "story": "Story Agent",
    "prompt": "Prompt Agent",
    "builder": "Builder Agent",
    "qa": "QA Agent",
    "supervisor_secretary": "Supervisor Agent (Secretary)",
    "retriever": "Retriever Agent",
    "document_reader": "Document Reader Agent",
    "fileops": "FileOps Agent",
    "finance": "Finance Agent",
    "learning": "Learning Agent",
    "business_plan": "Business Plan Agent",
    "report": "Report Agent",
    "secretary_qa": "QA Agent (Secretary)",
}

DEFAULT_STAFF_LABELS: dict[str, str] = {
    "supervisor_video": "视频团队｜主管Agent",
    "image": "视频团队｜图像分析员",
    "production": "视频团队｜制片规划员",
    "story": "视频团队｜剧情导演",
    "prompt": "视频团队｜提示词工程师",
    "builder": "视频团队｜工作流构建员",
    "qa": "视频团队｜质检员",
    "supervisor_secretary": "秘书团队｜主管Agent",
    "retriever": "秘书团队｜检索员",
    "document_reader": "秘书团队｜文档精读员",
    "fileops": "秘书团队｜文件运营员",
    "finance": "秘书团队｜财务分析员",
    "learning": "秘书团队｜学习规划员",
    "business_plan": "秘书团队｜商业计划员",
    "report": "秘书团队｜报告整合员",
    "secretary_qa": "秘书团队｜质检员",
}

DEFAULT_SUPERVISOR_TEAM_ROSTER: dict[str, list[str]] = {
    "supervisor_video": [
        "Image Analysis Agent",
        "Production Planner Agent",
        "Story Agent",
        "Prompt Agent",
        "Builder Agent",
        "QA Agent",
    ],
    "supervisor_secretary": [
        "Retriever Agent",
        "Document Reader Agent",
        "FileOps Agent",
        "Finance Agent",
        "Learning Agent",
        "Business Plan Agent",
        "Report Agent",
        "QA Agent (Secretary)",
    ],
}

DEFAULT_STAFF_SKILL_FILES: dict[str, str] = {}


def load_agent_role_config() -> tuple[
    dict[str, str],
    dict[str, str],
    dict[str, str],
    dict[str, list[str]],
    dict[str, str],
]:
    summaries = dict(DEFAULT_AGENT_ROLE_SUMMARIES)
    role_by_key = dict(DEFAULT_STAFF_ROLE_BY_KEY)
    labels = dict(DEFAULT_STAFF_LABELS)
    roster = {k: list(v) for k, v in DEFAULT_SUPERVISOR_TEAM_ROSTER.items()}
    skill_files = dict(DEFAULT_STAFF_SKILL_FILES)

    if not AGENT_ROLE_CONFIG_PATH.exists():
        return summaries, role_by_key, labels, roster, skill_files

    try:
        raw = json.loads(AGENT_ROLE_CONFIG_PATH.read_text(encoding="utf-8"))
        if isinstance(raw.get("agent_role_summaries"), dict):
            for k, v in raw["agent_role_summaries"].items():
                if isinstance(k, str) and isinstance(v, str):
                    summaries[k] = v
        if isinstance(raw.get("staff_role_by_key"), dict):
            for k, v in raw["staff_role_by_key"].items():
                if isinstance(k, str) and isinstance(v, str):
                    role_by_key[k] = v
        if isinstance(raw.get("staff_labels"), dict):
            for k, v in raw["staff_labels"].items():
                if isinstance(k, str) and isinstance(v, str):
                    labels[k] = v
        if isinstance(raw.get("supervisor_team_roster"), dict):
            for k, v in raw["supervisor_team_roster"].items():
                if isinstance(k, str) and isinstance(v, list):
                    roster[k] = [str(item) for item in v]
        if isinstance(raw.get("staff_skill_files"), dict):
            for k, v in raw["staff_skill_files"].items():
                if isinstance(k, str) and isinstance(v, str):
                    skill_files[k] = v
    except Exception as e:
        capture_exception(e, stage={"name": "load_agent_role_config"})

    return summaries, role_by_key, labels, roster, skill_files


AGENT_ROLE_SUMMARIES, STAFF_ROLE_BY_KEY, STAFF_LABELS, SUPERVISOR_TEAM_ROSTER, STAFF_SKILL_FILES = load_agent_role_config()
ALL_STAFF_KEYS = list(STAFF_LABELS.keys())
ROLE_TO_STAFF_KEY = {role_name: staff_key for staff_key, role_name in STAFF_ROLE_BY_KEY.items()}


def get_comfyui_bat_path() -> Path:
    base = Path(config.comfyui_path)
    candidates = [
        base / "run_nvidia_gpu.bat",
        base / "ComfyUI" / "run_nvidia_gpu.bat",
    ]
    for item in candidates:
        if item.exists():
            return item
    return candidates[0]


def get_comfyui_output_dir() -> Path:
    base = Path(config.comfyui_path)
    candidates = [
        base / "ComfyUI" / "output",
        base / "output",
    ]
    for item in candidates:
        if item.exists():
            return item
    return candidates[0]


def check_comfyui(url: str) -> bool:
    """Quickly probe ComfyUI API."""
    try:
        r = requests.get(f"{url}/system_stats", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def get_ollama_models(base_url: str) -> list[str]:
    """Return list of installed Ollama model names, empty list on failure."""
    try:
        r = requests.get(f"{base_url.rstrip('/')}/api/tags", timeout=5)
        if r.status_code == 200:
            data = r.json()
            return [m["name"] for m in data.get("models", [])]
    except Exception:
        pass
    return []


# ---------------------------------------------------------------------------
# Hermes-inspired Feature 1: Project Context File
# Loads CLAUDE.md as background context injected into every supervisor prompt.
# ---------------------------------------------------------------------------

def load_project_context() -> str:
    """Read CLAUDE.md and return a trimmed summary for prompt injection."""
    try:
        if PROJECT_CONTEXT_FILE.exists():
            raw = PROJECT_CONTEXT_FILE.read_text(encoding="utf-8")
            # Strip markdown headers and blank lines, keep useful text
            lines = [ln for ln in raw.splitlines() if ln.strip() and not ln.startswith("##")]
            trimmed = "\n".join(lines)[:PROJECT_CONTEXT_MAX_CHARS]
            return trimmed.strip()
    except Exception:
        pass
    return ""


def load_wiki_config() -> dict[str, Any]:
    if not WIKI_CONFIG_PATH.exists():
        return {
            "enabled": False,
            "index_path": str(WIKI_DEFAULT_INDEX_PATH.relative_to(PROJECT_ROOT).as_posix()),
            "state_path": str(WIKI_DEFAULT_STATE_PATH.relative_to(PROJECT_ROOT).as_posix()),
            "retrieval": {"top_k": 5, "max_context_chars": 2200, "min_score": 0.08},
            "weights": {
                "keyword": 1.0,
                "staff_scope_boost": 0.9,
                "team_scope_boost": 0.5,
                "skills_source_boost": 0.2,
                "project_context_boost": 0.1,
            },
        }
    try:
        raw = json.loads(WIKI_CONFIG_PATH.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return raw
    except Exception:
        pass
    return {
        "enabled": False,
        "index_path": str(WIKI_DEFAULT_INDEX_PATH.relative_to(PROJECT_ROOT).as_posix()),
        "state_path": str(WIKI_DEFAULT_STATE_PATH.relative_to(PROJECT_ROOT).as_posix()),
        "retrieval": {"top_k": 5, "max_context_chars": 2200, "min_score": 0.08},
        "weights": {
            "keyword": 1.0,
            "staff_scope_boost": 0.9,
            "team_scope_boost": 0.5,
            "skills_source_boost": 0.2,
            "project_context_boost": 0.1,
        },
    }


WIKI_CONFIG = load_wiki_config()


def _wiki_index_path() -> Path:
    rel = str(WIKI_CONFIG.get("index_path", "output/wiki/knowledge_index.json"))
    return PROJECT_ROOT / rel


def _wiki_state_path() -> Path:
    rel = str(WIKI_CONFIG.get("state_path", "output/wiki/knowledge_state.json"))
    return PROJECT_ROOT / rel


def _wiki_retrieval_cfg() -> dict[str, Any]:
    raw = WIKI_CONFIG.get("retrieval", {})
    if isinstance(raw, dict):
        return raw
    return {"top_k": 5, "max_context_chars": 2200, "min_score": 0.08}


def _wiki_weights_cfg() -> dict[str, float]:
    raw = WIKI_CONFIG.get("weights", {})
    if not isinstance(raw, dict):
        raw = {}
    return {
        "keyword": float(raw.get("keyword", 1.0)),
        "staff_scope_boost": float(raw.get("staff_scope_boost", 0.9)),
        "team_scope_boost": float(raw.get("team_scope_boost", 0.5)),
        "skills_source_boost": float(raw.get("skills_source_boost", 0.2)),
        "project_context_boost": float(raw.get("project_context_boost", 0.1)),
    }


def load_knowledge_index() -> dict[str, Any]:
    index_path = _wiki_index_path()
    if not index_path.exists():
        return {"meta": {"chunk_count": 0}, "chunks": []}
    try:
        raw = json.loads(index_path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return raw
    except Exception:
        pass
    return {"meta": {"chunk_count": 0}, "chunks": []}


def load_knowledge_state() -> dict[str, Any]:
    state_path = _wiki_state_path()
    if not state_path.exists():
        return {}
    try:
        raw = json.loads(state_path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return raw
    except Exception:
        pass
    return {}


def rebuild_knowledge_index() -> tuple[bool, str]:
    if not WIKI_BUILD_SCRIPT_PATH.exists():
        return False, "未找到索引脚本 build-knowledge-index.py"

    py_exe = Path(sys.executable)
    if not py_exe.exists():
        return False, "当前 Python 解释器不可用"

    try:
        proc = subprocess.run(
            [str(py_exe), str(WIKI_BUILD_SCRIPT_PATH)],
            cwd=str(PROJECT_ROOT / "agent-platform"),
            capture_output=True,
            text=True,
            timeout=180,
        )
        output = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        if proc.returncode != 0:
            return False, (err or output or "索引构建失败")[:600]
        return True, (output or "索引构建完成")[:600]
    except Exception as e:
        return False, f"索引构建异常: {e}"


def auto_learn_staff_skills() -> tuple[bool, str]:
    if not AUTO_SKILL_LEARN_SCRIPT_PATH.exists():
        return False, "未找到脚本 auto-learn-skills.py"

    py_exe = Path(sys.executable)
    if not py_exe.exists():
        return False, "当前 Python 解释器不可用"

    try:
        proc = subprocess.run(
            [str(py_exe), str(AUTO_SKILL_LEARN_SCRIPT_PATH)],
            cwd=str(PROJECT_ROOT / "agent-platform"),
            capture_output=True,
            text=True,
            timeout=240,
        )
        output = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        if proc.returncode != 0:
            return False, (err or output or "自动学习失败")[:800]
        return True, (output or "全员 Skills 自动学习完成")[:800]
    except Exception as e:
        return False, f"自动学习异常: {e}"


def _resolve_staff_key_for_scope(selected_role: str = "", staff_key: str = "") -> str:
    resolved = staff_key.strip()
    if not resolved and selected_role:
        resolved = ROLE_TO_STAFF_KEY.get(selected_role, "")
    if not resolved and selected_role == "QA Agent (Video)":
        resolved = "qa"
    return resolved


def _team_staff_keys(supervisor_key: str = "") -> list[str]:
    if not supervisor_key:
        return []
    keys = [supervisor_key]
    for role_name in SUPERVISOR_TEAM_ROSTER.get(supervisor_key, []):
        staff = ROLE_TO_STAFF_KEY.get(role_name)
        if staff and staff not in keys:
            keys.append(staff)
    return keys


def _knowledge_score(chunk: dict[str, Any], query: str, staff_key: str = "", supervisor_key: str = "") -> float:
    text = str(chunk.get("text", ""))
    if not text.strip():
        return 0.0

    query_tokens = set(_query_tokens(query))
    text_lower = text.lower()
    keyword_hits = sum(1 for token in query_tokens if token in text_lower)
    keyword_score = keyword_hits / max(len(query_tokens), 1) if query_tokens else 0.0

    scopes = chunk.get("staff_scopes", [])
    if not isinstance(scopes, list):
        scopes = []
    scope_set = {str(x) for x in scopes}

    weights = _wiki_weights_cfg()
    score = keyword_score * weights["keyword"]

    if staff_key and staff_key in scope_set:
        score += weights["staff_scope_boost"]

    if supervisor_key:
        team_set = set(_team_staff_keys(supervisor_key))
        if scope_set.intersection(team_set):
            score += weights["team_scope_boost"]

    source_type = str(chunk.get("source_type", ""))
    if source_type == "skills":
        score += weights["skills_source_boost"]
    if source_type == "project_context":
        score += weights["project_context_boost"]

    return score


def search_knowledge_chunks(
    query: str,
    selected_role: str = "",
    staff_key: str = "",
    supervisor_key: str = "",
    top_k: int | None = None,
) -> list[dict[str, Any]]:
    if not bool(WIKI_CONFIG.get("enabled", False)):
        return []
    if not query or not query.strip():
        return []

    index = load_knowledge_index()
    chunks = index.get("chunks", [])
    if not isinstance(chunks, list) or not chunks:
        return []

    resolved_staff_key = _resolve_staff_key_for_scope(selected_role, staff_key)
    retrieval_cfg = _wiki_retrieval_cfg()
    limit = int(top_k or retrieval_cfg.get("top_k", 5))
    min_score = float(retrieval_cfg.get("min_score", 0.08))

    scored: list[tuple[float, dict[str, Any]]] = []
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        score = _knowledge_score(chunk, query, resolved_staff_key, supervisor_key)
        if score >= min_score:
            scored.append((score, chunk))

    scored.sort(key=lambda item: item[0], reverse=True)
    top = scored[: max(limit, 1)]

    results: list[dict[str, Any]] = []
    for score, chunk in top:
        row = dict(chunk)
        row["score"] = round(score, 4)
        results.append(row)
    return results


def _source_abs_path(source_path: str) -> Path:
    raw = (source_path or "").strip().replace("\\", "/")
    src = Path(raw)
    if src.is_absolute():
        return src
    return PROJECT_ROOT / src


def _source_vscode_uri(source_path: str) -> str:
    abs_path = _source_abs_path(source_path).resolve()
    posix_path = abs_path.as_posix()
    # vscode://file/<abs_path>
    return f"vscode://file/{quote(posix_path)}"


def build_knowledge_context(
    query: str,
    selected_role: str = "",
    staff_key: str = "",
    supervisor_key: str = "",
) -> str:
    retrieval_cfg = _wiki_retrieval_cfg()
    max_chars = int(retrieval_cfg.get("max_context_chars", 2200))
    chunks = search_knowledge_chunks(
        query=query,
        selected_role=selected_role,
        staff_key=staff_key,
        supervisor_key=supervisor_key,
        top_k=int(retrieval_cfg.get("top_k", 5)),
    )
    if not chunks:
        return ""

    lines = ["[LLM Wiki 检索上下文]"]
    for idx, item in enumerate(chunks, start=1):
        src = str(item.get("source_path", "unknown"))
        title = str(item.get("title", "Document"))
        score = item.get("score", 0.0)
        text = str(item.get("text", "")).strip().replace("\n", " ")
        lines.append(f"{idx}. ({score}) {title} | {src}")
        lines.append(f"   {text[:380]}")

    context = "\n".join(lines)
    return context[:max_chars].strip()


# ---------------------------------------------------------------------------
# Hermes-inspired Feature 2: Skills System
# After complex supervisor sessions, key procedures are saved as skill files.
# These are loaded back and injected into future prompts.
# ---------------------------------------------------------------------------

def _ensure_skills_dir() -> None:
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)


def load_all_skills() -> dict[str, str]:
    """Return {skill_name: content} for all .md files in skills dir."""
    _ensure_skills_dir()
    skills: dict[str, str] = {}
    try:
        for f in sorted(SKILLS_DIR.glob("*.md")):
            content = f.read_text(encoding="utf-8").strip()
            if content:
                skills[f.stem] = content
    except Exception:
        pass
    return skills


def load_all_skill_files() -> dict[str, str]:
    """Return {file_name: content} for all .md files in skills dir."""
    _ensure_skills_dir()
    skills: dict[str, str] = {}
    try:
        for f in sorted(SKILLS_DIR.glob("*.md")):
            content = f.read_text(encoding="utf-8").strip()
            if content:
                skills[f.name] = content
    except Exception:
        pass
    return skills


def save_skill(name: str, content: str) -> Path:
    """Persist a skill to output/skills/<name>.md. Overwrites if exists."""
    _ensure_skills_dir()
    safe_name = re.sub(r"[^\w\u4e00-\u9fff\-]", "_", name.strip())[:60]
    path = SKILLS_DIR / f"{safe_name}.md"
    path.write_text(content.strip(), encoding="utf-8")
    return path


def delete_skill(name: str) -> bool:
    path = SKILLS_DIR / f"{name}.md"
    try:
        if path.exists():
            path.unlink()
            return True
    except Exception:
        pass
    return False


def auto_extract_skill(agent_key: str, response: str) -> str | None:
    """
    Hermes-inspired: if response contains a clear multi-step plan (>=3 numbered
    items or section headers), extract and return a candidate skill string.
    Returns None if not skill-worthy.
    """
    numbered = re.findall(r"(?:^|\n)\s*\d+[.、)]\s+.{10,}", response)
    if len(numbered) >= 3:
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M")
        title = f"skill_{agent_key}_{ts}"
        lines = [f"# {title}", "", "## 来源", f"自动从 {agent_key} 对话中提炼 ({ts})", "", "## 步骤"]
        lines += [ln.strip() for ln in numbered[:10]]
        return "\n".join(lines)
    return None


def _ordered_skill_files_for_supervisor(supervisor_key: str) -> list[str]:
    ordered_staff_keys = [supervisor_key]
    for role_name in SUPERVISOR_TEAM_ROSTER.get(supervisor_key, []):
        staff_key = ROLE_TO_STAFF_KEY.get(role_name)
        if staff_key and staff_key not in ordered_staff_keys:
            ordered_staff_keys.append(staff_key)

    ordered_files: list[str] = []
    for staff_key in ordered_staff_keys:
        file_name = STAFF_SKILL_FILES.get(staff_key)
        if file_name and file_name not in ordered_files:
            ordered_files.append(file_name)
    return ordered_files


def _query_tokens(query: str = "") -> list[str]:
    if not query or not query.strip():
        return []
    # Keep order and deduplicate tokens so previews stay stable.
    return list(dict.fromkeys(query.lower().split()))


def _count_query_hits(text: str, query: str = "") -> int:
    if not text:
        return 0
    text_lower = text.lower()
    return sum(1 for token in _query_tokens(query) if token in text_lower)


def _query_match_score(text: str, query: str = "") -> float:
    tokens = _query_tokens(query)
    if not tokens:
        return 0.0
    hits = _count_query_hits(text, query)
    return hits / max(len(tokens), 1)


def _score_level_and_color(score: float) -> tuple[str, str]:
    if score >= 0.67:
        return "高", "#2e7d32"
    if score >= 0.34:
        return "中", "#f9a825"
    return "低", "#c62828"


def _render_score_badge(score: float) -> str:
    level, color = _score_level_and_color(score)
    return (
        f"<span style='display:inline-block;padding:2px 8px;border-radius:999px;"
        f"background:{color};color:#ffffff;font-size:12px;font-weight:600;'>"
        f"相关度 {score:.2f} · {level}</span>"
    )


def _highlight_preview_text(preview_text: str, query: str = "") -> str:
    if not preview_text:
        return ""
    highlighted = preview_text
    tokens = sorted(_query_tokens(query), key=len, reverse=True)
    for token in tokens:
        if not token:
            continue
        highlighted = re.sub(
            re.escape(token),
            lambda match: f"**{match.group(0)}**",
            highlighted,
            flags=re.IGNORECASE,
        )
    return highlighted


def get_supervisor_skill_previews(query: str = "", supervisor_key: str = "") -> list[dict[str, Any]]:
    """Return preview metadata for the skills injected into a supervisor prompt."""
    skills = load_all_skill_files()
    if not skills:
        return []

    query_tokens = set(_query_tokens(query))

    def _skill_score(content: str) -> float:
        if not query_tokens:
            return 1.0
        content_lower = content.lower()
        hits = sum(1 for token in query_tokens if token in content_lower)
        return hits / max(len(query_tokens), 1)

    mapped_items: list[tuple[str, str]] = []
    if supervisor_key:
        for file_name in _ordered_skill_files_for_supervisor(supervisor_key):
            content = skills.get(file_name)
            if content:
                mapped_items.append((file_name, content))

    if mapped_items:
        primary = mapped_items[:1]
        remainder = sorted(mapped_items[1:], key=lambda kv: _skill_score(kv[1]), reverse=True)
        top = primary + remainder[: max(SKILLS_MAX_INJECT - len(primary), 0)]
    else:
        ranked = sorted(skills.items(), key=lambda kv: _skill_score(kv[1]), reverse=True)
        top = ranked[:SKILLS_MAX_INJECT]

    previews: list[dict[str, Any]] = []
    for file_name, content in top:
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        title = lines[0].lstrip("# ").strip() if lines else Path(file_name).stem
        preview_lines: list[str] = []
        for line in lines[1:]:
            if line.startswith("## ") and preview_lines:
                break
            preview_lines.append(line)
        previews.append(
            {
                "file_name": file_name,
                "title": title,
                "preview": "\n".join(preview_lines[:4]).strip(),
                "score": _query_match_score(content, query),
                "hit_count": _count_query_hits(content, query),
            }
        )
    return previews


def build_skills_context(query: str = "", supervisor_key: str = "") -> str:
    """Load role-mapped skills first, then format top relevant items for prompt injection."""
    skills = load_all_skill_files()
    if not skills:
        return ""
    query_tokens = set(_query_tokens(query))

    def _skill_score(content: str) -> float:
        if not query_tokens:
            return 1.0
        content_lower = content.lower()
        hits = sum(1 for t in query_tokens if t in content_lower)
        return hits / max(len(query_tokens), 1)

    mapped_items: list[tuple[str, str]] = []
    if supervisor_key:
        for file_name in _ordered_skill_files_for_supervisor(supervisor_key):
            content = skills.get(file_name)
            if content:
                mapped_items.append((file_name, content))

    if mapped_items:
        primary = mapped_items[:1]
        remainder = sorted(mapped_items[1:], key=lambda kv: _skill_score(kv[1]), reverse=True)
        top = primary + remainder[: max(SKILLS_MAX_INJECT - len(primary), 0)]
    else:
        ranked = sorted(skills.items(), key=lambda kv: _skill_score(kv[1]), reverse=True)
        top = ranked[:SKILLS_MAX_INJECT]

    if not top:
        return ""
    lines = ["[可复用技能库]"]
    for name, content in top:
        summary = content.splitlines()[0].lstrip("# ").strip()
        lines.append(f"• {Path(name).stem}: {summary}")
    return "\n".join(lines)


def build_role_skill_context(selected_role: str = "", staff_key: str = "") -> str:
    """Return the full skill content for a single staff role when available."""
    resolved_staff_key = staff_key
    if not resolved_staff_key and selected_role:
        resolved_staff_key = ROLE_TO_STAFF_KEY.get(selected_role, "")

    if not resolved_staff_key and selected_role == "QA Agent (Video)":
        resolved_staff_key = "qa"

    if not resolved_staff_key:
        return ""

    skill_file = STAFF_SKILL_FILES.get(resolved_staff_key, "")
    if not skill_file:
        return ""

    content = load_all_skill_files().get(skill_file, "")
    if not content:
        return ""

    return f"[岗位专属技能]\n{content}"


def get_staff_skill_preview(selected_role: str = "", staff_key: str = "", query: str = "") -> dict[str, Any]:
    """Return lightweight preview metadata for a staff skill file."""
    resolved_staff_key = staff_key
    if not resolved_staff_key and selected_role:
        resolved_staff_key = ROLE_TO_STAFF_KEY.get(selected_role, "")

    if not resolved_staff_key and selected_role == "QA Agent (Video)":
        resolved_staff_key = "qa"

    if not resolved_staff_key:
        return {}

    file_name = STAFF_SKILL_FILES.get(resolved_staff_key, "")
    if not file_name:
        return {}

    content = load_all_skill_files().get(file_name, "")
    if not content:
        return {"file_name": file_name}

    lines = [line.strip() for line in content.splitlines() if line.strip()]
    title = lines[0].lstrip("# ").strip() if lines else Path(file_name).stem
    query_tokens = set(_query_tokens(query))

    def _line_score(line: str) -> float:
        if not query_tokens:
            return 0.0
        line_lower = line.lower()
        hits = sum(1 for token in query_tokens if token in line_lower)
        return hits / max(len(query_tokens), 1)

    preview_lines: list[str] = []
    if query_tokens:
        ranked_lines = sorted(
            [line for line in lines[1:] if not line.startswith("#")],
            key=_line_score,
            reverse=True,
        )
        preview_lines = [line for line in ranked_lines if _line_score(line) > 0][:6]

    if not preview_lines:
        for line in lines[1:]:
            if line.startswith("## ") and preview_lines:
                break
            preview_lines.append(line)

    return {
        "staff_key": resolved_staff_key,
        "file_name": file_name,
        "title": title,
        "preview": "\n".join(preview_lines[:6]).strip(),
        "score": _query_match_score(content, query),
        "hit_count": _count_query_hits(content, query),
    }


# ---------------------------------------------------------------------------
# Hermes-inspired Feature 3: Memory Search
# Keyword search across all agent memory turns (cross-session recall).
# ---------------------------------------------------------------------------

def search_agent_memory(query: str, top_k: int = 6) -> list[dict]:
    """
    Search all agent memory turns for keyword matches.
    Returns list of {agent_key, user, assistant, ts, score}.
    """
    if not query or not query.strip():
        return []
    store = st.session_state.get("agent_memory_store", {})
    if not isinstance(store, dict):
        return []

    query_tokens = set(query.lower().split())
    results: list[tuple[float, dict]] = []

    for agent_key, raw_entry in store.items():
        entry = _normalize_agent_memory_entry(raw_entry)
        for turn in entry.get("turns", []):
            text = f"{turn.get('user', '')} {turn.get('assistant', '')}".lower()
            hits = sum(1 for t in query_tokens if t in text)
            if hits > 0:
                score = hits / max(len(query_tokens), 1)
                results.append((score, {
                    "agent_key": agent_key,
                    "user": str(turn.get("user", ""))[:200],
                    "assistant": str(turn.get("assistant", ""))[:300],
                    "ts": str(turn.get("ts", "")),
                    "score": round(score, 2),
                }))

    results.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in results[:top_k]]


def launch_comfyui() -> bool:
    """Launch ComfyUI in a detached process. Returns True if bat file exists."""
    comfyui_bat = get_comfyui_bat_path()
    if not comfyui_bat.exists():
        return False
    subprocess.Popen(
        ["cmd", "/c", "start", "", str(comfyui_bat)],
        cwd=str(comfyui_bat.parent),
        shell=False,
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )
    return True


def launch_ollama() -> bool:
    """Launch Ollama service in a detached process."""
    try:
        subprocess.Popen(
            ["cmd", "/c", "start", "", "ollama", "serve"],
            shell=False,
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
        return True
    except Exception:
        return False


def check_secretary_dashboard(url: str) -> bool:
    """Probe personal-secretary Streamlit endpoint."""
    try:
        r = requests.get(url, timeout=2)
        return r.status_code == 200
    except Exception:
        return False


def launch_secretary_dashboard() -> bool:
    """Launch personal-secretary dashboard in detached mode on fixed port."""
    if not SECRETARY_ROOT.exists():
        return False
    python_exe = SECRETARY_ROOT / ".venv" / "Scripts" / "python.exe"
    if not python_exe.exists():
        return False
    # Best-effort cleanup for stale dashboard listeners that cause 8502/8503 conflicts.
    for pids in _list_listening_pids_by_port({8502, int(SECRETARY_DASHBOARD_PORT)}).values():
        for pid in pids:
            _taskkill_pid(pid)
    subprocess.Popen(
        [
            "cmd",
            "/c",
            "start",
            "",
            str(python_exe),
            "-m",
            "streamlit",
            "run",
            "app_dashboard.py",
            "--server.port",
            str(SECRETARY_DASHBOARD_PORT),
        ],
        cwd=str(SECRETARY_ROOT),
        shell=False,
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )
    return True


def _list_pids_by_command_marker(marker: str) -> set[int]:
    if not marker:
        return set()
    safe_marker = marker.replace("'", "''")
    try:
        proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                (
                    "Get-CimInstance Win32_Process | "
                    "Where-Object { "
                    "($_.Name -match '^python(\\.exe)?$' -or $_.Name -match '^py(\\.exe)?$') -and "
                    f"$_.CommandLine -like '*{safe_marker}*' }} | "
                    "Select-Object -ExpandProperty ProcessId"
                ),
            ],
            capture_output=True,
            text=True,
            errors="ignore",
            timeout=8,
            check=False,
        )
    except Exception:
        return set()

    pids: set[int] = set()
    for line in proc.stdout.splitlines():
        text = line.strip()
        if text.isdigit():
            pids.add(int(text))
    return pids


def check_telegram_bot_poller() -> bool:
    return bool(_list_pids_by_command_marker("run_telegram_bot.py"))


def launch_telegram_bot_poller() -> bool:
    if not SECRETARY_ROOT.exists():
        return False
    python_exe = SECRETARY_ROOT / ".venv" / "Scripts" / "python.exe"
    if not python_exe.exists() or not TELEGRAM_BOT_SCRIPT_PATH.exists():
        return False
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    subprocess.Popen(
        [
            "cmd",
            "/c",
            "start",
            "",
            str(python_exe),
            str(TELEGRAM_BOT_SCRIPT_PATH.name),
        ],
        cwd=str(SECRETARY_ROOT),
        env=env,
        shell=False,
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )
    return True


def _list_listening_pids_by_port(target_ports: set[int]) -> dict[int, set[int]]:
    """Return {port: {pid, ...}} by parsing `netstat -ano -p tcp` output."""
    if not target_ports:
        return {}
    mapping: dict[int, set[int]] = {p: set() for p in target_ports}
    try:
        proc = subprocess.run(
            ["netstat", "-ano", "-p", "tcp"],
            capture_output=True,
            text=True,
            errors="ignore",
            timeout=8,
            check=False,
        )
    except Exception:
        return mapping

    for raw in proc.stdout.splitlines():
        line = raw.strip()
        if "LISTENING" not in line.upper():
            continue
        parts = re.split(r"\s+", line)
        if len(parts) < 5:
            continue
        local_addr = parts[1]
        pid_text = parts[-1]
        if ":" not in local_addr or not pid_text.isdigit():
            continue
        port_text = local_addr.rsplit(":", 1)[-1].strip()
        if not port_text.isdigit():
            continue
        port = int(port_text)
        if port in target_ports:
            mapping.setdefault(port, set()).add(int(pid_text))
    return mapping


def _taskkill_pid(pid: int) -> bool:
    try:
        proc = subprocess.run(
            ["taskkill", "/PID", str(pid), "/F", "/T"],
            capture_output=True,
            text=True,
            errors="ignore",
            timeout=8,
            check=False,
        )
        return proc.returncode == 0
    except Exception:
        return False


def stop_managed_services() -> dict[str, Any]:
    """Stop backend services used by GUI (not killing current Streamlit GUI process)."""
    target_ports = {8188, 11434, int(SECRETARY_DASHBOARD_PORT)}
    pid_map = _list_listening_pids_by_port(target_ports)
    telegram_pids = _list_pids_by_command_marker("run_telegram_bot.py")
    current_pid = os.getpid()
    stopped: list[str] = []
    failed: list[str] = []

    for port in sorted(target_ports):
        for pid in sorted(pid_map.get(port, set())):
            if pid == current_pid:
                continue
            if _taskkill_pid(pid):
                stopped.append(f"port={port} pid={pid}")
            else:
                failed.append(f"port={port} pid={pid}")

    # Extra fallback: ensure ollama background process is stopped even when not listening yet.
    try:
        subprocess.run(
            ["taskkill", "/IM", "ollama.exe", "/F", "/T"],
            capture_output=True,
            text=True,
            errors="ignore",
            timeout=8,
            check=False,
        )
    except Exception:
        pass

    for pid in sorted(telegram_pids):
        if pid == current_pid:
            continue
        if _taskkill_pid(pid):
            stopped.append(f"telegram pid={pid}")
        else:
            failed.append(f"telegram pid={pid}")

    remaining = _list_listening_pids_by_port(target_ports)
    open_ports = sorted([p for p in target_ports if remaining.get(p)])
    return {
        "stopped": stopped,
        "failed": failed,
        "open_ports": open_ports,
        "ok": len(open_ports) == 0,
    }


def restart_managed_services() -> dict[str, Any]:
    """Stop managed services then restart ComfyUI, Ollama, Secretary Dashboard and Telegram Bot."""
    stop_result = stop_managed_services()
    start_result = {
        "comfyui": launch_comfyui(),
        "ollama": launch_ollama(),
        "secretary": launch_secretary_dashboard(),
        "telegram": launch_telegram_bot_poller(),
    }
    return {"stop": stop_result, "start": start_result}


def get_secretary_agents() -> list[str]:
    """Read agent names from personal-secretary orchestrator without cross-import."""
    orchestrator = SECRETARY_ROOT / "src" / "personal_secretary" / "agent_orchestrator.py"
    if not orchestrator.exists():
        return []
    try:
        content = orchestrator.read_text(encoding="utf-8", errors="ignore")
        names = re.findall(r'"agent"\s*:\s*"([^"]+)"', content)
        # Keep order and remove duplicates
        seen: set[str] = set()
        ordered: list[str] = []
        for name in names:
            if name not in seen:
                seen.add(name)
                ordered.append(name)
        return ordered
    except Exception:
        return []


def get_secretary_stats() -> dict[str, int | str]:
    """Lightweight stats for boss dashboard."""
    stats: dict[str, int | str] = {
        "indexed_files": 0,
        "agent_runs": 0,
        "latest_run": "N/A",
    }
    if not SECRETARY_DB_PATH.exists():
        return stats
    try:
        with sqlite3.connect(SECRETARY_DB_PATH) as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM indexed_files")
            row = cur.fetchone()
            stats["indexed_files"] = int(row[0]) if row else 0

            cur.execute("SELECT COUNT(*) FROM agent_runs")
            row = cur.fetchone()
            stats["agent_runs"] = int(row[0]) if row else 0

            cur.execute("SELECT finished_at FROM agent_runs ORDER BY id DESC LIMIT 1")
            row = cur.fetchone()
            if row and row[0]:
                stats["latest_run"] = str(row[0])
    except Exception:
        return stats
    return stats


def get_comfyui_input_dir() -> Path:
    base = Path(config.comfyui_path)
    if base.name.lower() == "comfyui":
        return base / "input"
    nested = base / "ComfyUI" / "input"
    if nested.exists() or (base / "ComfyUI").exists():
        return nested
    return base / "input"


def save_uploaded_image(uploaded_file) -> str:
    suffix = Path(uploaded_file.name).suffix.lower()
    if suffix not in ALLOWED_IMAGE_SUFFIXES:
        raise ValueError(f"Unsupported image type: {suffix}")

    safe_stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(uploaded_file.name).stem).strip("._")
    safe_stem = safe_stem or "uploaded_image"
    filename = f"codex_{uuid.uuid4().hex[:10]}_{safe_stem}{suffix}"
    input_dir = get_comfyui_input_dir()
    input_dir.mkdir(parents=True, exist_ok=True)
    output_path = input_dir / filename
    output_path.write_bytes(uploaded_file.getbuffer())
    return str(output_path)


def save_boss_meeting_attachment(uploaded_file) -> dict[str, str]:
    suffix = Path(uploaded_file.name).suffix.lower()
    safe_stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(uploaded_file.name).stem).strip("._")
    safe_stem = safe_stem or "attachment"
    filename = f"boss_{uuid.uuid4().hex[:10]}_{safe_stem}{suffix}"
    BOSS_MEETING_ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = BOSS_MEETING_ATTACHMENTS_DIR / filename
    output_path.write_bytes(uploaded_file.getbuffer())

    raw_bytes = uploaded_file.getvalue()
    preview = ""
    if suffix in {".txt", ".md", ".json", ".csv", ".log", ".yaml", ".yml"}:
        for enc in ("utf-8", "gbk"):
            try:
                preview = raw_bytes.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        preview = preview[:600]

    return {
        "name": uploaded_file.name,
        "saved_path": str(output_path),
        "mime_type": str(getattr(uploaded_file, "type", "")),
        "size": str(len(raw_bytes)),
        "preview": preview,
    }


def fetch_available_node_types(base_url: str) -> set[str]:
    """Fetch registered ComfyUI node types from /object_info."""
    response = requests.get(f"{base_url}/object_info", timeout=5)
    response.raise_for_status()
    data = response.json()
    if isinstance(data, dict):
        return set(data.keys())
    return set()


def has_ltx_gemma_ready(base_url: str) -> bool:
    """Check whether LTX Gemma text encoder options are available in ComfyUI."""
    try:
        response = requests.get(f"{base_url}/object_info", timeout=5)
        response.raise_for_status()
        data = response.json()
        loader = data.get("LTXVGemmaCLIPModelLoader", {})
        required = (
            loader.get("input", {})
            .get("required", {})
            .get("gemma_path", [])
        )
        if not required:
            return False
        options = required[0] if isinstance(required, list) and required else []
        return bool(options)
    except Exception:
        return False


def get_missing_node_types(workflow_path: str, available_node_types: set[str]) -> list[str]:
    """Compare workflow required class_type against ComfyUI registered node types."""
    workflow_json = Path(workflow_path)
    if not workflow_json.exists():
        return [f"workflow_not_found:{workflow_path}"]

    with workflow_json.open("r", encoding="utf-8-sig") as f:
        workflow = json.load(f)

    required = {
        str(node.get("class_type", "")).strip()
        for node in workflow.values()
        if isinstance(node, dict) and node.get("class_type")
    }
    missing = sorted(node_type for node_type in required if node_type not in available_node_types)
    return missing


def write_run_report(result: dict, brief: str, workflow_path: str, input_image_path: str | None) -> tuple[str, str]:
    report_dir = PROJECT_ROOT / "output" / "run-reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    prompt_id = str(result.get("render_job_id", "unknown"))
    stem = f"run-{ts}-{prompt_id[:8]}"
    md_path = report_dir / f"{stem}.md"
    json_path = report_dir / f"{stem}.json"

    qa = result.get("qa_report", {}) or {}
    render_output = result.get("render_output", {}) or {}
    output_files: list[str] = []
    outputs = render_output.get("outputs", {}) if isinstance(render_output, dict) else {}
    for _, node_data in outputs.items():
        if not isinstance(node_data, dict):
            continue
        gifs = node_data.get("gifs", [])
        for g in gifs:
            if isinstance(g, dict):
                p = g.get("fullpath") or g.get("filename")
                if p:
                    output_files.append(str(p))

    status = result.get("render_status", "unknown")
    passed = qa.get("passed", False)
    md = (
        "# Run Report\n\n"
        f"- Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"- Prompt ID: {prompt_id}\n"
        f"- Workflow: {workflow_path}\n"
        f"- Input Image: {input_image_path or 'none'}\n"
        f"- Render Status: {status}\n"
        f"- QA Passed: {passed}\n"
        f"- QA Scores: face={qa.get('face', 'N/A')}, motion={qa.get('motion', 'N/A')}, artifact={qa.get('artifact', 'N/A')}\n"
        f"- Retry Count: {result.get('retry_count', 0)}\n"
        f"- Brief: {brief}\n\n"
        "## Output Files\n"
        + ("\n".join([f"- {p}" for p in output_files]) if output_files else "- none")
        + "\n"
    )
    md_path.write_text(md, encoding="utf-8")
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(md_path), str(json_path)


def _empty_agent_memory_entry() -> dict[str, Any]:
    return {
        "turns": [],
        "long_summary": "",
        "facts": [],
    }


def _normalize_agent_memory_entry(raw: Any) -> dict[str, Any]:
    entry = _empty_agent_memory_entry()

    # Backward compatibility: old format was directly a list of turns.
    if isinstance(raw, list):
        raw = {"turns": raw}

    if not isinstance(raw, dict):
        return entry

    turns = raw.get("turns", [])
    if isinstance(turns, list):
        filtered: list[dict[str, Any]] = []
        for item in turns:
            if not isinstance(item, dict):
                continue
            user = str(item.get("user", "")).strip()
            assistant = str(item.get("assistant", "")).strip()
            if user or assistant:
                filtered.append(
                    {
                        "user": user,
                        "assistant": assistant,
                        "ts": str(item.get("ts", "")).strip(),
                        "success": bool(item.get("success", True)),
                    }
                )
        entry["turns"] = filtered[-AGENT_MEMORY_MAX_TURNS:]

    summary = str(raw.get("long_summary", "")).strip()
    entry["long_summary"] = summary[:AGENT_MEMORY_SUMMARY_MAX_CHARS]

    facts = raw.get("facts", [])
    if isinstance(facts, list):
        clean_facts: list[str] = []
        for f in facts:
            fact = str(f).strip()
            if fact:
                clean_facts.append(fact)
        entry["facts"] = list(dict.fromkeys(clean_facts))[:AGENT_MEMORY_MAX_FACTS]

    return entry


def load_agent_memory_store() -> dict[str, dict[str, Any]]:
    if not AGENT_MEMORY_PATH.exists():
        return {}
    try:
        payload = json.loads(AGENT_MEMORY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    clean: dict[str, dict[str, Any]] = {}
    for agent_key, raw_entry in payload.items():
        if not isinstance(agent_key, str):
            continue
        clean[agent_key] = _normalize_agent_memory_entry(raw_entry)
    return clean


def save_agent_memory_store(store: dict[str, dict[str, Any]]) -> None:
    AGENT_MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    AGENT_MEMORY_PATH.write_text(
        json.dumps(store, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _tokenize_for_memory(text: str) -> set[str]:
    raw = (text or "").lower()
    return set(re.findall(r"[a-z0-9_]{2,}|[\u4e00-\u9fff]{2,}", raw))


def _memory_turn_score(turn: dict[str, Any], query_tokens: set[str]) -> float:
    recency = 0.3
    ts_raw = str(turn.get("ts", "")).strip()
    if ts_raw:
        try:
            dt = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            age_days = max(0.0, (datetime.now(dt.tzinfo) - dt).total_seconds() / 86400.0)
            recency = max(0.1, 1.0 - min(age_days / AGENT_MEMORY_RECENCY_DAYS, 1.0))
        except Exception:
            recency = 0.3

    text = f"{turn.get('user', '')} {turn.get('assistant', '')}"
    tokens = _tokenize_for_memory(text)
    overlap = len(query_tokens.intersection(tokens)) if query_tokens else 0
    relevance = min(1.0, overlap / 6.0) if query_tokens else 0.2
    success = 1.0 if bool(turn.get("success", True)) else 0.2

    # Weighted memory score: recency + relevance + historical success.
    return round(recency * 0.4 + relevance * 0.4 + success * 0.2, 3)


def build_agent_memory_context(agent_key: str, current_query: str = "") -> str:
    store = st.session_state.get("agent_memory_store", {})
    entry = _normalize_agent_memory_entry(store.get(agent_key, {})) if isinstance(store, dict) else _empty_agent_memory_entry()
    turns = entry.get("turns", [])
    summary = str(entry.get("long_summary", "")).strip()
    facts = entry.get("facts", [])

    if not turns and not summary and not facts:
        return ""

    lines: list[str] = []

    if summary:
        lines.append("[长期记忆摘要]")
        lines.append(summary)

    if isinstance(facts, list) and facts:
        lines.append("[关键事实]")
        for fact in facts[:8]:
            lines.append(f"- {fact}")

    query_tokens = _tokenize_for_memory(current_query)
    ranked_turns = sorted(
        turns,
        key=lambda t: _memory_turn_score(t, query_tokens),
        reverse=True,
    )
    clipped = ranked_turns[:AGENT_MEMORY_CONTEXT_TURNS]
    if clipped:
        lines.append("[检索记忆片段]")
    for idx, turn in enumerate(clipped, start=1):
        user = str(turn.get("user", "")).replace("\n", " ").strip()
        assistant = str(turn.get("assistant", "")).replace("\n", " ").strip()
        score = _memory_turn_score(turn, query_tokens)
        lines.append(f"{idx}. (score={score}) 用户: {user[:220]}")
        lines.append(f"   助手: {assistant[:220]}")
    return "\n".join(lines)


def _extract_memory_facts(user: str, assistant: str) -> list[str]:
    text = f"{user}\n{assistant}"
    patterns = [
        r"(?:记住|请记住|remember)[:：]?\s*([^\n。；]{4,60})",
        r"(?:偏好|喜欢|不要|必须)[:：]?\s*([^\n。；]{4,60})",
        r"(?:预算|截止|deadline|style|模型)[:：]?\s*([^\n。；]{2,60})",
    ]
    facts: list[str] = []
    for p in patterns:
        for m in re.findall(p, text, flags=re.IGNORECASE):
            candidate = str(m).strip(" .;；，,")
            if len(candidate) >= 4:
                facts.append(candidate)
    return list(dict.fromkeys(facts))[:5]


def _refresh_agent_memory_layers(agent_key: str) -> None:
    store = st.session_state.get("agent_memory_store", {})
    if not isinstance(store, dict):
        return

    entry = _normalize_agent_memory_entry(store.get(agent_key, {}))
    turns = entry.get("turns", [])
    if not turns:
        store[agent_key] = entry
        return

    # Update fact memory from latest turn.
    latest = turns[-1]
    new_facts = _extract_memory_facts(str(latest.get("user", "")), str(latest.get("assistant", "")))
    if new_facts:
        facts = entry.get("facts", [])
        if not isinstance(facts, list):
            facts = []
        entry["facts"] = list(dict.fromkeys(facts + new_facts))[:AGENT_MEMORY_MAX_FACTS]

    # Update long summary every 3 turns to control latency.
    need_summary = (len(turns) % 3 == 0) or not str(entry.get("long_summary", "")).strip()
    if need_summary:
        recent = turns[-10:]
        transcript = []
        for idx, t in enumerate(recent, start=1):
            transcript.append(f"{idx}) 用户: {str(t.get('user', ''))[:180]}")
            transcript.append(f"   助手: {str(t.get('assistant', ''))[:220]}")
        summary_prompt = (
            "请将以下对话记忆压缩为 6 条以内长期记忆要点，中文输出，突出稳定偏好、约束、目标。"
            "不要复述细节，不要超过 260 字。\n\n"
            + "\n".join(transcript)
        )
        try:
            compact = runtime.supervisor_agent.chat(summary_prompt)
            entry["long_summary"] = str(compact).strip()[:AGENT_MEMORY_SUMMARY_MAX_CHARS]
        except Exception:
            # Keep previous summary on failure.
            entry["long_summary"] = str(entry.get("long_summary", "")).strip()[:AGENT_MEMORY_SUMMARY_MAX_CHARS]

    store[agent_key] = entry


def append_agent_memory(agent_key: str, user: str, assistant: str, success: bool = True) -> None:
    store = st.session_state.setdefault("agent_memory_store", {})
    if not isinstance(store, dict):
        store = {}
        st.session_state.agent_memory_store = store

    entry = _normalize_agent_memory_entry(store.get(agent_key, {}))
    turns = entry.get("turns", [])
    if not isinstance(turns, list):
        turns = []
    turns.append(
        {
            "user": user.strip(),
            "assistant": assistant.strip(),
            "ts": datetime.utcnow().isoformat(),
            "success": bool(success),
        }
    )
    entry["turns"] = turns[-AGENT_MEMORY_MAX_TURNS:]
    store[agent_key] = entry

    _refresh_agent_memory_layers(agent_key)
    save_agent_memory_store(store)


def render_boss_meeting_attachments_panel() -> None:
    attachments = st.session_state.get("boss_meeting_attachments", [])
    with st.expander("会议附件箱", expanded=bool(attachments)):
        if not attachments:
            st.caption("尚未添加附件。你可以上传会议资料、截图、CSV、TXT、MD 等文件。")
            return
        for idx, item in enumerate(attachments, start=1):
            st.write(f"{idx}. {item.get('name', 'attachment')}")
            st.caption(
                f"类型: {item.get('mime_type', 'N/A')} | 大小: {item.get('size', 'N/A')} bytes | 路径: {item.get('saved_path', 'N/A')}"
            )
            preview = str(item.get("preview", "")).strip()
            if preview:
                st.text(preview[:400])


def build_boss_meeting_attachment_context() -> str:
    attachments = st.session_state.get("boss_meeting_attachments", [])
    if not attachments:
        return ""
    lines = ["[会议附件]"]
    for idx, item in enumerate(attachments, start=1):
        lines.append(
            f"{idx}. 文件: {item.get('name', 'attachment')} | 类型: {item.get('mime_type', 'N/A')} | 大小: {item.get('size', 'N/A')} bytes"
        )
        preview = str(item.get("preview", "")).strip()
        if preview:
            lines.append(f"   预览: {preview[:300]}")
    return "\n".join(lines)


def pick_boss_meeting_image_path() -> str:
    """Pick the first uploaded image attachment as optional I2V reference input."""
    attachments = st.session_state.get("boss_meeting_attachments", [])
    if not isinstance(attachments, list):
        return ""

    image_exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
    for item in attachments:
        if not isinstance(item, dict):
            continue
        saved_path = str(item.get("saved_path", "")).strip()
        if not saved_path:
            continue
        path_obj = Path(saved_path)
        if path_obj.suffix.lower() in image_exts and path_obj.exists():
            return str(path_obj)
    return ""


def clear_agent_memory(agent_key: str) -> None:
    store = st.session_state.get("agent_memory_store", {})
    if not isinstance(store, dict):
        return
    store[agent_key] = _empty_agent_memory_entry()
    save_agent_memory_store(store)


def get_agent_memory_stats(agent_key: str) -> dict[str, Any]:
    store = st.session_state.get("agent_memory_store", {})
    entry = _normalize_agent_memory_entry(store.get(agent_key, {})) if isinstance(store, dict) else _empty_agent_memory_entry()
    turns = entry.get("turns", [])
    facts = entry.get("facts", [])
    success_count = sum(1 for t in turns if bool(t.get("success", True)))
    total = len(turns)
    return {
        "turns": total,
        "facts": len(facts) if isinstance(facts, list) else 0,
        "summary_chars": len(str(entry.get("long_summary", ""))),
        "success_rate": round((success_count / total), 3) if total else 0.0,
    }


def render_agent_memory_panel(agent_key: str, title: str = "记忆面板") -> None:
    store = st.session_state.get("agent_memory_store", {})
    entry = _normalize_agent_memory_entry(store.get(agent_key, {})) if isinstance(store, dict) else _empty_agent_memory_entry()
    turns = entry.get("turns", [])
    with st.expander(title, expanded=False):
        st.caption(f"长期摘要长度: {len(str(entry.get('long_summary', '')))} chars")
        summary = str(entry.get("long_summary", "")).strip()
        if summary:
            st.write(summary)
        facts = entry.get("facts", [])
        if isinstance(facts, list) and facts:
            st.write("关键事实")
            for fact in facts[:10]:
                st.write(f"- {fact}")
        if turns:
            st.write("最近记忆")
            for t in turns[-4:]:
                u = str(t.get("user", ""))[:120]
                a = str(t.get("assistant", ""))[:140]
                st.caption(f"用户: {u}")
                st.caption(f"助手: {a}")


def build_team_conversation(
    result: dict,
    brief: str,
    workflow_path: str,
    input_image_path: str | None,
) -> list[dict[str, str]]:
    """Build a readable boss/staff conversation from pipeline state."""
    convo: list[dict[str, str]] = []

    def say(speaker: str, message: str) -> None:
        convo.append({"speaker": speaker, "message": message})

    qa = result.get("qa_report", {}) or {}
    plan = result.get("production_plan", {}) or {}
    scene = result.get("scene_spec", {}) or {}
    prompt_pack = result.get("prompt_pack", {}) or {}
    decision = result.get("supervisor_decision", {}) or {}
    retry_count = int(result.get("retry_count", 0))

    say("老板", f"任务需求：{brief}")
    say(
        "主管Agent",
        (
            "收到任务，开始组织分工："
            f"workflow={Path(workflow_path).name}，"
            f"有无参考图={'有' if input_image_path else '无'}。"
        ),
    )

    if "image_analysis" in result:
        image_info = result["image_analysis"]
        say(
            "Image Agent",
            (
                "参考图分析完成："
                f"{image_info.get('width', 'N/A')}x{image_info.get('height', 'N/A')}，"
                f"方向={image_info.get('orientation', 'N/A')}，"
                f"亮度={image_info.get('brightness', 'N/A')}。"
            ),
        )

    if plan:
        say(
            "Production Planner",
            (
                "制作方案已出："
                f"类型={plan.get('workflow_type', 'N/A')}，"
                f"目标格式={plan.get('target_format', 'N/A')}，"
                f"运动策略={plan.get('motion_strategy', 'N/A')}。"
            ),
        )

    if scene:
        say(
            "Story Agent",
            (
                "脚本拆解完成："
                f"场景={scene.get('scene', 'N/A')}；"
                f"动作={scene.get('action', 'N/A')}；"
                f"氛围={scene.get('mood', 'N/A')}。"
            ),
        )

    if prompt_pack:
        say(
            "Prompt Agent",
            (
                "提示词包完成："
                f"正向片段={str(prompt_pack.get('positive', ''))[:80]}...；"
                f"运动片段={str(prompt_pack.get('motion_prompt', ''))[:60]}..."
            ),
        )

    say("Builder Agent", "已将 Prompt、seed 和参考图信息注入工作流，提交渲染任务。")

    if retry_count > 0:
        say(
            "主管Agent",
            f"检测到质量风险，已触发重试 {retry_count} 次并给出重试提示：{decision.get('retry_hint', 'N/A')}",
        )

    say(
        "QA Agent",
        (
            "质检评分："
            f"face={qa.get('face', 'N/A')}，"
            f"motion={qa.get('motion', 'N/A')}，"
            f"artifact={qa.get('artifact', 'N/A')}，"
            f"结论={'通过' if qa.get('passed') else '未通过'}。"
        ),
    )

    say(
        "主管Agent",
        f"向老板汇报：任务已{'完成并通过质检' if qa.get('passed') else '完成但需复审'}。",
    )
    return convo


def render_team_conversation(conversation: list[dict[str, str]]) -> None:
    st.subheader("👔 老板-员工协作对话")
    st.caption("你下达任务后，主管Agent分派给各员工Agent并汇总回报。")
    for i, item in enumerate(conversation, start=1):
        speaker = item.get("speaker", "Agent")
        message = item.get("message", "")
        with st.container(border=True):
            st.markdown(f"**{i}. {speaker}**")
            st.write(message)


def render_staff_skills_assignment_overview() -> None:
    with st.expander("员工 skills 与分工矩阵", expanded=False):
        st.markdown("#### 视频团队")
        for key in ["image", "production", "story", "prompt", "builder", "qa"]:
            role = STAFF_ROLE_BY_KEY[key]
            st.write(f"- {STAFF_LABELS[key]}：{AGENT_ROLE_SUMMARIES.get(role, '岗位说明缺失')}")
        st.markdown("#### 秘书团队")
        for key in ["retriever", "document_reader", "fileops", "finance", "learning", "business_plan", "report", "secretary_qa"]:
            role = STAFF_ROLE_BY_KEY[key]
            st.write(f"- {STAFF_LABELS[key]}：{AGENT_ROLE_SUMMARIES.get(role, '岗位说明缺失')}")


def pick_first_compatible_workflow(base_url: str, candidates: list[Path]) -> tuple[str | None, list[str]]:
    """Pick first fully compatible workflow; returns path and diagnostics for all tried candidates."""
    diagnostics: list[str] = []
    try:
        available = fetch_available_node_types(base_url)
    except Exception as e:
        diagnostics.append(f"读取 /object_info 失败: {e}")
        return None, diagnostics

    for path in candidates:
        if not path.exists():
            diagnostics.append(f"{path.name}: 文件不存在")
            continue
        missing = get_missing_node_types(str(path), available)
        if not missing:
            return str(path), diagnostics
        diagnostics.append(f"{path.name}: 缺少节点 {', '.join(missing)}")

    return None, diagnostics


st.set_page_config(page_title="HoneyHive Studio | 蜂巢协作智能", layout="wide")

st.markdown(
    """
    <style>
    .stApp {
        background:
            radial-gradient(circle at 10% 10%, rgba(255, 209, 84, 0.30), transparent 35%),
            radial-gradient(circle at 90% 0%, rgba(255, 181, 46, 0.20), transparent 30%),
            linear-gradient(135deg, #fffaf0 0%, #fff2cc 100%);
        color: #1f1b16;
    }
    .stApp * {
        color: #1f1b16;
    }
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, rgba(255, 247, 226, 0.98), rgba(255, 239, 197, 0.98)) !important;
        border-right: 1px solid rgba(116, 78, 15, 0.28) !important;
    }
    [data-testid="stSidebar"] [data-testid="stSidebarContent"] {
        background: transparent !important;
    }
    .stMarkdown, .stText, .stCaption, .stMetric, p, li, label, span {
        color: #1f1b16 !important;
    }
    .stSidebar * {
        color: #241c12 !important;
        opacity: 1 !important;
    }
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3,
    [data-testid="stSidebar"] h4,
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] div,
    [data-testid="stSidebar"] span,
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] li,
    [data-testid="stSidebar"] strong {
        color: #1f160c !important;
        text-shadow: none !important;
    }
    [data-testid="stSidebar"] a {
        color: #4b2f00 !important;
        font-weight: 700 !important;
        text-decoration: underline !important;
    }
    [data-testid="stSidebar"] hr {
        border-color: rgba(108, 72, 10, 0.30) !important;
    }
    [data-testid="stTextArea"] textarea,
    [data-testid="stTextInput"] input,
    [data-testid="stNumberInput"] input,
    [data-testid="stChatInput"] textarea,
    [data-testid="stChatInput"] input,
    [data-testid="stFileUploaderDropzone"],
    [data-testid="stFileUploaderDropzone"] > div,
    .stSelectbox div[data-baseweb="select"] > div,
    [data-testid="stChatMessage"],
    [data-testid="stJson"],
    [data-testid="stCodeBlock"] {
        background: #ffffff !important;
        color: #1f1b16 !important;
        border: 1px solid rgba(108, 72, 10, 0.25) !important;
        border-radius: 10px !important;
    }
    div[role="listbox"],
    ul[role="listbox"] {
        background: #fffdf7 !important;
        border: 1px solid rgba(108, 72, 10, 0.30) !important;
        box-shadow: 0 8px 20px rgba(56, 39, 8, 0.14) !important;
    }
    div[role="option"],
    li[role="option"] {
        background: #fffdf7 !important;
        color: #1f1b16 !important;
    }
    div[role="option"] *,
    li[role="option"] * {
        color: #1f1b16 !important;
    }
    div[role="option"]:hover,
    li[role="option"]:hover {
        background: #ffe9b3 !important;
    }
    div[aria-selected="true"][role="option"],
    li[aria-selected="true"][role="option"] {
        background: #ffd775 !important;
        color: #2a1f0f !important;
        font-weight: 700;
    }
    [data-testid="stTextArea"] textarea::placeholder,
    [data-testid="stTextInput"] input::placeholder,
    [data-testid="stChatInput"] textarea::placeholder,
    [data-testid="stChatInput"] input::placeholder {
        color: #7a6a54 !important;
        opacity: 1 !important;
    }
    [data-testid="stFileUploader"] * {
        color: #1f1b16 !important;
    }
    [data-testid="stFileUploader"] small,
    [data-testid="stFileUploader"] p,
    [data-testid="stFileUploader"] span {
        color: #5a4730 !important;
    }
    [data-testid="stFileUploader"] button {
        background: #fff7df !important;
        color: #2a1f0f !important;
        border: 1px solid rgba(96, 65, 8, 0.35) !important;
    }
    .stTabs [role="tab"] {
        color: #2a1f0f !important;
        font-weight: 700;
    }
    .stTabs [aria-selected="true"] {
        background: rgba(195, 130, 18, 0.18) !important;
        border-radius: 10px;
    }
    h1, h2, h3, h4 {
        color: #2a1f0f !important;
    }
    a {
        color: #533500 !important;
    }
    .stButton > button,
    .stDownloadButton > button,
    .stLinkButton > a {
        color: #2a1f0f !important;
        border: 1px solid rgba(96, 65, 8, 0.35) !important;
        background: rgba(255, 245, 220, 0.92) !important;
    }
    [data-testid="stSidebar"] .stButton > button,
    [data-testid="stSidebar"] .stDownloadButton > button,
    [data-testid="stSidebar"] .stLinkButton > a {
        width: 100%;
        min-height: 44px;
        font-weight: 900 !important;
        letter-spacing: 0.2px;
        color: #ffffff !important;
        background: #0f0f10 !important;
        border: 2px solid #ffcc66 !important;
        text-shadow: none !important;
        box-shadow: 0 1px 0 rgba(255, 255, 255, 0.06) inset, 0 2px 6px rgba(0, 0, 0, 0.35);
    }
    [data-testid="stSidebar"] .stButton > button *,
    [data-testid="stSidebar"] .stDownloadButton > button *,
    [data-testid="stSidebar"] .stLinkButton > a * {
        color: #ffffff !important;
        fill: #ffffff !important;
        opacity: 1 !important;
    }
    [data-testid="stSidebar"] .stButton > button:hover,
    [data-testid="stSidebar"] .stDownloadButton > button:hover,
    [data-testid="stSidebar"] .stLinkButton > a:hover {
        background: #000000 !important;
        border-color: #ffd98f !important;
        color: #ffffff !important;
    }
    [data-testid="stSidebar"] .stButton > button:active,
    [data-testid="stSidebar"] .stDownloadButton > button:active,
    [data-testid="stSidebar"] .stLinkButton > a:active {
        background: #1a1a1c !important;
        border-color: #ffcc66 !important;
        color: #ffffff !important;
    }
    [data-testid="stSidebar"] .stButton > button:focus-visible,
    [data-testid="stSidebar"] .stDownloadButton > button:focus-visible,
    [data-testid="stSidebar"] .stLinkButton > a:focus-visible {
        outline: 3px solid #ffcc66 !important;
        outline-offset: 1px;
    }
    [data-testid="stSidebar"] .st-key-sidebar_stop_services_btn button[data-testid="stBaseButton-secondary"],
    [data-testid="stSidebar"] .st-key-sidebar_restart_services_btn button[data-testid="stBaseButton-secondary"] {
        background: #000000 !important;
        border: 2px solid #ffd37a !important;
        color: #ffffff !important;
        font-weight: 900 !important;
    }
    [data-testid="stSidebar"] .st-key-sidebar_stop_services_btn button[data-testid="stBaseButton-secondary"] [data-testid="stMarkdownContainer"] p,
    [data-testid="stSidebar"] .st-key-sidebar_restart_services_btn button[data-testid="stBaseButton-secondary"] [data-testid="stMarkdownContainer"] p {
        color: #ffffff !important;
        font-weight: 900 !important;
        font-size: 1.02rem !important;
        line-height: 1.15 !important;
        opacity: 1 !important;
    }
    [data-testid="stSidebar"] .st-key-sidebar_stop_services_btn button[data-testid="stBaseButton-secondary"]:hover,
    [data-testid="stSidebar"] .st-key-sidebar_restart_services_btn button[data-testid="stBaseButton-secondary"]:hover {
        background: #171717 !important;
        border-color: #ffe1a8 !important;
    }
    .stMetric label,
    .stMetric div,
    [data-testid="stMetricValue"],
    [data-testid="stMetricLabel"] {
        color: #2a1f0f !important;
    }
    [data-testid="stAlert"] * {
        color: inherit !important;
    }
    .stTabs [role="tabpanel"] {
        background: rgba(255, 255, 255, 0.68);
        border: 1px solid rgba(120, 86, 22, 0.22);
        border-radius: 14px;
        padding: 12px;
    }
    .hive-hero {
        border: 1px solid rgba(127, 81, 0, 0.35);
        background: linear-gradient(135deg, rgba(255, 214, 102, 0.45), rgba(255, 245, 212, 0.96));
        border-radius: 16px;
        padding: 18px 20px;
        margin-bottom: 10px;
        box-shadow: 0 8px 24px rgba(90, 60, 0, 0.16);
    }
    .hive-hero h1 {
        margin: 0;
        color: #3b2600;
        font-size: 2rem;
        letter-spacing: 0.3px;
    }
    .hive-hero p {
        margin: 6px 0 0 0;
        color: #4a3200;
        font-size: 1rem;
        font-weight: 600;
    }
    .hive-motto {
        margin-top: 8px;
        color: #4a3200;
        font-size: 0.95rem;
        font-weight: 700;
    }
    .boss-meeting-hero {
        border: 1px solid rgba(127, 81, 0, 0.35);
        background:
            radial-gradient(circle at 15% 20%, rgba(255, 233, 179, 0.95), transparent 30%),
            linear-gradient(135deg, rgba(255, 248, 230, 0.96), rgba(255, 233, 170, 0.90));
        border-radius: 16px;
        padding: 16px 18px;
        margin-bottom: 14px;
        box-shadow: 0 8px 24px rgba(90, 60, 0, 0.12);
    }
    .boss-meeting-hero h2 {
        margin: 0;
        color: #3b2600;
        font-size: 1.35rem;
    }
    .boss-meeting-hero p {
        margin: 6px 0 0 0;
        color: #5a3f07;
        font-weight: 600;
    }
    .boss-meeting-chip-row {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin-top: 10px;
    }
    .boss-meeting-chip {
        display: inline-block;
        border-radius: 999px;
        padding: 6px 12px;
        background: rgba(255, 255, 255, 0.82);
        border: 1px solid rgba(127, 81, 0, 0.20);
        color: #4d3300;
        font-size: 0.86rem;
        font-weight: 700;
    }
    .boss-meeting-surface {
        background: rgba(255, 251, 240, 0.88);
        border: 1px solid rgba(127, 81, 0, 0.18);
        border-radius: 16px;
        padding: 14px 16px;
        box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.55);
    }
    .boss-meeting-stat-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 10px;
    }
    .boss-meeting-stat {
        background: rgba(255, 255, 255, 0.82);
        border: 1px solid rgba(127, 81, 0, 0.16);
        border-radius: 12px;
        padding: 10px 12px;
    }
    .boss-meeting-stat .label {
        font-size: 0.82rem;
        color: #6a4a12;
        font-weight: 700;
        margin-bottom: 4px;
    }
    .boss-meeting-stat .value {
        font-size: 1.1rem;
        color: #2c1d06;
        font-weight: 800;
    }
    .boss-meeting-divider {
        height: 1px;
        background: linear-gradient(90deg, transparent, rgba(127, 81, 0, 0.28), transparent);
        margin: 12px 0;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hive-hero">
      <h1>HoneyHive Studio 蜂巢协作智能</h1>
      <p>Boss-First Multi-Agent Company Console</p>
      <div class="hive-motto">像蜜蜂一样分工，像蜂巢一样协同，像工厂一样稳定交付。</div>
    </div>
    """,
    unsafe_allow_html=True,
)

# Initialize with error handling
try:
    config = load_config()
    sentry_enabled = init_observability(config)
    runtime = create_runtime(config)
    
    # Health checks
    health_issues = []
    if config.enable_local_llm and runtime.llm:
        if not runtime.llm.health_check():
            health_issues.append("⚠️ Ollama 不可达，请确认已启动: ollama serve")
    
    # ComfyUI health check
    comfyui_ok = check_comfyui(config.comfyui_base_url)
    if not comfyui_ok:
        health_issues.append(f"⚠️ ComfyUI 不可达 ({config.comfyui_base_url})")

    if health_issues:
        st.sidebar.warning("\n\n".join(health_issues))

    st.sidebar.header("服务状态")
    st.sidebar.write(f"{'🟢' if comfyui_ok else '🔴'} ComfyUI ({config.comfyui_base_url})")
    ollama_ok = runtime.llm.health_check() if (config.enable_local_llm and runtime.llm) else None
    if ollama_ok is not None:
        st.sidebar.write(f"{'🟢' if ollama_ok else '🔴'} Ollama ({config.local_llm_model})")
    secretary_ok = check_secretary_dashboard(SECRETARY_DASHBOARD_URL)
    st.sidebar.write(f"{'🟢' if secretary_ok else '🔴'} Secretary Dashboard ({SECRETARY_DASHBOARD_URL})")
    telegram_ok = check_telegram_bot_poller()
    st.sidebar.write(f"{'🟢' if telegram_ok else '🔴'} Telegram Bot Poller")

    _svc_col1, _svc_col2 = st.sidebar.columns(2)
    with _svc_col1:
        if st.button("🛑 一键停服", key="sidebar_stop_services_btn", help="关闭 ComfyUI/Ollama/Secretary（不关闭当前GUI）"):
            _stop_result = stop_managed_services()
            if _stop_result.get("ok", False):
                st.sidebar.success("已停服：ComfyUI/Ollama/Secretary")
            else:
                st.sidebar.warning(f"停服后仍有端口占用: {_stop_result.get('open_ports', [])}")
            if _stop_result.get("stopped"):
                st.sidebar.caption("已结束进程: " + " | ".join(_stop_result["stopped"][:5]))
            if _stop_result.get("failed"):
                st.sidebar.caption("结束失败: " + " | ".join(_stop_result["failed"][:5]))

    with _svc_col2:
        if st.button("🔄 重启服务", key="sidebar_restart_services_btn", help="先停后起 ComfyUI/Ollama/Secretary"):
            _restart_result = restart_managed_services()
            _start = _restart_result.get("start", {})
            _ok_flags = [
                bool(_start.get("comfyui")),
                bool(_start.get("ollama")),
                bool(_start.get("secretary")),
                bool(_start.get("telegram")),
            ]
            if all(_ok_flags):
                st.sidebar.success("重启命令已发送：ComfyUI / Ollama / Secretary / Telegram")
            else:
                st.sidebar.warning(
                    "重启部分失败: "
                    f"ComfyUI={_start.get('comfyui')} "
                    f"Ollama={_start.get('ollama')} "
                    f"Secretary={_start.get('secretary')} "
                    f"Telegram={_start.get('telegram')}"
                )

    if not comfyui_ok:
        if st.sidebar.button("🚀 启动 ComfyUI"):
            comfyui_bat = get_comfyui_bat_path()
            if launch_comfyui():
                st.sidebar.success("ComfyUI 已发送启动命令，约 30 秒后可用")
            else:
                st.sidebar.error(f"找不到 {comfyui_bat}，请手动启动")

    if config.enable_local_llm and ollama_ok is False:
        if st.sidebar.button("🚀 启动 Ollama"):
            if launch_ollama():
                st.sidebar.success("Ollama 已发送启动命令，约 5-10 秒后可用")
            else:
                st.sidebar.error("无法启动 Ollama。请确认已安装并可在终端运行: ollama serve")

    if not secretary_ok:
        if st.sidebar.button("🚀 启动 Secretary Dashboard"):
            if launch_secretary_dashboard():
                st.sidebar.success("Secretary Dashboard 启动命令已发送，约 5-10 秒后可用")
            else:
                st.sidebar.error("无法启动 Secretary Dashboard，请检查 personal-secretary/.venv 是否存在")

    if not telegram_ok:
        if st.sidebar.button("🚀 启动 Telegram Bot"):
            if launch_telegram_bot_poller():
                st.sidebar.success("Telegram Bot Poller 启动命令已发送，约 3-5 秒后可用")
            else:
                st.sidebar.error("无法启动 Telegram Bot，请检查 personal-secretary/.venv 和 run_telegram_bot.py")

    st.sidebar.divider()
    st.sidebar.header("运行模式")
    st.sidebar.write(f"本地LLM: {config.enable_local_llm}")
    st.sidebar.write(f"Provider: {config.local_llm_provider}")

    # Model selector — dynamically pulls installed Ollama models
    if config.enable_local_llm and runtime.llm:
        _available_models = get_ollama_models(config.local_llm_base_url)
        _current_model = runtime.llm.config.model
        if _available_models:
            # Ensure current model is in list even if Ollama returns partial data
            if _current_model not in _available_models:
                _available_models.insert(0, _current_model)
            _MODEL_TOOLTIPS = {
                "hermes3:8b": "Agent任务/结构化输出",
                "qwen2.5:7b-instruct": "中文对话/代码/数学",
            }
            _selected_model = st.sidebar.selectbox(
                "🤖 当前模型",
                options=_available_models,
                index=_available_models.index(_current_model),
                help="hermes3:8b → Agent规划 / qwen2.5:7b-instruct → 中文对话",
                key="sidebar_model_selector",
            )
            if _selected_model != _current_model:
                runtime.llm.config.model = _selected_model
                st.sidebar.success(f"已切换至 {_selected_model}")
            _tip = _MODEL_TOOLTIPS.get(_selected_model, "")
            if _tip:
                st.sidebar.caption(f"💡 {_tip}")
        else:
            st.sidebar.write(f"Model: {_current_model}")
    st.sidebar.write(f"Sentry: {'enabled' if sentry_enabled else 'disabled'}")

    st.sidebar.divider()
    st.sidebar.header("Prompt 规则")
    rules_summary = runtime.prompt_agent.get_rewrite_rules_summary()
    st.sidebar.write(f"规则数量: {rules_summary.get('rule_count', 0)}")
    if st.sidebar.button("♻️ 热重载 Prompt 规则"):
        loaded = runtime.prompt_agent.reload_rewrite_rules()
        st.sidebar.success(f"已重载，当前规则数: {loaded}")
    tags = rules_summary.get("tags", [])
    if tags:
        st.sidebar.caption("标签: " + ", ".join(tags))

    # ------------------------------------------------------------------
    # Hermes-inspired: Skills Panel
    # ------------------------------------------------------------------
    st.sidebar.divider()
    st.sidebar.header("🧠 技能库")
    _all_skills = load_all_skills()
    if _all_skills:
        st.sidebar.caption(f"已存 {len(_all_skills)} 个技能，自动注入主管提示词")
        for _sk_name in list(_all_skills.keys()):
            _sk_col1, _sk_col2 = st.sidebar.columns([4, 1])
            with _sk_col1:
                with st.expander(_sk_name, expanded=False):
                    st.text(_all_skills[_sk_name][:400])
            with _sk_col2:
                if st.button("🗑", key=f"del_skill_{_sk_name}"):
                    delete_skill(_sk_name)
                    st.rerun()
    else:
        st.sidebar.caption("暂无技能。主管完成复杂任务后自动提炼保存。")

    # Pending skill save prompt (set by supervisor_dispatch_reply)
    if st.session_state.get("_pending_skill"):
        st.sidebar.info("🆕 检测到新技能，是否保存？")
        _pending = st.session_state["_pending_skill"]
        _default_name = re.search(r"#\s*(.+)", _pending)
        _default_name = _default_name.group(1).strip() if _default_name else "new_skill"
        _skill_name_input = st.sidebar.text_input("技能名称", value=_default_name, key="new_skill_name")
        _sc1, _sc2 = st.sidebar.columns(2)
        with _sc1:
            if st.button("💾 保存", key="save_skill_btn"):
                save_skill(_skill_name_input, _pending)
                del st.session_state["_pending_skill"]
                st.sidebar.success(f"已保存: {_skill_name_input}")
                st.rerun()
        with _sc2:
            if st.button("跳过", key="skip_skill_btn"):
                del st.session_state["_pending_skill"]
                st.rerun()

    # ------------------------------------------------------------------
    # LLM Wiki: Knowledge Base Panel
    # ------------------------------------------------------------------
    st.sidebar.divider()
    st.sidebar.header("📚 LLM Wiki")
    if bool(WIKI_CONFIG.get("enabled", False)):
        _index = load_knowledge_index()
        _meta = _index.get("meta", {}) if isinstance(_index, dict) else {}
        _state = load_knowledge_state()
        st.sidebar.write(f"索引块数: {_meta.get('chunk_count', 0)}")
        if _meta.get("built_at"):
            st.sidebar.caption(f"索引构建时间: {_meta.get('built_at')}")
        if _state.get("updated_at"):
            st.sidebar.caption(f"状态更新时间: {_state.get('updated_at')}")

        if st.sidebar.button("🔁 重建知识索引", key="rebuild_knowledge_index_btn"):
            ok, msg = rebuild_knowledge_index()
            if ok:
                st.sidebar.success(msg)
            else:
                st.sidebar.error(msg)

        if st.sidebar.button("🧠 自动学习全员Skills", key="auto_learn_staff_skills_btn"):
            ok, msg = auto_learn_staff_skills()
            if ok:
                st.sidebar.success(msg)
                st.rerun()
            else:
                st.sidebar.error(msg)

        st.sidebar.markdown("#### 检索调试")
        _wiki_debug_query = st.sidebar.text_input(
            "知识检索词",
            placeholder="输入关键词，查看命中来源与可点击跳转",
            key="sidebar_wiki_debug_query",
        )
        if _wiki_debug_query.strip():
            _wiki_hits = search_knowledge_chunks(_wiki_debug_query, top_k=5)
            if _wiki_hits:
                for _i, _hit in enumerate(_wiki_hits, start=1):
                    _src = str(_hit.get("source_path", ""))
                    _title = str(_hit.get("title", "Document"))
                    _score = _hit.get("score", 0.0)
                    with st.sidebar.expander(f"{_i}. {_title} ({_score})", expanded=False):
                        st.sidebar.caption(_src)
                        _uri = _source_vscode_uri(_src)
                        st.sidebar.link_button(
                            "在 VS Code 打开来源",
                            _uri
                        )
                        st.sidebar.write(str(_hit.get("text", ""))[:240])
            else:
                st.sidebar.caption("未命中知识片段")
    else:
        st.sidebar.caption("知识库已禁用，可在 wiki_knowledge_config.json 中开启。")

    # ------------------------------------------------------------------
    # Hermes-inspired: Memory Search
    # ------------------------------------------------------------------
    st.sidebar.divider()
    st.sidebar.header("🔍 记忆搜索")
    _mem_query = st.sidebar.text_input("搜索历史对话", placeholder="输入关键词…", key="sidebar_mem_search")
    if _mem_query:
        _mem_results = search_agent_memory(_mem_query)
        if _mem_results:
            st.sidebar.caption(f"找到 {len(_mem_results)} 条相关记忆")
            for _mr in _mem_results:
                with st.sidebar.expander(f"[{_mr['agent_key']}] {_mr['user'][:40]}…", expanded=False):
                    st.write(f"**问：** {_mr['user']}")
                    st.write(f"**答：** {_mr['assistant'][:300]}")
                    st.caption(f"时间: {_mr['ts'][:16]}  相关度: {_mr['score']}")
        else:
            st.sidebar.caption("未找到相关记忆")

except Exception as e:
    capture_exception(e, stage={"name": "app_initialization"})
    st.error(f"初始化失败: {e}")
    st.code(traceback.format_exc())
    st.stop()

if "agent_chats" not in st.session_state:
    st.session_state.agent_chats = {
        "supervisor": [],
        "supervisor_video": [],
        "supervisor_secretary": [],
        "image": [],
        "production": [],
        "story": [],
        "prompt": [],
        "builder": [],
        "qa": [],
        "retriever": [],
        "document_reader": [],
        "fileops": [],
        "finance": [],
        "learning": [],
        "business_plan": [],
        "report": [],
        "secretary_qa": [],
    }

if "agent_memory_store" not in st.session_state:
    st.session_state.agent_memory_store = load_agent_memory_store()

if "boss_meeting_attachments" not in st.session_state:
    st.session_state.boss_meeting_attachments = []

if "boss_meeting_records" not in st.session_state:
    st.session_state.boss_meeting_records = {}

if "boss_meeting_last_run" not in st.session_state:
    st.session_state.boss_meeting_last_run = {}


def render_chat(agent_key: str, reply_func, input_key: str | None = None):
    chat_bucket = st.session_state.agent_chats.setdefault(agent_key, [])

    for role, msg in chat_bucket:
        with st.chat_message(role):
            st.write(msg)

    user_msg = st.chat_input(f"和 {agent_key} agent 对话", key=input_key or f"chat_input_{agent_key}")
    if user_msg:
        chat_bucket.append(("user", user_msg))
        with st.chat_message("user"):
            st.write(user_msg)
        
        try:
            memory_context = build_agent_memory_context(agent_key, user_msg)
            reply = reply_func(user_msg, memory_context)
            chat_bucket.append(("assistant", reply))
            append_agent_memory(agent_key, user_msg, str(reply), success=True)
            with st.chat_message("assistant"):
                st.write(reply)
        except Exception as e:
            capture_exception(e, stage={"name": "agent_chat", "agent": agent_key})
            error_msg = f"Agent 调用失败: {e}"
            chat_bucket.append(("assistant", error_msg))
            append_agent_memory(agent_key, user_msg, error_msg, success=False)
            with st.chat_message("assistant"):
                st.error(error_msg)


def _supervisor_required_sections() -> list[str]:
    return ["任务拆解", "员工分配", "执行顺序", "风险与回退", "需老板补充的信息", "给老板的结论"]


def _is_valid_supervisor_response(text: str) -> bool:
    if not text:
        return False
    required = _supervisor_required_sections()
    has_sections = all(section in text for section in required)
    has_numbering = sum(1 for idx in range(1, 7) if f"{idx})" in text or f"{idx}." in text) >= 5
    return has_sections or has_numbering


def _extract_section_block(text: str, title: str, all_titles: list[str]) -> str:
    start = text.find(title)
    if start < 0:
        return ""
    start += len(title)
    end_candidates = []
    for next_title in all_titles:
        if next_title == title:
            continue
        pos = text.find(next_title, start)
        if pos >= 0:
            end_candidates.append(pos)
    end = min(end_candidates) if end_candidates else len(text)
    return text[start:end].strip("：: \n\t")


def build_meeting_minutes_and_todos(agent_key: str) -> tuple[str, list[str]]:
    bucket = st.session_state.get("agent_chats", {}).get(agent_key, [])
    last_user = ""
    last_assistant = ""

    if bucket:
        for role, msg in reversed(bucket):
            if not last_assistant and role == "assistant":
                last_assistant = str(msg)
            elif not last_user and role == "user":
                last_user = str(msg)
            if last_user and last_assistant:
                break

    if not last_assistant:
        record = st.session_state.get("boss_meeting_records", {}).get(agent_key, {})
        if isinstance(record, dict):
            last_user = str(record.get("last_user", ""))
            last_assistant = str(record.get("last_assistant", ""))

    if not last_assistant:
        store = st.session_state.get("agent_memory_store", {})
        if isinstance(store, dict):
            entry = _normalize_agent_memory_entry(store.get(agent_key, {}))
            turns = entry.get("turns", [])
            if isinstance(turns, list) and turns:
                latest = turns[-1]
                if isinstance(latest, dict):
                    last_user = str(latest.get("user", ""))
                    last_assistant = str(latest.get("assistant", ""))

    if not last_assistant:
        return "", []

    titles = _supervisor_required_sections()
    minutes_lines = [f"会议主题：{last_user[:220] if last_user else 'N/A'}"]
    for title in titles:
        block = _extract_section_block(last_assistant, title, titles)
        if block:
            minutes_lines.append(f"{title}：{block[:420]}")

    todo_candidates = []
    for title in ["员工分配", "执行顺序", "需老板补充的信息"]:
        block = _extract_section_block(last_assistant, title, titles)
        if not block:
            continue
        for line in block.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith(("-", "*", "1", "2", "3", "4", "5", "6", "7", "8", "9")):
                todo_candidates.append(stripped.lstrip("-* "))
    todos = todo_candidates[:8]
    return "\n".join(minutes_lines), todos


def render_boss_meeting_minutes_panel(agent_key: str) -> None:
    minutes, todos = build_meeting_minutes_and_todos(agent_key)
    with st.expander("自动会议纪要与待办", expanded=True):
        if not minutes:
            st.caption("还没有可用会议纪要。先和主管完成一次对话。")
            return
        st.text(minutes)
        st.write("待办分派清单")
        if not todos:
            st.caption("暂未提取到明确待办，请在主管回复中强调员工分配和执行顺序。")
            return
        for idx, item in enumerate(todos, start=1):
            st.write(f"{idx}. {item}")


def supervisor_dispatch_reply(supervisor_key: str, user_msg: str, memory_context: str = "") -> str:
    role_name = STAFF_ROLE_BY_KEY.get(supervisor_key, "Supervisor Agent")
    roster = SUPERVISOR_TEAM_ROSTER.get(supervisor_key, list(AGENT_ROLE_SUMMARIES.keys()))

    # Hermes-inspired: inject project context + relevant skills
    project_ctx = load_project_context()
    skills_ctx = build_skills_context(user_msg, supervisor_key)
    wiki_ctx = build_knowledge_context(query=user_msg, supervisor_key=supervisor_key)

    prompt = (
        f"你是 HoneyHive 公司的 {role_name}。"
        "你的职责是接收老板输入，先拆解任务，再安排员工，再做风险把关与汇总。\n"
        "你当前可统筹的员工有："
        + "、".join(roster)
        + "。\n"
        "请按以下格式输出：1) 任务拆解 2) 员工分配 3) 执行顺序 4) 风险与回退 5) 需老板补充的信息 6) 给老板的结论。\n"
        "输出必须清晰可执行，且不要直接以员工口吻执行任务。\n\n"
        + (f"[项目背景]\n{project_ctx}\n\n" if project_ctx else "")
        + (f"{skills_ctx}\n\n" if skills_ctx else "")
        + (f"{wiki_ctx}\n\n" if wiki_ctx else "")
        + (f"历史记忆:\n{memory_context}\n\n" if memory_context else "")
        + f"老板指令：{user_msg}"
    )
    response = runtime.supervisor_agent.chat(prompt)
    if _is_valid_supervisor_response(response):
        # Hermes-inspired: auto-extract skill from complex plans
        skill_candidate = auto_extract_skill(supervisor_key, response)
        if skill_candidate:
            st.session_state["_pending_skill"] = skill_candidate
        return response

    retry_prompt = prompt
    for _ in range(SUPERVISOR_RESPONSE_MAX_RETRIES):
        retry_prompt += (
            "\n\n上一版输出未通过结构校验。"
            "请严格使用这 6 个小节标题：任务拆解、员工分配、执行顺序、风险与回退、需老板补充的信息、给老板的结论。"
            f"\n上一版输出如下：\n{response}"
        )
        response = runtime.supervisor_agent.chat(retry_prompt)
        if _is_valid_supervisor_response(response):
            skill_candidate = auto_extract_skill(supervisor_key, response)
            if skill_candidate:
                st.session_state["_pending_skill"] = skill_candidate
            return response

    return response + "\n\n[提示] 本次输出未完全满足 6 段结构，建议让主管按固定模板重答。"


def orchestrator_supervisor_reply(user_msg: str, memory_context: str = "") -> str:
    return supervisor_dispatch_reply("supervisor_secretary", user_msg, memory_context)


def build_staff_role_prompt(
    selected_role: str,
    user_msg: str,
    memory_context: str = "",
    staff_key: str = "",
) -> str:
    project_ctx = load_project_context()
    role_skill_ctx = build_role_skill_context(selected_role, staff_key)
    wiki_ctx = build_knowledge_context(query=user_msg, selected_role=selected_role, staff_key=staff_key)
    role_summary = AGENT_ROLE_SUMMARIES.get(
        selected_role,
        "负责把与自己岗位相关的任务做成可执行的结果。",
    )
    return (
        f"你现在以 {selected_role} 身份回复。"
        "请给出可执行、可落地的回答，必要时列出下一步动作和输入要求。\n\n"
        f"你的岗位职责：{role_summary}\n\n"
        + (f"[项目背景]\n{project_ctx}\n\n" if project_ctx else "")
        + (f"{role_skill_ctx}\n\n" if role_skill_ctx else "")
        + (f"{wiki_ctx}\n\n" if wiki_ctx else "")
        + (f"历史记忆:\n{memory_context}\n\n" if memory_context else "")
        + f"用户问题：{user_msg}"
    )


def staff_role_reply(selected_role: str, user_msg: str, memory_context: str = "", staff_key: str = "") -> str:
    if _is_meta_identity_question(user_msg):
        return build_employee_identity_reply(selected_role, user_msg, memory_context, staff_key)

    role_prompt = build_staff_role_prompt(selected_role, user_msg, memory_context, staff_key)
    return runtime.supervisor_agent.chat(role_prompt)


def _is_meta_identity_question(user_msg: str) -> bool:
    meta_keywords = (
        "你是做什么",
        "你做什么",
        "有哪些skills",
        "有什么skills",
        "skills",
        "skill",
        "能力",
        "简介",
        "你是谁",
        "自我介绍",
        "职责",
        "作用",
        "擅长",
        "介绍一下",
    )
    normalized_msg = user_msg.lower()
    return any(keyword in normalized_msg for keyword in meta_keywords)


def build_employee_identity_reply(
    selected_role: str,
    user_msg: str,
    memory_context: str = "",
    staff_key: str = "",
) -> str:
    role_summary = AGENT_ROLE_SUMMARIES.get(
        selected_role,
        "负责把与自己岗位相关的任务做成可执行的结果。",
    )
    prompt = build_employee_identity_card_prompt(selected_role, role_summary, user_msg, memory_context, staff_key)
    return runtime.supervisor_agent.chat(prompt)


def build_employee_identity_card_prompt(
    selected_role: str,
    role_summary: str,
    user_msg: str,
    memory_context: str = "",
    staff_key: str = "",
) -> str:
    project_ctx = load_project_context()
    role_skill_ctx = build_role_skill_context(selected_role, staff_key)
    wiki_ctx = build_knowledge_context(query=user_msg, selected_role=selected_role, staff_key=staff_key)
    return (
        f"你现在是 {selected_role}。请用中文自然语言回答，不要输出 JSON。\n"
        "请严格按以下结构输出，并保持简洁清晰：\n"
        "1. 岗位职责：用 1 句话说明你负责什么。\n"
        "2. 核心 skills：用 3 到 5 条短句列出你的核心能力。\n"
        "3. 适合接的任务：用 1 到 3 条说明你最擅长处理什么。\n"
        "4. 协作对象：说明你通常会和哪些员工配合。\n\n"
        f"你的岗位说明：{role_summary}\n\n"
        + (f"[项目背景]\n{project_ctx}\n\n" if project_ctx else "")
        + (f"{role_skill_ctx}\n\n" if role_skill_ctx else "")
        + (f"{wiki_ctx}\n\n" if wiki_ctx else "")
        + (f"历史记忆:\n{memory_context}\n\n" if memory_context else "")
        + f"用户问题：{user_msg}"
    )


def story_agent_reply(user_msg: str, memory_context: str = "") -> str:
    if _is_meta_identity_question(user_msg):
        prompt = build_employee_identity_card_prompt(
            "Story Agent",
            "负责把创意需求整理成适合视频生成的场景结构，输出 scene、action、mood。",
            user_msg,
            memory_context,
            "story",
        )
        return runtime.supervisor_agent.chat(prompt)

    scene = runtime.story_agent.run(user_msg)
    return json.dumps(scene.model_dump(), ensure_ascii=False, indent=2)


col1, col2 = st.columns([1, 2])
with col1:
    st.subheader("页面导航")
    with st.container(border=True):
        st.markdown("### 使用入口")
        st.write("- 老板全员总览：看全团队、skills 分工和联合控制")
        st.write("- 主管Agent：给 Video 或 Secretary 主管下达目标")
        st.write("- 单Agent对话：直连某个员工，查看其专属 skill")
        st.write("- 老板会议室：以主管为入口推进会议式协作")
    with st.container(border=True):
        st.markdown("### 当前结构")
        st.write("- 视频团队：主管 + 6 名员工")
        st.write("- 秘书团队：主管 + 8 名员工")
        st.write("- 员工技能：16 份专属 skill，已按角色映射注入")

with col2:
    tab_boss, tab_sup, tab_agents, tab_run, tab_obs = st.tabs(["老板全员总览", "主管Agent", "单Agent对话", "老板会议室", "📚 知识库 Obsidian"])

    with tab_boss:
        st.subheader("👔 老板全员总览（双项目整合）")
        st.caption("在一个界面同时查看 Video Studio + Personal Secretary 的所有员工 Agent。")
        render_staff_skills_assignment_overview()

        video_agents = [
            "Supervisor Agent",
            "Image Analysis Agent",
            "Production Planner Agent",
            "Story Agent",
            "Prompt Agent",
            "Builder Agent",
            "QA Agent",
        ]
        secretary_agents = get_secretary_agents()
        secretary_stats = get_secretary_stats()

        m1, m2, m3 = st.columns(3)
        with m1:
            st.metric("Video Agents", len(video_agents))
        with m2:
            st.metric("Secretary Agents", len(secretary_agents))
        with m3:
            st.metric("Total Team Size", len(video_agents) + len(secretary_agents))

        s1, s2, s3 = st.columns(3)
        with s1:
            st.metric("Indexed Files", int(secretary_stats.get("indexed_files", 0)))
        with s2:
            st.metric("Secretary Runs", int(secretary_stats.get("agent_runs", 0)))
        with s3:
            st.write("Latest Secretary Run")
            st.caption(str(secretary_stats.get("latest_run", "N/A")))

        left, right = st.columns(2)
        with left:
            with st.container(border=True):
                st.markdown("### 🎬 Video Studio Team")
                for name in video_agents:
                    st.write(f"- {name}")

        with right:
            with st.container(border=True):
                st.markdown("### 📎 Personal Secretary Team")
                if secretary_agents:
                    for name in secretary_agents:
                        st.write(f"- {name}")
                else:
                    st.warning("未读取到秘书项目 agent 列表，请检查 agent_orchestrator.py")

        st.divider()
        st.markdown("### 🔗 联合控制")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("启动/重启 Secretary Dashboard", key="boss_launch_secretary"):
                if launch_secretary_dashboard():
                    st.success("启动命令已发送，请等待数秒后访问。")
                else:
                    st.error("启动失败，请检查 personal-secretary 的虚拟环境。")
        with c2:
            st.link_button("打开 Secretary Dashboard", SECRETARY_DASHBOARD_URL)

    with tab_sup:
        st.info("可选择对话主管：Video 主管 或 Secretary 主管（全员统筹）。")
        sup_options = {
            "Video 主管Agent": "supervisor_video",
            "Secretary 主管Agent": "supervisor_secretary",
        }
        selected_supervisor_label = st.selectbox(
            "选择主管",
            list(sup_options.keys()),
            key="supervisor_chat_selector",
        )
        selected_supervisor_key = sup_options[selected_supervisor_label]
        supervisor_preview_query = st.text_input(
            "当前输入预览",
            value="",
            placeholder="输入任务关键词，预览主管当前会命中的 skills",
            key=f"supervisor_skill_preview_query_{selected_supervisor_key}",
        )
        supervisor_skill_previews = get_supervisor_skill_previews(supervisor_preview_query, selected_supervisor_key)

        with st.container(border=True):
            st.markdown("### 当前注入 Skills")
            if supervisor_skill_previews:
                if supervisor_preview_query.strip():
                    st.caption(f"基于当前输入关键词预览命中的 3 个技能：{supervisor_preview_query.strip()}")
                else:
                    st.caption("显示主管自身和当前团队默认命中的 3 个技能。")
                for idx, item in enumerate(supervisor_skill_previews, start=1):
                    score = float(item.get("score", 0.0))
                    hit_count = int(item.get("hit_count", 0))
                    list_col, score_col = st.columns([6, 2])
                    with list_col:
                        st.write(f"{idx}. {item.get('title', '未命名技能')} ({item.get('file_name', '未知文件')})")
                    with score_col:
                        if supervisor_preview_query.strip():
                            st.markdown(_render_score_badge(score), unsafe_allow_html=True)
                            st.progress(max(0.0, min(score, 1.0)))
                        else:
                            st.caption("默认命中")
                    preview_text = item.get("preview", "")
                    if preview_text:
                        with st.expander(f"查看技能预览 {idx}", expanded=False):
                            if supervisor_preview_query.strip():
                                st.caption(f"命中关键词: {hit_count}")
                            st.markdown(_highlight_preview_text(preview_text[:600], supervisor_preview_query).replace("\n", "  \n"))
            else:
                st.caption("当前主管未命中可注入技能。")

        sup_stats = get_agent_memory_stats(selected_supervisor_key)
        s1, s2, s3, s4 = st.columns(4)
        with s1:
            st.metric("记忆轮次", sup_stats["turns"])
        with s2:
            st.metric("关键事实", sup_stats["facts"])
        with s3:
            st.metric("记忆摘要长度", sup_stats["summary_chars"])
        with s4:
            st.metric("记忆成功率", sup_stats["success_rate"])

        if st.button("清空当前主管记忆", key=f"clear_sup_memory_{selected_supervisor_key}"):
            clear_agent_memory(selected_supervisor_key)
            st.success("已清空该主管记忆。")

        render_agent_memory_panel(selected_supervisor_key, "主管记忆面板")

        if selected_supervisor_key == "supervisor_video":
            render_chat(
                "supervisor_video",
                lambda msg, memory: supervisor_dispatch_reply("supervisor_video", msg, memory),
                input_key="chat_input_supervisor_tab_video",
            )
        else:
            render_chat(
                "supervisor_secretary",
                lambda msg, memory: supervisor_dispatch_reply("supervisor_secretary", msg, memory),
                input_key="chat_input_supervisor_tab_secretary",
            )

    with tab_agents:
        st.caption("当前可对话员工：16 名（按团队分组显示）")
        selected = st.selectbox("选择Agent", ALL_STAFF_KEYS, format_func=lambda key: STAFF_LABELS.get(key, key))
        selected_role = STAFF_ROLE_BY_KEY.get(selected, selected)
        agent_preview_query = st.text_input(
            "当前输入预览",
            value="",
            placeholder="输入任务关键词，预览当前员工最相关的技能片段",
            key=f"agent_skill_preview_query_{selected}",
        )
        skill_preview = get_staff_skill_preview(selected_role, selected, agent_preview_query)

        with st.container(border=True):
            st.markdown("### 当前注入 Skill")
            if skill_preview:
                st.write(f"岗位：{STAFF_LABELS.get(selected, selected)}")
                st.write(f"技能文件：{skill_preview.get('file_name', '未配置')}")
                st.write(f"技能标题：{skill_preview.get('title', '未命名技能')}")
                if agent_preview_query.strip():
                    st.caption(f"以下预览基于当前输入关键词：{agent_preview_query.strip()}")
                preview_text = skill_preview.get("preview", "")
                if preview_text:
                    with st.expander("查看技能预览", expanded=False):
                        if agent_preview_query.strip():
                            score = float(skill_preview.get("score", 0.0))
                            hit_count = int(skill_preview.get("hit_count", 0))
                            st.markdown(_render_score_badge(score), unsafe_allow_html=True)
                            st.caption(f"命中关键词: {hit_count}")
                        st.markdown(_highlight_preview_text(preview_text[:800], agent_preview_query).replace("\n", "  \n"))
            else:
                st.caption("当前员工未配置专属 skill 文件。")

        agent_stats = get_agent_memory_stats(selected)
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric("记忆轮次", agent_stats["turns"])
        with m2:
            st.metric("关键事实", agent_stats["facts"])
        with m3:
            st.metric("记忆摘要长度", agent_stats["summary_chars"])
        with m4:
            st.metric("记忆成功率", agent_stats["success_rate"])

        if st.button("清空当前员工记忆", key=f"clear_agent_memory_{selected}"):
            clear_agent_memory(selected)
            st.success("已清空该员工记忆。")

        render_agent_memory_panel(selected, "员工记忆面板")

        def _reply(msg: str, memory_context: str = "") -> str:
            msg_with_memory = (
                f"历史记忆:\n{memory_context}\n\n当前消息:\n{msg}"
                if memory_context
                else msg
            )
            if _is_meta_identity_question(msg):
                return build_employee_identity_reply(
                    selected_role,
                    msg,
                    memory_context,
                    selected,
                )
            if selected == "supervisor_video":
                return supervisor_dispatch_reply("supervisor_video", msg, memory_context)
            if selected == "supervisor_secretary":
                return supervisor_dispatch_reply("supervisor_secretary", msg, memory_context)
            if selected == "image":
                image_path = st.session_state.get("last_uploaded_image_path")
                if not image_path:
                    return "请先在执行页上传一张图片，再和 Image Analysis Agent 对话。"
                analysis = runtime.image_agent.run(image_path, msg_with_memory)
                return json.dumps(analysis.model_dump(), ensure_ascii=False, indent=2)
            if selected == "production":
                image_path = st.session_state.get("last_uploaded_image_path")
                image_analysis = None
                if image_path:
                    image_analysis = runtime.image_agent.run(image_path, msg_with_memory).model_dump()
                plan = runtime.production_planner_agent.run(
                    user_brief=msg_with_memory,
                    image_analysis=image_analysis,
                    requested_workflow=str(I2V_WORKFLOW_PATH) if image_path else config.comfyui_workflow_path,
                )
                return json.dumps(plan.model_dump(), ensure_ascii=False, indent=2)
            if selected == "story":
                return story_agent_reply(msg, memory_context)
            if selected == "prompt":
                scene = SceneSpec(scene=msg_with_memory, action="walking", mood="cinematic")
                prompt_pack = runtime.prompt_agent.run(scene)
                return json.dumps(prompt_pack.model_dump(), ensure_ascii=False, indent=2)
            if selected == "builder":
                return staff_role_reply("Builder Agent", msg, memory_context, "builder")
            if selected == "qa":
                return staff_role_reply("QA Agent", msg, memory_context, "qa")

            return staff_role_reply(selected_role, msg, memory_context, selected)

        render_chat(selected, _reply, input_key=f"chat_input_single_tab_{selected}")

    with tab_run:
        st.markdown(
            """
            <div class="boss-meeting-hero">
              <h2>老板会议室</h2>
              <p>你只和主管开会，下达目标、约束、附件和优先级，不在这里直接分派普通员工。</p>
              <div class="boss-meeting-chip-row">
                <span class="boss-meeting-chip">主管决策</span>
                <span class="boss-meeting-chip">附件驱动</span>
                <span class="boss-meeting-chip">记忆保留</span>
                <span class="boss-meeting-chip">任务拆解</span>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        meeting_sup_options = {
            "Video 主管Agent": "supervisor_video",
            "Secretary 主管Agent": "supervisor_secretary",
        }

        top_left, top_right = st.columns([1.2, 1])
        with top_left:
            meeting_supervisor_label = st.selectbox(
                "选择会议主管",
                list(meeting_sup_options.keys()),
                key="boss_meeting_supervisor_selector",
            )
            meeting_supervisor_key = meeting_sup_options[meeting_supervisor_label]
            if st.button("清空当前会议主管记忆", key=f"clear_meeting_memory_{meeting_supervisor_key}"):
                clear_agent_memory(meeting_supervisor_key)
                st.success("已清空该主管记忆。")
        with top_right:
            meeting_stats = get_agent_memory_stats(meeting_supervisor_key)
            st.markdown(
                f"""
                <div class="boss-meeting-stat-grid">
                  <div class="boss-meeting-stat"><div class="label">记忆轮次</div><div class="value">{meeting_stats['turns']}</div></div>
                  <div class="boss-meeting-stat"><div class="label">关键事实</div><div class="value">{meeting_stats['facts']}</div></div>
                  <div class="boss-meeting-stat"><div class="label">摘要长度</div><div class="value">{meeting_stats['summary_chars']}</div></div>
                  <div class="boss-meeting-stat"><div class="label">成功率</div><div class="value">{meeting_stats['success_rate']}</div></div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown('<div class="boss-meeting-divider"></div>', unsafe_allow_html=True)

        left_panel, right_panel = st.columns([1.15, 0.85])
        with left_panel:
            st.markdown('<div class="boss-meeting-surface">', unsafe_allow_html=True)
            st.markdown("### 会议输入")
            meeting_topic = st.text_area(
                "会议议题",
                "请为我拆解这次任务，并列出你需要统筹的员工、执行顺序、风险和回退方案。",
                height=130,
            )
            meeting_tone = st.selectbox(
                "会议要求",
                ["简洁明确", "专业严谨", "强调风险", "强调成本控制"],
                key="boss_meeting_tone",
            )
            uploaded_meeting_files = st.file_uploader(
                "上传会议附件（可多选）",
                accept_multiple_files=True,
                key="boss_meeting_attachments_uploader",
                help="支持会议资料、截图、CSV、TXT、MD 等文件。附件会带入主管上下文。",
            )
            if uploaded_meeting_files:
                new_attachments = [save_boss_meeting_attachment(item) for item in uploaded_meeting_files]
                st.session_state.boss_meeting_attachments = new_attachments
            if st.button("清空会议附件", key="clear_boss_meeting_attachments"):
                st.session_state.boss_meeting_attachments = []
                st.success("已清空会议附件。")
            st.caption(f"当前附件数：{len(st.session_state.get('boss_meeting_attachments', []))}")
            st.markdown('</div>', unsafe_allow_html=True)

        with right_panel:
            st.markdown('<div class="boss-meeting-surface">', unsafe_allow_html=True)
            st.markdown("### 会议资料与记忆")
            render_boss_meeting_attachments_panel()
            st.markdown("<div class='boss-meeting-divider'></div>", unsafe_allow_html=True)
            render_agent_memory_panel(meeting_supervisor_key, "会议主管记忆面板")
            st.markdown("<div class='boss-meeting-divider'></div>", unsafe_allow_html=True)
            render_boss_meeting_minutes_panel(meeting_supervisor_key)
            st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="boss-meeting-divider"></div>', unsafe_allow_html=True)
        st.markdown('<div class="boss-meeting-surface">', unsafe_allow_html=True)
        st.markdown("### 确认并执行生成")
        st.caption("此处会直接触发 Story→Prompt→Builder→ComfyUI→QA。")

        default_brief = st.session_state.get(
            "boss_meeting_execution_brief",
            str(meeting_topic).strip() or "请根据会议目标生成视频",
        )
        execution_brief = st.text_area(
            "执行需求（发送给执行管线）",
            value=default_brief,
            height=120,
            key=f"boss_meeting_execute_brief_{meeting_supervisor_key}",
        )
        seed = st.number_input(
            "seed",
            min_value=0,
            value=42,
            step=1,
            key=f"boss_meeting_execute_seed_{meeting_supervisor_key}",
        )

        reference_image_path = pick_boss_meeting_image_path()
        if reference_image_path:
            st.caption(f"检测到参考图附件，将启用图生视频分支：{reference_image_path}")
        else:
            st.caption("未检测到图片附件，将使用纯文本生成分支。")

        run_col, clear_col = st.columns([1, 1])
        with run_col:
            if st.button("由会议主管统筹并执行生成", type="primary", key=f"boss_meeting_execute_{meeting_supervisor_key}"):
                try:
                    human_keywords = (
                        "人", "女生", "女孩", "少女", "女人", "男人", "人物", "舞", "跳舞",
                        "girl", "woman", "man", "person", "human", "portrait", "dance",
                    )
                    is_human_task = any(k in str(execution_brief).lower() for k in human_keywords)
                    if is_human_task and not reference_image_path:
                        st.error("当前是人像/舞蹈任务，但未检测到参考图附件。请先上传真实人物参考图，再执行生成。")
                        st.caption("未上传参考图会导致 Image Analysis 阶段被跳过，人物一致性和真实感会明显下降。")
                        st.stop()

                    pipeline = runtime.build_pipeline().build()
                    payload = {
                        "user_brief": execution_brief,
                        "seed": int(seed),
                        "retry_count": 0,
                    }
                    if reference_image_path:
                        payload["input_image_path"] = reference_image_path

                    if is_human_task:
                        payload["strict_reference_mode"] = True
                        payload["workflow_path"] = str((PROJECT_ROOT / "workflow_sd15_i2v_two_stage.json").resolve())

                    started_at = time.time()
                    with st.status("执行中：主管正在协调员工并提交渲染...", expanded=True) as run_status:
                        run_status.write("1/8 接收老板需求并构建执行上下文")
                        run_status.write("2/8 Supervisor：制定监督计划与重试策略")
                        run_status.write("3/8 Image/Production：分析输入并产出制作计划")
                        run_status.write("4/8 Story：生成分镜场景")
                        run_status.write("5/8 Prompt：生成正负提示词与运动提示")
                        run_status.write("6/8 Builder：注入工作流并准备提交 ComfyUI")
                        run_status.write("7/8 Render：ComfyUI 执行渲染任务")
                        run_status.write("8/8 QA+Supervisor：质检并给出是否重试决策")

                        result = pipeline.invoke(payload, config={"recursion_limit": 80})
                        elapsed = round(time.time() - started_at, 2)
                        run_status.update(
                            label=f"执行完成：总耗时 {elapsed} 秒",
                            state="complete",
                            expanded=False,
                        )

                    ended_at = time.time()
                    st.session_state.boss_meeting_last_run = {
                        "supervisor": meeting_supervisor_key,
                        "brief": execution_brief,
                        "seed": int(seed),
                        "started_at": datetime.fromtimestamp(started_at).isoformat(timespec="seconds"),
                        "duration_sec": round(ended_at - started_at, 2),
                        "result": result,
                    }
                    st.success("执行完成：已提交并完成本次生成流程。")
                except Exception as exc:
                    capture_exception(exc, stage={"name": "boss_meeting_execute", "supervisor": meeting_supervisor_key})
                    st.error(f"执行失败: {exc}")

        with clear_col:
            if st.button("清空本次执行结果", key=f"boss_meeting_clear_run_{meeting_supervisor_key}"):
                st.session_state.boss_meeting_last_run = {}
                st.success("已清空执行结果。")

        last_run = st.session_state.get("boss_meeting_last_run", {})
        if isinstance(last_run, dict) and last_run.get("result"):
            result = last_run.get("result", {})
            st.markdown("#### 最近一次执行结果")
            try:
                summary_text = runtime.supervisor_agent.summarize_run(result)
                if summary_text:
                    st.write(summary_text)
            except Exception:
                pass

            render_job_id = result.get("render_job_id", "N/A") if isinstance(result, dict) else "N/A"
            qa_report = result.get("qa_report", {}) if isinstance(result, dict) else {}
            qa_passed = qa_report.get("passed", "N/A") if isinstance(qa_report, dict) else "N/A"
            qa_score = qa_report.get("score", "N/A") if isinstance(qa_report, dict) else "N/A"
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.metric("Render Job ID", str(render_job_id))
            with c2:
                st.metric("QA Passed", str(qa_passed))
            with c3:
                st.metric("QA Score", str(qa_score))
            with c4:
                st.metric("总耗时(s)", str(last_run.get("duration_sec", "N/A")))

            supervision_plan = result.get("supervision_plan", {}) if isinstance(result, dict) else {}
            adaptive_max = int(supervision_plan.get("adaptive_max_retries", config.max_render_retries)) if isinstance(supervision_plan, dict) else config.max_render_retries
            retry_limit = max(0, min(adaptive_max, config.max_render_retries))
            retries_done = int(result.get("retry_count", 0)) if isinstance(result, dict) else 0
            decision = result.get("supervisor_decision", {}) if isinstance(result, dict) else {}
            retry_reason = str(decision.get("reason", "N/A")) if isinstance(decision, dict) else "N/A"

            r1, r2, r3 = st.columns(3)
            with r1:
                st.metric("重试次数", str(retries_done))
            with r2:
                st.metric("重试上限", str(retry_limit))
            with r3:
                st.metric("停止原因", retry_reason)

            if retry_limit > 0 and retries_done >= max(0, retry_limit - 1):
                st.warning(
                    f"当前已接近重试上限（{retries_done}/{retry_limit}）。若仍未通过 QA，建议先降分辨率/帧数后再执行。"
                )

            stage_defs = [
                ("supervision_plan", "Supervisor 监督计划"),
                ("image_analysis", "Image Analysis 场景分析"),
                ("production_plan", "Production Planner 制作计划"),
                ("scene_spec", "Story 分镜脚本"),
                ("prompt_pack", "Prompt 提示词包"),
                ("workflow_request", "Builder 工作流请求"),
                ("render_output", "Render 渲染输出"),
                ("qa_report", "QA 质检报告"),
                ("supervisor_decision", "Supervisor 重试决策"),
            ]
            completed_steps = 0
            for key, _ in stage_defs:
                if isinstance(result, dict) and result.get(key):
                    completed_steps += 1
            progress_ratio = completed_steps / len(stage_defs)
            st.progress(progress_ratio)
            st.caption(f"执行阶段完成度：{completed_steps}/{len(stage_defs)}")

            st.markdown("#### 员工分工协作与执行回放")
            for key, title in stage_defs:
                data = result.get(key) if isinstance(result, dict) else None
                with st.expander(f"{title} {'✅' if data else '⏭️'}", expanded=False):
                    if data:
                        st.json(data)
                    else:
                        st.caption("该阶段无输出（可能被跳过或不适用）。")

            workflow_resolution = result.get("workflow_resolution", {}) if isinstance(result, dict) else {}
            if workflow_resolution:
                st.markdown("#### 工作流执行情况")
                w1, w2, w3 = st.columns(3)
                with w1:
                    st.metric("Fallback Used", str(workflow_resolution.get("fallback_used", False)))
                with w2:
                    st.metric("LTX Ready", str(workflow_resolution.get("ltx_dependencies_ready", "N/A")))
                with w3:
                    st.metric("Fallback Reason", str(workflow_resolution.get("fallback_reason", "N/A")))

            with st.expander("查看完整执行结果 JSON", expanded=False):
                st.json(result)

        st.markdown('</div>', unsafe_allow_html=True)

        meeting_instruction = (
            f"会议要求：{meeting_tone}\n"
            "你只能作为主管回应，不要直接指挥普通员工。\n"
            "请先给出任务拆解，再说明你将如何统筹员工。"
        )
        attachment_context = build_boss_meeting_attachment_context()

        def _meeting_reply(msg: str, memory_context: str = "") -> str:
            prompt = (
                "你是老板会议室里的主管Agent，只能与老板对话，负责把老板需求转成统筹方案。\n"
                + meeting_instruction
                + f"\n会议议题：{meeting_topic}\n"
                + "\n"
                + (f"附件上下文:\n{attachment_context}\n\n" if attachment_context else "")
                + (f"历史记忆:\n{memory_context}\n\n" if memory_context else "")
                + f"老板会议内容：{msg}"
            )
            if meeting_supervisor_key == "supervisor_secretary":
                response = supervisor_dispatch_reply("supervisor_secretary", prompt, memory_context)
            else:
                response = supervisor_dispatch_reply("supervisor_video", prompt, memory_context)

            meeting_records = st.session_state.get("boss_meeting_records", {})
            if isinstance(meeting_records, dict):
                meeting_records[meeting_supervisor_key] = {
                    "last_user": msg,
                    "last_assistant": response,
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                }
                st.session_state.boss_meeting_records = meeting_records
            return response

        st.markdown('<div class="boss-meeting-divider"></div>', unsafe_allow_html=True)
        st.markdown('<div class="boss-meeting-surface">', unsafe_allow_html=True)
        st.markdown("### 与主管对话")
        render_chat(
            meeting_supervisor_key,
            _meeting_reply,
            input_key=f"chat_input_meeting_{meeting_supervisor_key}",
        )
        st.markdown('</div>', unsafe_allow_html=True)

    # ─────────────────────────────────────────────────────────────────────
    # 📚 知识库 & Obsidian 可视化入口
    # ─────────────────────────────────────────────────────────────────────
    with tab_obs:
        st.subheader("📚 知识库 & Obsidian 可视化")
        st.caption("在这里管理本地知识索引、浏览 Obsidian Vault 结构，并触发重建流程。")

        OBSIDIAN_VAULT = PROJECT_ROOT / "output" / "obsidian_vault"
        KNOWLEDGE_FOLDER = OBSIDIAN_VAULT / "00_ProjectKnowledge"
        KNOWLEDGE_INDEX_PATH = PROJECT_ROOT / "output" / "wiki" / "knowledge_index.json"

        # ── 统计区 ──────────────────────────────────────────────────────
        def _load_knowledge_stats() -> dict:
            if not KNOWLEDGE_INDEX_PATH.exists():
                return {}
            try:
                with open(KNOWLEDGE_INDEX_PATH, encoding="utf-8") as f:
                    data = json.load(f)
                chunks = data.get("chunks", [])
                by_type: dict[str, int] = {}
                by_src: dict[str, int] = {}
                for c in chunks:
                    t = c.get("source_type", "unknown")
                    s = c.get("source", "unknown")
                    by_type[t] = by_type.get(t, 0) + 1
                    by_src[s] = by_src.get(s, 0) + 1
                return {
                    "total": len(chunks),
                    "by_type": by_type,
                    "by_src": by_src,
                    "build_time": data.get("build_time", "N/A"),
                }
            except Exception:
                return {}

        kb_stats = _load_knowledge_stats()
        col_a, col_b, col_c, col_d = st.columns(4)
        with col_a:
            st.metric("总知识块", kb_stats.get("total", 0))
        with col_b:
            by_type = kb_stats.get("by_type", {})
            st.metric("来源类型", len(by_type))
        with col_c:
            vault_notes = list(KNOWLEDGE_FOLDER.rglob("*.md")) if KNOWLEDGE_FOLDER.exists() else []
            st.metric("Vault 笔记数", len(vault_notes))
        with col_d:
            canvas_file = KNOWLEDGE_FOLDER / "_Knowledge_Map.canvas"
            st.metric("Canvas 地图", "✅" if canvas_file.exists() else "❌")

        if kb_stats.get("build_time"):
            st.caption(f"最后构建时间：{kb_stats['build_time']}")

        st.divider()

        # ── 类型分布 ────────────────────────────────────────────────────
        if by_type:
            st.markdown("#### 知识块类型分布")
            type_cols = st.columns(len(by_type))
            for i, (t, cnt) in enumerate(sorted(by_type.items(), key=lambda x: -x[1])):
                with type_cols[i]:
                    st.metric(t, cnt)

        st.divider()

        # ── Obsidian Vault 入口 ─────────────────────────────────────────
        st.markdown("#### 🗂️ Obsidian Vault 路径")
        vault_abs = str(OBSIDIAN_VAULT.resolve())
        safe_vault_abs = html.escape(vault_abs)
        st.markdown(
            f"""
            <div style="
                background: #0b1220;
                color: #f8fafc;
                border: 1px solid #334155;
                border-radius: 10px;
                padding: 12px 14px;
                font-family: Consolas, 'Courier New', monospace;
                font-size: 0.92rem;
                line-height: 1.45;
                word-break: break-all;
            ">{safe_vault_abs}</div>
            """,
            unsafe_allow_html=True,
        )
        st.caption("在 Obsidian 中选择「打开文件夹作为库」，选上面的路径即可导入所有笔记和 Canvas。")

        path_c1, path_c2 = st.columns(2)
        with path_c1:
            if st.button("📂 打开 Vault 文件夹", key="obs_open_vault_folder"):
                try:
                    os.startfile(str(OBSIDIAN_VAULT))
                    st.success("已在资源管理器打开 Vault 文件夹。")
                except Exception as e:
                    st.error(f"打开失败：{e}")
        with path_c2:
            if st.button("🗺️ 打开 Canvas 文件", key="obs_open_canvas_file"):
                try:
                    if canvas_file.exists():
                        os.startfile(str(canvas_file))
                        st.success("已调用系统默认程序打开 Canvas 文件。")
                    else:
                        st.warning("未找到 _Knowledge_Map.canvas，请先重建知识库。")
                except Exception as e:
                    st.error(f"打开失败：{e}")

        with st.expander("Canvas 怎么打开看？", expanded=False):
            st.markdown(
                """
1. 点击上面的「🗺️ 打开 Canvas 文件」。
2. 如果系统没有自动用 Obsidian 打开：
   - 先在 Obsidian 中执行「打开文件夹作为库」，选择 Vault 路径。
   - 在文件列表中打开 `00_ProjectKnowledge/_Knowledge_Map.canvas`。
3. 打开后按住空格拖动画布，滚轮缩放，点击节点可跳转到对应笔记。
                """
            )

        st.markdown("#### 📄 关键可视化文件")
        key_files = [
            ("_INDEX.md", "知识库入口：所有层级与来源的导航"),
            ("_Knowledge_Map.canvas", "🗺️ 3 层 Canvas 知识地图（主推荐）"),
            ("_VISUALIZATION.md", "使用指南：Graph View + Canvas 操作说明"),
            ("_LAYER_management_experience.md", "管理经验层"),
            ("_LAYER_tech_stack.md", "技术栈层"),
            ("_LAYER_self_growth.md", "自我成长层"),
        ]
        for fname, desc in key_files:
            fpath = KNOWLEDGE_FOLDER / fname
            exists = fpath.exists()
            icon = "✅" if exists else "⬜"
            st.write(f"{icon} **{fname}** — {desc}")
            if exists:
                with st.expander(f"预览 {fname}", expanded=False):
                    try:
                        content = fpath.read_text(encoding="utf-8")
                        preview = content[:1200] + ("…（已截断）" if len(content) > 1200 else "")
                        st.markdown(preview)
                    except Exception as e:
                        st.error(f"读取失败：{e}")

        st.divider()

        # ── 重建按钮 ────────────────────────────────────────────────────
        st.markdown("#### 🔄 重建知识库")
        st.caption("重建将重新索引所有文档（docs/、skills/、CLAUDE.md、E:/Dropbox/…）并更新 Obsidian Vault。")
        if st.button("🚀 立即重建知识库", key="obs_rebuild_btn"):
            py_exe = Path(sys.executable)
            script = WIKI_BUILD_SCRIPT_PATH
            config = WIKI_CONFIG_PATH
            if not script.exists():
                st.error(f"找不到构建脚本：{script}")
            else:
                with st.spinner("正在重建知识库，请稍候…"):
                    try:
                        proc = subprocess.run(
                            [str(py_exe), str(script), "--config", str(config)],
                            capture_output=True, text=True, timeout=300,
                            cwd=str(PROJECT_ROOT),
                        )
                        if proc.returncode == 0:
                            st.success("✅ 知识库重建成功！请刷新页面查看最新统计。")
                            if proc.stdout:
                                with st.expander("构建输出"):
                                    st.text(proc.stdout[-3000:])
                        else:
                            st.error(f"构建失败（exit {proc.returncode}）")
                            st.text(proc.stderr[-2000:])
                    except subprocess.TimeoutExpired:
                        st.warning("超时（5分钟），任务仍在后台运行。")
                    except Exception as e:
                        st.error(f"启动构建失败：{e}")

        st.divider()

        # ── 知识图谱可视化（展示具体知识/技能，而非 md 文件名）────────────────
        st.markdown("#### 🌐 Canvas 知识地图结构（知识点图）")
        if KNOWLEDGE_INDEX_PATH.exists():
            try:
                index_data = json.loads(KNOWLEDGE_INDEX_PATH.read_text(encoding="utf-8"))
                chunks = index_data.get("chunks", [])

                by_type: dict[str, list[dict[str, Any]]] = {}
                for item in chunks:
                    source_type = str(item.get("source_type", "unknown"))
                    by_type.setdefault(source_type, []).append(item)

                source_types_sorted = sorted(by_type.items(), key=lambda kv: len(kv[1]), reverse=True)
                selected_types = source_types_sorted[:6]

                def _clean_topic_label(text: str) -> str:
                    label = str(text or "").strip().replace('"', "'")
                    label = re.sub(r"\s+", " ", label)
                    if not label:
                        label = "未命名知识"
                    return label[:48] + ("…" if len(label) > 48 else "")

                def _extract_topic_title(chunk: dict[str, Any]) -> str:
                    title = str(chunk.get("title", "")).strip()
                    if title and title.lower() not in {"untitled", "none", "nan"}:
                        return title
                    text = str(chunk.get("text", "")).strip()
                    if text:
                        return text.splitlines()[0][:60]
                    return str(chunk.get("source_type", "知识条目"))

                dot_lines = [
                    "digraph KnowledgeMap {",
                    "  rankdir=LR;",
                    "  graph [bgcolor=\"transparent\", pad=\"0.2\", nodesep=\"0.36\", ranksep=\"0.72\"];",
                    "  node [shape=box, style=\"rounded,filled\", color=\"#334155\", fontname=\"Microsoft YaHei\", fontsize=11, fontcolor=\"#0f172a\"];",
                    "  edge [color=\"#64748b\", arrowsize=0.7];",
                    '  "core" [label="知识中枢\\nKnowledge Core", fillcolor="#f8fafc", color="#0f172a", penwidth=1.4];',
                ]

                total_topic_nodes = 0
                total_edges = 0
                legend_map = {
                    "skills": "#22c55e",
                    "docs": "#3b82f6",
                    "project_context": "#f59e0b",
                    "boss_personal": "#a855f7",
                    "unknown": "#64748b",
                }

                detail_rows: list[tuple[str, str]] = []

                for idx, (stype, items) in enumerate(selected_types):
                    type_node_id = f"type_{idx}"
                    type_color = legend_map.get(stype, "#94a3b8")
                    type_label = f"{stype}\\n{len(items)} chunks"
                    dot_lines.append(
                        f'  "{type_node_id}" [label="{type_label}", fillcolor="{type_color}", fontcolor="#ffffff", color="#1e293b"];'
                    )
                    dot_lines.append(f'  "core" -> "{type_node_id}";')
                    total_edges += 1

                    # 重点：显示具体知识/技能标题，不显示 md 文件名
                    unique_titles: list[str] = []
                    seen_titles: set[str] = set()
                    per_type_limit = 8 if stype == "skills" else 5

                    for chunk in items:
                        candidate = _clean_topic_label(_extract_topic_title(chunk))
                        lowered = candidate.lower()
                        if lowered in seen_titles:
                            continue
                        seen_titles.add(lowered)
                        unique_titles.append(candidate)
                        if len(unique_titles) >= per_type_limit:
                            break

                    for t_idx, topic in enumerate(unique_titles):
                        topic_node_id = f"topic_{idx}_{t_idx}"
                        dot_lines.append(
                            f'  "{topic_node_id}" [label="{topic}", fillcolor="#e2e8f0", color="#475569", fontcolor="#0f172a"];'
                        )
                        dot_lines.append(f'  "{type_node_id}" -> "{topic_node_id}";')
                        total_topic_nodes += 1
                        total_edges += 1
                        detail_rows.append((stype, topic))

                dot_lines.append("}")
                dot_graph = "\n".join(dot_lines)

                m1, m2, m3 = st.columns(3)
                with m1:
                    st.metric("来源类型节点", len(selected_types))
                with m2:
                    st.metric("知识/技能节点", total_topic_nodes)
                with m3:
                    st.metric("连接数", total_edges)

                st.graphviz_chart(dot_graph, use_container_width=True)
                st.caption("图中节点均来自知识索引中的具体 title/text 摘要，已过滤 md 文件名展示。")

                with st.expander("查看知识/技能节点明细", expanded=False):
                    for stype, topic in detail_rows:
                        st.write(f"- [{stype}] {topic}")

            except Exception as e:
                st.warning(f"知识地图渲染失败：{e}")
                st.info("可先点击上方“重建知识库”，再刷新页面重试。")
        else:
            st.info("尚未找到 knowledge_index.json，请先点击「重建知识库」。")
