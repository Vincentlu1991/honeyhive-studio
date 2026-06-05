from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass
class SourceFolder:
    path: Path
    project: str


@dataclass
class SecretaryConfig:
    data_dir: Path
    copy_only: bool
    hermes_exe: str
    source_folders: list[SourceFolder]
    telegram_enabled: bool
    telegram_bot_token: str
    telegram_allowed_chat_id: str
    outlook_enabled: bool
    outlook_client_id: str
    outlook_tenant_id: str
    outlook_account_email: str
    outlook_attachment_days: int



def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}



def load_config() -> SecretaryConfig:
    load_dotenv()

    data_dir = Path(os.getenv("SECRETARY_DATA_DIR", "data"))
    source_folders: list[SourceFolder] = []

    for idx in range(1, 11):
        p = os.getenv(f"SOURCE_DIR_{idx}", "").strip()
        if not p:
            continue
        project = os.getenv(f"SOURCE_DIR_{idx}_PROJECT", "general").strip() or "general"
        source_folders.append(SourceFolder(path=Path(p), project=project))

    return SecretaryConfig(
        data_dir=data_dir,
        copy_only=_bool_env("SECRETARY_COPY_ONLY", True),
        hermes_exe=os.getenv("SECRETARY_HERMES_EXE", "").strip(),
        source_folders=source_folders,
        telegram_enabled=_bool_env("TELEGRAM_ENABLED", False),
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
        telegram_allowed_chat_id=os.getenv("TELEGRAM_ALLOWED_CHAT_ID", "").strip(),
        outlook_enabled=_bool_env("OUTLOOK_ENABLED", False),
        outlook_client_id=os.getenv("OUTLOOK_CLIENT_ID", "").strip(),
        outlook_tenant_id=os.getenv("OUTLOOK_TENANT_ID", "common").strip() or "common",
        outlook_account_email=os.getenv("OUTLOOK_ACCOUNT_EMAIL", "").strip(),
        outlook_attachment_days=int(os.getenv("OUTLOOK_ATTACHMENT_DAYS", "14")),
    )
