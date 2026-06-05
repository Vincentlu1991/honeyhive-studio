from __future__ import annotations

import hashlib
import re
import shutil
from datetime import datetime
from pathlib import Path

from personal_secretary.config import SecretaryConfig, SourceFolder
from personal_secretary.models import IngestedFile
from personal_secretary.storage import SecretaryStorage


ALLOWED_EXT = {
    ".pdf",
    ".txt",
    ".md",
    ".docx",
    ".xlsx",
    ".xls",
    ".csv",
    ".pptx",
    ".json",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
}


class FolderCollector:
    _WINDOWS_RESERVED_NAMES = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        "COM1",
        "COM2",
        "COM3",
        "COM4",
        "COM5",
        "COM6",
        "COM7",
        "COM8",
        "COM9",
        "LPT1",
        "LPT2",
        "LPT3",
        "LPT4",
        "LPT5",
        "LPT6",
        "LPT7",
        "LPT8",
        "LPT9",
    }

    def __init__(self, config: SecretaryConfig, storage: SecretaryStorage) -> None:
        self.config = config
        self.storage = storage

    def collect(self) -> list[IngestedFile]:
        results: list[IngestedFile] = []
        for source in self.config.source_folders:
            items, _ = self.collect_incremental(source.path, source.project)
            results.extend(items)

        return results

    def collect_incremental(self, folder_path: Path, project: str) -> tuple[list[IngestedFile], dict]:
        source = SourceFolder(path=folder_path, project=project)
        return self._collect_from_source(source)

    def _collect_from_source(self, source: SourceFolder) -> tuple[list[IngestedFile], dict]:
        if not source.path.exists():
            return [], {
                "path": str(source.path),
                "project": source.project,
                "scanned_files": 0,
                "new_files": 0,
                "skipped_existing": 0,
                "missing_path": True,
            }

        results: list[IngestedFile] = []
        scanned_files = 0
        skipped_existing = 0
        skipped_invalid = 0
        iterator = source.path.rglob("*")

        while True:
            try:
                path = next(iterator)
            except StopIteration:
                break
            except OSError as exc:
                skipped_invalid += 1
                print(f"[folder_collector_skip] failed to iterate under {source.path}: {exc}")
                continue

            try:
                if not path.is_file() or path.suffix.lower() not in ALLOWED_EXT:
                    continue

                scanned_files += 1
                source_id = self._source_id(path)
                if self.storage.has_source_item("folder", source_id):
                    skipped_existing += 1
                    continue

                target = self.storage.inbox / "folder" / source.project
                target.mkdir(parents=True, exist_ok=True)
                safe_name = self._safe_file_name(path.name)
                local_path = target / safe_name
                local_path = self._dedupe_path(local_path)
                shutil.copy2(path, local_path)

                item = IngestedFile(
                    source="folder",
                    source_id=source_id,
                    file_name=path.name,
                    local_path=local_path,
                    created_at=datetime.utcnow().isoformat(),
                    sender=str(source.path),
                    subject=source.project,
                )
                self.storage.register_ingested(item)
                results.append(item)
            except (OSError, ValueError) as exc:
                skipped_invalid += 1
                print(f"[folder_collector_skip] {path}: {exc}")
                continue

        stats = {
            "path": str(source.path),
            "project": source.project,
            "scanned_files": scanned_files,
            "new_files": len(results),
            "skipped_existing": skipped_existing,
            "skipped_invalid": skipped_invalid,
            "missing_path": False,
            "already_organized": scanned_files > 0 and len(results) == 0,
        }
        return results, stats

    def _source_id(self, path: Path) -> str:
        hasher = hashlib.sha1()
        hasher.update(str(path).encode("utf-8", errors="ignore"))
        try:
            stat = path.stat()
            hasher.update(str(stat.st_size).encode("utf-8"))
            hasher.update(str(int(stat.st_mtime)).encode("utf-8"))
        except OSError:
            pass
        return hasher.hexdigest()

    @staticmethod
    def _dedupe_path(path: Path) -> Path:
        if not path.exists():
            return path
        stem = path.stem
        suffix = path.suffix
        idx = 1
        while True:
            candidate = path.with_name(f"{stem}_{idx}{suffix}")
            if not candidate.exists():
                return candidate
            idx += 1

    @classmethod
    def _safe_file_name(cls, file_name: str) -> str:
        # Keep source filename for metadata, but sanitize destination for Windows.
        safe = re.sub(r'[<>:"/\\|?*]', "_", file_name)
        safe = safe.rstrip(" .")
        if not safe:
            safe = "unnamed"

        stem = Path(safe).stem
        suffix = Path(safe).suffix
        if stem.upper() in cls._WINDOWS_RESERVED_NAMES:
            safe = f"{stem}_reserved{suffix}"
        return safe
