from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from multi_agent_video.models import PromptPack, WorkflowRequest
from multi_agent_video.workflow_config import get_workflow_manager


# ---------------------------------------------------------------------------
# Builder knowledge base based on:
#   - ComfyUI API node structure (class_type + inputs schema)
#   - AnimateDiff-Evolved node documentation (Kosinkadink README)
#   - ComfyUI API wiki (/prompt endpoint spec)
# ---------------------------------------------------------------------------

# Known node class types and their prompt input field names
# Source: ComfyUI node_helpers.py + community workflow inspection
_PROMPT_INPUT_FIELDS = {
    "CLIPTextEncode": "text",
    "CLIPTextEncodeSDXL": "text_g",     # SDXL uses text_g + text_l
    "smZ CLIPTextEncode": "text",        # smZ custom nodes
    "BNK_CLIPTextEncodeAdvanced": "text",
}

_SEED_INPUT_FIELDS = {
    "KSampler": "seed",
    "KSamplerAdvanced": "noise_seed",
    "SamplerCustom": "noise_seed",
    "LTXVSampler": "seed",
    "KSamplerSelect": None,              # no seed in this node
}

# Recommended parameter ranges (from ComfyUI community + AnimateDiff docs)
RECOMMENDED_PARAMS = {
    "animatediff_sd15": {
        "steps": 25,
        "cfg": 7.5,
        "sampler_name": "dpmpp_2m",
        "scheduler": "karras",
        "denoise": 1.0,
        "context_length": 16,
        "beta_schedule": "sqrt_linear (AnimateDiff)",
    },
    "sd15_image": {
        "steps": 30,
        "cfg": 7.0,
        "sampler_name": "dpmpp_2m",
        "scheduler": "karras",
    },
}


class ComfyUIBuilderAgent:
    """专业工作流构建 Agent — ComfyUI 节点图管理专家

    知识基础 (引用来源):
    ┌─────────────────────────────────────────────────────────────────────┐
    │ ComfyUI API   → /prompt endpoint, node class_type + inputs schema  │
    │ ADE-Evolved   → ADE_AnimateDiffLoaderGen1 节点参数规范              │
    │ Community     → 已验证工作流结构 (SD1.5 + AnimateDiff Gen1)         │
    └─────────────────────────────────────────────────────────────────────┘

    职责:
    - 将 PromptPack 精确注入到对应工作流节点
    - 自动检测节点 class_type 确定正确的输入字段名
    - 验证工作流完整性（必需节点存在性检查）
    - 防止修改原始工作流（深度拷贝隔离）
    - 提供详细的注入诊断日志
    """

    def __init__(self, node_mapping: dict[str, str] | None = None) -> None:
        self._custom_mapping = node_mapping is not None
        self.node_mapping = node_mapping or self._default_mapping()

    def _default_mapping(self) -> dict[str, str]:
        """Default node ID mapping for SD1.5 + AnimateDiff Gen1 workflows.
        
        Node IDs verified against workflow_sd15_animatediff_simple.json:
          Node 1: CheckpointLoaderSimple
          Node 2: ADE_AnimateDiffLoaderGen1
          Node 3: CLIPTextEncode (positive)
          Node 4: CLIPTextEncode (negative)
          Node 5: EmptyLatentImage
          Node 6: KSampler
          Node 7: VAEDecode
          Node 8: SaveImage
        """
        return {
            "positive_prompt_node": "3",
            "negative_prompt_node": "4",
            "sampler_node": "6",
            "image_node": "1",
        }

    def _get_prompt_field(self, node: dict[str, Any]) -> str:
        """Auto-detect the correct text input field for a CLIP node."""
        class_type = node.get("class_type", "CLIPTextEncode")
        return _PROMPT_INPUT_FIELDS.get(class_type, "text")

    def _get_seed_field(self, node: dict[str, Any]) -> str:
        """Auto-detect the correct seed field for a sampler node."""
        class_type = node.get("class_type", "KSampler")
        return _SEED_INPUT_FIELDS.get(class_type, "seed")

    def _resolve_node_mapping_for_workflow(self, workflow_path: str) -> dict[str, str] | None:
        """Resolve node mapping from workflow config for known workflow paths."""
        try:
            manager = get_workflow_manager()
        except Exception:
            return None

        candidate = Path(workflow_path).name

        for workflow in manager.list_workflows():
            configured_name = Path(workflow.file_path).name
            if candidate == configured_name or workflow_path == workflow.name:
                return workflow.get_node_mapping()
        return None

    def _sync_node_mapping(self, workflow_path: str) -> None:
        """Update mapping for known workflow when no custom mapping was provided."""
        if self._custom_mapping:
            return

        resolved = self._resolve_node_mapping_for_workflow(workflow_path)
        if resolved:
            self.node_mapping = resolved

    def validate_workflow(self, workflow: dict[str, Any]) -> list[str]:
        """Check workflow integrity. Returns list of warning strings."""
        warnings = []
        required = [
            ("positive_prompt_node", ["CLIPTextEncode", "CLIPTextEncodeSDXL"]),
            ("negative_prompt_node", ["CLIPTextEncode", "CLIPTextEncodeSDXL"]),
            ("sampler_node", ["KSampler", "KSamplerAdvanced", "SamplerCustom", "LTXVSampler"]),
        ]
        for mapping_key, valid_types in required:
            node_id = self.node_mapping.get(mapping_key)
            if not node_id:
                warnings.append(f"Missing mapping key: {mapping_key}")
                continue
            if node_id not in workflow:
                warnings.append(f"Node '{node_id}' ({mapping_key}) not in workflow")
                continue
            node_type = workflow[node_id].get("class_type", "")
            if valid_types and node_type not in valid_types:
                warnings.append(
                    f"Node '{node_id}' is {node_type}, expected one of {valid_types}"
                )
        return warnings

    def run(
        self,
        workflow_path: str,
        prompt_pack: PromptPack,
        seed: int,
        image_path: str | None = None,
    ) -> WorkflowRequest:
        self._sync_node_mapping(workflow_path)

        payload: dict[str, Any] = {
            "positive": prompt_pack.positive,
            "negative": prompt_pack.negative,
            "motion_prompt": prompt_pack.motion_prompt,
            "lora_tags": prompt_pack.lora_tags,
            "seed": seed,
            "node_mapping": self.node_mapping,
        }
        if image_path:
            payload["image_path"] = image_path
            payload["image_filename"] = Path(image_path).name
        return WorkflowRequest(workflow_path=workflow_path, prompt_payload=payload)

    def inject_to_workflow(
        self,
        workflow: dict[str, Any],
        prompt_pack: PromptPack,
        seed: int,
        image_filename: str | None = None,
    ) -> dict[str, Any]:
        """Inject PromptPack values into workflow with auto field detection."""
        modified = copy.deepcopy(workflow)

        # Validate before injection
        warnings = self.validate_workflow(modified)
        for w in warnings:
            print(f"⚠️ BuilderAgent: {w}")

        # Inject positive prompt
        pos_node_id = self.node_mapping.get("positive_prompt_node")
        if pos_node_id and pos_node_id in modified:
            field = self._get_prompt_field(modified[pos_node_id])
            modified[pos_node_id]["inputs"][field] = prompt_pack.positive
            print(f"✓ Injected positive prompt → node {pos_node_id} [{field}]")
        else:
            print(f"⚠️ positive_prompt_node '{pos_node_id}' not found")

        # Inject negative prompt
        neg_node_id = self.node_mapping.get("negative_prompt_node")
        if neg_node_id and neg_node_id in modified:
            field = self._get_prompt_field(modified[neg_node_id])
            modified[neg_node_id]["inputs"][field] = prompt_pack.negative
            print(f"✓ Injected negative prompt → node {neg_node_id} [{field}]")
        else:
            print(f"⚠️ negative_prompt_node '{neg_node_id}' not found")

        # Inject seed
        sampler_node_id = self.node_mapping.get("sampler_node")
        if sampler_node_id and sampler_node_id in modified:
            field = self._get_seed_field(modified[sampler_node_id])
            if field:
                modified[sampler_node_id]["inputs"][field] = seed
                print(f"✓ Injected seed {seed} → node {sampler_node_id} [{field}]")

            # Cap only extreme denoise values that would destroy identity entirely.
            if image_filename:
                sampler_inputs = modified[sampler_node_id].setdefault("inputs", {})
                denoise = sampler_inputs.get("denoise")
                if isinstance(denoise, (int, float)) and denoise > 0.90:
                    sampler_inputs["denoise"] = 0.80
                    print(
                        f"✓ Capped extreme denoise for i2v → node {sampler_node_id} [denoise=0.80]"
                    )

                # For high-motion requests (dance/jump/run), increase generation freedom
                # so scene intent and full-body motion are less likely to collapse into static output.
                motion_text = f"{prompt_pack.motion_prompt} {prompt_pack.positive}".lower()
                high_motion_markers = (
                    "dance",
                    "dancing",
                    "jump",
                    "leap",
                    "run",
                    "spin",
                    "跳",
                    "舞",
                    "跑",
                    "转身",
                    "旋转",
                )
                if any(k in motion_text for k in high_motion_markers):
                    cur_denoise = sampler_inputs.get("denoise")
                    if isinstance(cur_denoise, (int, float)) and cur_denoise < 0.76:
                        sampler_inputs["denoise"] = 0.76
                        print(
                            f"✓ Boosted i2v denoise for high motion → node {sampler_node_id} [denoise=0.76]"
                        )

                    cur_steps = sampler_inputs.get("steps")
                    if isinstance(cur_steps, (int, float)) and cur_steps < 28:
                        sampler_inputs["steps"] = 28
                        print(
                            f"✓ Boosted i2v steps for high motion → node {sampler_node_id} [steps=28]"
                        )

                    cur_cfg = sampler_inputs.get("cfg")
                    if isinstance(cur_cfg, (int, float)) and cur_cfg < 7.2:
                        sampler_inputs["cfg"] = 7.2
                        print(
                            f"✓ Boosted i2v cfg for high motion → node {sampler_node_id} [cfg=7.2]"
                        )
        else:
            print(f"⚠️ sampler_node '{sampler_node_id}' not found")

        # Inject uploaded image filename for image-to-video workflows.
        image_node_id = self.node_mapping.get("image_node")
        if image_filename and image_node_id and image_node_id in modified:
            node = modified[image_node_id]
            if node.get("class_type") == "LoadImage":
                node.setdefault("inputs", {})["image"] = image_filename
                node["inputs"]["upload"] = "image"
                print(f"Injected image {image_filename} -> node {image_node_id} [image]")
            else:
                print(f"image_node '{image_node_id}' is {node.get('class_type')}, expected LoadImage")
        elif image_filename:
            print(f"image_node '{image_node_id}' not found")

        return modified
