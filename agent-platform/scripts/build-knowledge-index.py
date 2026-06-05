from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "agent-platform" / "config" / "wiki_knowledge_config.json"
AGENT_ROLE_CONFIG_PATH = ROOT / "agent-platform" / "config" / "agent_roles.json"


@dataclass
class SourceSpec:
    path: Path
    source_type: str
    globs: list[str]
    excludes: list[Path] = None

    def __post_init__(self):
        if self.excludes is None:
            self.excludes = []


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _load_config() -> dict[str, Any]:
    raw = _read_json(CONFIG_PATH, {})
    if not isinstance(raw, dict):
        raise ValueError("wiki_knowledge_config.json 格式错误")
    return raw


def _source_specs(config: dict[str, Any]) -> list[SourceSpec]:
    specs: list[SourceSpec] = []
    for item in config.get("sources", []):
        if not isinstance(item, dict):
            continue
        rel_path = str(item.get("path", "")).strip()
        source_type = str(item.get("type", "docs")).strip() or "docs"
        raw_globs = item.get("globs", None)
        if isinstance(raw_globs, list):
            globs = [str(g).strip() for g in raw_globs if str(g).strip()]
        else:
            globs = [str(item.get("glob", "**/*.md")).strip()]
        globs = [g for g in globs if g]
        if not globs:
            globs = ["**/*.md"]
        if not rel_path:
            continue
        raw_path = Path(rel_path)
        source_path = raw_path if raw_path.is_absolute() else (ROOT / raw_path)
        raw_excludes = item.get("excludes", [])
        excludes: list[Path] = []
        for ex in (raw_excludes if isinstance(raw_excludes, list) else []):
            ex_path = Path(str(ex).strip())
            if not ex_path.is_absolute():
                ex_path = source_path / ex_path
            excludes.append(ex_path.resolve())
        specs.append(SourceSpec(path=source_path, source_type=source_type, globs=globs, excludes=excludes))
    return specs


def _display_path(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _iter_source_files(spec: SourceSpec) -> list[Path]:
    if spec.path.is_file():
        return [spec.path]
    if not spec.path.exists() or not spec.path.is_dir():
        return []
    discovered: dict[str, Path] = {}
    exclude_resolved = [ex.resolve() for ex in (spec.excludes or [])]
    for pattern in spec.globs or ["**/*.md"]:
        for path in spec.path.glob(pattern):
            if not path.is_file():
                continue
            resolved = path.resolve()
            if any(resolved == ex or ex in resolved.parents for ex in exclude_resolved):
                continue
            discovered[str(resolved)] = path
    return list(discovered.values())


def _extract_pdf_text(file_path: Path) -> str:
    try:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(str(file_path))
        pages: list[str] = []
        for page in reader.pages:
            pages.append((page.extract_text() or "").strip())
        return "\n\n".join(part for part in pages if part)
    except Exception:
        return ""


def _extract_docx_text(file_path: Path) -> str:
    try:
        from docx import Document  # type: ignore

        doc = Document(str(file_path))
        lines = [p.text.strip() for p in doc.paragraphs if p.text and p.text.strip()]
        return "\n".join(lines)
    except Exception:
        return ""


def _extract_image_summary(file_path: Path) -> str:
    stat = file_path.stat()
    lines = [
        f"Image asset: {file_path.name}",
        f"Extension: {file_path.suffix.lower()}",
        f"Size bytes: {stat.st_size}",
        f"Modified: {datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()}",
        f"Path: {_display_path(file_path)}",
    ]
    try:
        from PIL import Image  # type: ignore

        with Image.open(file_path) as img:
            lines.append(f"Width: {img.width}")
            lines.append(f"Height: {img.height}")
            lines.append(f"Mode: {img.mode}")
            if getattr(img, "format", None):
                lines.append(f"Format: {img.format}")
    except Exception:
        lines.append("Image parser not available, only metadata indexed.")
    return "\n".join(lines)


def _metadata_only_content(file_path: Path, kind: str) -> str:
    stat = file_path.stat()
    return (
        f"{kind}: {file_path.name}\n"
        f"Path: {_display_path(file_path)}\n"
        f"Extension: {file_path.suffix.lower()}\n"
        f"Size bytes: {stat.st_size}\n"
        "Text extraction unavailable; metadata-only indexing fallback."
    )


def _read_source_content(file_path: Path) -> str:
    ext = file_path.suffix.lower()
    if ext in {".md", ".txt", ".rst", ".csv", ".json", ".yml", ".yaml", ".ipynb"}:
        try:
            return file_path.read_text(encoding="utf-8")
        except Exception:
            try:
                return file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                return ""
    if ext in {".html", ".htm"}:
        try:
            raw = file_path.read_text(encoding="utf-8", errors="ignore")
            text = re.sub(r"<[^>]+>", " ", raw)
            text = re.sub(r"\s+", " ", text).strip()
            return text
        except Exception:
            return _metadata_only_content(file_path, "HTML document")
    if ext == ".pdf":
        text = _extract_pdf_text(file_path)
        if text:
            return text
        return _metadata_only_content(file_path, "PDF document")
    if ext == ".docx":
        text = _extract_docx_text(file_path)
        if text:
            return text
        return _metadata_only_content(file_path, "DOCX document")
    if ext in {".doc", ".pptx", ".ppt", ".xlsx", ".xls", ".rtf"}:
        return _metadata_only_content(file_path, "Office document")
    if ext in {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".gif"}:
        return _extract_image_summary(file_path)
    return ""


def _file_fingerprint(path: Path) -> str:
    stat = path.stat()
    return f"{stat.st_mtime_ns}:{stat.st_size}"


def _collect_fingerprints(specs: list[SourceSpec]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for spec in specs:
        for file_path in _iter_source_files(spec):
            mapping[_display_path(file_path)] = _file_fingerprint(file_path)
    return mapping


def _indexer_signature() -> str:
    digest = hashlib.sha1(Path(__file__).read_bytes()).hexdigest()
    return digest


def _load_staff_skill_map() -> dict[str, str]:
    raw = _read_json(AGENT_ROLE_CONFIG_PATH, {})
    if not isinstance(raw, dict):
        return {}
    mapping = raw.get("staff_skill_files", {})
    if not isinstance(mapping, dict):
        return {}
    valid: dict[str, str] = {}
    for staff_key, file_name in mapping.items():
        if isinstance(staff_key, str) and isinstance(file_name, str):
            valid[staff_key] = file_name
    return valid


def _extract_staff_scope(file_path: Path, staff_skill_map: dict[str, str]) -> list[str]:
    if not staff_skill_map:
        return []
    for staff_key, file_name in staff_skill_map.items():
        if file_name == file_path.name:
            return [staff_key]
    return []


def _extract_tags(file_path: Path, source_type: str) -> list[str]:
    tags: list[str] = [source_type]
    rel_parts = _display_path(file_path).split("/")
    tags.extend(part for part in rel_parts[:-1] if part and part not in {"docs", "output", "skills"})
    if file_path.suffix:
        tags.append(file_path.suffix.lower().lstrip("."))
    return list(dict.fromkeys(tags))


def _split_sections(text: str) -> list[tuple[str, str]]:
    lines = text.splitlines()
    sections: list[tuple[str, list[str]]] = []
    current_title = "Document"
    current_lines: list[str] = []
    for raw in lines:
        line = raw.rstrip()
        if line.startswith("#") and current_lines:
            sections.append((current_title, current_lines))
            current_title = line.lstrip("# ").strip() or "Section"
            current_lines = []
            continue
        if line.startswith("#"):
            current_title = line.lstrip("# ").strip() or "Section"
            continue
        current_lines.append(line)
    if current_lines:
        sections.append((current_title, current_lines))
    return [(title, "\n".join(content).strip()) for title, content in sections if "\n".join(content).strip()]


def _chunk_text(text: str, max_chars: int, overlap_chars: int, min_chars: int) -> list[str]:
    clean = text.strip()
    if not clean:
        return []
    if len(clean) <= max_chars:
        return [clean] if len(clean) >= min_chars else []

    chunks: list[str] = []
    start = 0
    while start < len(clean):
        end = min(start + max_chars, len(clean))
        chunk = clean[start:end].strip()
        if len(chunk) >= min_chars:
            chunks.append(chunk)
        if end == len(clean):
            break
        start = max(end - overlap_chars, 0)
    return chunks


def _stable_chunk_id(rel_path: str, title: str, chunk_text: str) -> str:
    digest = hashlib.sha1(f"{rel_path}|{title}|{chunk_text}".encode("utf-8")).hexdigest()
    return digest


def _sanitize_note_name(value: str, fallback: str = "note") -> str:
    # Windows and Obsidian friendly file names.
    text = re.sub(r'[<>:"/\\|?*]', "_", value).strip().rstrip(".")
    text = re.sub(r"\s+", " ", text)
    if not text:
        text = fallback
    return text[:120]


def _resolve_output_path(path_str: str) -> Path:
    raw = Path(path_str)
    return raw if raw.is_absolute() else (ROOT / raw)


def _layer_name_for_source_type(source_type: str) -> str:
    normalized = source_type.strip().lower()
    if normalized in {"docs", "project_context"}:
        return "management_experience"
    if normalized in {"skills"}:
        return "tech_stack"
    if normalized in {"boss_personal"}:
        return "self_growth"
    return "self_growth"


def _write_obsidian_layer_notes(
    knowledge_root: Path,
    knowledge_folder: str,
    source_types: list[str],
) -> dict[str, list[str]]:
    layer_to_sources: dict[str, list[str]] = {
        "management_experience": [],
        "tech_stack": [],
        "self_growth": [],
    }
    for source_type in source_types:
        layer_to_sources.setdefault(_layer_name_for_source_type(source_type), []).append(source_type)

    layer_title = {
        "management_experience": "Management Experience Layer",
        "tech_stack": "Tech Stack Layer",
        "self_growth": "Self Growth Layer",
    }
    for layer, members in layer_to_sources.items():
        note_path = knowledge_root / f"_LAYER_{layer}.md"
        lines = [
            f"# {layer_title.get(layer, layer)}",
            "",
            f"- Source groups: {len(members)}",
            "- Linked from: [[_INDEX]]",
            "",
            "## Hubs",
        ]
        for source_type in sorted(members):
            safe_name = _sanitize_note_name(source_type, "general")
            lines.append(f"- [[{knowledge_folder}/_HUB_{safe_name}|{source_type} hub]]")
        note_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return layer_to_sources


def _write_obsidian_canvas(
    vault_root: Path,
    knowledge_folder: str,
    layer_to_sources: dict[str, list[str]],
) -> None:
    canvas_nodes: list[dict[str, Any]] = []
    canvas_edges: list[dict[str, Any]] = []

    def _id(seed: str) -> str:
        return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]

    index_id = _id("index")
    canvas_nodes.append(
        {
            "id": index_id,
            "type": "file",
            "file": f"{knowledge_folder}/_INDEX.md",
            "x": 0,
            "y": 0,
            "width": 360,
            "height": 220,
        }
    )

    layer_order = ["management_experience", "tech_stack", "self_growth"]

    layer_gap_y = 280
    start_layer_y = -((len(layer_order) - 1) * layer_gap_y // 2)
    for i, layer in enumerate(layer_order):
        y = start_layer_y + i * layer_gap_y
        layer_id = _id(f"layer:{layer}")
        canvas_nodes.append(
            {
                "id": layer_id,
                "type": "file",
                "file": f"{knowledge_folder}/_LAYER_{layer}.md",
                "x": 520,
                "y": y,
                "width": 360,
                "height": 200,
            }
        )
        canvas_edges.append(
            {
                "id": _id(f"edge:index:layer:{layer}"),
                "fromNode": index_id,
                "fromSide": "right",
                "toNode": layer_id,
                "toSide": "left",
            }
        )

        members = sorted(layer_to_sources.get(layer, []))
        hub_gap_y = 180
        start_hub_y = y - ((len(members) - 1) * hub_gap_y // 2 if members else 0)
        for j, source_type in enumerate(members):
            safe = _sanitize_note_name(source_type, "general")
            hub_id = _id(f"hub:{safe}")
            hub_y = start_hub_y + j * hub_gap_y
            canvas_nodes.append(
                {
                    "id": hub_id,
                    "type": "file",
                    "file": f"{knowledge_folder}/_HUB_{safe}.md",
                    "x": 980,
                    "y": hub_y,
                    "width": 420,
                    "height": 180,
                }
            )
            canvas_edges.append(
                {
                    "id": _id(f"edge:layer:{layer}:hub:{safe}"),
                    "fromNode": layer_id,
                    "fromSide": "right",
                    "toNode": hub_id,
                    "toSide": "left",
                }
            )

    canvas_path = vault_root / f"{knowledge_folder}/_Knowledge_Map.canvas"
    canvas_data = {"nodes": canvas_nodes, "edges": canvas_edges}
    canvas_path.write_text(json.dumps(canvas_data, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_obsidian_visual_guide(vault_root: Path, knowledge_folder: str) -> None:
    guide = vault_root / f"{knowledge_folder}/_VISUALIZATION.md"
    content = (
        "# Obsidian Official Visualization\n\n"
        "## 1. Graph View (官方)\n"
        "- Open: Graph view\n"
        "- Start from: [[_INDEX]]\n"
        "- Filter suggestion: `path:\""
        + knowledge_folder
        + "\"`\n\n"
        "## 2. Canvas (官方)\n"
        "- Open: [[_Knowledge_Map.canvas]]\n"
        "- Structure: `_INDEX` -> `_LAYER_*` -> `_HUB_*` -> detail notes\n\n"
        "## 3. Hubs\n"
        "- `_HUB_*` notes are automatically generated as source-type visual anchors.\n"
        "\n"
        "## 4. Layer Design\n"
        "- `management_experience`: docs + project context\n"
        "- `tech_stack`: skills and engineering know-how\n"
        "- `self_growth`: personal material and long-term learning\n"
    )
    guide.write_text(content, encoding="utf-8")


def _export_obsidian(index_data: dict[str, Any], config: dict[str, Any]) -> Path | None:
    obsidian_cfg = config.get("obsidian", {})
    if not isinstance(obsidian_cfg, dict):
        return None
    if not bool(obsidian_cfg.get("enabled", True)):
        return None

    vault_path = str(obsidian_cfg.get("vault_path", "output/obsidian_vault")).strip()
    knowledge_folder = str(obsidian_cfg.get("knowledge_folder", "00_ProjectKnowledge")).strip() or "00_ProjectKnowledge"
    vault_root = _resolve_output_path(vault_path)
    knowledge_root = vault_root / knowledge_folder
    knowledge_root.mkdir(parents=True, exist_ok=True)

    chunks = index_data.get("chunks", [])
    if not isinstance(chunks, list):
        return knowledge_root

    by_type: dict[str, list[dict[str, Any]]] = {}
    notes_by_type: dict[str, list[str]] = {}
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        source_type = str(chunk.get("source_type", "general")).strip() or "general"
        by_type.setdefault(source_type, []).append(chunk)

    total_written = 0
    for source_type, typed_chunks in by_type.items():
        section_dir = knowledge_root / _sanitize_note_name(source_type, "general")
        section_dir.mkdir(parents=True, exist_ok=True)

        for chunk in typed_chunks:
            chunk_id = str(chunk.get("id", ""))
            title = str(chunk.get("title", "Document")).strip() or "Document"
            source_path = str(chunk.get("source_path", ""))
            tags = chunk.get("tags", [])
            if not isinstance(tags, list):
                tags = []
            text = str(chunk.get("text", "")).strip()
            if not text:
                continue

            tag_line = " ".join(f"#{_sanitize_note_name(str(t), 'tag').replace(' ', '_')}" for t in tags)
            note_name = _sanitize_note_name(f"{Path(source_path).stem}_{title}_{chunk_id[:8]}", "chunk")
            note_path = section_dir / f"{note_name}.md"
            rel_note = f"{knowledge_folder}/{_sanitize_note_name(source_type, 'general')}/{note_name}.md"
            safe_title = title.replace('"', "'").replace("\n", " ").strip()

            content = (
                "---\n"
                f"id: {chunk_id}\n"
                f"source_type: {source_type}\n"
                f"source_path: {source_path}\n"
                f"title: \"{safe_title}\"\n"
                f"updated_at: {chunk.get('updated_at', '')}\n"
                "---\n\n"
                f"# {title}\n\n"
                f"{text}\n\n"
                "## Metadata\n"
                f"- Source: {source_path}\n"
                f"- Type: {source_type}\n"
                f"- Tags: {tag_line if tag_line else 'none'}\n"
            )
            note_path.write_text(content, encoding="utf-8")
            notes_by_type.setdefault(source_type, []).append(rel_note)
            total_written += 1

    max_notes_per_hub = int(obsidian_cfg.get("max_notes_per_hub", 120))
    for source_type in sorted(by_type.keys()):
        safe_name = _sanitize_note_name(source_type, "general")
        hub_path = knowledge_root / f"_HUB_{safe_name}.md"
        rel_notes = notes_by_type.get(source_type, [])
        lines = [
            f"# Hub: {source_type}",
            "",
            f"- Total notes: {len(rel_notes)}",
            "- Linked from: [[_INDEX]]",
            "",
            "## Notes",
        ]
        for rel in rel_notes[:max_notes_per_hub]:
            note_ref = rel.replace(".md", "")
            lines.append(f"- [[{note_ref}]]")
        if len(rel_notes) > max_notes_per_hub:
            lines.append("")
            lines.append(f"... truncated {len(rel_notes) - max_notes_per_hub} notes")
        hub_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if bool(obsidian_cfg.get("write_meta_index", True)):
        index_note = knowledge_root / "_INDEX.md"
        lines = [
            "# Project Knowledge Index",
            "",
            f"- Built at: {index_data.get('meta', {}).get('built_at', '')}",
            f"- Chunk count: {index_data.get('meta', {}).get('chunk_count', 0)}",
            f"- Notes written: {total_written}",
            "",
            "## Layers",
            "- [[_LAYER_management_experience|Management Experience Layer]]",
            "- [[_LAYER_tech_stack|Tech Stack Layer]]",
            "- [[_LAYER_self_growth|Self Growth Layer]]",
            "",
            "## Source Types",
        ]
        for source_type in sorted(by_type.keys()):
            safe_name = _sanitize_note_name(source_type, "general")
            lines.append(f"- [[{knowledge_folder}/_HUB_{safe_name}|{source_type} hub]]")
        index_note.write_text("\n".join(lines) + "\n", encoding="utf-8")

    layer_to_sources = _write_obsidian_layer_notes(
        knowledge_root=knowledge_root,
        knowledge_folder=knowledge_folder,
        source_types=sorted(by_type.keys()),
    )
    _write_obsidian_canvas(
        vault_root=vault_root,
        knowledge_folder=knowledge_folder,
        layer_to_sources=layer_to_sources,
    )
    _write_obsidian_visual_guide(vault_root=vault_root, knowledge_folder=knowledge_folder)

    return knowledge_root


def _build_index(config: dict[str, Any]) -> dict[str, Any]:
    chunk_cfg = config.get("chunk", {})
    max_chars = int(chunk_cfg.get("max_chars", 900))
    overlap_chars = int(chunk_cfg.get("overlap_chars", 120))
    min_chars = int(chunk_cfg.get("min_chars", 80))

    specs = _source_specs(config)
    staff_skill_map = _load_staff_skill_map()
    chunks: list[dict[str, Any]] = []

    for spec in specs:
        for file_path in _iter_source_files(spec):
            rel_path = _display_path(file_path)
            content = _read_source_content(file_path)
            if not content.strip():
                continue

            sections = _split_sections(content)
            if not sections and content.strip():
                sections = [(file_path.stem, content.strip())]

            for title, section_text in sections:
                for chunk_text in _chunk_text(section_text, max_chars, overlap_chars, min_chars):
                    chunk_id = _stable_chunk_id(rel_path, title, chunk_text)
                    chunks.append(
                        {
                            "id": chunk_id,
                            "source_path": rel_path,
                            "source_type": spec.source_type,
                            "title": title,
                            "text": chunk_text,
                            "tags": _extract_tags(file_path, spec.source_type),
                            "staff_scopes": _extract_staff_scope(file_path, staff_skill_map),
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        }
                    )

    return {
        "meta": {
            "built_at": datetime.now(timezone.utc).isoformat(),
            "chunk_count": len(chunks),
            "version": 1,
        },
        "chunks": chunks,
    }


def main() -> int:
    config = _load_config()
    if not bool(config.get("enabled", True)):
        print("Knowledge index disabled by config.")
        return 0

    index_path = ROOT / str(config.get("index_path", "output/wiki/knowledge_index.json"))
    state_path = ROOT / str(config.get("state_path", "output/wiki/knowledge_state.json"))

    specs = _source_specs(config)
    current_files = _collect_fingerprints(specs)
    previous_state = _read_json(state_path, {})
    previous_files = previous_state.get("files", {}) if isinstance(previous_state, dict) else {}
    previous_signature = previous_state.get("indexer_signature", "") if isinstance(previous_state, dict) else ""
    current_signature = _indexer_signature()

    if current_files == previous_files and previous_signature == current_signature and index_path.exists():
        print("Knowledge index up-to-date, no rebuild needed.")
        return 0

    index_data = _build_index(config)
    _ensure_parent(index_path)
    index_path.write_text(json.dumps(index_data, ensure_ascii=False, indent=2), encoding="utf-8")

    state_data = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "files": current_files,
        "indexer_signature": current_signature,
    }
    _ensure_parent(state_path)
    state_path.write_text(json.dumps(state_data, ensure_ascii=False, indent=2), encoding="utf-8")

    obsidian_path = _export_obsidian(index_data, config)

    print(f"Knowledge index rebuilt: {index_data.get('meta', {}).get('chunk_count', 0)} chunks")
    print(f"Index path: {index_path.relative_to(ROOT).as_posix()}")
    if obsidian_path is not None:
        print(f"Obsidian export path: {_display_path(obsidian_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
