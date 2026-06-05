from __future__ import annotations

from datetime import datetime
import os
import re
import subprocess
from pathlib import Path

import requests

from personal_secretary.agent_orchestrator import MultiAgentOrchestrator
from personal_secretary.config import SecretaryConfig
from personal_secretary.hermes_client import HermesClient
from personal_secretary.models import IngestedFile
from personal_secretary.storage import SecretaryStorage


PROJECT_ROOT = Path(__file__).resolve().parents[4]
BOSS_PROFILE_PATH = PROJECT_ROOT / "output" / "personal_profiles" / "boss_profile.md"
KNOWLEDGE_FACTS_DIR = PROJECT_ROOT / "output" / "telegram_knowledge" / "facts"
KNOWLEDGE_REBUILD_SCRIPT = PROJECT_ROOT / "scripts" / "build-knowledge-index.ps1"


class TelegramCollector:
    def __init__(
        self,
        config: SecretaryConfig,
        storage: SecretaryStorage,
        hermes_client: HermesClient | None = None,
    ) -> None:
        self.config = config
        self.storage = storage
        self.hermes = hermes_client or HermesClient(config)

    def collect(self) -> list[IngestedFile]:
        if not self.config.telegram_enabled or not self.config.telegram_bot_token:
            return []

        state = self.storage.load_state()
        offset = int(state.get("telegram_offset", 0))

        base = f"https://api.telegram.org/bot{self.config.telegram_bot_token}"
        try:
            resp = requests.get(
                f"{base}/getUpdates",
                params={"offset": offset + 1, "timeout": 15},
                timeout=30,
            )
            resp.raise_for_status()
        except requests.HTTPError as exc:
            response = getattr(exc, "response", None)
            if response is not None and getattr(response, "status_code", None) == 409:
                return []
            raise
        except requests.RequestException:
            return []

        payload = resp.json()
        if not payload.get("ok"):
            return []

        items: list[IngestedFile] = []
        max_update = offset

        for update in payload.get("result", []):
            update_id = update.get("update_id", 0)
            max_update = max(max_update, update_id)

            message = update.get("message") or update.get("channel_post") or {}
            chat_id = str((message.get("chat") or {}).get("id", ""))
            if self.config.telegram_allowed_chat_id and chat_id != self.config.telegram_allowed_chat_id:
                continue

            text = str(message.get("text") or message.get("caption") or "").strip()
            if text:
                reply = self._answer_text_message(text=text, chat_id=chat_id)
                self._send_message(chat_id=chat_id, text=reply, reply_to_message_id=message.get("message_id"))
                self.storage.save_chat_message(role="telegram_user", content=text, attachments=[])
                self.storage.save_chat_message(role="telegram_assistant", content=reply, attachments=[])

            doc = message.get("document")
            if not doc:
                continue

            file_id = doc.get("file_id")
            file_name = doc.get("file_name") or f"telegram_{file_id}"
            source_id = str(file_id)

            if self.storage.has_source_item("telegram", source_id):
                continue

            file_meta = requests.get(f"{base}/getFile", params={"file_id": file_id}, timeout=30)
            file_meta.raise_for_status()
            file_result = file_meta.json().get("result", {})
            file_path = file_result.get("file_path", "")
            if not file_path:
                continue

            dl = requests.get(
                f"https://api.telegram.org/file/bot{self.config.telegram_bot_token}/{file_path}",
                timeout=60,
            )
            dl.raise_for_status()

            target_dir = self.storage.inbox / "telegram"
            target_dir.mkdir(parents=True, exist_ok=True)
            local_path = self._dedupe_path(target_dir / file_name)
            local_path.write_bytes(dl.content)

            item = IngestedFile(
                source="telegram",
                source_id=source_id,
                file_name=file_name,
                local_path=local_path,
                created_at=datetime.utcnow().isoformat(),
                sender=chat_id,
                subject=message.get("caption", ""),
            )
            self.storage.register_ingested(item)
            items.append(item)

        state["telegram_offset"] = max_update
        self.storage.save_state(state)
        return items

    def _answer_text_message(self, text: str, chat_id: str = "") -> str:
        command = (text or "").strip().lower()
        if command in {"/start", "start", "/help", "help"}:
            return (
                "我是你的项目主管 Bot。你可以直接问我项目、学习资料、签证材料、家庭档案或执行计划。\n\n"
                "我会先调度主管/子代理做检索、精读、学习提炼、计划汇总，再给你结论。"
            )

        # Clarification loop: if a previous turn requested missing details, combine and continue.
        pending = self._get_pending_clarification(chat_id)
        from_pending = False
        if pending:
            original_q = str(pending.get("question", "")).strip()
            merged_text = f"原问题：{original_q}\n用户补充：{text}".strip()
            self._clear_pending_clarification(chat_id)
            text = merged_text
            from_pending = True

        if not from_pending:
            clarification = self._analyze_clarification_need(text)
            if clarification.get("need"):
                questions = [str(q).strip() for q in clarification.get("questions", []) if str(q).strip()]
                if questions:
                    self._set_pending_clarification(chat_id, question=text, questions=questions)
                    return self._format_clarification_prompt(questions)

        if self._is_marriage_query(text):
            marriage_reply = self._answer_marriage_query(text)
            if marriage_reply:
                return marriage_reply
            return (
                "我已优先检查结婚证与档案，但暂时没能提取到结婚日期。\n"
                "请发一张更清晰的结婚证正页（含 Date of Marriage/ROM）给我，我会自动识图并回填知识库。"
            )

        if self._is_personal_profile_query(text):
            profile_reply = self._answer_from_boss_profile_file(text)
            if profile_reply:
                return profile_reply

        supervisor_reply = self._answer_as_supervisor(text)
        if supervisor_reply:
            return supervisor_reply

        return self._answer_from_indexed_context(text)

    def _answer_as_supervisor(self, text: str) -> str:
        if not hasattr(self.hermes, "summarize"):
            return ""

        rows = self.storage.all_indexed_files()
        if not rows:
            return "当前还没有可用的已入库资料。请先运行同步或发送文件后再问我。"

        try:
            orchestrator = MultiAgentOrchestrator(self.config, self.storage, self.hermes)
            payload = orchestrator.run(
                objective=text,
                backend="auto",
                ollama_base_url="http://127.0.0.1:11434",
                ollama_model="qwen2.5:7b-instruct",
                temperature=0.2,
                max_context_chars=12000,
                max_files=6,
                agent_params={
                    "retriever_max_files": 6,
                    "learning_weeks": 4,
                    "learning_topic_limit": 6,
                    "business_plan_style": "concise",
                    "qa_require_business_plan": False,
                },
            )
        except Exception:
            return ""

        report = payload.get("report") or {}
        qa = payload.get("qa") or {}
        reader = report.get("reader") or {}
        learning = report.get("learning") or {}
        finance = report.get("finance") or {}

        parts: list[str] = ["项目主管答复"]

        reader_summary = str(reader.get("summary") or "").strip()
        if reader_summary:
            parts.append(reader_summary[:1200])

        top_projects = [str(x) for x in (report.get("top_projects") or [])[:3] if str(x).strip()]
        if top_projects:
            parts.append("涉及项目：" + "、".join(top_projects))

        retrieved_files = [str(x) for x in (report.get("retrieved_files") or [])[:4] if str(x).strip()]
        if retrieved_files:
            parts.append("参考材料：" + "；".join(retrieved_files))

        topics = [str(x) for x in (learning.get("topics") or [])[:4] if str(x).strip()]
        if topics:
            parts.append("学习重点：" + "、".join(topics))

        if finance:
            parts.append(
                "财务概览：收入 {income}，支出 {expense}，净额 {net}".format(
                    income=finance.get("income_total", 0),
                    expense=finance.get("expense_total", 0),
                    net=finance.get("net", 0),
                )
            )

        actions = [str(x) for x in (report.get("action_items") or [])[:3] if str(x).strip()]
        if actions:
            parts.append("下一步：" + "；".join(actions))

        if qa:
            qa_label = "通过" if qa.get("passed") else "需复核"
            missing = [str(x) for x in (qa.get("missing") or [])[:3] if str(x).strip()]
            qa_text = f"QA：{qa_label}"
            if missing:
                qa_text += "；缺失：" + "、".join(missing)
            parts.append(qa_text)

        return "\n\n".join(part for part in parts if part).strip()

    def _answer_from_indexed_context(self, text: str) -> str:
        rows = self.storage.all_indexed_files()
        profile = self._build_query_profile(text)
        words = profile["tokens"]
        scored: list[tuple[int, dict]] = []
        for row in rows:
            score = self._score_row(row, profile)
            if score > 0:
                scored.append((score, row))

        scored.sort(key=lambda x: x[0], reverse=True)
        selected = [row for _, row in scored[:8]]
        if not selected:
            selected = self._recent_rows_by_project_hint(rows, words, limit=8) or rows[:8]

        selected = self._dedupe_rows(selected)
        chunks: list[str] = []
        for row in selected:
            chunks.append(
                "\n".join(
                    [
                        f"File: {row.get('file_name', '')}",
                        f"Project: {row.get('project', 'general')}",
                        f"Category: {row.get('category', 'general')}",
                        f"Text: {str(row.get('extracted_text', ''))[:1000]}",
                    ]
                )
            )

        context = "\n\n---\n\n".join(chunks)[:12000]
        if not context.strip():
            context = "No indexed files available yet."

        return self.hermes.answer(text, context, backend="auto", timeout_seconds=120)

    @staticmethod
    def _is_personal_profile_query(text: str) -> bool:
        lower = (text or "").lower()
        personal_keywords = [
            "身份证", "护照", "nric", "ltvp", "pr", "签证", "出生", "住址", "电话", "邮箱", "工资单",
            "我妈", "妈妈", "母亲", "我爸", "父亲", "我老婆", "太太", "配偶", "岳母", "我本人",
        ]
        return any(k in lower for k in personal_keywords)

    @staticmethod
    def _is_marriage_query(text: str) -> bool:
        lower = (text or "").lower()
        marriage_keywords = [
            "什么时候结婚",
            "结婚日期",
            "结婚证",
            "婚期",
            "rom",
            "marriage date",
            "date of marriage",
            "结婚",
        ]
        return any(k in lower for k in marriage_keywords)

    def _answer_marriage_query(self, text: str) -> str:
        profile_content = BOSS_PROFILE_PATH.read_text(encoding="utf-8", errors="ignore") if BOSS_PROFILE_PATH.exists() else ""
        existing_date = self._extract_table_field(profile_content, ["结婚日期", "Date of Marriage", "ROM 日期"])
        if existing_date:
            return (
                f"你和配偶的结婚日期是：{existing_date}\n\n"
                f"来源：{BOSS_PROFILE_PATH}"
            )

        cert_paths = self._extract_marriage_cert_paths(profile_content)
        cert_paths.extend(self._discover_marriage_cert_candidates())
        # dedupe preserving order
        unique_paths: list[Path] = []
        seen: set[str] = set()
        for p in cert_paths:
            key = str(p)
            if key in seen:
                continue
            seen.add(key)
            unique_paths.append(p)

        cert_paths = unique_paths
        for cert_path in cert_paths:
            if not cert_path.exists():
                continue
            text_blob = self._extract_text_from_file(cert_path)
            marriage_date = self._extract_marriage_date(text_blob)
            if not marriage_date:
                marriage_date = self._extract_marriage_date_from_filename(cert_path.name)
            if not marriage_date:
                continue

            self._record_marriage_fact(marriage_date, cert_path)
            self._rebuild_knowledge_index()
            return (
                f"你和配偶的结婚日期是：{marriage_date}\n\n"
                f"证据来源：{cert_path}\n"
                f"已记录到：{KNOWLEDGE_FACTS_DIR / 'marriage_facts.md'}"
            )

        return ""

    @staticmethod
    def _extract_marriage_cert_paths(profile_content: str) -> list[Path]:
        paths: list[Path] = []
        # markdown table row: | 结婚证 | E:\Dropbox\结婚\PR\MarriageCert.jpeg |
        for match in re.finditer(r"\|\s*结婚证\s*\|\s*([^|\n]+)\|", profile_content):
            raw = match.group(1).strip()
            if raw:
                paths.append(Path(raw))
        # fallback: any direct mention of MarriageCert
        for match in re.finditer(r"([A-Za-z]:\\[^\n|]*MarriageCert[^\n|]*)", profile_content):
            raw = match.group(1).strip()
            if raw:
                paths.append(Path(raw))
        # dedupe preserving order
        seen: set[str] = set()
        result: list[Path] = []
        for p in paths:
            key = str(p)
            if key in seen:
                continue
            seen.add(key)
            result.append(p)
        return result

    @staticmethod
    def _extract_text_from_file(path: Path) -> str:
        ext = path.suffix.lower()
        try:
            if ext in {".txt", ".md", ".csv", ".json"}:
                return path.read_text(encoding="utf-8", errors="ignore")

            if ext in {".jpg", ".jpeg", ".png", ".webp"}:
                from PIL import Image  # type: ignore
                import pytesseract  # type: ignore

                tesseract_cmd = os.getenv("TESSERACT_CMD", "").strip()
                if tesseract_cmd:
                    pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
                with Image.open(path) as img:
                    return pytesseract.image_to_string(img) or ""

            if ext == ".pdf":
                from pypdf import PdfReader  # type: ignore

                reader = PdfReader(str(path))
                texts: list[str] = []
                for page in reader.pages[:5]:
                    texts.append(page.extract_text() or "")
                return "\n".join(texts)
        except Exception:
            return ""
        return ""

    @staticmethod
    def _discover_marriage_cert_candidates() -> list[Path]:
        candidates: list[Path] = []
        search_roots = [
            PROJECT_ROOT / "personal-secretary" / "data" / "inbox",
            PROJECT_ROOT / "personal-secretary" / "data" / "organized",
            Path(r"E:\Dropbox\结婚"),
        ]
        patterns = [
            "**/*Marriage*.*",
            "**/*marriage*.*",
            "**/*ROM*.*",
            "**/*结婚证*.*",
            "**/*MarriageCertificate*.*",
        ]
        allowed_ext = {".jpg", ".jpeg", ".png", ".webp", ".pdf"}

        for root in search_roots:
            if not root.exists():
                continue
            for pattern in patterns:
                for p in root.glob(pattern):
                    if p.is_file() and p.suffix.lower() in allowed_ext:
                        candidates.append(p)
        return candidates

    @staticmethod
    def _extract_marriage_date_from_filename(file_name: str) -> str:
        name = file_name or ""
        # e.g. 01_MarriageCertificate_20220418.jpeg
        m = re.search(r"(20\d{2})(\d{2})(\d{2})", name)
        if m:
            y, mo, d = m.group(1), m.group(2), m.group(3)
            return f"{y}-{mo}-{d}"
        m = re.search(r"(\d{4})[-_](\d{1,2})[-_](\d{1,2})", name)
        if m:
            y, mo, d = m.group(1), int(m.group(2)), int(m.group(3))
            return f"{y}-{mo:02d}-{d:02d}"
        return ""

    @staticmethod
    def _extract_marriage_date(text: str) -> str:
        if not text:
            return ""
        normalized = text.replace("\r", "\n")
        lines = [ln.strip() for ln in normalized.split("\n") if ln.strip()]

        date_patterns = [
            r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b",
            r"\b(\d{4}[/-]\d{1,2}[/-]\d{1,2})\b",
            r"\b(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})\b",
        ]
        date_union = r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})"

        def _normalize_date(raw: str) -> str:
            s = (raw or "").strip()
            if not s:
                return ""

            m = re.match(r"^(\d{4})[/-](\d{1,2})[/-](\d{1,2})$", s)
            if m:
                y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                return f"{y}/{mo}/{d}"

            m = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})$", s)
            if m:
                d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if y < 100:
                    y += 2000
                return f"{y}/{mo}/{d}"

            m = re.match(r"^(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{4})$", s)
            if m:
                d = int(m.group(1))
                mon = m.group(2).lower()
                y = int(m.group(3))
                month_map = {
                    "jan": 1,
                    "january": 1,
                    "feb": 2,
                    "february": 2,
                    "mar": 3,
                    "march": 3,
                    "apr": 4,
                    "april": 4,
                    "may": 5,
                    "jun": 6,
                    "june": 6,
                    "jul": 7,
                    "july": 7,
                    "aug": 8,
                    "august": 8,
                    "sep": 9,
                    "sept": 9,
                    "september": 9,
                    "oct": 10,
                    "october": 10,
                    "nov": 11,
                    "november": 11,
                    "dec": 12,
                    "december": 12,
                }
                mo = month_map.get(mon)
                if mo:
                    return f"{y}/{mo}/{d}"
            return s

        # Highest-priority marriage keywords first.
        strong_keywords = [
            "solemnization details",
            "solemnization date",
            "date of marriage",
            "marriage date",
            "结婚日期",
        ]
        weak_keywords = ["marriage", "rom", "结婚"]
        noise_keywords = [
            "printed on",
            "application no",
            "class schedule",
            "appointment at rom",
            "submitted",
            "application",
        ]

        def _find_date_in_line(line: str) -> str:
            for pat in date_patterns:
                m = re.search(pat, line, flags=re.IGNORECASE)
                if m:
                    return _normalize_date(m.group(1).strip())
            return ""

        # Section-anchored extraction: prioritize marriage-ceremony date fields.
        priority_patterns = [
            rf"solemnization\s*details\s*[:\-]?\s*{date_union}",
            rf"solemnization\s*details[\s\S]{{0,120}}?{date_union}",
            rf"date\s*of\s*marriage\s*[:\-]?\s*{date_union}",
            rf"marriage\s*date\s*[:\-]?\s*{date_union}",
            rf"结婚日期\s*[:：]?\s*{date_union}",
        ]
        for pat in priority_patterns:
            m = re.search(pat, normalized, flags=re.IGNORECASE)
            if m:
                return _normalize_date(m.group(1).strip())

        for idx, line in enumerate(lines):
            ll = line.lower()
            if any(k in ll for k in strong_keywords):
                date_text = _find_date_in_line(line)
                if date_text:
                    return date_text
                # Sometimes the date appears on the next one or two lines.
                for nxt in lines[idx + 1 : idx + 5]:
                    date_text = _find_date_in_line(nxt)
                    if date_text:
                        return date_text

        keyword_blob = " ".join(lines).lower()
        if any(k in keyword_blob for k in (strong_keywords + weak_keywords)):
            for line in lines:
                ll = line.lower()
                if any(k in ll for k in noise_keywords):
                    continue
                if any(k in ll for k in weak_keywords):
                    date_text = _find_date_in_line(line)
                    if date_text:
                        return date_text

        return ""

    @staticmethod
    def _record_marriage_fact(marriage_date: str, source_path: Path) -> None:
        KNOWLEDGE_FACTS_DIR.mkdir(parents=True, exist_ok=True)
        fact_path = KNOWLEDGE_FACTS_DIR / "marriage_facts.md"
        now_text = datetime.utcnow().isoformat()
        content = "\n".join(
            [
                "# Marriage Facts",
                "",
                f"- Fact: Lu Weixiong 与配偶结婚日期 = {marriage_date}",
                f"- Source: {source_path}",
                "- Evidence Type: marriage certificate OCR/text extraction",
                f"- Updated At (UTC): {now_text}",
                "",
            ]
        )
        fact_path.write_text(content, encoding="utf-8")

    @staticmethod
    def _rebuild_knowledge_index() -> bool:
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
                    str(PROJECT_ROOT),
                ],
                capture_output=True,
                text=True,
                errors="ignore",
                timeout=300,
                check=False,
            )
            return True
        except Exception:
            return False

    def _answer_from_boss_profile_file(self, text: str) -> str:
        if not BOSS_PROFILE_PATH.exists():
            return ""

        content = BOSS_PROFILE_PATH.read_text(encoding="utf-8", errors="ignore")
        target_person = self._detect_person_label(text)
        section = self._extract_person_section(content, target_person)
        if not section:
            return ""

        lower = (text or "").lower()
        if "身份证" in lower:
            value = self._extract_table_field(section, ["中国身份证号", "身份证号", "身份证"])
            if value:
                return (
                    f"{target_person}的身份证号是：{value}\n\n"
                    f"来源：{BOSS_PROFILE_PATH}"
                )
        if "护照" in lower:
            value = self._extract_table_field(section, ["护照号", "passport", "护照"])
            if value:
                return (
                    f"{target_person}的护照号是：{value}\n\n"
                    f"来源：{BOSS_PROFILE_PATH}"
                )
        if "nric" in lower or "新加坡ic" in lower or "ic号" in lower:
            value = self._extract_table_field(section, ["新加坡 NRIC", "NRIC"])
            if value:
                return (
                    f"{target_person}的 NRIC 是：{value}\n\n"
                    f"来源：{BOSS_PROFILE_PATH}"
                )

        summary_fields = [
            ("中文姓名", self._extract_table_field(section, ["中文姓名", "姓名"])),
            ("英文姓名", self._extract_table_field(section, ["英文姓名", "英文全名"])),
            ("身份证号", self._extract_table_field(section, ["中国身份证号", "身份证号"])),
            ("护照号", self._extract_table_field(section, ["护照号"])),
            ("出生日期", self._extract_table_field(section, ["出生日期"])),
        ]
        parts = [f"{target_person}信息如下："]
        for label, value in summary_fields:
            if value:
                parts.append(f"- {label}：{value}")

        if len(parts) == 1:
            return ""
        parts.append("")
        parts.append(f"来源：{BOSS_PROFILE_PATH}")
        return "\n".join(parts)

    @staticmethod
    def _detect_person_label(text: str) -> str:
        lower = (text or "").lower()
        mapping = [
            (["我妈", "妈妈", "母亲", "张玉玲"], "妈妈（母亲）"),
            (["我爸", "爸爸", "父亲", "卢瑛"], "父亲"),
            (["我老婆", "太太", "妻子", "配偶", "张蓓琦", "beiqi"], "配偶"),
            (["岳母", "丈母娘", "伍红英"], "岳母"),
            (["我", "本人", "lu weixiong", "卢卫雄"], "本人"),
        ]
        for keys, label in mapping:
            if any(k in lower for k in keys):
                return label
        return "本人"

    @staticmethod
    def _extract_person_section(content: str, person_label: str) -> str:
        heading_map = {
            "妈妈（母亲）": r"##\s*妈妈（母亲）信息",
            "父亲": r"##\s*父亲信息",
            "配偶": r"##\s*配偶信息",
            "岳母": r"##\s*岳母信息",
            "本人": r"##\s*本人信息",
        }
        pattern = heading_map.get(person_label)
        if not pattern:
            return ""
        match = re.search(pattern, content)
        if not match:
            return ""
        start = match.start()
        tail = content[start:]
        stop = re.search(r"\n---\n|\n##\s+", tail[3:])
        if not stop:
            return tail
        return tail[: stop.start() + 3]

    @staticmethod
    def _extract_table_field(section: str, field_names: list[str]) -> str:
        for name in field_names:
            pattern = rf"\|\s*{re.escape(name)}\s*\|\s*([^|\n]+)\|"
            match = re.search(pattern, section, flags=re.IGNORECASE)
            if match:
                return match.group(1).strip().strip("*")
        return ""

    def _build_query_profile(self, text: str) -> dict[str, list[str] | str]:
        tokens = self._tokenize_query(text)
        lower = (text or "").lower()
        project_hints: list[str] = []
        category_hints: list[str] = []

        if any(k in lower for k in ["数据", "python", "machine learning", "ml", "assignment", "课程", "学习"]):
            project_hints.append("data_science")
            category_hints.append("study_outline")
        if any(k in lower for k in ["创业", "business", "startup", "adelaide", "innovation", "enterprise"]):
            project_hints.append("entrepreneurship")
            category_hints.extend(["study_outline", "business_plan"])
        if any(k in lower for k in ["护照", "身份证", "签证", "ltvp", "pr", "简历", "工资单", "账单", "cpf", "noa"]):
            project_hints.extend(["boss_profile", "life_expenses"])
            category_hints.extend(["identity_document", "personal_record", "expense_report", "income_report"])

        return {
            "raw": text,
            "tokens": tokens,
            "project_hints": project_hints,
            "category_hints": category_hints,
        }

    def _score_row(self, row: dict, profile: dict[str, list[str] | str]) -> int:
        tokens = [str(x) for x in profile.get("tokens", [])]
        file_name = str(row.get("file_name", "")).lower()
        project = str(row.get("project", "")).lower()
        category = str(row.get("category", "")).lower()
        subject = str(row.get("subject", "")).lower()
        sender = str(row.get("sender", "")).lower()
        text = str(row.get("extracted_text", ""))[:2500].lower()

        score = 0
        for token in tokens:
            if token in file_name:
                score += 6
            if token in subject:
                score += 5
            if token in project:
                score += 4
            if token in category:
                score += 4
            if token in sender:
                score += 2
            if token in text:
                score += 1

        for hint in [str(x).lower() for x in profile.get("project_hints", [])]:
            if hint and hint == project:
                score += 10
        for hint in [str(x).lower() for x in profile.get("category_hints", [])]:
            if hint and hint == category:
                score += 8
        return score

    @staticmethod
    def _tokenize_query(text: str) -> list[str]:
        raw = (text or "").lower()
        tokens = set()
        for token in re.findall(r"[a-z0-9_]{2,}|[\u4e00-\u9fff]{2,}", raw):
            token = token.strip()
            if not token:
                continue
            tokens.add(token)
            if re.fullmatch(r"[\u4e00-\u9fff]{2,}", token):
                for idx in range(len(token) - 1):
                    tokens.add(token[idx : idx + 2])
        return sorted(tokens, key=len, reverse=True)

    @staticmethod
    def _row_blob(row: dict) -> str:
        return " ".join(
            [
                str(row.get("file_name", "")),
                str(row.get("project", "")),
                str(row.get("category", "")),
                str(row.get("subject", "")),
                str(row.get("sender", "")),
                str(row.get("extracted_text", ""))[:2000],
            ]
        ).lower()

    @staticmethod
    def _dedupe_rows(rows: list[dict]) -> list[dict]:
        seen: set[tuple[str, str]] = set()
        result: list[dict] = []
        for row in rows:
            key = (str(row.get("source", "")), str(row.get("source_id", "")))
            if key in seen:
                continue
            seen.add(key)
            result.append(row)
        return result

    @staticmethod
    def _recent_rows_by_project_hint(rows: list[dict], tokens: list[str], limit: int = 8) -> list[dict]:
        text = " ".join(tokens)
        project_hints = []
        if any(k in text for k in ["data_science", "数据", "data", "science", "学习"]):
            project_hints.append("data_science")
        if any(k in text for k in ["entrepreneurship", "创业", "business", "商业", "startup"]):
            project_hints.append("entrepreneurship")
        if any(k in text for k in ["expense", "开销", "支出", "bill", "账单", "uob", "utilities", "internet", "phone"]):
            project_hints.extend(["general", "life_expenses"])

        hinted = [row for row in rows if str(row.get("project", "")) in project_hints]
        return hinted[:limit]

    def _send_message(self, chat_id: str, text: str, reply_to_message_id: int | None = None) -> None:
        if not chat_id or not text:
            return

        base = f"https://api.telegram.org/bot{self.config.telegram_bot_token}"
        payload: dict[str, object] = {
            "chat_id": chat_id,
            "text": text[:3900],
        }
        if reply_to_message_id is not None:
            payload["reply_to_message_id"] = reply_to_message_id

        try:
            requests.post(f"{base}/sendMessage", json=payload, timeout=30).raise_for_status()
        except Exception:
            return

    def _analyze_clarification_need(self, text: str) -> dict[str, object]:
        raw = (text or "").strip()
        lower = raw.lower()
        if not raw:
            return {"need": False}

        # Do not interrupt explicit commands.
        if lower.startswith("/"):
            return {"need": False}

        factual_keywords = [
            "什么时候", "日期", "几号", "多少", "金额", "费用", "身份证", "护照", "地址", "电话", "邮箱",
            "到期", "有效期", "签证", "合同", "婚", "birth", "date", "expiry", "amount", "id", "passport",
        ]
        is_factual = any(k in lower for k in factual_keywords)

        if not is_factual:
            return {"need": False}

        rows = self.storage.all_indexed_files()
        profile = self._build_query_profile(raw)
        scored: list[tuple[int, dict]] = []
        for row in rows:
            score = self._score_row(row, profile)
            if score > 0:
                scored.append((score, row))
        scored.sort(key=lambda x: x[0], reverse=True)

        top1 = scored[0][0] if scored else 0
        top2 = scored[1][0] if len(scored) > 1 else 0

        need = False
        questions: list[str] = []

        # Low confidence: not enough evidence matched.
        if top1 < 6:
            need = True
            questions.append("你要我查哪一类资料？例如：护照/身份证/签证/账单/婚姻文件。")

        # Ambiguous scope: multiple similarly relevant documents.
        if top1 > 0 and top2 > 0 and abs(top1 - top2) <= 2:
            need = True
            questions.append("你要优先以哪个来源为准？例如：官方证件原件、政府回执、还是我已入库档案。")

        # Time/date questions often need person and exact target field.
        if any(k in lower for k in ["什么时候", "日期", "date", "几号"]):
            if not any(k in lower for k in ["我", "本人", "配偶", "老婆", "妈妈", "父亲", "岳母"]):
                need = True
                questions.append("这条信息是查谁的？例如：本人/配偶/妈妈/父亲。")

        # Keep to 2 concise questions to reduce friction.
        questions = questions[:2]
        return {"need": need and bool(questions), "questions": questions}

    @staticmethod
    def _format_clarification_prompt(questions: list[str]) -> str:
        lines = ["为保证答案准确，我先确认两点："]
        for idx, q in enumerate(questions, start=1):
            lines.append(f"{idx}. {q}")
        lines.append("请直接回复这两点，我收到后会给你最终答案和证据来源。")
        return "\n".join(lines)

    def _get_pending_clarification(self, chat_id: str) -> dict[str, object] | None:
        if not chat_id:
            return None
        state = self.storage.load_state()
        pending_all = state.get("telegram_pending_clarifications", {})
        if not isinstance(pending_all, dict):
            return None
        pending = pending_all.get(chat_id)
        return pending if isinstance(pending, dict) else None

    def _set_pending_clarification(self, chat_id: str, question: str, questions: list[str]) -> None:
        if not chat_id:
            return
        state = self.storage.load_state()
        pending_all = state.get("telegram_pending_clarifications", {})
        if not isinstance(pending_all, dict):
            pending_all = {}
        pending_all[chat_id] = {
            "question": question,
            "questions": questions,
            "created_at": datetime.utcnow().isoformat(),
        }
        state["telegram_pending_clarifications"] = pending_all
        self.storage.save_state(state)

    def _clear_pending_clarification(self, chat_id: str) -> None:
        if not chat_id:
            return
        state = self.storage.load_state()
        pending_all = state.get("telegram_pending_clarifications", {})
        if not isinstance(pending_all, dict):
            return
        if chat_id in pending_all:
            pending_all.pop(chat_id, None)
            state["telegram_pending_clarifications"] = pending_all
            self.storage.save_state(state)

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
