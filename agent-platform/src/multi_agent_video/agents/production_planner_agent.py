from __future__ import annotations

from pathlib import Path
from typing import Any

from multi_agent_video.models import ProductionPlan


class ProductionPlannerAgent:
    """Plan a generation run as a sellable video production job."""

    def __init__(self, llm=None) -> None:
        self.llm = llm

    def _is_human_subject(self, text: str) -> bool:
        t = (text or "").lower()
        keywords = (
            "girl", "woman", "man", "person", "human", "portrait", "face", "dance",
            "少女", "女生", "女人", "男人", "人物", "人像", "脸", "跳舞", "舞蹈",
        )
        return any(k in t for k in keywords)

    def _default_workflow_for_brief(self, brief: str, has_image: bool) -> str:
        if has_image and self._is_human_subject(brief):
            # Prefer stable identity-preserving workflow for realistic human i2v.
            return str((Path(__file__).resolve().parents[4] / "workflow_sd15_i2v_two_stage.json").resolve())
        if has_image:
            return "workflow_ltxv_img2video_test.json"
        return "configured default workflow"

    def run(
        self,
        user_brief: str,
        image_analysis: dict[str, Any] | None = None,
        requested_workflow: str | None = None,
    ) -> ProductionPlan:
        brief = user_brief.strip() or "Create a short cinematic AI video."
        has_image = bool(image_analysis)
        workflow_type = "image-to-video" if has_image else "text-to-video"
        requested = str(requested_workflow or "").strip()
        recommended_workflow = requested or self._default_workflow_for_brief(brief, has_image)

        target_format = self._target_format(brief, image_analysis)
        motion_strategy = self._motion_strategy(brief, has_image)
        quality_risks = self._quality_risks(brief, has_image)
        commercial_notes = self._commercial_notes(workflow_type)
        complexity = self._complexity_level(brief, has_image)
        cost_band = self._cost_band(workflow_type, complexity)

        prompt_context = (
            f"Production plan: {workflow_type}; target format: {target_format}; "
            f"workflow: {recommended_workflow}; motion strategy: {motion_strategy}; "
            f"quality risks: {', '.join(quality_risks)}; "
            f"complexity: {complexity}; cost band: {cost_band}; "
            f"commercial notes: {', '.join(commercial_notes)}."
        )

        return ProductionPlan(
            creative_goal=brief,
            target_format=target_format,
            workflow_type=workflow_type,
            recommended_workflow=recommended_workflow,
            motion_strategy=motion_strategy,
            quality_risks=quality_risks,
            commercial_notes=commercial_notes,
            prompt_context=prompt_context,
        )

    def _target_format(self, brief: str, image_analysis: dict[str, Any] | None) -> str:
        text = brief.lower()
        if "tiktok" in text or "shorts" in text or "reels" in text:
            return "vertical short-form social clip"
        if image_analysis:
            orientation = image_analysis.get("orientation")
            if orientation == "portrait":
                return "portrait reference-led clip"
            if orientation == "landscape":
                return "landscape cinematic clip"
        return "short cinematic preview clip"

    def _motion_strategy(self, brief: str, has_image: bool) -> str:
        text = brief.lower()
        if has_image:
            return "preserve reference identity; use subtle camera, expression, lighting, and atmosphere motion"
        if any(word in text for word in ("fast", "fight", "run", "battle", "explosion")):
            return "simplify action into one clear motion beat to protect temporal coherence"
        return "use one stable camera move and one subject motion beat"

    def _quality_risks(self, brief: str, has_image: bool) -> list[str]:
        text = brief.lower()
        risks = ["temporal flicker", "workflow node mismatch"]
        if has_image:
            risks.extend(["identity drift", "reference image not present in ComfyUI input folder"])
        if any(word in text for word in ("face", "portrait", "girl", "woman", "man", "person")):
            risks.append("face consistency")
        if any(word in text for word in ("text", "logo", "brand")):
            risks.append("text/logo distortion")
        return risks

    def _commercial_notes(self, workflow_type: str) -> list[str]:
        notes = [
            "store source image and prompt metadata for reproducibility",
            "track render failures and latency for client delivery SLAs",
            "review output rights and user-uploaded asset ownership before delivery",
        ]
        if workflow_type == "image-to-video":
            notes.append("record explicit user permission for uploaded reference images")
        return notes

    def _complexity_level(self, brief: str, has_image: bool) -> str:
        text = brief.lower()
        score = 0
        if has_image:
            score += 1
        if any(word in text for word in ("fight", "explosion", "crowd", "fast", "complex")):
            score += 2
        if any(word in text for word in ("portrait", "face", "realistic", "cinematic")):
            score += 1

        if score >= 3:
            return "high"
        if score >= 2:
            return "medium"
        return "low"

    def _cost_band(self, workflow_type: str, complexity: str) -> str:
        if workflow_type == "image-to-video" and complexity == "high":
            return "high"
        if workflow_type == "image-to-video" or complexity == "medium":
            return "medium"
        return "low"
