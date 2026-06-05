from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Callable
from typing import Any

from personal_secretary.analysis import estimate_money
from personal_secretary.config import SecretaryConfig
from personal_secretary.document_reader_agent import DocumentReaderAgent
from personal_secretary.hermes_client import HermesClient
from personal_secretary.shared_capabilities_adapter import SecretarySharedCapabilitiesAdapter
from personal_secretary.storage import SecretaryStorage


class MultiAgentOrchestrator:
    def __init__(self, config: SecretaryConfig, storage: SecretaryStorage, hermes: HermesClient) -> None:
        self.config = config
        self.storage = storage
        self.hermes = hermes
        self.document_reader_agent = DocumentReaderAgent(hermes)
        self.shared_capabilities = SecretarySharedCapabilitiesAdapter(hermes)

    def recommended_agents(self) -> list[dict[str, str]]:
        return [
            {
                "agent": "Supervisor Agent",
                "responsibility": "规划任务、分配子代理、追踪全局状态",
                "for_you": "你有学习+商业+财务混合需求，需统一调度",
            },
            {
                "agent": "Retriever Agent",
                "responsibility": "从已整理文件中检索与目标最相关内容",
                "for_you": "快速从 Adelaide 与 数据科学资料中取重点",
            },
            {
                "agent": "Document Reader Agent",
                "responsibility": "精读文件内容并生成带证据的总结（图片/Word/PDF/CSV）",
                "for_you": "输出可追溯证据摘要，减少漏读和误读",
            },
            {
                "agent": "FileOps Agent",
                "responsibility": "检测已整理/未整理，触发增量整理",
                "for_you": "避免重复扫描，专注新增文件",
            },
            {
                "agent": "Finance Agent",
                "responsibility": "提取开销与收入线索并汇总",
                "for_you": "持续跟踪成本/现金流",
            },
            {
                "agent": "Learning Agent",
                "responsibility": "提炼学习主题，生成学习大纲",
                "for_you": "企业家精神与数据科学双轨学习",
            },
            {
                "agent": "Business Plan Agent",
                "responsibility": "从资料生成商业计划草案",
                "for_you": "把课程与资料转化为可执行商业方案",
            },
            {
                "agent": "Report Agent",
                "responsibility": "整合多代理输出为统一dashboard结论",
                "for_you": "一个界面看到总结、行动项、风险",
            },
            {
                "agent": "QA Agent",
                "responsibility": "验证输出完整性和关键字段",
                "for_you": "避免错漏，确保报告可用",
            },
        ]

    def run(
        self,
        objective: str,
        backend: str,
        ollama_base_url: str,
        ollama_model: str,
        temperature: float,
        max_context_chars: int,
        max_files: int,
        agent_params: dict[str, Any] | None = None,
        progress_callback: Callable[[dict[str, Any], list[dict[str, Any]]], None] | None = None,
    ) -> dict[str, Any]:
        all_files = self.storage.all_indexed_files()
        started_at = datetime.utcnow().isoformat()
        steps: list[dict[str, Any]] = []
        params = agent_params or {}

        def run_step(name: str, duty: str, func):
            start = datetime.utcnow()
            try:
                data = func()
                status = "completed"
                error = ""
            except Exception as exc:
                data = {}
                status = "failed"
                error = str(exc)
            end = datetime.utcnow()
            step = {
                "agent": name,
                "duty": duty,
                "status": status,
                "started_at": start.isoformat(),
                "ended_at": end.isoformat(),
                "duration_sec": round((end - start).total_seconds(), 3),
                "error": error,
                "output": data,
            }
            steps.append(step)
            if progress_callback:
                progress_callback(step, steps)
            return data

        plan = run_step(
            "Supervisor Agent",
            "根据 objective 制定执行计划",
            lambda: self._supervisor_plan(objective, all_files),
        )

        retrieved = run_step(
            "Retriever Agent",
            "检索最相关文件",
            lambda: self._retrieve_relevant(
                all_files,
                plan,
                max_files=int(params.get("retriever_max_files", max_files)),
                include_subject=bool(params.get("retriever_include_subject", True)),
            ),
        )

        reader = run_step(
            "Document Reader Agent",
            "精读多格式文件并生成证据摘要",
            lambda: self._document_reader_summary(
                objective=objective,
                files=retrieved.get("files", []),
                backend=backend,
                ollama_base_url=ollama_base_url,
                ollama_model=ollama_model,
                temperature=temperature,
                max_context_chars=max_context_chars,
            ),
        )

        file_ops = run_step(
            "FileOps Agent",
            "检查整理覆盖率",
            lambda: self._fileops_status(all_files),
        )

        finance = run_step(
            "Finance Agent",
            "汇总收入与开销",
            lambda: self._finance_summary(
                retrieved.get("files", []),
                min_amount=float(params.get("finance_min_amount", 0.0)),
            ),
        )

        learning = run_step(
            "Learning Agent",
            "提炼学习主题与大纲",
            lambda: self._learning_outline(
                retrieved.get("files", []),
                weeks=int(params.get("learning_weeks", 4)),
                topic_limit=int(params.get("learning_topic_limit", 8)),
            ),
        )

        business = run_step(
            "Business Plan Agent",
            "生成 business plan 草稿",
            lambda: self._business_plan(
                objective=objective,
                files=retrieved.get("files", []),
                backend=backend,
                ollama_base_url=ollama_base_url,
                ollama_model=ollama_model,
                temperature=temperature,
                max_context_chars=max_context_chars,
                plan_style=str(params.get("business_plan_style", "concise")),
            ),
        )

        report = run_step(
            "Report Agent",
            "整合多代理输出",
            lambda: self._build_report(objective, plan, retrieved, reader, file_ops, finance, learning, business),
        )

        qa = run_step(
            "QA Agent",
            "检查输出完整性",
            lambda: self._qa_check(
                report,
                require_business_plan=bool(params.get("qa_require_business_plan", True)),
            ),
        )

        finished_at = datetime.utcnow().isoformat()
        payload = {
            "objective": objective,
            "started_at": started_at,
            "finished_at": finished_at,
            "steps": steps,
            "report": report,
            "qa": qa,
        }
        self.storage.save_agent_run(payload)
        return payload

    def _supervisor_plan(self, objective: str, all_files: list[dict[str, Any]]) -> dict[str, Any]:
        projects = Counter((row.get("project") or "general") for row in all_files)
        top_projects = [name for name, _ in projects.most_common(5)]
        return {
            "objective": objective,
            "top_projects": top_projects,
            "active_agents": [
                "Retriever Agent",
                "Document Reader Agent",
                "FileOps Agent",
                "Finance Agent",
                "Learning Agent",
                "Business Plan Agent",
                "Report Agent",
                "QA Agent",
            ],
        }

    def _document_reader_summary(
        self,
        objective: str,
        files: list[dict[str, Any]],
        backend: str,
        ollama_base_url: str,
        ollama_model: str,
        temperature: float,
        max_context_chars: int,
    ) -> dict[str, Any]:
        reader_result = self.document_reader_agent.run(
            objective=objective,
            files=files,
            backend=backend,
            ollama_base_url=ollama_base_url,
            ollama_model=ollama_model,
            temperature=temperature,
            max_context_chars=max_context_chars,
        )

        docs_payload: list[dict[str, Any]] = []
        for idx, row in enumerate(files, start=1):
            docs_payload.append(
                {
                    "doc_id": str(row.get("source_id") or f"doc_{idx}"),
                    "title": str(row.get("file_name") or f"doc_{idx}"),
                    "source": str(row.get("source") or ""),
                    "text": str(row.get("extracted_text") or ""),
                }
            )

        read_result = self.shared_capabilities.read_documents(docs_payload)
        rank_result = self.shared_capabilities.rank_context(
            query=objective,
            docs=read_result.docs,
            top_k=5,
        )
        shared_errors = read_result.errors + rank_result.errors

        reader_result["shared_context_preview"] = rank_result.contexts
        reader_result["shared_redaction_counts"] = read_result.redaction_counts
        reader_result["shared_context_errors"] = [
            {
                "code": e.code,
                "message": e.message,
                "retryable": e.retryable,
                "reference_id": e.reference_id,
            }
            for e in shared_errors
        ]
        return reader_result

    def _retrieve_relevant(
        self,
        all_files: list[dict[str, Any]],
        plan: dict[str, Any],
        max_files: int,
        include_subject: bool,
    ) -> dict[str, Any]:
        words = [w.strip().lower() for w in plan.get("objective", "").split() if len(w.strip()) > 2]
        if not words:
            words = ["business", "study", "expense", "income", "数据", "创业"]

        scored: list[tuple[int, dict[str, Any]]] = []
        for row in all_files:
            fields = [
                str(row.get("file_name", "")),
                str(row.get("project", "")),
                str(row.get("category", "")),
                str(row.get("extracted_text", ""))[:1500],
            ]
            if include_subject:
                fields.append(str(row.get("subject", "")))
            blob = " ".join(fields).lower()
            score = sum(1 for w in words if w in blob)
            if score > 0:
                scored.append((score, row))

        scored.sort(key=lambda x: x[0], reverse=True)
        selected = [r for _, r in scored[:max_files]] or all_files[: min(max_files, 3)]
        return {
            "count": len(selected),
            "files": selected,
            "titles": [x.get("file_name", "") for x in selected],
        }

    def _fileops_status(self, all_files: list[dict[str, Any]]) -> dict[str, Any]:
        organized = sum(1 for row in all_files if row.get("target_path"))
        pending = len(all_files) - organized
        return {
            "indexed_total": len(all_files),
            "organized": organized,
            "pending": pending,
            "coverage": round((organized / len(all_files)) * 100, 2) if all_files else 0.0,
        }

    def _finance_summary(self, files: list[dict[str, Any]], min_amount: float) -> dict[str, Any]:
        income = 0.0
        expense = 0.0
        for row in files:
            i, e = estimate_money(
                text=str(row.get("extracted_text", "")),
                source=str(row.get("source", "")),
                subject=str(row.get("subject", "")),
                sender=str(row.get("sender", "")),
                created_at=str(row.get("created_at", "")),
                category=str(row.get("category", "")),
                file_name=str(row.get("file_name", "")),
            )
            if i < min_amount:
                i = 0.0
            if e < min_amount:
                e = 0.0
            income += i
            expense += e
        return {
            "income_total": round(income, 2),
            "expense_total": round(expense, 2),
            "net": round(income - expense, 2),
        }

    def _learning_outline(self, files: list[dict[str, Any]], weeks: int, topic_limit: int) -> dict[str, Any]:
        text = "\n".join(str(row.get("extracted_text", ""))[:2000] for row in files)
        keywords = [
            "entrepreneur", "startup", "strategy", "marketing", "finance", "data", "python", "ml", "analysis",
            "创业", "企业", "商业", "数据", "分析", "学习", "课程",
        ]
        counter: Counter[str] = Counter()
        lower = text.lower()
        for kw in keywords:
            counter[kw] += lower.count(kw)
        topics = [k for k, v in counter.most_common(max(1, topic_limit)) if v > 0]
        if not topics:
            topics = ["business fundamentals", "data analysis", "execution planning"]

        week_templates = [
            "Core concepts and key vocabulary",
            "Case studies and applied exercises",
            "Build one practical mini project",
            "Review, reflection, and action plan",
        ]
        outline = []
        for idx in range(max(1, weeks)):
            label = week_templates[min(idx, len(week_templates) - 1)]
            outline.append(f"Week {idx + 1}: {label}")
        return {
            "topics": topics,
            "outline": outline,
        }

    def _business_plan(
        self,
        objective: str,
        files: list[dict[str, Any]],
        backend: str,
        ollama_base_url: str,
        ollama_model: str,
        temperature: float,
        max_context_chars: int,
        plan_style: str,
    ) -> dict[str, Any]:
        chunks = []
        for row in files:
            chunks.append(
                "\n".join(
                    [
                        f"File: {row.get('file_name', '')}",
                        f"Project: {row.get('project', '')}",
                        f"Category: {row.get('category', '')}",
                        f"Text: {str(row.get('extracted_text', ''))[:1200]}",
                    ]
                )
            )
        context = "\n\n---\n\n".join(chunks)[:max_context_chars]
        style_instruction = {
            "concise": "Keep it concise and executive-friendly.",
            "detailed": "Provide more detail per section with actionable steps.",
            "investor": "Use investor-oriented language and add traction assumptions.",
        }.get(plan_style.lower(), "Keep it concise and executive-friendly.")
        prompt = (
            f"Objective: {objective}\n"
            "Please build a business plan with these sections: opportunity, target user, monetization, 30-day roadmap, risks.\n"
            f"Style: {style_instruction}"
        )
        plan_text = self.hermes.answer(
            question=prompt,
            context=context,
            backend=backend,
            ollama_base_url=ollama_base_url,
            ollama_model=ollama_model,
            temperature=temperature,
            timeout_seconds=180,
        )
        return {"plan": plan_text}

    def _build_report(
        self,
        objective: str,
        plan: dict[str, Any],
        retrieved: dict[str, Any],
        reader: dict[str, Any],
        file_ops: dict[str, Any],
        finance: dict[str, Any],
        learning: dict[str, Any],
        business: dict[str, Any],
    ) -> dict[str, Any]:
        action_items = [
            "先补齐未整理文件，再重新运行多代理分析",
            "把 Finance Agent 的净值变化接入周报",
            "按 Learning Agent 的四周大纲推进学习",
        ]
        return {
            "objective": objective,
            "top_projects": plan.get("top_projects", []),
            "retrieved_files": retrieved.get("titles", []),
            "reader": reader,
            "file_ops": file_ops,
            "finance": finance,
            "learning": learning,
            "business_plan": business.get("plan", ""),
            "action_items": action_items,
        }

    def _qa_check(self, report: dict[str, Any], require_business_plan: bool) -> dict[str, Any]:
        checks = {
            "has_projects": bool(report.get("top_projects")),
            "has_finance": "finance" in report,
            "has_learning": "learning" in report,
            "has_reader_summary": bool((report.get("reader") or {}).get("summary", "").strip()),
            "has_actions": bool(report.get("action_items")),
        }
        if require_business_plan:
            checks["has_business_plan"] = bool(report.get("business_plan"))
        passed = all(checks.values())
        return {
            "passed": passed,
            "checks": checks,
            "missing": [k for k, v in checks.items() if not v],
        }
