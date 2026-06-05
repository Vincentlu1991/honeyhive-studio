from __future__ import annotations

from typing import Any, Literal, TypedDict

from langgraph.graph import END, StateGraph

from multi_agent_video.agents import (
    ComfyUIBuilderAgent,
    ImageAnalysisAgent,
    ProductionPlannerAgent,
    PromptEngineerAgent,
    StoryAgent,
    SupervisorAgent,
    VideoQAAgent,
)
from multi_agent_video.comfyui_client import ComfyUIClient
from multi_agent_video.config import AppConfig
from multi_agent_video.shared_capabilities import SharedCapabilitiesService


class GraphState(TypedDict, total=False):
    user_brief: str
    input_image_path: str
    workflow_path: str
    evidence_documents: list[dict[str, Any]]
    strict_reference_mode: bool
    shared_context: dict[str, Any]
    shared_context_errors: list[dict[str, Any]]
    image_analysis: dict[str, Any]
    production_plan: dict[str, Any]
    supervision_plan: dict[str, Any]
    seed: int
    retry_count: int
    retry_hint: str
    scene_spec: dict[str, Any]
    prompt_pack: dict[str, Any]
    workflow_request: dict[str, Any]
    workflow_resolution: dict[str, Any]
    render_job_id: str
    render_status: str
    render_output: dict[str, Any]
    qa_report: dict[str, Any]
    supervisor_decision: dict[str, Any]
    supervision_history: dict[str, Any]


class VideoPipeline:
    def __init__(
        self,
        config: AppConfig,
        image_agent: ImageAnalysisAgent | None = None,
        production_planner_agent: ProductionPlannerAgent | None = None,
        story_agent: StoryAgent | None = None,
        prompt_agent: PromptEngineerAgent | None = None,
        builder_agent: ComfyUIBuilderAgent | None = None,
        qa_agent: VideoQAAgent | None = None,
        supervisor_agent: SupervisorAgent | None = None,
        shared_capabilities: SharedCapabilitiesService | None = None,
    ) -> None:
        self.config = config
        self.image_agent = image_agent or ImageAnalysisAgent()
        self.production_planner_agent = production_planner_agent or ProductionPlannerAgent()
        self.story_agent = story_agent or StoryAgent()
        self.prompt_agent = prompt_agent or PromptEngineerAgent()
        self.builder_agent = builder_agent or ComfyUIBuilderAgent()
        self.qa_agent = qa_agent or VideoQAAgent()
        self.supervisor_agent = supervisor_agent or SupervisorAgent()
        self.shared_capabilities = shared_capabilities or SharedCapabilitiesService()
        self.client = ComfyUIClient(config.comfyui_base_url, config.comfyui_timeout_seconds)

    def _shared_context_node(self, state: GraphState) -> GraphState:
        if not self.config.enable_shared_context_injection:
            return {}

        docs = state.get("evidence_documents") or []
        if not isinstance(docs, list) or not docs:
            return {}

        read_result = self.shared_capabilities.read_documents(docs)
        rank_result = self.shared_capabilities.rank_context(
            query=state.get("user_brief", ""),
            docs=read_result.docs,
            top_k=self.config.shared_context_top_k,
        )

        context_lines: list[str] = []
        for item in rank_result.contexts:
            title = str(item.get("title", "evidence"))
            snippet = str(item.get("snippet", "")).strip()
            if not snippet:
                continue
            context_lines.append(f"[{title}] {snippet}")

        all_errors = read_result.errors + rank_result.errors
        serialized_errors = [
            {
                "code": e.code,
                "message": e.message,
                "retryable": e.retryable,
                "reference_id": e.reference_id,
            }
            for e in all_errors
        ]

        return {
            "shared_context": {
                "context_text": "\n".join(context_lines).strip(),
                "redaction_counts": read_result.redaction_counts,
                "ranked_count": len(rank_result.contexts),
            },
            "shared_context_errors": serialized_errors,
        }

    def _resolve_workflow_path(self, requested_path: str) -> dict[str, Any]:
        workflow_path = str(requested_path or "").strip() or self.config.comfyui_workflow_path
        lowered = workflow_path.lower()

        resolution = {
            "requested_workflow_path": workflow_path,
            "selected_workflow_path": workflow_path,
            "fallback_enabled": bool(self.config.enable_workflow_fallback),
            "fallback_used": False,
            "fallback_reason": "",
            "ltx_dependencies_ready": None,
            "ltx_dependency_diagnostics": {},
        }

        if not self.config.enable_workflow_fallback:
            resolution["fallback_reason"] = "fallback_disabled"
            return resolution

        is_ltx_workflow = "ltx" in lowered
        if not is_ltx_workflow:
            resolution["fallback_reason"] = "not_ltx_workflow"
            return resolution

        diagnostics = self.client.get_ltx_dependency_diagnostics()
        ready = bool(diagnostics.get("ready", False))
        reason = str(diagnostics.get("reason", "unknown"))
        resolution["ltx_dependencies_ready"] = ready
        resolution["ltx_dependency_diagnostics"] = diagnostics

        if ready:
            resolution["fallback_reason"] = "ok"
            return resolution

        fallback = str(self.config.fallback_workflow_path).strip()
        if fallback:
            print(f"LTX dependencies unavailable ({reason}); falling back to {fallback}")
            resolution["selected_workflow_path"] = fallback
            resolution["fallback_used"] = True
            resolution["fallback_reason"] = reason
            return resolution

        resolution["fallback_reason"] = f"{reason}_no_fallback_path"
        return resolution

    def _image_analysis_node(self, state: GraphState) -> GraphState:
        image_path = state.get("input_image_path")
        if not image_path:
            return {}
        analysis = self.image_agent.run(image_path, state.get("user_brief", ""))
        return {"image_analysis": analysis.model_dump()}

    def _production_plan_node(self, state: GraphState) -> GraphState:
        plan = self.production_planner_agent.run(
            user_brief=state.get("user_brief", ""),
            image_analysis=state.get("image_analysis"),
            requested_workflow=state.get("workflow_path"),
        )
        return {"production_plan": plan.model_dump()}

    def _supervision_plan_node(self, state: GraphState) -> GraphState:
        plan = self.supervisor_agent.make_supervision_plan(
            user_brief=state.get("user_brief", ""),
            production_plan=state.get("production_plan"),
            image_analysis=state.get("image_analysis"),
            max_retries=self.config.max_render_retries,
        )
        return {"supervision_plan": plan}

    def _story_node(self, state: GraphState) -> GraphState:
        brief = state.get("user_brief", "")
        image_analysis = state.get("image_analysis")
        production_plan = state.get("production_plan")
        if image_analysis:
            image_context = image_analysis.get("prompt_context", "")
            brief = f"{brief}\n\nImage analysis context: {image_context}".strip()
        if production_plan:
            plan_context = production_plan.get("prompt_context", "")
            brief = f"{brief}\n\nProduction context: {plan_context}".strip()
        shared_context = state.get("shared_context") or {}
        shared_text = str(shared_context.get("context_text") or "").strip()
        if shared_text:
            brief = f"{brief}\n\nDocument evidence context:\n{shared_text}".strip()
        # Keep story generation focused on user scene semantics only.
        # Retry/ops directives are applied later at prompt and supervisor stages.
        scene_spec = self.story_agent.run(brief)
        return {"scene_spec": scene_spec.model_dump()}

    def _prompt_node(self, state: GraphState) -> GraphState:
        from multi_agent_video.models import SceneSpec

        scene_spec = SceneSpec.model_validate(state["scene_spec"])
        workflow_type = str((state.get("production_plan") or {}).get("workflow_type", ""))
        issue_tags = list((state.get("qa_report") or {}).get("issue_tags", []))
        prompt_pack = self.prompt_agent.run(
            scene_spec,
            workflow_type=workflow_type,
            issue_tags=issue_tags,
            retry_hint=state.get("retry_hint"),
            strict_mode=bool(state.get("strict_reference_mode", False)),
        )
        refined = self.supervisor_agent.refine_prompt_pack(
            prompt_pack=prompt_pack.model_dump(),
            supervision_plan=state.get("supervision_plan"),
            retry_hint=state.get("retry_hint"),
        )
        shared_context = state.get("shared_context") or {}
        evidence_context = str(shared_context.get("context_text") or "").strip()
        if evidence_context:
            positive = str(refined.get("positive", "")).strip()
            merged_positive = f"{positive}, evidence grounded details: {evidence_context[:420]}".strip(", ")
            refined["positive"] = merged_positive
        return {"prompt_pack": refined}

    def _builder_node(self, state: GraphState) -> GraphState:
        from multi_agent_video.models import PromptPack

        def _cap_text(text: str, max_chars: int) -> str:
            t = str(text or "").strip()
            if len(t) <= max_chars:
                return t
            return t[:max_chars].rstrip(", ")

        prompt_pack = PromptPack.model_validate(state["prompt_pack"])
        strict_mode = bool(state.get("strict_reference_mode", False))
        if state.get("input_image_path"):
            motion_bridge = _cap_text(prompt_pack.motion_prompt, 320)
            # Keep identity lock explicit for image-to-video branches.
            prompt_pack = PromptPack(
                positive=(
                    "same person as uploaded reference photo, keep facial identity, "
                    "consistent hairstyle and clothing, preserve character identity, "
                    f"{_cap_text(prompt_pack.positive, 780)}, {motion_bridge}"
                ),
                negative=(
                    f"{prompt_pack.negative}, identity drift, face swap, different person, "
                    "age change, hairstyle change, outfit inconsistency"
                ),
                motion_prompt=prompt_pack.motion_prompt,
                lora_tags=prompt_pack.lora_tags,
            )

            if strict_mode:
                # Strict reference mode: preserve identity while keeping motion from prompt.
                prompt_pack = PromptPack(
                    positive=(
                        f"{prompt_pack.positive}, close identity match to uploaded image, "
                        "preserve facial geometry, preserve skin tone, preserve outfit details"
                    ),
                    negative=(
                        f"{prompt_pack.negative}, identity drift, face swap, different person"
                    ),
                    motion_prompt=prompt_pack.motion_prompt,
                    lora_tags=prompt_pack.lora_tags,
                )

            prompt_pack = PromptPack(
                positive=_cap_text(prompt_pack.positive, 950),
                negative=_cap_text(prompt_pack.negative, 1200),
                motion_prompt=_cap_text(prompt_pack.motion_prompt, 420),
                lora_tags=prompt_pack.lora_tags,
            )

        seed = int(state.get("seed", 42)) + int(state.get("retry_count", 0))
        workflow_resolution = self._resolve_workflow_path(
            state.get("workflow_path", self.config.comfyui_workflow_path)
        )
        workflow_path = str(workflow_resolution.get("selected_workflow_path", self.config.comfyui_workflow_path))
        workflow_request = self.builder_agent.run(
            workflow_path,
            prompt_pack,
            seed,
            image_path=state.get("input_image_path"),
        )
        return {
            "workflow_request": workflow_request.model_dump(),
            "workflow_resolution": workflow_resolution,
        }

    def _render_node(self, state: GraphState) -> GraphState:
        from multi_agent_video.models import PromptPack

        workflow_path = state["workflow_request"]["workflow_path"]
        workflow = self.client.load_workflow(workflow_path)

        # Precise node injection if available
        payload = state["workflow_request"]["prompt_payload"]
        prompt_pack = PromptPack(
            positive=payload["positive"],
            negative=payload["negative"],
            motion_prompt=payload["motion_prompt"],
            lora_tags=payload.get("lora_tags", []),
        )
        seed = int(payload["seed"])

        workflow = self.builder_agent.inject_to_workflow(
            workflow,
            prompt_pack,
            seed,
            image_filename=payload.get("image_filename"),
        )

        if self.config.enable_debug_workflow_dump:
            import json
            from pathlib import Path

            debug_path = Path(self.config.output_dir) / "debug_workflow.json"
            debug_path.parent.mkdir(parents=True, exist_ok=True)
            with open(debug_path, "w", encoding="utf-8") as f:
                json.dump(workflow, f, indent=2, ensure_ascii=False)
            print(f"🔍 Debug: Modified workflow saved to {debug_path}")

        prompt_id = self.client.submit_prompt(workflow)
        result = self.client.wait_for_completion(prompt_id)
        workflow_resolution = state.get("workflow_resolution")
        if isinstance(result, dict) and isinstance(workflow_resolution, dict):
            result.setdefault("workflow_resolution", workflow_resolution)
        return {
            "render_job_id": prompt_id,
            "render_status": "completed",
            "render_output": result,
        }

    def _qa_node(self, state: GraphState) -> GraphState:
        qa = self.qa_agent.run(state.get("render_output", {}))
        return {"qa_report": qa.model_dump()}

    def _supervisor_review_node(self, state: GraphState) -> GraphState:
        decision = self.supervisor_agent.decide_retry(
            qa_report=state.get("qa_report", {}),
            retries_done=int(state.get("retry_count", 0)),
            max_retries=self.config.max_render_retries,
            supervision_plan=state.get("supervision_plan"),
            strict_zero_retry=self.config.strict_zero_retry,
        )

        # Record completed runs into supervisor history to support adaptive retries.
        if not bool(decision.get("should_retry", False)):
            self.supervisor_agent.register_run_outcome(
                qa_report=state.get("qa_report", {}),
                retries_done=int(state.get("retry_count", 0)),
                supervision_plan=state.get("supervision_plan"),
            )

        return {
            "supervisor_decision": decision,
            "supervision_history": self.supervisor_agent.get_history_snapshot(),
        }

    def _route_after_qa(self, state: GraphState) -> Literal["retry", "done"]:
        decision = state.get("supervisor_decision", {})
        if bool(decision.get("should_retry", False)):
            return "retry"
        return "done"

    def _retry_node(self, state: GraphState) -> GraphState:
        decision = state.get("supervisor_decision", {})
        return {
            "retry_count": int(state.get("retry_count", 0)) + 1,
            "retry_hint": str(decision.get("retry_hint", "")).strip(),
        }

    def build(self):
        graph = StateGraph(GraphState)
        graph.add_node("node_image_analysis", self._image_analysis_node)
        graph.add_node("node_production_plan", self._production_plan_node)
        graph.add_node("node_shared_context", self._shared_context_node)
        graph.add_node("node_supervision_plan", self._supervision_plan_node)
        graph.add_node("node_story", self._story_node)
        graph.add_node("node_prompt", self._prompt_node)
        graph.add_node("node_builder", self._builder_node)
        graph.add_node("node_render", self._render_node)
        graph.add_node("node_qa", self._qa_node)
        graph.add_node("node_supervisor_review", self._supervisor_review_node)
        graph.add_node("node_retry", self._retry_node)

        graph.set_entry_point("node_image_analysis")
        graph.add_edge("node_image_analysis", "node_production_plan")
        graph.add_edge("node_production_plan", "node_shared_context")
        graph.add_edge("node_shared_context", "node_supervision_plan")
        graph.add_edge("node_supervision_plan", "node_story")
        graph.add_edge("node_story", "node_prompt")
        graph.add_edge("node_prompt", "node_builder")
        graph.add_edge("node_builder", "node_render")
        graph.add_edge("node_render", "node_qa")
        graph.add_edge("node_qa", "node_supervisor_review")

        graph.add_conditional_edges(
            "node_supervisor_review",
            self._route_after_qa,
            {
                "retry": "node_retry",
                "done": END,
            },
        )
        graph.add_edge("node_retry", "node_prompt")

        return graph.compile()
