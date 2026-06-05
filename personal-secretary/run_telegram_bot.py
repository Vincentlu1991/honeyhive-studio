from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from personal_secretary.classifiers import FileClassifier
from personal_secretary.collectors.telegram_collector import TelegramCollector
from personal_secretary.config import load_config
from personal_secretary.hermes_client import HermesClient
from personal_secretary.storage import SecretaryStorage

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE_REBUILD_SCRIPT = WORKSPACE_ROOT / "scripts" / "build-knowledge-index.ps1"


def rebuild_knowledge_index() -> bool:
    if not KNOWLEDGE_REBUILD_SCRIPT.exists():
        return False
    try:
        subprocess.run(
            [
                "powershell",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(KNOWLEDGE_REBUILD_SCRIPT),
                "-Root",
                str(WORKSPACE_ROOT),
            ],
            check=False,
            timeout=300,
            capture_output=True,
            text=True,
            errors="ignore",
        )
        return True
    except Exception:
        return False


def main() -> None:
    config = load_config()
    storage = SecretaryStorage(config)
    hermes = HermesClient(config)
    collector = TelegramCollector(config, storage, hermes_client=hermes)
    classifier = FileClassifier(config, storage)

    poll_interval = float(os.getenv("TELEGRAM_POLL_INTERVAL_SECONDS", "5"))
    print(f"Telegram bot poller started. interval={poll_interval}s")

    while True:
        try:
            items = collector.collect()
            if items:
                classified_count = 0
                for item in items:
                    classified = classifier.classify_and_place(item)
                    classified_count += 1
                    collector._send_message(
                        chat_id=item.sender,
                        text=(
                            f"文件已归档完成。\n"
                            f"项目: {classified.project}\n"
                            f"分类: {classified.category}\n"
                            f"路径: {classified.target_path.name}\n"
                            "知识类文件会进入知识库，个人资料/账单会进入老板资料库。"
                        ),
                    )
                rebuild_knowledge_index()
                print(f"Processed {len(items)} file attachment(s). Classified {classified_count} item(s).")
        except KeyboardInterrupt:
            print("Telegram bot poller stopped.")
            break
        except Exception as exc:
            print(f"[telegram_poller_error] {exc}")

        time.sleep(poll_interval)


if __name__ == "__main__":
    main()