from __future__ import annotations

from personal_secretary.analysis import run_analysis
from personal_secretary.classifiers import FileClassifier
from personal_secretary.collectors.fs_collector import FolderCollector
from personal_secretary.collectors.outlook_collector import OutlookCollector
from personal_secretary.collectors.telegram_collector import TelegramCollector
from personal_secretary.config import load_config
from personal_secretary.hermes_client import HermesClient
from personal_secretary.storage import SecretaryStorage



def run_sync() -> dict:
    config = load_config()
    storage = SecretaryStorage(config)
    classifier = FileClassifier(config, storage)
    hermes = HermesClient(config)

    all_items = []

    def collect_safely(label: str, callback):
        try:
            return callback()
        except Exception as exc:
            print(f"[{label}_collector_error] {exc}")
            return []

    folder_collector = FolderCollector(config, storage)
    all_items.extend(collect_safely("folder", folder_collector.collect))

    telegram_collector = TelegramCollector(config, storage, hermes_client=hermes)
    all_items.extend(collect_safely("telegram", telegram_collector.collect))

    outlook_collector = OutlookCollector(config, storage)
    all_items.extend(collect_safely("outlook", outlook_collector.collect))

    classified_count = 0
    for item in all_items:
        classifier.classify_and_place(item)
        classified_count += 1

    report = run_analysis(config, storage)
    print(f"Sync complete. New files: {len(all_items)} | Classified: {classified_count}")
    print(f"Income(est): {report.get('income_total', 0)} | Expense(est): {report.get('expense_total', 0)}")
    return report
