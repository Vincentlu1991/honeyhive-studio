from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from personal_secretary.analysis import estimate_money_details
from personal_secretary.classifiers import FileClassifier
from personal_secretary.config import SecretaryConfig, SourceFolder
from personal_secretary.document_reader_agent import DocumentReaderAgent
from personal_secretary.models import IngestedFile
from personal_secretary.collectors.telegram_collector import TelegramCollector
from personal_secretary.storage import SecretaryStorage


class RequirementsReadAnalyzeClassifyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.config = SecretaryConfig(
            data_dir=base / "data",
            copy_only=True,
            hermes_exe="",
            source_folders=[SourceFolder(path=base / "src", project="entrepreneurship")],
            telegram_enabled=False,
            telegram_bot_token="",
            telegram_allowed_chat_id="",
            outlook_enabled=False,
            outlook_client_id="",
            outlook_tenant_id="common",
            outlook_account_email="",
            outlook_attachment_days=14,
        )
        self.storage = SecretaryStorage(self.config)
        self.classifier = FileClassifier(self.config, self.storage)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_extract_text_supports_docx_and_pptx(self) -> None:
        docx_path = self._build_min_docx(Path(self.tmp.name) / "sample.docx", "UOB transfer bill")
        pptx_path = self._build_min_pptx(Path(self.tmp.name) / "sample.pptx", "internet charge 59.90")

        docx_text = self.classifier.extract_text(docx_path)
        pptx_text = self.classifier.extract_text(pptx_path)

        self.assertIn("UOB transfer bill", docx_text)
        self.assertIn("internet charge 59.90", pptx_text)

    def test_expense_policy_only_counts_qualified_outlook_docs(self) -> None:
        text = "Date 2026-05-15\nAmount SGD 128.50\nUOB transfer payment"

        qualified = estimate_money_details(
            text=text,
            source="outlook",
            subject="UOB transfer alert",
            sender="alerts@uob.com",
            created_at="2026-05-16T10:00:00",
            category="expense_report",
            file_name="uob_bill.pdf",
        )
        uploaded = estimate_money_details(
            text=text,
            source="chat_upload",
            subject="UOB transfer alert",
            sender="me@local",
            created_at="2026-05-16T10:00:00",
            category="uob_transfer",
            file_name="uob_bill_upload.pdf",
        )
        unqualified = estimate_money_details(
            text=text,
            source="folder",
            subject="UOB transfer alert",
            sender="alerts@uob.com",
            created_at="2026-05-16T10:00:00",
            category="expense_report",
            file_name="uob_bill.pdf",
        )

        self.assertEqual(qualified["expense"], 128.5)
        self.assertEqual(uploaded["expense"], 128.5)
        self.assertGreaterEqual(qualified["income"], 0.0)
        self.assertTrue(qualified["qualified_outlook_expense_doc"])
        self.assertTrue(uploaded["qualified_outlook_expense_doc"])

        self.assertEqual(unqualified["expense"], 0.0)
        self.assertFalse(unqualified["qualified_outlook_expense_doc"])

    def test_expense_audit_rejects_mixed_non_finance_content(self) -> None:
        noisy_text = (
            "Week 3 lecture notes for data science and personal profile update.\n"
            "UOB alumni event announcement, no payment instruction."
        )
        details = estimate_money_details(
            text=noisy_text,
            source="outlook",
            subject="UOB student newsletter",
            sender="newsletter@uob.edu",
            created_at="2026-05-20T09:00:00",
            category="study_outline",
            file_name="study_newsletter.docx",
        )
        self.assertEqual(details["expense"], 0.0)
        self.assertFalse(details["qualified_outlook_expense_doc"])

    def test_expense_audit_rejects_old_bill_date_mismatch(self) -> None:
        stale_text = "Statement Date: 2018-01-03\nAmount SGD 188.00\nutilities bill"
        details = estimate_money_details(
            text=stale_text,
            source="outlook",
            subject="SP services bill",
            sender="billing@sp.com.sg",
            created_at="2026-05-20T09:00:00",
            category="expense_report",
            file_name="utility_bill.pdf",
        )
        self.assertEqual(details["expense"], 0.0)
        self.assertFalse(details["qualified_outlook_expense_doc"])

    def test_manual_override_allows_expense_after_reject(self) -> None:
        stale_text = "Statement Date: 2018-01-03\nAmount SGD 188.00\nutilities bill"
        base = estimate_money_details(
            text=stale_text,
            source="chat_upload",
            subject="SP services bill",
            sender="billing@sp.com.sg",
            created_at="2026-05-20T09:00:00",
            category="utilities",
            file_name="utility_bill.pdf",
        )
        overridden = estimate_money_details(
            text=stale_text,
            source="chat_upload",
            subject="SP services bill",
            sender="billing@sp.com.sg",
            created_at="2026-05-20T09:00:00",
            category="utilities",
            file_name="utility_bill.pdf",
            manual_expense_override=True,
            manual_expense_category="utilities",
        )

        self.assertFalse(base["qualified_outlook_expense_doc"])
        self.assertEqual(base["expense"], 0.0)
        self.assertTrue(overridden["qualified_outlook_expense_doc"])
        self.assertEqual(overridden["expense"], 188.0)

    def test_storage_manual_override_can_be_revoked(self) -> None:
        src_dir = Path(self.tmp.name) / "src"
        src_dir.mkdir(parents=True, exist_ok=True)
        sample = src_dir / "upload_bill.txt"
        sample.write_text("Amount SGD 25.00", encoding="utf-8")

        item = IngestedFile(
            source="chat_upload",
            source_id="override-1",
            file_name=sample.name,
            local_path=sample,
            created_at="2026-05-27T00:00:00",
            sender="dashboard_user",
            subject="bill",
        )
        self.storage.register_ingested(item)

        self.storage.set_manual_expense_override("chat_upload", "override-1", "phone", "test")
        rows = self.storage.all_indexed_files()
        row = next(x for x in rows if x.get("source_id") == "override-1")
        self.assertEqual(row.get("manual_expense_override"), 1)
        self.assertEqual(row.get("manual_expense_category"), "phone")

        self.storage.clear_manual_expense_override("chat_upload", "override-1")
        rows2 = self.storage.all_indexed_files()
        row2 = next(x for x in rows2 if x.get("source_id") == "override-1")
        self.assertEqual(row2.get("manual_expense_override"), 0)
        self.assertEqual(row2.get("manual_expense_category"), "")

    def test_telegram_text_message_gets_reply(self) -> None:
        config = SecretaryConfig(
            data_dir=Path(self.tmp.name) / "data_telegram",
            copy_only=True,
            hermes_exe="",
            source_folders=[],
            telegram_enabled=True,
            telegram_bot_token="bot-token",
            telegram_allowed_chat_id="",
            outlook_enabled=False,
            outlook_client_id="",
            outlook_tenant_id="common",
            outlook_account_email="",
            outlook_attachment_days=14,
        )
        storage = SecretaryStorage(config)

        class FakeHermes:
            def __init__(self) -> None:
                self.calls: list[tuple[str, str]] = []

            def answer(self, question: str, context: str, **kwargs) -> str:
                self.calls.append((question, context))
                return "机器人回复：我收到了"

        fake_hermes = FakeHermes()

        def fake_get(url, params=None, timeout=None, **kwargs):
            if url.endswith("/getUpdates"):
                return self._fake_response(
                    {
                        "ok": True,
                        "result": [
                            {
                                "update_id": 101,
                                "message": {
                                    "message_id": 7,
                                    "chat": {"id": 999},
                                    "text": "你好，帮我看看文件",
                                },
                            }
                        ],
                    }
                )
            raise AssertionError(f"Unexpected GET url: {url}")

        def fake_post(url, json=None, timeout=None, **kwargs):
            self.assertIn("sendMessage", url)
            self.assertEqual(json["chat_id"], "999")
            self.assertIn("机器人回复", json["text"])
            return self._fake_response({"ok": True, "result": {}})

        collector = TelegramCollector(config, storage, hermes_client=fake_hermes)

        with patch("personal_secretary.collectors.telegram_collector.requests.get", side_effect=fake_get), patch(
            "personal_secretary.collectors.telegram_collector.requests.post", side_effect=fake_post
        ):
            items = collector.collect()

        self.assertEqual(items, [])
        self.assertEqual(len(fake_hermes.calls), 1)
        self.assertEqual(fake_hermes.calls[0][0], "你好，帮我看看文件")
        chat_rows = storage.recent_chat_messages(limit=10)
        self.assertEqual([row["role"] for row in chat_rows], ["telegram_user", "telegram_assistant"])
        self.assertEqual(chat_rows[1]["content"], "机器人回复：我收到了")

    def test_telegram_context_selection_handles_chinese_queries(self) -> None:
        config = SecretaryConfig(
            data_dir=Path(self.tmp.name) / "data_context",
            copy_only=True,
            hermes_exe="",
            source_folders=[],
            telegram_enabled=True,
            telegram_bot_token="bot-token",
            telegram_allowed_chat_id="",
            outlook_enabled=False,
            outlook_client_id="",
            outlook_tenant_id="common",
            outlook_account_email="",
            outlook_attachment_days=14,
        )
        storage = SecretaryStorage(config)
        for idx in range(1, 9):
            item = IngestedFile(
                source="folder",
                source_id=f"ctx-{idx}",
                file_name=f"file_{idx}.txt",
                local_path=Path(self.tmp.name) / f"file_{idx}.txt",
                created_at=f"2026-05-27T00:00:0{idx}",
                sender="E:/Dropbox/共享文件夹/SP_数据科学",
                subject="数据科学",
            )
            item.local_path.write_text(f"document {idx}", encoding="utf-8")
            storage.register_ingested(item)
            storage.register_classified(
                type("C", (), {
                    "project": "data_science",
                    "category": "general",
                    "extracted_text": f"document {idx}",
                    "target_path": item.local_path,
                    "ingested": item,
                })()
            )

        class FakeHermes:
            def __init__(self) -> None:
                self.contexts: list[str] = []

            def answer(self, question: str, context: str, **kwargs) -> str:
                self.contexts.append(context)
                return "ok"

        fake_hermes = FakeHermes()
        collector = TelegramCollector(config, storage, hermes_client=fake_hermes)

        with patch.object(collector, "_send_message", return_value=None):
            collector._answer_text_message("请总结一下这些中文资料，帮我梳理学习重点")

        self.assertEqual(len(fake_hermes.contexts), 1)
        context = fake_hermes.contexts[0]
        self.assertGreaterEqual(context.count("File:"), 8)

    def test_classifier_places_file_with_project_and_category(self) -> None:
        src_dir = Path(self.tmp.name) / "src"
        src_dir.mkdir(parents=True, exist_ok=True)
        sample = src_dir / "expense_note.txt"
        sample.write_text("invoice payment amount 320", encoding="utf-8")

        item = IngestedFile(
            source="folder",
            source_id="abc-1",
            file_name=sample.name,
            local_path=sample,
            created_at="2026-05-27T00:00:00",
            sender=str(src_dir),
            subject="entrepreneurship",
        )

        classified = self.classifier.classify_and_place(item)

        self.assertEqual(classified.project, "entrepreneurship")
        self.assertEqual(classified.category, "expense_report")
        self.assertTrue(classified.target_path.exists())
        self.assertIn("invoice", classified.extracted_text.lower())

    def test_classifier_routes_life_expense_to_dedicated_folder(self) -> None:
        src_dir = Path(self.tmp.name) / "src"
        src_dir.mkdir(parents=True, exist_ok=True)
        sample = src_dir / "uob_statement.txt"
        sample.write_text("UOB transfer Amount SGD 89.10", encoding="utf-8")

        item = IngestedFile(
            source="chat_upload",
            source_id="chat-1",
            file_name=sample.name,
            local_path=sample,
            created_at="2026-05-27T00:00:00",
            sender="dashboard_user",
            subject="monthly uob transfer",
        )

        classified = self.classifier.classify_and_place(item)
        self.assertEqual(classified.project, "life_expenses")
        self.assertEqual(classified.category, "uob_transfer")
        self.assertIn(str(Path("life_expenses") / "uob_transfer"), str(classified.target_path))

    def test_telegram_upload_exports_to_knowledge_and_boss_profile_surfaces(self) -> None:
        src_dir = Path(self.tmp.name) / "src"
        src_dir.mkdir(parents=True, exist_ok=True)

        study_file = src_dir / "week3_assignment.txt"
        study_file.write_text("Week 3 data science assignment and python learning notes", encoding="utf-8")
        study_item = IngestedFile(
            source="telegram",
            source_id="tg-study-1",
            file_name=study_file.name,
            local_path=study_file,
            created_at="2026-05-27T00:00:00",
            sender="999",
            subject="学习资料",
        )

        profile_file = src_dir / "passport_scan.txt"
        profile_file.write_text("Passport number EK1234567 visa and LTVP record", encoding="utf-8")
        profile_item = IngestedFile(
            source="telegram",
            source_id="tg-profile-1",
            file_name=profile_file.name,
            local_path=profile_file,
            created_at="2026-05-27T00:00:00",
            sender="999",
            subject="个人资料",
        )

        study_classified = self.classifier.classify_and_place(study_item)
        profile_classified = self.classifier.classify_and_place(profile_item)

        knowledge_dir = self.config.data_dir.parent / "telegram_knowledge"
        profile_dir = self.config.data_dir.parent / "personal_profiles"

        self.assertTrue(any(knowledge_dir.rglob("*.md")))
        self.assertTrue(any(profile_dir.rglob("*.md")))
        self.assertEqual(study_classified.project, "data_science")
        self.assertEqual(profile_classified.project, "boss_profile")

    def test_document_reader_agent_outputs_evidence_and_confidence(self) -> None:
        class FakeHermes:
            def answer(self, question: str, context: str, **kwargs) -> str:
                return "Summary with [C1_1] evidence"

        agent = DocumentReaderAgent(FakeHermes())
        files = [
            {
                "file_name": "report.csv",
                "local_path": str(Path(self.tmp.name) / "report.csv"),
                "project": "data_science",
                "category": "general",
                "extracted_text": "Sheet: main\nRevenue 1200\nExpense 900\nContact a@b.com",
            },
            {
                "file_name": "diagram.png",
                "local_path": str(Path(self.tmp.name) / "diagram.png"),
                "project": "data_science",
                "category": "general",
                "extracted_text": "[image_meta] format=PNG size=1024x768",
            },
        ]

        result = agent.run(
            objective="总结收入和风险并给出行动项",
            files=files,
            backend="ollama",
            ollama_base_url="http://127.0.0.1:11434",
            ollama_model="qwen2.5:7b-instruct",
            temperature=0.2,
            max_context_chars=6000,
        )

        self.assertEqual(result["file_count"], 2)
        self.assertGreaterEqual(result["text_ready_count"], 2)
        self.assertEqual(result["image_file_count"], 1)
        self.assertIn("table", result["format_breakdown"])
        self.assertIn("image", result["format_breakdown"])
        self.assertGreater(result["confidence"], 0)
        self.assertTrue(result["evidence_files"])
        self.assertIn("email", result["redaction_counts"])

    @staticmethod
    def _build_min_docx(path: Path, text: str) -> Path:
        content_types = """<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>
<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">
  <Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/>
  <Default Extension=\"xml\" ContentType=\"application/xml\"/>
  <Override PartName=\"/word/document.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml\"/>
</Types>
"""
        rels = """<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>
<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">
  <Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" Target=\"word/document.xml\"/>
</Relationships>
"""
        doc_xml = f"""<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>
<w:document xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\">
  <w:body>
    <w:p><w:r><w:t>{text}</w:t></w:r></w:p>
  </w:body>
</w:document>
"""
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("[Content_Types].xml", content_types)
            zf.writestr("_rels/.rels", rels)
            zf.writestr("word/document.xml", doc_xml)
        return path

    @staticmethod
    def _build_min_pptx(path: Path, text: str) -> Path:
        content_types = """<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>
<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">
  <Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/>
  <Default Extension=\"xml\" ContentType=\"application/xml\"/>
  <Override PartName=\"/ppt/slides/slide1.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.presentationml.slide+xml\"/>
</Types>
"""
        slide_xml = f"""<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>
<p:sld xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\" xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\">
  <p:cSld>
    <p:spTree>
      <p:sp>
        <p:txBody>
          <a:p><a:r><a:t>{text}</a:t></a:r></a:p>
        </p:txBody>
      </p:sp>
    </p:spTree>
  </p:cSld>
</p:sld>
"""
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("[Content_Types].xml", content_types)
            zf.writestr("ppt/slides/slide1.xml", slide_xml)
        return path

    @staticmethod
    def _fake_response(payload: dict):
        class _Response:
            def __init__(self, data: dict) -> None:
                self._data = data

            def json(self) -> dict:
                return self._data

            def raise_for_status(self) -> None:
                return None

        return _Response(payload)


if __name__ == "__main__":
    unittest.main()
