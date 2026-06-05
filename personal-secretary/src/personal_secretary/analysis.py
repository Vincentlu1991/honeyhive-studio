from __future__ import annotations

import os
import re
from collections import Counter, defaultdict
from datetime import date, datetime

from personal_secretary.config import SecretaryConfig
from personal_secretary.hermes_client import HermesClient
from personal_secretary.storage import SecretaryStorage


MONEY_PATTERN = re.compile(r"(?<!\d)(\d{1,3}(?:[,\s]\d{3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)(?!\d)")
INCOME_KEYWORDS = ["income", "revenue", "salary", "进账", "收入", "credited", "credit alert", "deposit"]
EXPENSE_LINE_KEYWORDS = [
    "expense", "cost", "invoice", "bill", "charge", "charged", "fee", "debit", "deducted", "payment",
    "transfer", "paid", "amount due", "water", "electric", "electricity", "internet", "broadband", "phone", "telco",
    "开销", "支出", "花费", "账单", "缴费", "扣款", "转账", "费用", "话费", "网费", "水费", "电费",
]
EXPENSE_DOC_KEYWORDS = [
    "statement", "invoice", "receipt", "bill", "payment advice", "transaction alert",
    "bank alert", "account summary", "发票", "收据", "账单", "交易提醒", "扣款通知", "缴费通知",
]
MONEY_CONTEXT_KEYWORDS = [
    "sgd", "s$", "usd", "rmb", "cny", "$", "amount", "total", "due", "paid", "payment", "transfer", "charge",
    "fee", "bill", "debit", "credit", "金额", "实付", "应付", "账单", "费用", "扣款", "转账",
]
OUTLOOK_EXPENSE_CATEGORIES = {
    "uob_transfer": ["uob", "uob bank", "uob transfer", "paynow", "fast transfer", "bank transfer", "转账"],
    "utilities": ["sp services", "utility", "utilities", "water", "electric", "electricity", "gas", "水费", "电费", "煤气费"],
    "internet": ["internet", "broadband", "wifi", "fiber", "myrepublic", "starhub broadband", "网费", "宽带"],
    "phone": ["phone bill", "mobile", "telco", "singtel", "starhub", "m1", "gomo", "电话费", "话费", "手机费"],
}
MANUAL_OVERRIDE_CATEGORIES = ["uob_transfer", "utilities", "internet", "phone", "expense_report"]
ALLOWED_EXPENSE_SOURCES = {"outlook", "chat_upload", "telegram"}
ALLOWED_EXPENSE_CATEGORIES = {
    "general",
    "expense_report",
    "uob_transfer",
    "utilities",
    "internet",
    "phone",
}
EXPENSE_CATEGORY_LABELS = {
    "uob_transfer": "UOB transfer",
    "utilities": "Utilities",
    "internet": "Internet",
    "phone": "Phone",
}
DATE_PATTERNS = [
    re.compile(r"\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b"),
    re.compile(r"\b(\d{1,2})[-/](\d{1,2})[-/](\d{4})\b"),
]



def run_analysis(config: SecretaryConfig, storage: SecretaryStorage) -> dict:
    rows = storage.all_indexed_files()
    hermes = HermesClient(config)
    summary_limit = int(os.getenv("SECRETARY_HERMES_SUMMARY_LIMIT", "0"))

    project_counter: Counter[str] = Counter()
    category_counter: Counter[str] = Counter()
    income_total = 0.0
    expense_total = 0.0
    project_money: dict[str, dict[str, float]] = defaultdict(lambda: {"income": 0.0, "expense": 0.0})
    expense_category_totals: dict[str, float] = defaultdict(float)
    qualified_outlook_expense_docs = 0
    rejected_expense_candidates: list[dict] = []

    hermes_summaries: list[dict] = []

    for row in rows:
        project = row.get("project") or "general"
        category = row.get("category") or "general"
        text = row.get("extracted_text") or ""
        name = row.get("file_name") or ""

        project_counter[project] += 1
        category_counter[category] += 1

        details = estimate_money_details(
            text=text,
            source=str(row.get("source", "")),
            subject=str(row.get("subject", "")),
            sender=str(row.get("sender", "")),
            created_at=str(row.get("created_at", "")),
            category=category,
            file_name=name,
            manual_expense_override=bool(row.get("manual_expense_override")),
            manual_expense_category=str(row.get("manual_expense_category", "")),
        )
        file_income = details["income"]
        file_expense = details["expense"]
        income_total += file_income
        expense_total += file_expense
        project_money[project]["income"] += file_income
        project_money[project]["expense"] += file_expense
        if details["qualified_outlook_expense_doc"]:
            qualified_outlook_expense_docs += 1
            if details["expense_categories"]:
                primary_category = details["expense_categories"][0]
                expense_category_totals[primary_category] += file_expense
        elif details["expense_audit"].get("expense_candidate"):
            rejected_expense_candidates.append(
                {
                    "source": str(row.get("source", "")),
                    "source_id": str(row.get("source_id", "")),
                    "file_name": name,
                    "category": category,
                    "detected_categories": details["expense_categories"],
                    "rejection_reasons": details["expense_audit"].get("rejection_reasons", []),
                }
            )

        if text.strip() and len(hermes_summaries) < summary_limit:
            try:
                summary = hermes.summarize(name, text)
            except Exception as exc:
                summary = f"[summary_error] {exc}"
            hermes_summaries.append(
                {
                    "project": project,
                    "title": name,
                    "summary": summary,
                }
            )

    project_stats = [
        {
            "project": project,
            "count": count,
            "income": round(project_money[project]["income"], 2),
            "expense": round(project_money[project]["expense"], 2),
        }
        for project, count in project_counter.most_common()
    ]
    category_stats = [{"category": cat, "count": count} for cat, count in category_counter.most_common()]

    report = {
        "total_files": len(rows),
        "analyzed_files": sum(1 for r in rows if (r.get("extracted_text") or "").strip()),
        "income_total": round(income_total, 2),
        "expense_total": round(expense_total, 2),
        "expense_policy": "Only Outlook or uploaded documents matching UOB transfer, utilities, internet, or phone bill are counted as expenses.",
        "expense_audit_policy": "Expense requires source/category match, amount evidence, and date audit (bill date or file created date with consistency check).",
        "expense_scope": {
            "qualified_outlook_docs": qualified_outlook_expense_docs,
            "category_totals": [
                {
                    "category": EXPENSE_CATEGORY_LABELS.get(cat, cat),
                    "amount": round(val, 2),
                }
                for cat, val in sorted(expense_category_totals.items(), key=lambda x: x[1], reverse=True)
            ],
            "rejected_candidates": rejected_expense_candidates,
        },
        "project_stats": project_stats,
        "category_stats": category_stats,
        "hermes_summaries": hermes_summaries,
    }
    storage.save_report(report)
    return report



def estimate_money(
    text: str,
    source: str = "",
    subject: str = "",
    sender: str = "",
    created_at: str = "",
    category: str = "",
    file_name: str = "",
) -> tuple[float, float]:
    details = estimate_money_details(
        text=text,
        source=source,
        subject=subject,
        sender=sender,
        created_at=created_at,
        category=category,
        file_name=file_name,
    )
    return details["income"], details["expense"]


def estimate_money_details(
    text: str,
    source: str = "",
    subject: str = "",
    sender: str = "",
    created_at: str = "",
    category: str = "",
    file_name: str = "",
    manual_expense_override: bool = False,
    manual_expense_category: str = "",
) -> dict:
    if not text:
        return {
            "income": 0.0,
            "expense": 0.0,
            "expense_categories": [],
            "qualified_outlook_expense_doc": False,
            "expense_audit": {},
        }

    income = 0.0
    expense = 0.0
    expense_categories = detect_outlook_expense_categories(text=text, subject=subject, sender=sender)
    if manual_expense_override:
        preferred = (manual_expense_category or category or "expense_report").strip().lower()
        if preferred in MANUAL_OVERRIDE_CATEGORIES and preferred not in expense_categories:
            expense_categories = [preferred] + expense_categories
    audit = audit_expense_document(
        text=text,
        source=source,
        subject=subject,
        sender=sender,
        created_at=created_at,
        category=category,
        file_name=file_name,
        expense_categories=expense_categories,
        manual_expense_override=manual_expense_override,
    )
    qualified_outlook_expense_doc = audit["qualified"]

    for line in text.splitlines():
        ll = line.lower()
        nums = [parse_number(m.group(1)) for m in MONEY_PATTERN.finditer(line)]
        if not nums:
            continue

        has_money_context = any(k in ll for k in MONEY_CONTEXT_KEYWORDS)
        if not has_money_context and not any(ch in line for ch in ["$", ",", "."]):
            continue

        candidates = [n for n in nums if 0.5 <= n <= 200000]
        if not candidates:
            continue
        val = max(candidates)

        if any(k in ll for k in INCOME_KEYWORDS):
            income += val
        if qualified_outlook_expense_doc and (any(k in ll for k in EXPENSE_LINE_KEYWORDS) or has_money_context):
            expense += val

    return {
        "income": income,
        "expense": expense,
        "expense_categories": expense_categories,
        "qualified_outlook_expense_doc": qualified_outlook_expense_doc,
        "expense_audit": audit,
    }


def detect_outlook_expense_categories(text: str, subject: str = "", sender: str = "") -> list[str]:
    blob = "\n".join([subject, sender, text[:8000]]).lower()
    matched: list[str] = []
    for category, keywords in OUTLOOK_EXPENSE_CATEGORIES.items():
        if any(kw in blob for kw in keywords):
            matched.append(category)
    return matched


def audit_expense_document(
    text: str,
    source: str,
    subject: str,
    sender: str,
    created_at: str,
    category: str,
    file_name: str,
    expense_categories: list[str],
    manual_expense_override: bool = False,
) -> dict:
    blob = "\n".join([file_name, subject, sender, text[:10000]]).lower()
    has_doc_keyword = any(k in blob for k in EXPENSE_DOC_KEYWORDS)
    has_expense_keyword = any(k in blob for k in EXPENSE_LINE_KEYWORDS)
    has_amount = bool(MONEY_PATTERN.search(text))
    has_money_context = any(k in blob for k in MONEY_CONTEXT_KEYWORDS)
    content_ok = has_amount and has_money_context and (has_doc_keyword or has_expense_keyword)

    created_date = parse_date_like(created_at)
    bill_dates = extract_dates(blob)
    has_date_evidence = bool(bill_dates) or created_date is not None
    date_consistent = check_date_consistency(created_date=created_date, bill_dates=bill_dates)

    source_ok = source.strip().lower() in ALLOWED_EXPENSE_SOURCES
    category_ok = bool(expense_categories)
    classifier_hint_ok = (category or "").strip().lower() in ALLOWED_EXPENSE_CATEGORIES
    expense_candidate = source_ok and (has_amount or has_doc_keyword or has_expense_keyword or category_ok)

    if manual_expense_override:
        qualified = has_amount and (has_money_context or has_doc_keyword or has_expense_keyword)
    else:
        qualified = source_ok and category_ok and classifier_hint_ok and content_ok and has_date_evidence and date_consistent

    rejection_reasons: list[str] = []
    if not source_ok:
        rejection_reasons.append("source_not_allowed")
    if not category_ok:
        rejection_reasons.append("expense_category_not_detected")
    if not classifier_hint_ok:
        rejection_reasons.append("classifier_category_not_allowed")
    if not content_ok:
        rejection_reasons.append("insufficient_amount_or_context")
    if not has_date_evidence:
        rejection_reasons.append("missing_date_evidence")
    if not date_consistent:
        rejection_reasons.append("date_mismatch")
    if manual_expense_override:
        rejection_reasons = [x for x in rejection_reasons if x not in {"source_not_allowed", "classifier_category_not_allowed", "missing_date_evidence", "date_mismatch"}]

    return {
        "qualified": qualified,
        "source_ok": source_ok,
        "category_ok": category_ok,
        "classifier_hint_ok": classifier_hint_ok,
        "manual_override": manual_expense_override,
        "expense_candidate": expense_candidate,
        "content_ok": content_ok,
        "has_amount": has_amount,
        "has_money_context": has_money_context,
        "has_doc_keyword": has_doc_keyword,
        "has_expense_keyword": has_expense_keyword,
        "has_date_evidence": has_date_evidence,
        "date_consistent": date_consistent,
        "rejection_reasons": rejection_reasons,
    }


def parse_date_like(raw: str) -> date | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text).date()
    except Exception:
        pass

    for pattern in DATE_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        try:
            g1, g2, g3 = (int(x) for x in match.groups())
            if g1 > 1900:
                return date(g1, g2, g3)
            return date(g3, g2, g1)
        except Exception:
            continue
    return None


def extract_dates(text: str) -> list[date]:
    values: list[date] = []
    for pattern in DATE_PATTERNS:
        for match in pattern.finditer(text):
            try:
                g1, g2, g3 = (int(x) for x in match.groups())
                if g1 > 1900:
                    values.append(date(g1, g2, g3))
                else:
                    values.append(date(g3, g2, g1))
            except Exception:
                continue
    return values


def check_date_consistency(created_date: date | None, bill_dates: list[date]) -> bool:
    if not bill_dates:
        return created_date is not None
    if created_date is None:
        return True

    # Invoice/statement date and ingest date should be reasonably close.
    best_gap = min(abs((created_date - d).days) for d in bill_dates)
    return best_gap <= 120



def parse_number(raw: str) -> float:
    cleaned = raw.replace(",", "").replace(" ", "")
    try:
        return float(cleaned)
    except ValueError:
        return 0.0
