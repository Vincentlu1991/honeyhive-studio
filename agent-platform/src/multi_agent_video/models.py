from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SceneSpec(BaseModel):
    scene: str
    action: str
    mood: str


class ImageAnalysis(BaseModel):
    image_path: str
    width: int
    height: int
    orientation: str
    dominant_colors: list[str] = Field(default_factory=list)
    brightness: str
    composition: str
    subject_hint: str
    video_opportunities: list[str] = Field(default_factory=list)
    prompt_context: str


class ProductionPlan(BaseModel):
    creative_goal: str
    target_format: str
    workflow_type: str
    recommended_workflow: str
    motion_strategy: str
    quality_risks: list[str] = Field(default_factory=list)
    commercial_notes: list[str] = Field(default_factory=list)
    prompt_context: str


class PromptPack(BaseModel):
    positive: str
    negative: str
    motion_prompt: str
    lora_tags: list[str] = Field(default_factory=list)


class WorkflowRequest(BaseModel):
    workflow_path: str
    prompt_payload: dict[str, Any]


class QAReport(BaseModel):
    face: int = Field(ge=0, le=10)
    motion: int = Field(ge=0, le=10)
    artifact: int = Field(ge=0, le=10)
    passed: bool
    notes: str
    issue_tags: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)


class PipelineState(BaseModel):
    user_brief: str
    input_image_path: str | None = None
    workflow_path: str | None = None
    seed: int = 42
    retry_count: int = 0
    image_analysis: ImageAnalysis | None = None
    production_plan: ProductionPlan | None = None
    scene_spec: SceneSpec | None = None
    prompt_pack: PromptPack | None = None
    workflow_request: WorkflowRequest | None = None
    render_job_id: str | None = None
    render_status: str | None = None
    render_output: dict[str, Any] | None = None
    qa_report: QAReport | None = None

    def to_graph_state(self) -> dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_graph_state(cls, state: dict[str, Any]) -> "PipelineState":
        return cls.model_validate(state)
