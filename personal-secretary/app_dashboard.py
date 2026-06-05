from __future__ import annotations

import hashlib
import os
from datetime import datetime
from pathlib import Path

from personal_secretary.analysis import MANUAL_OVERRIDE_CATEGORIES, run_analysis
from personal_secretary.agent_orchestrator import MultiAgentOrchestrator
from personal_secretary.classifiers import FileClassifier
from personal_secretary.collectors.fs_collector import FolderCollector
from personal_secretary.collectors.outlook_collector import OutlookCollector
from personal_secretary.config import load_config
from personal_secretary.hermes_client import HermesClient
from personal_secretary.models import IngestedFile
from personal_secretary.pipeline import run_sync
from personal_secretary.storage import SecretaryStorage

import pandas as pd
import streamlit as st


st.set_page_config(page_title="Personal Secretary Dashboard", layout="wide")
st.title("Personal Secretary Console")

config = load_config()
storage = SecretaryStorage(config)
classifier = FileClassifier(config, storage)
folder_collector = FolderCollector(config, storage)
outlook_collector = OutlookCollector(config, storage)
hermes = HermesClient(config)
orchestrator = MultiAgentOrchestrator(config, storage, hermes)

DEFAULT_LOCAL_MODELS = [
    "qwen2.5:7b-instruct",
    "qwen2.5:14b-instruct",
    "llama3.1:8b",
    "deepseek-r1:7b",
]

MODEL_PROFILES = {
    "General chat / summary": {
        "model": "qwen2.5:7b-instruct",
        "precision": "Balanced",
        "reason": "Fast and stable for daily secretary chat and summaries.",
    },
    "Expense document analysis": {
        "model": "qwen2.5:14b-instruct",
        "precision": "High Accuracy",
        "reason": "Stronger extraction and reasoning for bank and bill documents.",
    },
    "Planning and strategy": {
        "model": "llama3.1:8b",
        "precision": "Balanced",
        "reason": "Good structure for roadmap and business planning.",
    },
    "Complex reasoning": {
        "model": "deepseek-r1:7b",
        "precision": "High Accuracy",
        "reason": "Better multi-step reasoning for difficult decisions.",
    },
}

BOSS_COMMAND_TEMPLATES = {
    "本周经营复盘": {
        "objective": "Weekly Executive Review",
        "custom_objective": "请给我本周经营复盘：收入、开销、净值变化、核心风险、下周前三个行动项。",
        "precision": "Balanced",
        "retriever_max_files": 6,
        "retriever_include_subject": True,
        "finance_min_amount": 0.0,
        "learning_weeks": 4,
        "learning_topic_limit": 8,
        "business_plan_style": "concise",
        "qa_require_business_plan": False,
        "expected_output": [
            "经营总览：收入、开销、净值（本周）",
            "异常点：金额、来源文件、影响",
            "下周优先行动：按优先级列出3项",
        ],
    },
    "开销异常审计": {
        "objective": "Expense and Income Review",
        "custom_objective": "请审计开销异常：列出可疑支出、证据来源、金额影响、建议处理动作。",
        "precision": "High Accuracy",
        "retriever_max_files": 10,
        "retriever_include_subject": True,
        "finance_min_amount": 50.0,
        "learning_weeks": 4,
        "learning_topic_limit": 8,
        "business_plan_style": "concise",
        "qa_require_business_plan": False,
        "expected_output": [
            "异常支出清单：金额、证据文件、异常原因",
            "风险评估：高/中/低",
            "处置建议：48小时内动作",
        ],
    },
    "学习-商业双轨计划": {
        "objective": "Cross-Project Strategic Summary",
        "custom_objective": "请给出学习-商业双轨计划：学习主题、每周里程碑、与业务落地的映射关系。",
        "precision": "Balanced",
        "retriever_max_files": 8,
        "retriever_include_subject": True,
        "finance_min_amount": 0.0,
        "learning_weeks": 6,
        "learning_topic_limit": 10,
        "business_plan_style": "detailed",
        "qa_require_business_plan": True,
        "expected_output": [
            "学习路线：按周列出主题和里程碑",
            "商业映射：每个学习主题对应业务动作",
            "本月交付：可执行清单和验收标准",
        ],
    },
    "风险优先行动清单": {
        "objective": "Cross-Project Strategic Summary",
        "custom_objective": "请输出风险优先行动清单：按高/中/低风险排序，给出负责角色与48小时内动作。",
        "precision": "High Accuracy",
        "retriever_max_files": 8,
        "retriever_include_subject": True,
        "finance_min_amount": 0.0,
        "learning_weeks": 4,
        "learning_topic_limit": 8,
        "business_plan_style": "investor",
        "qa_require_business_plan": True,
        "expected_output": [
            "风险列表：按高/中/低分组",
            "责任分配：负责人和截止时间",
            "行动清单：48小时内可执行任务",
        ],
    },
}


def _apply_template(template_name: str) -> None:
    template = BOSS_COMMAND_TEMPLATES[template_name]
    st.session_state.boss_template = template_name
    st.session_state.objective_choice = template["objective"]
    st.session_state.custom_objective = template["custom_objective"]
    st.session_state.agent_precision = template["precision"]
    st.session_state.retriever_max_files = template["retriever_max_files"]
    st.session_state.retriever_include_subject = template["retriever_include_subject"]
    st.session_state.finance_min_amount = template["finance_min_amount"]
    st.session_state.learning_weeks = template["learning_weeks"]
    st.session_state.learning_topic_limit = template["learning_topic_limit"]
    st.session_state.business_plan_style = template["business_plan_style"]
    st.session_state.qa_require_business_plan = template["qa_require_business_plan"]


def _compose_objective_with_expected_output(raw_objective: str, template_name: str) -> str:
    template = BOSS_COMMAND_TEMPLATES.get(template_name, {})
    expected = template.get("expected_output", [])
    if not expected:
        return raw_objective
    expected_text = "；".join(f"{idx + 1}) {item}" for idx, item in enumerate(expected))
    return f"{raw_objective}\n\n输出格式要求：{expected_text}"


def _suggest_template_from_instruction(instruction: str) -> str:
    text = (instruction or "").strip().lower()
    if not text:
        return st.session_state.boss_template

    keyword_map = {
        "本周经营复盘": ["复盘", "经营", "周报", "summary", "review", "净值", "收入", "开销"],
        "开销异常审计": ["审计", "异常", "开销", "支出", "expense", "risk", "可疑"],
        "学习-商业双轨计划": ["学习", "双轨", "路线", "roadmap", "里程碑", "计划"],
        "风险优先行动清单": ["风险", "优先", "清单", "action", "48小时", "负责人"],
    }

    best_name = st.session_state.boss_template
    best_score = -1
    for name, keywords in keyword_map.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > best_score:
            best_score = score
            best_name = name
    return best_name


def _read_env_map(env_path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not env_path.exists():
        return data
    for raw in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def _update_env_values(env_path: Path, updates: dict[str, str]) -> None:
    env_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8", errors="ignore").splitlines()

    seen: set[str] = set()
    output: list[str] = []
    for raw in lines:
        if "=" not in raw or raw.lstrip().startswith("#"):
            output.append(raw)
            continue
        key, _ = raw.split("=", 1)
        key = key.strip()
        if key in updates:
            output.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            output.append(raw)

    for key, value in updates.items():
        if key not in seen:
            output.append(f"{key}={value}")

    env_path.write_text("\n".join(output) + "\n", encoding="utf-8")


def _latest_report_timestamp() -> str:
    files = sorted(storage.reports.glob("report_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return "N/A"
    return datetime.fromtimestamp(files[0].stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")


def _connector_status() -> list[dict]:
    return [
        {
            "connector": "Telegram",
            "enabled": bool(config.telegram_enabled and config.telegram_bot_token),
            "detail": "Configured" if (config.telegram_enabled and config.telegram_bot_token) else "Disabled or token missing",
        },
        {
            "connector": "Outlook",
            "enabled": bool(config.outlook_enabled and config.outlook_client_id),
            "detail": "Configured" if (config.outlook_enabled and config.outlook_client_id) else "Disabled or client id missing",
        },
        {
            "connector": "Folder Sources",
            "enabled": bool(config.source_folders),
            "detail": f"{len(config.source_folders)} source folders",
        },
    ]


def _precision_to_runtime(precision_mode: str) -> dict:
    mode = precision_mode.strip().lower()
    if mode == "fast":
        return {"temperature": 0.4, "max_context_chars": 7000, "max_files": 3}
    if mode == "high accuracy":
        return {"temperature": 0.1, "max_context_chars": 22000, "max_files": 8}
    return {"temperature": 0.2, "max_context_chars": 14000, "max_files": 5}


def _ingest_uploaded_file(uploaded_file) -> dict:
    raw = uploaded_file.getvalue()
    source_id = hashlib.sha1((uploaded_file.name + str(len(raw))).encode("utf-8")).hexdigest()
    if storage.has_source_item("chat_upload", source_id):
        return {"name": uploaded_file.name, "status": "already_indexed"}

    upload_dir = storage.inbox / "chat_upload"
    upload_dir.mkdir(parents=True, exist_ok=True)
    target = upload_dir / uploaded_file.name
    if target.exists():
        stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        target = upload_dir / f"{Path(uploaded_file.name).stem}_{stamp}{Path(uploaded_file.name).suffix}"
    target.write_bytes(raw)

    item = IngestedFile(
        source="chat_upload",
        source_id=source_id,
        file_name=uploaded_file.name,
        local_path=target,
        created_at=datetime.utcnow().isoformat(),
        sender="dashboard_user",
        subject="chat_attachment",
    )
    storage.register_ingested(item)
    classified = classifier.classify_and_place(item)
    return {
        "name": uploaded_file.name,
        "status": "indexed",
        "project": classified.project,
        "category": classified.category,
        "text": classified.extracted_text[:5000],
    }


def _build_context(question: str, attachment_items: list[dict], max_context_chars: int, max_files: int) -> str:
    rows = storage.all_indexed_files()
    words = [w.strip().lower() for w in question.replace("\n", " ").split() if len(w.strip()) > 2]
    scored: list[tuple[int, dict]] = []
    for row in rows:
        blob = " ".join(
            [
                str(row.get("file_name", "")),
                str(row.get("project", "")),
                str(row.get("category", "")),
                str(row.get("subject", "")),
                str(row.get("extracted_text", ""))[:2000],
            ]
        ).lower()
        score = sum(1 for w in words if w in blob)
        if score > 0:
            scored.append((score, row))
    scored.sort(key=lambda x: x[0], reverse=True)

    selected = [row for _, row in scored[:max_files]] or rows[: min(max_files, 3)]
    chunks: list[str] = []
    for row in selected:
        chunks.append(
            "\n".join(
                [
                    f"File: {row.get('file_name', '')}",
                    f"Project: {row.get('project', 'general')}",
                    f"Category: {row.get('category', 'general')}",
                    f"Text: {str(row.get('extracted_text', ''))[:1200]}",
                ]
            )
        )

    for item in attachment_items:
        chunks.append(
            "\n".join(
                [
                    f"Attachment: {item.get('name', '')}",
                    f"Status: {item.get('status', '')}",
                    f"Detected project/category: {item.get('project', '')}/{item.get('category', '')}",
                    f"Attachment text: {item.get('text', '')}",
                ]
            )
        )

    merged = "\n\n---\n\n".join(chunks)
    return merged[:max_context_chars]


def _append_chat_message(role: str, content: str, attachments: list[str] | None = None) -> None:
    record = {
        "role": role,
        "content": content,
        "attachments": attachments or [],
    }
    st.session_state.chat_messages.append(record)
    storage.save_chat_message(role=role, content=content, attachments=attachments or [])


def _render_agent_flow() -> None:
    flow = """
digraph Agents {
    rankdir=LR;
    node [shape=box, style=rounded];
    Supervisor -> Retriever;
    Retriever -> DocumentReader;
    Supervisor -> FileOps;
    Supervisor -> Finance;
    Supervisor -> Learning;
    Supervisor -> BusinessPlan;
    DocumentReader -> Report;
    Retriever -> Report;
    FileOps -> Report;
    Finance -> Report;
    Learning -> Report;
    BusinessPlan -> Report;
    Report -> QA;
}
"""
    st.graphviz_chart(flow)


def _run_summary_row(run_id: int, created_at: str, payload: dict) -> dict:
    steps = payload.get("steps", [])
    completed = sum(1 for x in steps if x.get("status") == "completed")
    failed = sum(1 for x in steps if x.get("status") == "failed")
    total_time = round(sum(float(x.get("duration_sec", 0.0)) for x in steps), 3)
    qa_passed = bool((payload.get("qa") or {}).get("passed", False))
    return {
        "run_id": run_id,
        "created_at": created_at,
        "objective": payload.get("objective", ""),
        "completed": completed,
        "failed": failed,
        "duration_sec": total_time,
        "qa_passed": qa_passed,
    }


def _render_history_compare_panel() -> None:
    st.markdown("### Run History & Compare")
    history = storage.list_agent_runs(limit=40)
    if not history:
        st.caption("No historical runs yet.")
        return

    summary_rows = [_run_summary_row(x["id"], x["created_at"], x.get("payload", {})) for x in history]
    st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

    options = {f"Run #{x['id']} | {x['created_at']} | {x.get('payload', {}).get('objective', 'N/A')}": x for x in history}
    labels = list(options.keys())

    c1, c2 = st.columns(2)
    label_a = c1.selectbox("Compare Run A", labels, index=0)
    label_b = c2.selectbox("Compare Run B", labels, index=1 if len(labels) > 1 else 0)

    run_a = options[label_a]
    run_b = options[label_b]
    payload_a = run_a.get("payload", {})
    payload_b = run_b.get("payload", {})

    top1, top2, top3 = st.columns(3)
    top1.metric("Run A Duration(s)", f"{_run_summary_row(run_a['id'], run_a['created_at'], payload_a)['duration_sec']}")
    top2.metric("Run B Duration(s)", f"{_run_summary_row(run_b['id'], run_b['created_at'], payload_b)['duration_sec']}")

    net_a = float(((payload_a.get("report") or {}).get("finance") or {}).get("net", 0.0))
    net_b = float(((payload_b.get("report") or {}).get("finance") or {}).get("net", 0.0))
    top3.metric("Finance Net Delta", f"{round(net_a - net_b, 2):,.2f}")

    steps_a = {x.get("agent", ""): x for x in payload_a.get("steps", [])}
    steps_b = {x.get("agent", ""): x for x in payload_b.get("steps", [])}
    all_agents = sorted(set(steps_a.keys()) | set(steps_b.keys()))
    compare_rows = []
    for name in all_agents:
        sa = steps_a.get(name, {})
        sb = steps_b.get(name, {})
        da = float(sa.get("duration_sec", 0.0))
        db = float(sb.get("duration_sec", 0.0))
        compare_rows.append(
            {
                "agent": name,
                "status_a": sa.get("status", "N/A"),
                "status_b": sb.get("status", "N/A"),
                "duration_a": da,
                "duration_b": db,
                "delta_sec": round(da - db, 3),
            }
        )

    st.markdown("#### Step Comparison")
    st.dataframe(pd.DataFrame(compare_rows), use_container_width=True, hide_index=True)

    with st.expander("Run A Full Payload"):
        st.json(payload_a)
    with st.expander("Run B Full Payload"):
        st.json(payload_b)


def _render_agent_run_board(run_payload: dict) -> None:
    if not run_payload:
        st.caption("No agent collaboration run yet.")
        return

    steps = run_payload.get("steps", [])
    if not steps:
        st.caption("No steps recorded.")
        return

    completed = sum(1 for x in steps if x.get("status") == "completed")
    failed = sum(1 for x in steps if x.get("status") == "failed")
    total_time = round(sum(float(x.get("duration_sec", 0.0)) for x in steps), 3)

    c1, c2, c3 = st.columns(3)
    c1.metric("Completed Agents", completed)
    c2.metric("Failed Agents", failed)
    c3.metric("Total Duration(s)", total_time)

    rows = []
    for idx, step in enumerate(steps, start=1):
        rows.append(
            {
                "order": idx,
                "agent": step.get("agent", ""),
                "duty": step.get("duty", ""),
                "status": step.get("status", ""),
                "duration_sec": step.get("duration_sec", 0.0),
                "error": step.get("error", ""),
            }
        )

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.markdown("#### Step Output Details")
    for idx, step in enumerate(steps, start=1):
        title = f"{idx}. {step.get('agent', 'Unknown')} | {step.get('status', 'unknown')}"
        with st.expander(title):
            st.write("Duty:", step.get("duty", ""))
            if step.get("error"):
                st.error(step.get("error", ""))
            st.write("Started:", step.get("started_at", ""))
            st.write("Ended:", step.get("ended_at", ""))
            st.write("Duration(s):", step.get("duration_sec", 0.0))
            st.markdown("Output")
            st.json(step.get("output", {}))

    report = run_payload.get("report", {})
    qa = run_payload.get("qa", {})

    if report:
        st.subheader("Integrated Report")
        st.write("Objective:", report.get("objective", ""))
        st.write("Top Projects:", ", ".join(report.get("top_projects", [])) or "N/A")
        st.write("Retrieved Files:", ", ".join(report.get("retrieved_files", [])) or "N/A")

        finance = report.get("finance", {})
        if finance:
            f1, f2, f3 = st.columns(3)
            f1.metric("Income", f"{finance.get('income_total', 0):,.2f}")
            f2.metric("Expense", f"{finance.get('expense_total', 0):,.2f}")
            f3.metric("Net", f"{finance.get('net', 0):,.2f}")

        reader = report.get("reader", {})
        if reader:
            st.markdown("#### Document Reader Summary")
            st.write(
                "Coverage:",
                f"files={reader.get('file_count', 0)}, "
                f"text_ready={reader.get('text_ready_count', 0)}, "
                f"images={reader.get('image_file_count', 0)}",
            )
            st.write(
                "Quality:",
                f"confidence={reader.get('confidence', 0)}, "
                f"retrieval_chunks={reader.get('retrieval_chunks', 0)}",
            )
            conflicts = reader.get("conflicts", [])
            if conflicts:
                for item in conflicts:
                    st.warning(item)
            redactions = reader.get("redaction_counts", {})
            if redactions:
                st.caption(f"Sensitive redactions: {redactions}")
            shared_redactions = reader.get("shared_redaction_counts", {})
            if shared_redactions:
                st.caption(f"Shared contract redactions: {shared_redactions}")
            if reader.get("summary"):
                st.write(reader.get("summary", ""))
            evidence = reader.get("evidence_files", [])
            if evidence:
                st.dataframe(pd.DataFrame(evidence), use_container_width=True, hide_index=True)
            shared_preview = reader.get("shared_context_preview", [])
            if shared_preview:
                st.markdown("#### Shared Context Preview")
                st.dataframe(pd.DataFrame(shared_preview), use_container_width=True, hide_index=True)
            shared_errors = reader.get("shared_context_errors", [])
            if shared_errors:
                st.markdown("#### Shared Context Errors")
                st.dataframe(pd.DataFrame(shared_errors), use_container_width=True, hide_index=True)

        learning = report.get("learning", {})
        if learning:
            st.write("Learning Topics:", ", ".join(learning.get("topics", [])) or "N/A")
            for line in learning.get("outline", []):
                st.write("-", line)

        bp = report.get("business_plan", "")
        if bp:
            with st.expander("Business Plan Draft"):
                st.write(bp)

    if qa:
        st.subheader("QA Result")
        st.write("Passed:", qa.get("passed", False))
        checks = qa.get("checks", {})
        if checks:
            st.dataframe(
                pd.DataFrame([{"check": k, "passed": v} for k, v in checks.items()]),
                use_container_width=True,
                hide_index=True,
            )


def _summarize_step_output(step: dict) -> str:
    output = step.get("output") or {}
    agent = step.get("agent", "")
    if agent == "Supervisor Agent":
        top_projects = output.get("top_projects", [])
        return f"目标={output.get('objective', '')}；重点项目={', '.join(top_projects) or 'N/A'}"
    if agent == "Retriever Agent":
        titles = output.get("titles", [])
        return f"检索到 {output.get('count', 0)} 个相关文件：{', '.join(titles[:3]) or 'N/A'}"
    if agent == "Document Reader Agent":
        formats = output.get("format_breakdown", {})
        top_formats = ", ".join(f"{k}:{v}" for k, v in list(formats.items())[:4])
        return (
            f"精读文件={output.get('file_count', 0)}，可解析文本={output.get('text_ready_count', 0)}，"
            f"图片={output.get('image_file_count', 0)}；格式分布={top_formats or 'N/A'}；"
            f"置信度={output.get('confidence', 0)}"
        )
    if agent == "FileOps Agent":
        return (
            f"已整理={output.get('organized', 0)}，未整理={output.get('pending', 0)}，"
            f"覆盖率={output.get('coverage', 0)}%"
        )
    if agent == "Finance Agent":
        return (
            f"收入={output.get('income_total', 0):,.2f}，"
            f"开销={output.get('expense_total', 0):,.2f}，"
            f"净值={output.get('net', 0):,.2f}"
        )
    if agent == "Learning Agent":
        topics = output.get("topics", [])
        return f"学习主题={', '.join(topics[:4]) or 'N/A'}"
    if agent == "Business Plan Agent":
        plan = str(output.get("plan", ""))
        return f"商业计划草案已生成：{plan[:90]}..." if plan else "商业计划草案为空"
    if agent == "Report Agent":
        actions = (output.get("action_items") or [])
        return f"整合报告完成，行动项数量={len(actions)}"
    if agent == "QA Agent":
        missing = output.get("missing", [])
        return f"质检 {'通过' if output.get('passed') else '未通过'}；缺失项={', '.join(missing) or '无'}"
    return "任务执行完成"


def _build_agent_conversation_lines(objective: str, steps: list[dict]) -> list[str]:
    lines: list[str] = [f"老板：目标是“{objective}”，请团队分工协作并给我结论。"]
    for step in steps:
        status = step.get("status", "unknown")
        if status == "completed":
            lines.append(f"{step.get('agent', 'Agent')}：{_summarize_step_output(step)}")
        else:
            lines.append(
                f"{step.get('agent', 'Agent')}：执行失败，错误={step.get('error', 'unknown error')}"
            )
    if steps:
        qa_step = next((s for s in steps if s.get("agent") == "QA Agent"), None)
        if qa_step and qa_step.get("status") == "completed":
            qa_passed = bool((qa_step.get("output") or {}).get("passed", False))
            lines.append(
                "主管Agent：向老板汇报，"
                + ("本轮协作已通过质检，可直接执行。" if qa_passed else "本轮有风险，建议复核缺失项后再决策。")
            )
    return lines


def _render_agent_conversation(run_payload: dict, live_steps: list[dict] | None = None) -> None:
    st.markdown("### Boss-Employee Conversation")
    if not run_payload:
        st.caption("No collaboration run yet.")
        return

    objective = str(run_payload.get("objective", ""))
    steps = live_steps if live_steps is not None else list(run_payload.get("steps", []))
    if not steps:
        st.caption("No conversation records yet.")
        return

    lines = _build_agent_conversation_lines(objective, steps)
    for idx, line in enumerate(lines, start=1):
        with st.container(border=True):
            st.write(f"{idx}. {line}")


if "agent_running" not in st.session_state:
    st.session_state.agent_running = False

if "agent_backend" not in st.session_state:
    st.session_state.agent_backend = "Auto (Hermes -> Ollama)"

if "agent_model" not in st.session_state:
    st.session_state.agent_model = DEFAULT_LOCAL_MODELS[0]

if "model_profile" not in st.session_state:
    st.session_state.model_profile = "General chat / summary"

if "agent_precision" not in st.session_state:
    st.session_state.agent_precision = "Balanced"

if "ollama_base_url" not in st.session_state:
    st.session_state.ollama_base_url = "http://127.0.0.1:11434"

if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = storage.recent_chat_messages(limit=80)

if "agent_run_payload" not in st.session_state:
    st.session_state.agent_run_payload = storage.latest_agent_run()

if "agent_live_steps" not in st.session_state:
    st.session_state.agent_live_steps = []

if "boss_template" not in st.session_state:
    st.session_state.boss_template = "本周经营复盘"

if "retriever_max_files" not in st.session_state:
    st.session_state.retriever_max_files = 6

if "retriever_include_subject" not in st.session_state:
    st.session_state.retriever_include_subject = True

if "finance_min_amount" not in st.session_state:
    st.session_state.finance_min_amount = 0.0

if "learning_weeks" not in st.session_state:
    st.session_state.learning_weeks = 4

if "learning_topic_limit" not in st.session_state:
    st.session_state.learning_topic_limit = 8

if "business_plan_style" not in st.session_state:
    st.session_state.business_plan_style = "concise"

if "qa_require_business_plan" not in st.session_state:
    st.session_state.qa_require_business_plan = True

if "objective_choice" not in st.session_state:
    st.session_state.objective_choice = "Weekly Executive Review"

if "custom_objective" not in st.session_state:
    st.session_state.custom_objective = ""

if "boss_instruction" not in st.session_state:
    st.session_state.boss_instruction = ""

if "outlook_connect_status" not in st.session_state:
    st.session_state.outlook_connect_status = ""

if "outlook_client_id_input" not in st.session_state:
    st.session_state.outlook_client_id_input = config.outlook_client_id

if "outlook_tenant_id_input" not in st.session_state:
    st.session_state.outlook_tenant_id_input = config.outlook_tenant_id

if "outlook_email_input" not in st.session_state:
    st.session_state.outlook_email_input = config.outlook_account_email

if "outlook_enabled_input" not in st.session_state:
    st.session_state.outlook_enabled_input = bool(config.outlook_enabled)

if "outlook_days_input" not in st.session_state:
    st.session_state.outlook_days_input = int(config.outlook_attachment_days)

with st.sidebar:
    st.header("Secretary Status")
    connector_df = pd.DataFrame(_connector_status())
    st.dataframe(connector_df, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Outlook Connection")
    st.session_state.outlook_enabled_input = st.checkbox(
        "Enable Outlook collector",
        value=st.session_state.outlook_enabled_input,
    )
    st.session_state.outlook_client_id_input = st.text_input(
        "Outlook Client ID",
        value=st.session_state.outlook_client_id_input,
        placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    ).strip()
    st.session_state.outlook_tenant_id_input = st.text_input(
        "Tenant ID",
        value=st.session_state.outlook_tenant_id_input or "common",
        help="Use common for personal account, or your Azure tenant ID.",
    ).strip() or "common"
    st.session_state.outlook_email_input = st.text_input(
        "Outlook account email",
        value=st.session_state.outlook_email_input,
    ).strip()
    st.session_state.outlook_days_input = int(
        st.number_input(
            "Attachment sync days",
            min_value=1,
            max_value=365,
            value=int(st.session_state.outlook_days_input),
            step=1,
        )
    )

    c_save, c_connect = st.columns(2)
    if c_save.button("Save Outlook Settings", use_container_width=True):
        env_path = Path(__file__).resolve().parent / ".env"
        _update_env_values(
            env_path,
            {
                "OUTLOOK_ENABLED": "true" if st.session_state.outlook_enabled_input else "false",
                "OUTLOOK_CLIENT_ID": st.session_state.outlook_client_id_input,
                "OUTLOOK_TENANT_ID": st.session_state.outlook_tenant_id_input,
                "OUTLOOK_ACCOUNT_EMAIL": st.session_state.outlook_email_input,
                "OUTLOOK_ATTACHMENT_DAYS": str(st.session_state.outlook_days_input),
            },
        )
        st.success("Outlook settings saved to .env")

    outlook_status = outlook_collector.status(
        client_id=st.session_state.outlook_client_id_input,
        tenant_id=st.session_state.outlook_tenant_id_input,
        account_email=st.session_state.outlook_email_input,
    )
    lamp = "🟢 Connected" if outlook_status.get("connected") else "🔴 Not Connected"
    st.write("Status:", lamp)
    st.caption(outlook_status.get("message", ""))

    outlook_stats = storage.outlook_attachment_stats(recent_days=config.outlook_attachment_days)
    m1, m2 = st.columns(2)
    m1.metric("Outlook Total", int(outlook_stats.get("total", 0)))
    m2.metric(f"Recent {outlook_stats.get('recent_days', 14)}d", int(outlook_stats.get("recent", 0)))
    st.caption(f"Last attachment sync: {outlook_stats.get('last_sync') or 'N/A'}")

    if c_connect.button("Connect Outlook", use_container_width=True):
        with st.spinner("Connecting to Outlook..."):
            result = outlook_collector.connect(
                client_id=st.session_state.outlook_client_id_input,
                tenant_id=st.session_state.outlook_tenant_id_input,
                account_email=st.session_state.outlook_email_input,
            )
        st.session_state.outlook_connect_status = result.get("message", "")
        if result.get("connected"):
            st.success("Outlook connected.")
        else:
            st.error("Outlook connection failed.")

    if st.session_state.outlook_connect_status:
        st.caption(st.session_state.outlook_connect_status)

    st.divider()
    st.subheader("Agent Runtime")
    st.write("Status:", "Running" if st.session_state.agent_running else "Stopped")

    col_a, col_b = st.columns(2)
    if col_a.button("Start Agent", use_container_width=True):
        st.session_state.agent_running = True
        st.success("Agent started")
    if col_b.button("Stop Agent", use_container_width=True):
        st.session_state.agent_running = False
        st.warning("Agent stopped")

    backend_options = ["Auto (Hermes -> Ollama)", "Hermes CLI", "Ollama Local"]
    st.session_state.agent_backend = st.selectbox(
        "Backend",
        backend_options,
        index=backend_options.index(st.session_state.agent_backend),
    )

    profile_options = list(MODEL_PROFILES.keys())
    profile_index = profile_options.index(st.session_state.model_profile) if st.session_state.model_profile in profile_options else 0
    st.session_state.model_profile = st.selectbox("Task Profile", profile_options, index=profile_index)
    profile = MODEL_PROFILES[st.session_state.model_profile]
    st.caption(f"Recommended: {profile['model']} | {profile['precision']}")
    st.caption(profile["reason"])
    if st.button("Apply Recommended Model", use_container_width=True):
        st.session_state.agent_model = profile["model"]
        st.session_state.agent_precision = profile["precision"]
        st.success("Recommended local model applied.")

    model_index = DEFAULT_LOCAL_MODELS.index(st.session_state.agent_model) if st.session_state.agent_model in DEFAULT_LOCAL_MODELS else 0
    st.session_state.agent_model = st.selectbox("Local Model", DEFAULT_LOCAL_MODELS, index=model_index)
    custom_model = st.text_input("Custom Model (optional)", value=st.session_state.agent_model).strip()
    if custom_model:
        st.session_state.agent_model = custom_model

    precision_options = ["Fast", "Balanced", "High Accuracy"]
    st.session_state.agent_precision = st.selectbox(
        "Precision Mode",
        precision_options,
        index=precision_options.index(st.session_state.agent_precision),
    )
    st.session_state.ollama_base_url = st.text_input("Ollama URL", value=st.session_state.ollama_base_url)

    st.divider()
    st.subheader("Folder Incremental Organizer")
    folder_input = st.text_input("Folder Path", placeholder="E:/Dropbox/共享文件夹/Adelaide")
    project_input = st.text_input("Project Name", value="general")
    if st.button("Analyze & Organize New Files"):
        if not folder_input.strip():
            st.error("Please enter a folder path.")
        else:
            with st.spinner("Scanning folder and organizing only new files..."):
                items, stats = folder_collector.collect_incremental(Path(folder_input.strip()), project_input.strip() or "general")
                for item in items:
                    classifier.classify_and_place(item)
                run_analysis(config, storage)

            if stats.get("missing_path"):
                st.error(f"Path not found: {stats.get('path')}")
            elif stats.get("already_organized"):
                st.success(
                    f"Folder already organized. Scanned {stats.get('scanned_files', 0)} files, skipped {stats.get('skipped_existing', 0)} existing files."
                )
            else:
                st.success(
                    f"Done. New files: {stats.get('new_files', 0)}, skipped existing: {stats.get('skipped_existing', 0)}, scanned: {stats.get('scanned_files', 0)}."
                )
            st.rerun()

    if st.button("Run Full Sync", type="primary"):
        with st.spinner("Syncing files from all sources..."):
            run_sync()
        st.success("Full sync complete.")
        st.rerun()

    if st.button("Run Analysis Only"):
        with st.spinner("Running analysis..."):
            report = run_analysis(config, storage)
        st.success(f"Analysis complete. Files analyzed: {report.get('analyzed_files', 0)}")
        st.rerun()

summary = storage.latest_report()
if not summary:
    st.info("No report yet. Use 'Run Full Sync' from sidebar.")
    summary = {
        "total_files": len(storage.all_indexed_files()),
        "income_total": 0,
        "expense_total": 0,
        "project_stats": [],
        "category_stats": [],
        "hermes_summaries": [],
    }

st.subheader("Overview")
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Files", summary.get("total_files", 0))
col2.metric("Income (est.)", f"{summary.get('income_total', 0):,.2f}")
col3.metric("Expense (est.)", f"{summary.get('expense_total', 0):,.2f}")
col4.metric("Last Report", _latest_report_timestamp())

tab1, tab2, tab3, tab4 = st.tabs(["Dashboard", "Secretary Chat", "Recent Files", "Agent Collaboration"])

with tab1:
    if summary.get("expense_policy"):
        st.info(f"Expense policy: {summary.get('expense_policy')}")
    scope = summary.get("expense_scope", {})
    category_rows = scope.get("category_totals", [])
    if category_rows:
        st.caption(f"Qualified expense docs: {scope.get('qualified_outlook_docs', 0)}")
        st.dataframe(pd.DataFrame(category_rows), use_container_width=True, hide_index=True)

    st.subheader("Expense Audit Review Queue")
    rejected_candidates = scope.get("rejected_candidates", [])
    if rejected_candidates:
        review_rows = []
        for row in rejected_candidates:
            review_rows.append(
                {
                    "source": row.get("source", ""),
                    "file_name": row.get("file_name", ""),
                    "detected_categories": ", ".join(row.get("detected_categories", [])),
                    "rejection_reasons": ", ".join(row.get("rejection_reasons", [])),
                }
            )
        st.dataframe(pd.DataFrame(review_rows), use_container_width=True, hide_index=True)

        selected_idx = st.selectbox(
            "Select a rejected file to override",
            options=list(range(len(rejected_candidates))),
            format_func=lambda i: f"{rejected_candidates[i].get('file_name', '')} | {rejected_candidates[i].get('source', '')}",
            key="expense_review_selected_idx",
        )
        selected = rejected_candidates[selected_idx]
        suggested = selected.get("detected_categories", [])
        default_category = "expense_report"
        if suggested:
            top = str(suggested[0]).strip().lower()
            if top in MANUAL_OVERRIDE_CATEGORIES:
                default_category = top

        override_category = st.selectbox(
            "Override category",
            options=MANUAL_OVERRIDE_CATEGORIES,
            index=MANUAL_OVERRIDE_CATEGORIES.index(default_category),
            key="expense_review_override_category",
        )
        override_note = st.text_input("Override note", value="dashboard_manual_review", key="expense_review_note")

        if st.button("Mark as qualified expense", key="expense_review_apply"):
            storage.set_manual_expense_override(
                source=str(selected.get("source", "")),
                source_id=str(selected.get("source_id", "")),
                category=override_category,
                note=override_note.strip() or "dashboard_manual_review",
            )
            with st.spinner("Applying manual override and refreshing analysis..."):
                run_analysis(config, storage)
            st.success("Manual override applied.")
            st.rerun()
    else:
        st.caption("No rejected expense candidates.")

    st.subheader("Manual Expense Overrides")
    all_rows = storage.all_indexed_files()
    overridden_rows = [r for r in all_rows if bool(r.get("manual_expense_override"))]
    if overridden_rows:
        override_df = pd.DataFrame(
            [
                {
                    "source": r.get("source", ""),
                    "file_name": r.get("file_name", ""),
                    "override_category": r.get("manual_expense_category", ""),
                    "created_at": r.get("created_at", ""),
                }
                for r in overridden_rows
            ]
        )
        st.dataframe(override_df, use_container_width=True, hide_index=True)

        revoke_idx = st.selectbox(
            "Select an override to revoke",
            options=list(range(len(overridden_rows))),
            format_func=lambda i: f"{overridden_rows[i].get('file_name', '')} | {overridden_rows[i].get('source', '')}",
            key="expense_review_revoke_idx",
        )
        revoke_target = overridden_rows[revoke_idx]
        if st.button("Revoke manual override", key="expense_review_revoke_apply"):
            storage.clear_manual_expense_override(
                source=str(revoke_target.get("source", "")),
                source_id=str(revoke_target.get("source_id", "")),
            )
            with st.spinner("Reverting manual override and refreshing analysis..."):
                run_analysis(config, storage)
            st.success("Manual override revoked.")
            st.rerun()
    else:
        st.caption("No manual overrides yet.")

    st.subheader("By Project")
    project_df = pd.DataFrame(summary.get("project_stats", []))
    if not project_df.empty:
        st.dataframe(project_df, use_container_width=True, hide_index=True)
    else:
        st.caption("No project stats available.")

    st.subheader("Category Distribution")
    cat_df = pd.DataFrame(summary.get("category_stats", []))
    if not cat_df.empty:
        st.bar_chart(cat_df.set_index("category")["count"])
        st.dataframe(cat_df, use_container_width=True, hide_index=True)
    else:
        st.caption("No category stats available.")

    st.subheader("Hermes Summaries")
    for item in summary.get("hermes_summaries", [])[:8]:
        with st.expander(f"{item.get('project', 'unknown')} | {item.get('title', 'summary')}"):
            st.write(item.get("summary", ""))

with tab2:
    st.subheader("Talk to Your Secretary")
    st.caption("You can ask questions and upload attachments in the same request.")
    if not st.session_state.agent_running:
        st.warning("Agent is stopped. Start agent from sidebar before chatting.")

    for msg in st.session_state.chat_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            for att in msg.get("attachments", []):
                st.caption(f"Attachment: {att}")

    with st.form("chat_form", clear_on_submit=True):
        user_text = st.text_area("Message", height=120, placeholder="例如：总结一下本周学习重点，并生成下周计划")
        uploads = st.file_uploader(
            "Add attachments",
            accept_multiple_files=True,
            type=["pdf", "txt", "md", "csv", "xlsx", "xls", "json"],
        )
        submitted = st.form_submit_button("Send")

    if submitted and (user_text.strip() or uploads):
        if not st.session_state.agent_running:
            st.error("Agent is not running. Please click Start Agent first.")
            st.stop()

        processed_attachments: list[dict] = []
        upload_names: list[str] = []
        for up in uploads or []:
            info = _ingest_uploaded_file(up)
            processed_attachments.append(info)
            upload_names.append(up.name)

        _append_chat_message(
            role="user",
            content=user_text or "(Attachment-only request)",
            attachments=upload_names,
        )

        runtime = _precision_to_runtime(st.session_state.agent_precision)
        backend_map = {
            "Auto (Hermes -> Ollama)": "auto",
            "Hermes CLI": "hermes",
            "Ollama Local": "ollama",
        }
        backend = backend_map.get(st.session_state.agent_backend, "auto")

        with st.spinner("Secretary is thinking..."):
            context = _build_context(
                user_text or "Please analyze attachments",
                processed_attachments,
                max_context_chars=runtime["max_context_chars"],
                max_files=runtime["max_files"],
            )
            answer = hermes.answer(
                user_text or "Please summarize these attachments.",
                context,
                backend=backend,
                ollama_base_url=st.session_state.ollama_base_url,
                ollama_model=st.session_state.agent_model,
                temperature=runtime["temperature"],
                timeout_seconds=180,
            )

        _append_chat_message(
            role="assistant",
            content=answer,
            attachments=[f"{x.get('name')} ({x.get('status')})" for x in processed_attachments],
        )
        st.rerun()

with tab3:
    rows = storage.all_indexed_files()
    if not rows:
        st.caption("No indexed files yet.")
    else:
        preview_df = pd.DataFrame(rows)
        cols = ["created_at", "source", "file_name", "project", "category", "manual_expense_override", "sender", "subject"]
        available = [c for c in cols if c in preview_df.columns]
        st.dataframe(preview_df[available], use_container_width=True, hide_index=True)

with tab4:
    st.subheader("Multi-Agent Collaboration")
    st.caption("Visualize agent division of work and run orchestrated analysis for your project.")

    st.markdown("### 老板指令模板")
    st.text_input(
        "老板一句话指令（可选）",
        key="boss_instruction",
        placeholder="例如：帮我做本周经营复盘，并按风险给出下周前三动作",
    )
    auto_col1, auto_col2 = st.columns(2)
    if auto_col1.button("自动匹配模板并应用", use_container_width=True):
        matched = _suggest_template_from_instruction(st.session_state.boss_instruction)
        _apply_template(matched)
        st.success(f"已自动匹配模板：{matched}")
        st.rerun()

    st.selectbox(
        "选择模板",
        options=list(BOSS_COMMAND_TEMPLATES.keys()),
        key="boss_template",
    )
    if auto_col2.button("应用模板到目标与参数", use_container_width=True):
        _apply_template(st.session_state.boss_template)
        st.success("模板已应用。")
        st.rerun()

    template_preview = BOSS_COMMAND_TEMPLATES.get(st.session_state.boss_template, {})
    expected_preview = template_preview.get("expected_output", [])
    if expected_preview:
        st.caption("该模板预期输出格式")
        for idx, item in enumerate(expected_preview, start=1):
            st.write(f"{idx}. {item}")

    st.markdown("### Recommended Agent Team For Your Project")
    st.dataframe(pd.DataFrame(orchestrator.recommended_agents()), use_container_width=True, hide_index=True)

    st.markdown("### Collaboration Flow")
    _render_agent_flow()

    st.markdown("### Agent Parameter Panel")
    p1, p2, p3 = st.columns(3)
    retriever_max_files = p1.slider("Retriever Top-K", min_value=2, max_value=15, step=1, key="retriever_max_files")
    retriever_include_subject = p1.checkbox("Retriever include subject", key="retriever_include_subject")

    finance_min_amount = p2.number_input("Finance min amount filter", min_value=0.0, max_value=100000.0, step=10.0, key="finance_min_amount")
    learning_weeks = p2.slider("Learning weeks", min_value=2, max_value=12, step=1, key="learning_weeks")
    learning_topic_limit = p2.slider("Learning topic limit", min_value=3, max_value=15, step=1, key="learning_topic_limit")

    business_plan_style = p3.selectbox("Business plan style", ["concise", "detailed", "investor"], key="business_plan_style")
    qa_require_business_plan = p3.checkbox("QA require business plan", key="qa_require_business_plan")

    col_goal, col_btn = st.columns([3, 1])
    objective = col_goal.selectbox(
        "Objective",
        [
            "Weekly Executive Review",
            "Expense and Income Review",
            "Study Roadmap",
            "Business Plan Draft",
            "Cross-Project Strategic Summary",
        ],
        key="objective_choice",
    )
    custom_objective = st.text_input("Custom objective (optional)", key="custom_objective")
    raw_objective = custom_objective.strip() or objective
    run_objective = _compose_objective_with_expected_output(raw_objective, st.session_state.boss_template)

    live_progress = st.progress(0.0, text="Idle")
    live_table_slot = st.empty()
    live_conversation_slot = st.empty()

    if col_btn.button("Run Agent Team", type="primary", use_container_width=True):
        if not st.session_state.agent_running:
            st.error("Agent is not running. Please Start Agent from sidebar.")
            st.stop()

        runtime = _precision_to_runtime(st.session_state.agent_precision)
        backend_map = {
            "Auto (Hermes -> Ollama)": "auto",
            "Hermes CLI": "hermes",
            "Ollama Local": "ollama",
        }
        backend = backend_map.get(st.session_state.agent_backend, "auto")
        runtime["max_files"] = retriever_max_files

        agent_params = {
            "retriever_max_files": retriever_max_files,
            "retriever_include_subject": retriever_include_subject,
            "finance_min_amount": finance_min_amount,
            "learning_weeks": learning_weeks,
            "learning_topic_limit": learning_topic_limit,
            "business_plan_style": business_plan_style,
            "qa_require_business_plan": qa_require_business_plan,
        }
        st.session_state.agent_live_steps = []

        def _on_step(step: dict, steps: list[dict]) -> None:
            st.session_state.agent_live_steps = steps.copy()
            total = 9
            done = len(steps)
            agent_name = step.get("agent", "")
            live_progress.progress(min(done / total, 1.0), text=f"{done}/{total} complete - {agent_name}")
            rows = []
            for idx, s in enumerate(steps, start=1):
                rows.append(
                    {
                        "order": idx,
                        "agent": s.get("agent", ""),
                        "status": s.get("status", ""),
                        "duration_sec": s.get("duration_sec", 0.0),
                        "error": s.get("error", ""),
                    }
                )
            live_table_slot.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            with live_conversation_slot.container():
                _render_agent_conversation(
                    {"objective": run_objective, "steps": steps},
                    live_steps=steps,
                )

        with st.spinner("Running multi-agent collaboration pipeline..."):
            payload = orchestrator.run(
                objective=run_objective,
                backend=backend,
                ollama_base_url=st.session_state.ollama_base_url,
                ollama_model=st.session_state.agent_model,
                temperature=runtime["temperature"],
                max_context_chars=runtime["max_context_chars"],
                max_files=runtime["max_files"],
                agent_params=agent_params,
                progress_callback=_on_step,
            )

        st.session_state.agent_run_payload = payload
        live_progress.progress(1.0, text="9/9 complete - all agents finished")
        st.success("Multi-agent run complete.")

    st.markdown("### Latest Collaboration Status")
    _render_agent_conversation(st.session_state.agent_run_payload)
    _render_agent_run_board(st.session_state.agent_run_payload)

    _render_history_compare_panel()
