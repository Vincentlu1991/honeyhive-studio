from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class IngestedFile:
    source: str
    source_id: str
    file_name: str
    local_path: Path
    created_at: str
    sender: str = ""
    subject: str = ""


@dataclass
class ClassifiedFile:
    ingested: IngestedFile
    project: str
    category: str
    target_path: Path
    extracted_text: str
