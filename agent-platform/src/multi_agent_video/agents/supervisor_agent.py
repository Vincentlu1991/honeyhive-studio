from __future__ import annotations

from collections import deque
import json
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Supervisor knowledge base — AI video production expertise
# Based on: LangGraph multi-agent patterns, AnimateDiff optimization guides,
#           RTX 3070 VRAM profiling, Civitai community parameter guides
# ---------------------------------------------------------------------------

# Parameter recommendations by scene complexity
_PARAM_PROFILES = {
    "character_portrait": {
        "steps": 30, "cfg": 7.5, "sampler": "dpmpp_2m karras",
        "resolution": "512x512", "frames": 16,
        "note": "stable face, standard profile"
    },
    "action_scene": {
        "steps": 25, "cfg": 7.0, "sampler": "dpmpp_2m karras",
        "resolution": "512x512", "frames": 16,
        "note": "lower CFG reduces over-saturation in dynamic scenes"
    },
    "landscape": {
        "steps": 30, "cfg": 8.0, "sampler": "dpmpp_2m karras",
        "resolution": "512x768", "frames": 16,
        "note": "higher CFG for landscape detail, portrait orientation"
    },
    "default": {
        "steps": 25, "cfg": 7.5, "sampler": "dpmpp_2m karras",
        "resolution": "512x512", "frames": 16,
        "note": "balanced default for RTX 3070 8GB"
    },
}

# Risk assessment patterns
_RISK_KEYWORDS = {
    "high": ["multiple people", "crowd", "fight", "explosion", "highly detailed face"],
    "medium": ["portrait", "close-up", "hands", "text on screen", "realistic"],
    "low": ["landscape", "nature", "abstract", "background", "slow movement"],
}


class SupervisorAgent:
    """主管Agent — AI视频制作全局统筹与优化专家

    知识基础 (引用来源):
    ┌───────────────────────────────────────────────────────────────────┐
    │ LangGraph     → 多步骤调度、状态管理、重试策略           │
    │ AnimateDiff   → RTX 3070 8GB 最佳参数组合                 │
    │ Civitai       → CFG/steps 经验数据，不同场景参数策略     │
    │ 工程最佳实践 → 成本控制、风险评估、错误诊断分级     │
    └───────────────────────────────────────────────────────────────────┘
    """

    def __init__(self, llm=None, history_file: str | None = None) -> None:
        self.llm = llm
        self._run_history: deque[dict[str, Any]] = deque(maxlen=30)
        self._history_file = Path(history_file).expanduser() if history_file else None
        self._load_history_from_disk()

    def register_run_outcome(self, qa_report: dict[str, Any], retries_done: int, supervision_plan: dict[str, Any] | None) -> None:
        entry = {
            "passed": bool(qa_report.get("passed", False)),
            "face": int(qa_report.get("face", 0)),
            "motion": int(qa_report.get("motion", 0)),
            "artifact": int(qa_report.get("artifact", 0)),
            "retries_done": int(retries_done),
            "cost_tier": str((supervision_plan or {}).get("cost_tier", "unknown")),
        }
        self._run_history.append(entry)
        self._append_history_to_disk(entry)

    def get_history_snapshot(self) -> dict[str, Any]:
        recent = list(self._run_history)
        if not recent:
            return {
                "sample_size": 0,
                "pass_rate": 0.0,
                "avg_retries": 0.0,
                "avg_face": 0.0,
                "avg_motion": 0.0,
            }

        n = len(recent)
        pass_rate = sum(1 for r in recent if r["passed"]) / n
        avg_retries = sum(r["retries_done"] for r in recent) / n
        avg_face = sum(r["face"] for r in recent) / n
        avg_motion = sum(r["motion"] for r in recent) / n
        return {
            "sample_size": n,
            "pass_rate": round(pass_rate, 3),
            "avg_retries": round(avg_retries, 3),
            "avg_face": round(avg_face, 3),
            "avg_motion": round(avg_motion, 3),
        }

    def make_supervision_plan(
        self,
        user_brief: str,
        production_plan: dict[str, Any] | None,
        image_analysis: dict[str, Any] | None,
        max_retries: int,
    ) -> dict[str, Any]:
        """Build a structured run-level strategy for orchestration and cost control."""
        profile = self._detect_profile(user_brief)
        risk = self._assess_risk(user_brief)

        has_image = bool(image_analysis)
        workflow_type = (production_plan or {}).get("workflow_type", "text-to-video")
        complexity = self._estimate_complexity(user_brief=user_brief, workflow_type=workflow_type, has_image=has_image)

        # Local-first rough runtime estimate for RTX 3070 8GB.
        base_runtime_sec = 85 if workflow_type == "image-to-video" else 70
        if complexity == "high":
            base_runtime_sec += 40
        elif complexity == "medium":
            base_runtime_sec += 20

        retry_policy = {
            "max_retries": max_retries,
            "seed_step": 1,
            "on_face_low": "tighten identity lock and reduce motion intensity",
            "on_motion_low": "simplify motion beat and enforce stable camera",
            "on_artifact_high": "reduce cfg by 0.5 and increase steps by 5",
        }

        history = self.get_history_snapshot()
        adaptive_max_retries = self._adaptive_retry_budget(
            base=max_retries,
            cost_tier=self._cost_tier(base_runtime_sec, max_retries, complexity),
            history=history,
        )

        return {
            "profile": profile,
            "risk": risk,
            "complexity": complexity,
            "workflow_type": workflow_type,
            "has_image": has_image,
            "cost_tier": self._cost_tier(base_runtime_sec, max_retries, complexity),
            "estimated_runtime_sec": base_runtime_sec,
            "identity_lock_required": has_image,
            "retry_policy": retry_policy,
            "adaptive_max_retries": adaptive_max_retries,
            "history_snapshot": history,
            "prompt_directives": self._prompt_directives(risk=risk, complexity=complexity, has_image=has_image),
        }

    def refine_prompt_pack(
        self,
        prompt_pack: dict[str, Any],
        supervision_plan: dict[str, Any] | None,
        retry_hint: str | None = None,
    ) -> dict[str, Any]:
        """Apply supervisor-level prompt constraints without changing public PromptPack API."""
        if not supervision_plan:
            return prompt_pack

        positive = str(prompt_pack.get("positive", ""))
        negative = str(prompt_pack.get("negative", ""))
        motion = str(prompt_pack.get("motion_prompt", ""))

        directives = supervision_plan.get("prompt_directives", [])
        if directives:
            positive = self._append_unique_phrases(positive, directives)

        if supervision_plan.get("identity_lock_required"):
            positive = self._append_unique_phrases(
                positive,
                [
                    "same person as reference image",
                    "keep facial identity",
                    "consistent hairstyle and clothing",
                ],
            )
            negative = self._append_unique_phrases(
                negative,
                [
                    "identity drift",
                    "face swap",
                    "different person",
                    "age change",
                    "hairstyle change",
                    "outfit inconsistency",
                ],
            )

        if retry_hint:
            motion = self._append_unique_phrases(motion, [retry_hint])

        positive = self._trim_prompt(positive, 900)
        negative = self._trim_prompt(negative, 1100)
        motion = self._trim_prompt(motion, 320)

        result = dict(prompt_pack)
        result["positive"] = positive
        result["negative"] = negative
        result["motion_prompt"] = motion
        return result

    def _append_unique_phrases(self, base: str, extras: list[str]) -> str:
        parts = [p.strip() for p in str(base).split(",") if p.strip()]
        seen = {p.lower() for p in parts}
        for item in extras:
            token = str(item).strip()
            if not token:
                continue
            key = token.lower()
            if key in seen:
                continue
            parts.append(token)
            seen.add(key)
        return ", ".join(parts)

    def _trim_prompt(self, text: str, max_chars: int) -> str:
        t = str(text).strip().replace("\n", " ")
        if len(t) <= max_chars:
            return t
        clipped = t[:max_chars]
        last_comma = clipped.rfind(",")
        if last_comma > int(max_chars * 0.7):
            clipped = clipped[:last_comma]
        return clipped.rstrip(", ")

    def decide_retry(
        self,
        qa_report: dict[str, Any],
        retries_done: int,
        max_retries: int,
        supervision_plan: dict[str, Any] | None,
        strict_zero_retry: bool = False,
    ) -> dict[str, Any]:
        """Centralized retry decision with quality + cost guardrails."""
        passed = bool(qa_report.get("passed", False))
        if passed:
            return {
                "should_retry": False,
                "reason": "qa_passed",
                "retry_hint": "",
            }

        adaptive_max = int((supervision_plan or {}).get("adaptive_max_retries", max_retries))
        if strict_zero_retry and max_retries <= 0:
            retry_ceiling = 0
        else:
            retry_ceiling = max(0, min(adaptive_max, max_retries))
        if retries_done >= retry_ceiling:
            return {
                "should_retry": False,
                "reason": "retry_budget_exhausted",
                "retry_hint": "",
            }

        face = int(qa_report.get("face", 0))
        motion = int(qa_report.get("motion", 0))
        artifact = int(qa_report.get("artifact", 0))
        issue_tags = [str(t) for t in qa_report.get("issue_tags", [])]
        recommended_actions = [str(a) for a in qa_report.get("recommended_actions", [])]

        hints = []
        if "face_consistency" in issue_tags or face < 6:
            hints.append("reduce motion intensity and prioritize identity consistency")
        if "motion_instability" in issue_tags or motion < 6:
            hints.append("use one clear motion beat with stable camera")
        if "artifact_noise" in issue_tags or artifact > 5:
            hints.append("reduce cfg by 0.5 and increase steps by 5")
        if "incomplete_frames" in issue_tags:
            hints.append("reduce complexity to secure full frame sequence")
        if recommended_actions:
            hints.extend(recommended_actions[:2])
        if not hints:
            hints.append("change seed and keep composition stable")

        # Risk-aware guardrail: high risk + very low quality gets only one rescue retry.
        risk = str((supervision_plan or {}).get("risk", "low"))
        if risk == "high" and retries_done >= 1 and (face <= 3 or motion <= 3):
            return {
                "should_retry": False,
                "reason": "high_risk_low_quality_stop",
                "retry_hint": "",
            }

        return {
            "should_retry": True,
            "reason": "qa_below_threshold",
            "retry_hint": "; ".join(hints),
        }

    def _estimate_complexity(self, user_brief: str, workflow_type: str, has_image: bool) -> str:
        b = user_brief.lower()
        score = 0
        if workflow_type == "image-to-video":
            score += 1
        if has_image:
            score += 1
        if any(k in b for k in ("fight", "crowd", "explosion", "multiple people", "fast")):
            score += 2
        if any(k in b for k in ("portrait", "face", "close-up", "realistic")):
            score += 1

        if score >= 4:
            return "high"
        if score >= 2:
            return "medium"
        return "low"

    def _prompt_directives(self, risk: str, complexity: str, has_image: bool) -> list[str]:
        directives = ["temporally consistent", "stable composition", "no flickering"]
        if has_image:
            directives.append("preserve uploaded reference identity")
        if risk in ("medium", "high"):
            directives.append("avoid abrupt camera movement")
        if complexity == "high":
            directives.append("single dominant motion beat")
        return directives

    def _cost_tier(self, est_runtime_sec: int, max_retries: int, complexity: str) -> str:
        score = est_runtime_sec + max_retries * 25 + (20 if complexity == "high" else 0)
        if score >= 190:
            return "high"
        if score >= 130:
            return "medium"
        return "low"

    def _adaptive_retry_budget(self, base: int, cost_tier: str, history: dict[str, Any]) -> int:
        """Adapt retry budget from recent outcomes while respecting local cost constraints."""
        if history.get("sample_size", 0) < 4:
            return base

        pass_rate = float(history.get("pass_rate", 0.0))
        avg_retries = float(history.get("avg_retries", 0.0))

        # Stable runs: reduce retries to cut cost/latency.
        if pass_rate >= 0.85 and avg_retries <= 0.5:
            return max(1, base - 1)

        # Unstable but affordable runs: allow one extra rescue retry.
        if pass_rate <= 0.45 and cost_tier in ("low", "medium"):
            return min(base + 1, 4)

        # High-cost jobs keep conservative retry cap.
        if cost_tier == "high":
            return max(1, base)

        return base

    def _load_history_from_disk(self) -> None:
        if self._history_file is None or not self._history_file.exists():
            return

        try:
            lines = self._history_file.read_text(encoding="utf-8").splitlines()
        except OSError:
            return

        # Keep only recent records and ignore malformed lines.
        for line in lines[-self._run_history.maxlen :]:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            if not isinstance(record, dict):
                continue

            self._run_history.append(
                {
                    "passed": bool(record.get("passed", False)),
                    "face": int(record.get("face", 0)),
                    "motion": int(record.get("motion", 0)),
                    "artifact": int(record.get("artifact", 0)),
                    "retries_done": int(record.get("retries_done", 0)),
                    "cost_tier": str(record.get("cost_tier", "unknown")),
                }
            )

    def _append_history_to_disk(self, entry: dict[str, Any]) -> None:
        if self._history_file is None:
            return

        try:
            self._history_file.parent.mkdir(parents=True, exist_ok=True)
            with self._history_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            # Persistence failure should never block pipeline execution.
            return

    def _build_system_prompt(self) -> str:
        return (
            "你是AI视频生成平台的首席主管Agent，拥有丰富的实战经验。\n\n"
            "你的专业能力：\n"
            "1. 参数优化: 知道不同场景类型对应的最佳CFG/steps/分辨率组合\n"
            "2. 风险评估: 提前识别哪些场景容易失败（对称面部、太多人、文字）\n"
            "3. 成本意识: RTX 3070 8GB 内存限制，16帧@512px 大约占用5-6GB\n"
            "4. 错误诊断: 能快速定位400错误、参数异常、节点类型错误的根因\n"
            "5. 重试策略: 根据QA分数提供具体的参数调整方案\n\n"
            "回答规则：\n"
            "- 具体可执行：提供具体数字和参数\n"
            "- 分级建议: 先最容易改变的（seed），再到最复杂的（模型换人）\n"
            "- 如果多次成功: 指出下一步可进行的质量提升（如 steps 20→30）\n"
            "- 回答用中文，专业且简洁"
        )

    def _detect_profile(self, user_brief: str) -> dict[str, Any]:
        """Detect best parameter profile from brief keywords."""
        b = user_brief.lower()
        if any(k in b for k in ("portrait", "face", "close-up", "character")):
            return _PARAM_PROFILES["character_portrait"]
        if any(k in b for k in ("action", "fight", "run", "explode", "battle")):
            return _PARAM_PROFILES["action_scene"]
        if any(k in b for k in ("landscape", "mountain", "ocean", "forest", "sky")):
            return _PARAM_PROFILES["landscape"]
        return _PARAM_PROFILES["default"]

    def _assess_risk(self, user_brief: str) -> str:
        """Return risk level based on scene complexity."""
        b = user_brief.lower()
        for level, keywords in _RISK_KEYWORDS.items():
            if any(k in b for k in keywords):
                return level
        return "low"

    def chat(self, message: str) -> str:
        if self.llm is None:
            return (
                "主管Agent建议："
                "将执行 Story Agent→Prompt Agent→Builder Agent→ComfyUI渲染→QA Agent 完整流程。\n"
                "若QA不达标：先调整 motion prompt，再换 seed，最后考虑改变 CFG/steps 参数。"
            )
        system_prompt = self._build_system_prompt()
        return self.llm.chat(system_prompt=system_prompt, user_prompt=message, temperature=0.2)

    def plan(self, user_brief: str) -> str:
        """分析需求，返回执行计划 + 参数建议 + 风险评估"""
        profile = self._detect_profile(user_brief)
        risk = self._assess_risk(user_brief)

        plan_text = (
            f"计划: steps={profile['steps']}, CFG={profile['cfg']}, "
            f"sampler={profile['sampler']}, 分辨率={profile['resolution']}, "
            f"帧数={profile['frames']}\n"
            f"风险等级: {risk} | 备注: {profile['note']}"
        )

        if self.llm is None:
            return plan_text

        system_prompt = self._build_system_prompt()
        user_prompt = (
            f"用户需求：{user_brief}\n\n"
            f"初步参数建议：{plan_text}\n\n"
            "请分析并制定执行计划：\n"
            "1. 将需求拆解为具体视觉元素\n"
            "2. 识别潜在技术风险（面部一致性、运动复杂度）\n"
            "3. 确认或调整参数建议\n"
            "4. 预估执行时间和失败风险"
        )
        return self.llm.chat(system_prompt=system_prompt, user_prompt=user_prompt, temperature=0.2)

    def advise_retry(self, qa_report: dict[str, Any], attempt: int) -> str:
        """根据QA结果提供针对性重试建议"""
        face = qa_report.get('face', 0)
        motion = qa_report.get('motion', 0)
        artifact = qa_report.get('artifact', 0)

        # Build data-driven advice without LLM
        tips = []
        if face < 6:
            tips.append("face<6: 将 seed 加 1 再试，或增加负向提示词中 face-related 标签")
        if motion < 6:
            tips.append("motion<6: 简化 motion_prompt，正向提示词加入 'smooth motion, temporally consistent'")
        if artifact > 5:
            tips.append(f"artifact={artifact} (问题多): 调低 CFG 0.5，或增加 steps 5")
        if not tips:
            tips.append("各项接近预期，建议增加 steps 5 提升细节")

        base_advice = f"第{attempt}次重试: " + "; ".join(tips)

        if self.llm is None:
            return base_advice

        system_prompt = self._build_system_prompt()
        user_prompt = (
            f"第{attempt}次渲染QA结果：\n"
            f"- 面部: {face}/10\n"
            f"- 运动: {motion}/10\n"
            f"- 特效清洁度: {artifact}/10 (越高=越少问题)\n"
            f"- QA备注: {qa_report.get('notes', 'N/A')}\n\n"
            f"初步建议: {base_advice}\n\n"
            "请给出最具针对性的参数调整建议，按优先级较高到较低排列"
        )
        return self.llm.chat(system_prompt=system_prompt, user_prompt=user_prompt, temperature=0.2)

    def summarize_run(self, graph_state: dict[str, Any]) -> str:
        qa = graph_state.get("qa_report", {})
        status = graph_state.get("render_status", "unknown")
        retries = graph_state.get("retry_count", 0)
        scene = graph_state.get("scene_spec", {})
        prompt = graph_state.get("prompt_pack", {})

        qa_passed = qa.get('passed', False)
        face_score = qa.get('face', 'N/A')
        motion_score = qa.get('motion', 'N/A')
        artifact_score = qa.get('artifact', 'N/A')

        # Quality grade based on combined scores
        if face_score != 'N/A' and motion_score != 'N/A':
            avg = (face_score + motion_score) / 2
            grade = "优秀 ★★★" if avg >= 8 else "良好 ★★" if avg >= 6 else "需改进 ★"
        else:
            grade = "未知"

        summary_lines = [
            f"🎬 **渲染状态**: {'success ✅' if status == 'completed' else status}",
            f"🔁 **重试次数**: {retries}",
            f"🎨 **场景**: {str(scene.get('scene', 'N/A'))[:70]}",
            f"💬 **正向提示词**: {str(prompt.get('positive', 'N/A'))[:80]}...",
            f"📊 **质检结果** ({'**通过**' if qa_passed else '**未通过**'}): "
            f"面部={face_score}/10 | 运动={motion_score}/10 | 特效清洁={artifact_score}/10",
            f"🏆 **综合评级**: {grade}",
        ]

        if qa.get('notes'):
            summary_lines.append(f"📝 **QA备注**: {qa['notes']}")

        if self.llm is not None:
            try:
                advice = self.llm.chat(
                    system_prompt=self._build_system_prompt(),
                    user_prompt=(
                        f"视频已渲染{'success' if status == 'completed' else 'failed'}，"
                        f"QA评分: 面部{face_score}, 运动{motion_score}, 特效{artifact_score}，"
                        f"{'qa通过' if qa_passed else 'qa未通过'}。\n"
                        "请给出一句总结和1-2条具体的下一步改进建议。"
                    ),
                    temperature=0.2
                )
                summary_lines.append(f"\n🧠 **主管建议**: {advice}")
            except Exception:
                pass

        return "\n".join(summary_lines)
