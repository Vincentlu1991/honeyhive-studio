from __future__ import annotations

import hashlib
import os
import re
import shutil
import zipfile
from xml.etree import ElementTree as ET
from pathlib import Path

from pypdf import PdfReader

from personal_secretary.config import SecretaryConfig
from personal_secretary.models import ClassifiedFile, IngestedFile
from personal_secretary.storage import SecretaryStorage


PROJECT_KEYWORDS = {
    "entrepreneurship": ["adelaide", "entrepreneur", "business", "startup", "商业", "企业", "创业"],
    "data_science": ["data", "science", "python", "ml", "analytics", "数据", "分析"],
}

CATEGORY_KEYWORDS = {
    "expense_report": ["expense", "cost", "invoice", "receipt", "开销", "支出", "花费"],
    "income_report": ["income", "revenue", "salary", "payment", "收入", "进账"],
    "study_outline": ["syllabus", "outline", "lecture", "assignment", "学习", "课程", "大纲"],
    "business_plan": ["business plan", "go-to-market", "strategy", "pitch", "商业计划"],
}
LIFE_EXPENSE_CATEGORY_KEYWORDS = {
    "uob_transfer": ["uob", "uob bank", "uob transfer", "paynow", "fast transfer", "bank transfer", "转账"],
    "utilities": ["sp services", "utility", "utilities", "water", "electric", "electricity", "gas", "水费", "电费", "煤气费"],
    "internet": ["internet", "broadband", "wifi", "fiber", "myrepublic", "starhub broadband", "网费", "宽带"],
    "phone": ["phone bill", "mobile", "telco", "singtel", "starhub", "m1", "gomo", "电话费", "话费", "手机费"],
}
PERSONAL_PROFILE_KEYWORDS = [
    "passport", "护照", "nric", "身份证", "identity card", "ltvp", "visa", "签证",
    "resume", "cv", "简历", "payslip", "工资单", "cpf", "noa",
    "birth cert", "出生证明", "户口本", "marriage", "结婚证", "medical", "病历",
]
BOSS_PROFILE_PROJECT_KEYWORDS = [
    "passport", "护照", "nric", "身份证", "identity card", "ltvp", "resume", "cv", "简历",
    "payslip", "工资单", "cpf", "noa", "visa", "签证", "birth cert", "出生证明", "户口本",
    "marriage", "结婚证", "medical", "病历",
]
WORKSPACE_ROOT = Path(__file__).resolve().parents[3]


class FileClassifier:
    def __init__(self, config: SecretaryConfig, storage: SecretaryStorage) -> None:
        self.config = config
        self.storage = storage

    def classify_and_place(self, item: IngestedFile) -> ClassifiedFile:
        text = self.extract_text(item.local_path)
        project = self._detect_project(item, text)
        category = self._detect_category(item, text)

        life_expense_category = self._detect_life_expense_category(item, text)
        if life_expense_category:
            project = "life_expenses"
            category = life_expense_category

        target_dir = self.storage.organized / project / category
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = self._dedupe_path(target_dir / item.file_name)

        if self.config.copy_only:
            shutil.copy2(item.local_path, target_path)
        else:
            shutil.move(str(item.local_path), str(target_path))

        classified = ClassifiedFile(
            ingested=item,
            project=project,
            category=category,
            target_path=target_path,
            extracted_text=text,
        )
        self.storage.register_classified(classified)
        self._export_for_knowledge_surfaces(classified)
        return classified

    def _export_for_knowledge_surfaces(self, classified: ClassifiedFile) -> None:
        item = classified.ingested
        if item.source not in {"telegram", "chat_upload"}:
            return

        routes: list[tuple[str, Path]] = []
        if self._should_route_to_boss_profile(classified):
            routes.append(("boss_profile", self._boss_profile_export_dir() / classified.project / classified.category))
        if self._should_route_to_knowledge_base(classified):
            routes.append(("knowledge", self._knowledge_export_dir() / classified.project / classified.category))

        for route_name, out_dir in routes:
            out_dir.mkdir(parents=True, exist_ok=True)
            note_path = out_dir / self._note_name(item.file_name)
            note_path.write_text(self._build_note_content(classified, route_name), encoding="utf-8")

    def _workspace_aware_export_base(self) -> Path:
        data_base = self.storage.base.resolve()
        workspace_root = WORKSPACE_ROOT.resolve()
        if workspace_root == data_base or workspace_root in data_base.parents:
            return workspace_root / "output"
        return data_base.parent

    def _knowledge_export_dir(self) -> Path:
        return self._workspace_aware_export_base() / "telegram_knowledge"

    def _boss_profile_export_dir(self) -> Path:
        base = self._workspace_aware_export_base()
        if base.name == "output":
            return base / "personal_profiles" / "telegram_ingest"
        return base / "personal_profiles"

    @staticmethod
    def _note_name(file_name: str) -> str:
        stem = Path(file_name).stem
        safe = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._-]+", "_", stem).strip("._") or "telegram_upload"
        digest = hashlib.sha1(file_name.encode("utf-8", errors="ignore")).hexdigest()[:8]
        return f"{safe}_{digest}.md"

    def _build_note_content(self, classified: ClassifiedFile, route_name: str) -> str:
        item = classified.ingested
        text = classified.extracted_text[:20000]
        route_label = "知识库" if route_name == "knowledge" else "老板资料库"
        return "\n".join(
            [
                f"# Telegram Upload - {item.file_name}",
                "",
                f"- Route: {route_label}",
                f"- Source: {item.source}",
                f"- Source ID: {item.source_id}",
                f"- Chat ID: {item.sender}",
                f"- Subject: {item.subject}",
                f"- Created At: {item.created_at}",
                f"- Project: {classified.project}",
                f"- Category: {classified.category}",
                f"- Original File: {item.local_path}",
                f"- Organized Path: {classified.target_path}",
                "",
                "## Extracted Text",
                "",
                text or "[no extracted text]",
                "",
            ]
        )

    @staticmethod
    def _should_route_to_knowledge_base(classified: ClassifiedFile) -> bool:
        if classified.project in {"entrepreneurship", "data_science"}:
            return True
        return classified.category in {"study_outline", "business_plan"}

    @staticmethod
    def _should_route_to_boss_profile(classified: ClassifiedFile) -> bool:
        if classified.project == "boss_profile":
            return True
        return classified.category in {
            "identity_document",
            "personal_record",
            "expense_report",
            "income_report",
            "uob_transfer",
            "utilities",
            "internet",
            "phone",
        }

    def extract_text(self, path: Path) -> str:
        ext = path.suffix.lower()
        try:
            if ext in {".txt", ".md", ".json"}:
                return path.read_text(encoding="utf-8", errors="ignore")
            if ext == ".csv":
                return self._extract_csv_text(path)
            if ext == ".pdf":
                return self._extract_pdf_text(path)
            if ext == ".docx":
                return self._extract_docx_text(path)
            if ext == ".pptx":
                return self._extract_pptx_text(path)
            if ext in {".xlsx", ".xls"}:
                import pandas as pd

                xls = pd.ExcelFile(path)
                chunks: list[str] = []
                for sheet in xls.sheet_names[:3]:
                    df = pd.read_excel(path, sheet_name=sheet)
                    chunks.append(f"Sheet: {sheet}\n{df.head(30).to_string(index=False)}")
                return "\n\n".join(chunks)
            if ext in {".png", ".jpg", ".jpeg", ".webp"}:
                return self._extract_image_text(path)
        except Exception as exc:
            return f"[extract_error] {exc}"
        return ""

    @staticmethod
    def _extract_pdf_text(path: Path) -> str:
        reader = PdfReader(str(path))
        chunks: list[str] = []
        for idx, page in enumerate(reader.pages[:10], start=1):
            text = (page.extract_text() or "").strip()
            chunks.append(f"[page={idx}]\n{text}")
        return "\n\n".join(chunks)

    @staticmethod
    def _extract_csv_text(path: Path) -> str:
        import pandas as pd

        # Use robust fallback order for messy CSV files.
        last_err = None
        for enc in ("utf-8", "utf-8-sig", "gbk", "latin-1"):
            try:
                df = pd.read_csv(path, encoding=enc)
                break
            except Exception as exc:
                last_err = exc
        else:
            return f"[csv_extract_error] {last_err}"

        head = df.head(30).to_string(index=False)
        dtypes = ", ".join(f"{k}:{v}" for k, v in df.dtypes.to_dict().items())
        missing = int(df.isna().sum().sum())
        return (
            f"[csv_meta] rows={len(df)} cols={len(df.columns)} missing={missing}\n"
            f"[csv_dtypes] {dtypes}\n"
            f"[csv_head]\n{head}"
        )

    @staticmethod
    def _extract_image_text(path: Path) -> str:
        # Keep image ingestion useful even when OCR runtime is unavailable.
        from PIL import Image

        with Image.open(path) as img:
            header = f"[image_meta] format={img.format} size={img.width}x{img.height} mode={img.mode}"

        try:
            import pytesseract  # type: ignore

            tesseract_cmd = os.getenv("TESSERACT_CMD", "").strip()
            if tesseract_cmd:
                pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

            with Image.open(path) as img:
                text = pytesseract.image_to_string(img)
            text = (text or "").strip()
            if text:
                return f"{header}\n[image_ocr]\n{text[:10000]}"
            return header
        except Exception:
            return header

    @staticmethod
    def _extract_docx_text(path: Path) -> str:
        with zipfile.ZipFile(path) as zf:
            try:
                xml = zf.read("word/document.xml")
            except KeyError:
                return ""
        root = ET.fromstring(xml)
        parts: list[str] = []
        for node in root.iter():
            if node.tag.endswith("}t") and node.text:
                parts.append(node.text)
        return "\n".join(parts)

    @staticmethod
    def _extract_pptx_text(path: Path) -> str:
        with zipfile.ZipFile(path) as zf:
            slide_names = sorted(
                [n for n in zf.namelist() if n.startswith("ppt/slides/slide") and n.endswith(".xml")]
            )
            texts: list[str] = []
            for slide_name in slide_names[:8]:
                xml = zf.read(slide_name)
                root = ET.fromstring(xml)
                for node in root.iter():
                    if node.tag.endswith("}t") and node.text:
                        texts.append(node.text)
        return "\n".join(texts)

    def _detect_project(self, item: IngestedFile, text: str) -> str:
        lower = " ".join([item.file_name, item.subject, item.sender, text[:2000]]).lower()

        if any(kw in lower for kw in BOSS_PROFILE_PROJECT_KEYWORDS):
            return "boss_profile"

        for source in self.config.source_folders:
            if source.project and source.project.lower() in lower:
                return source.project

        if "adelaide" in lower:
            return "entrepreneurship"
        if "数据" in lower or "data" in lower:
            return "data_science"

        best_project = "general"
        best_score = 0
        for project, kws in PROJECT_KEYWORDS.items():
            score = sum(1 for kw in kws if kw in lower)
            if score > best_score:
                best_score = score
                best_project = project
        return best_project

    def _detect_category(self, item: IngestedFile, text: str) -> str:
        lower = " ".join([item.file_name, item.subject, text[:3000]]).lower()
        if any(kw in lower for kw in ["passport", "护照", "身份证", "nric", "ltvp", "签证", "visa"]):
            return "identity_document"
        if any(kw in lower for kw in ["resume", "cv", "简历", "payslip", "工资单", "cpf", "noa", "medical", "出生证明", "户口本", "结婚证"]):
            return "personal_record"
        best_cat = "general"
        best_score = 0
        for cat, kws in CATEGORY_KEYWORDS.items():
            score = sum(1 for kw in kws if kw in lower)
            if score > best_score:
                best_score = score
                best_cat = cat

        if best_cat == "general":
            if re.search(r"\b(week\s*\d+|lecture|lesson)\b", lower):
                return "study_outline"
        return best_cat

    def _detect_life_expense_category(self, item: IngestedFile, text: str) -> str:
        lower = " ".join([item.file_name, item.subject, item.sender, text[:5000]]).lower()
        best_category = ""
        best_score = 0
        for category, keywords in LIFE_EXPENSE_CATEGORY_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in lower)
            if score > best_score:
                best_score = score
                best_category = category
        return best_category

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
