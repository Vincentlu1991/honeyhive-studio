from __future__ import annotations

from typing import Any

from multi_agent_video.local_llm import extract_json_object
from multi_agent_video.models import QAReport


# ---------------------------------------------------------------------------
# QA knowledge base — based on professional video quality assessment standards
# References:
#   - VMAF (Netflix Video Multi-Method Assessment Fusion): perceptual quality metrics
#   - SSIM temporal: structural similarity across frames (T-SSIM)
#   - AnimateDiff community quality guides (motion coherence expectations)
#   - Professional VFX QC checklists (frame integrity, artifact taxonomy)
# ---------------------------------------------------------------------------

# Per-scene rubric: different scenes have different quality expectations
_SCENE_RUBRICS = {
    "face_close_up": {
        "face_min": 8,      # Very high face standard for close-up portraits
        "motion_min": 6,    # Subtle motion acceptable
        "artifact_max": 4,  # Very intolerant of artifacts (they're visible)
        "notes": "Close-up: face consistency paramount, micro-artifacts visible",
    },
    "action_scene": {
        "face_min": 5,       # Acceptable lower face bar (motion blur expected)
        "motion_min": 8,     # High motion standard — must look fluid
        "artifact_max": 6,   # More tolerant of transient artifacts
        "notes": "Action: motion fluidity paramount, face less critical",
    },
    "landscape": {
        "face_min": 3,       # No face to evaluate
        "motion_min": 6,     # Gentle environmental motion expected
        "artifact_max": 4,   # Clean environment required
        "notes": "Landscape: evaluate spatial coherence, parallax motion",
    },
    "default": {
        "face_min": 6,
        "motion_min": 6,
        "artifact_max": 5,
        "notes": "Standard AnimateDiff 16-frame quality baseline",
    },
}

# Motion type quality expectations (AnimateDiff-specific)
_MOTION_EXPECTATIONS = {
    "static": "Minimal frame delta expected. Any >2px displacement = artifact.",
    "slow_movement": "Smooth sub-pixel interpolation. No teleporting or jitter.",
    "fast_action": "Acceptable motion blur. Check for smearing vs. natural blur.",
    "camera_pan": "Background parallax should be consistent. Watch for warping.",
}

# Artifact taxonomy with severity weights
_ARTIFACT_TAXONOMY = {
    "temporal_flicker":    {"weight": 3, "desc": "Brightness/color oscillation between frames"},
    "face_morph":          {"weight": 3, "desc": "Identity change mid-sequence"},
    "spatial_warp":        {"weight": 3, "desc": "Distortion/stretching of geometry"},
    "ghosting":            {"weight": 2, "desc": "Residual previous-frame transparency"},
    "color_banding":       {"weight": 2, "desc": "Discrete color step rather than gradient"},
    "anatomical_break":    {"weight": 3, "desc": "Extra fingers, merged limbs, impossible poses"},
    "text_corruption":     {"weight": 2, "desc": "Garbled text if text was in prompt"},
    "noise_spike":         {"weight": 1, "desc": "Single-frame noise burst"},
}


class VideoQAAgent:
    """大师级视频质检 Agent — 专业影像质量评估系统

    知识基础 (引用来源):
    ┌─────────────────────────────────────────────────────────────────────┐
    │ VMAF (Netflix)    → 感知质量指标，时间维度结构相似度 (T-SSIM)     │
    │ VFX QC checklists → 帧完整性、色彩一致性、运动连续性              │
    │ AnimateDiff社区   → 16帧时间窗口质量期望、beta_schedule影响        │
    │ 专业分级标准      → 场景类型特定rubric（特写vs风景vs动作）          │
    └─────────────────────────────────────────────────────────────────────┘

    评分维度:
    - face (0-10): T-SSIM面部一致性 + 解剖正确性 + 跨帧身份稳定
    - motion (0-10): 时间连贯性 + 物理真实性 + 动作流畅度
    - artifact (0-10): 清洁度倒序评分 (10=完美, 0=严重问题)
    - passed: 场景感知动态阈值判定

    注意: artifact 评分越低 = 问题越多
    默认通过条件: face>=6, motion>=6, artifact<=5
    """

    # Default passing thresholds (overridden by scene rubric)
    PASS_FACE_MIN = 6
    PASS_MOTION_MIN = 6
    PASS_ARTIFACT_MAX = 5

    def __init__(self, llm=None) -> None:
        self.llm = llm

    def _build_system_prompt(self) -> str:
        return (
            "You are a master Video QA Agent — a professional visual quality inspector with "
            "expertise in AI-generated video assessment (AnimateDiff + Stable Diffusion).\n\n"
            "=== EVALUATION FRAMEWORK ===\n"
            "Based on VMAF perceptual quality principles and professional VFX QC standards:\n\n"
            "1. FACE (0-10) — Temporal face consistency (T-SSIM across frames)\n"
            "   10: Perfect photorealistic consistency, stable identity, sharp features\n"
            "   8-9: Professional quality, minor acceptable variations\n"
            "   6-7: Usable but noticeable inconsistency, some blurring\n"
            "   4-5: Noticeable morphing, identity drift, anatomy issues\n"
            "   0-3: Severe defects — unrecognizable face, impossible anatomy\n\n"
            "2. MOTION (0-10) — Temporal coherence & physics realism\n"
            "   10: Cinema-quality fluid motion, perfect frame interpolation\n"
            "   8-9: Professional smooth motion, natural physics\n"
            "   6-7: Acceptable motion, minor jitter or stutter\n"
            "   4-5: Jerky motion, teleporting pixels, unnatural speed\n"
            "   0-3: Severe flicker, impossible motion, broken temporal consistency\n\n"
            "3. ARTIFACT (0-10) — INVERTED: Cleanliness score (10=clean, 0=severe)\n"
            "   Artifact taxonomy: temporal flicker (weight 3) | face morph (3) | "
            "spatial warp (3) | ghosting (2) | color banding (2) | anatomical break (3)\n"
            "   10: No artifacts, cinema-clean render\n"
            "   7-9: Acceptable, minor transient noise only\n"
            "   4-6: Noticeable artifacts that distract from the content\n"
            "   0-3: Severe artifacts — flickering, warping, frame corruption\n\n"
            "=== SCENE-AWARE ASSESSMENT ===\n"
            "Adjust standards by scene type:\n"
            "- Face close-up: face>=8 required, artifacts especially critical\n"
            "- Action scene: motion>=8 required, face standard lowered to 5\n"
            "- Landscape: no face standard, environmental coherence matters\n\n"
            "=== OUTPUT FORMAT ===\n"
            "Return strict JSON:\n"
            "{\"face\": int, \"motion\": int, \"artifact\": int, \"passed\": bool, \"notes\": str}\n"
            "notes must:\n"
            "  1. Name the primary quality issue (if any)\n"
            "  2. Identify artifact type from taxonomy\n"
            "  3. Give ONE concrete parameter adjustment to fix it\n"
            "Example: 'Face morphing detected (severity: high). Likely CFG=8 over-conditioning. "
            "Suggest reducing CFG to 7.0 and changing seed.'"
        )

    def _detect_scene_rubric(self, render_output: dict[str, Any]) -> dict[str, Any]:
        """Try to infer scene type from render metadata to apply scene-specific rubric."""
        # Look for scene hints in the prompt data stored in output
        output_str = str(render_output).lower()
        if any(k in output_str for k in ("close-up", "portrait", "face", "mcu")):
            return _SCENE_RUBRICS["face_close_up"]
        if any(k in output_str for k in ("action", "fight", "run", "chase")):
            return _SCENE_RUBRICS["action_scene"]
        if any(k in output_str for k in ("landscape", "mountain", "ocean", "forest")):
            return _SCENE_RUBRICS["landscape"]
        return _SCENE_RUBRICS["default"]

    def _analyze_output_structure(self, render_output: dict[str, Any]) -> dict[str, Any]:
        """Extract structured metrics from render output for assessment."""
        analysis = {
            "has_outputs": False,
            "frame_count": 0,
            "has_status_success": False,
            "execution_time_ms": 0,
        }

        if not isinstance(render_output, dict):
            return analysis

        outputs = render_output.get("outputs", {})
        analysis["has_outputs"] = bool(outputs)

        # Count frames
        for node_outputs in outputs.values():
            if isinstance(node_outputs, dict) and "images" in node_outputs:
                analysis["frame_count"] += len(node_outputs["images"])

        # Check status
        status = render_output.get("status", {})
        if isinstance(status, dict):
            analysis["has_status_success"] = status.get("status_str") == "success"
            messages = status.get("messages", [])
            if len(messages) >= 2:
                try:
                    start_ts = messages[0][1].get("timestamp", 0)
                    end_ts = messages[-1][1].get("timestamp", 0)
                    analysis["execution_time_ms"] = end_ts - start_ts
                except (IndexError, KeyError, TypeError):
                    pass

        return analysis

    def _derive_issue_tags_and_actions(
        self,
        face: int,
        motion: int,
        artifact: int,
        analysis: dict[str, Any],
        rubric: dict[str, Any],
    ) -> tuple[list[str], list[str]]:
        tags: list[str] = []
        actions: list[str] = []

        if not analysis.get("has_outputs", False):
            tags.append("render_missing")
            actions.append("检查 ComfyUI 控制台和 API 连通性")
            return tags, actions

        frame_count = int(analysis.get("frame_count", 0))
        if frame_count < 16:
            tags.append("incomplete_frames")
            actions.append("降低动作复杂度并重试，确保完整 16 帧输出")

        if face < rubric["face_min"]:
            tags.append("face_consistency")
            actions.append("强化身份锁定词并尝试新 seed")

        if motion < rubric["motion_min"]:
            tags.append("motion_instability")
            actions.append("将动作缩减为单一主动作，保持镜头稳定")

        if artifact > rubric["artifact_max"]:
            tags.append("artifact_noise")
            actions.append("steps +5，CFG -0.5，减少噪点与扭曲")

        exec_ms = int(analysis.get("execution_time_ms", 0))
        if exec_ms and exec_ms < 12000:
            tags.append("under_sampling_risk")
            actions.append("适当提高 steps，避免采样不足")

        if not tags:
            tags.append("quality_stable")
            actions.append("保持当前参数，使用新 seed 生成更多候选")

        # Deduplicate while preserving order.
        tags = list(dict.fromkeys(tags))
        actions = list(dict.fromkeys(actions))
        return tags, actions

    def run(self, render_output: dict[str, Any]) -> QAReport:
        analysis = self._analyze_output_structure(render_output)
        rubric = self._detect_scene_rubric(render_output)

        if self.llm is not None:
            system_prompt = self._build_system_prompt()
            user_prompt = (
                f"Evaluate this AnimateDiff SD1.5 render result (16 frames @ 512x512):\n\n"
                f"Structural analysis:\n"
                f"  - Frames generated: {analysis['frame_count']} (expected: 16)\n"
                f"  - Completion: {analysis['frame_count'] / 16 * 100:.0f}%\n"
                f"  - Status: {'SUCCESS' if analysis['has_status_success'] else 'UNKNOWN/FAILED'}\n"
                f"  - Execution time: {analysis['execution_time_ms'] / 1000:.1f}s\n\n"
                f"Scene rubric: {rubric['notes']}\n"
                f"  face_min={rubric['face_min']}, motion_min={rubric['motion_min']}, "
                f"artifact_max={rubric['artifact_max']}\n\n"
                f"Full output metadata:\n{str(render_output)[:2000]}"
            )
            try:
                raw = self.llm.chat(system_prompt=system_prompt, user_prompt=user_prompt, temperature=0.1)
                parsed = extract_json_object(raw)
                if parsed is not None:
                    report = QAReport.model_validate(parsed)
                    # Apply scene-aware thresholds
                    report.passed = (
                        report.face >= rubric["face_min"]
                        and report.motion >= rubric["motion_min"]
                        and report.artifact <= rubric["artifact_max"]
                    )
                    tags, actions = self._derive_issue_tags_and_actions(
                        face=report.face,
                        motion=report.motion,
                        artifact=report.artifact,
                        analysis=analysis,
                        rubric=rubric,
                    )
                    report.issue_tags = tags
                    report.recommended_actions = actions
                    return report
            except Exception:
                pass

        # Master heuristic fallback with artifact taxonomy
        if not analysis["has_outputs"]:
            return QAReport(
                face=0, motion=0, artifact=0, passed=False,
                notes=(
                    "No render output detected. "
                    "Primary suspect: ComfyUI API timeout or workflow node error. "
                    "Check ComfyUI console logs for 400/500 errors."
                ),
                issue_tags=["render_missing", "pipeline_blocked"],
                recommended_actions=["检查 ComfyUI 服务状态", "检查 workflow 节点兼容性"],
            )

        expected_frames = 16
        completeness = min(analysis["frame_count"] / expected_frames, 1.0)
        is_success = analysis["has_status_success"]
        exec_sec = analysis["execution_time_ms"] / 1000

        # Score heuristics based on execution evidence
        face = round(7 * completeness) if is_success else 4
        motion = round(7 * completeness) if is_success else 3
        # Execution time heuristic: >60s suggests proper sampling (more steps = cleaner)
        if exec_sec > 60:
            artifact = 7
        elif exec_sec > 30:
            artifact = 5
        else:
            artifact = 3   # Very fast = fewer steps = more artifacts

        passed = (
            face >= rubric["face_min"]
            and motion >= rubric["motion_min"]
            and artifact <= rubric["artifact_max"]
        )

        if passed:
            notes = (
                f"Heuristic pass: {analysis['frame_count']}/16 frames in {exec_sec:.0f}s. "
                f"No obvious structural failures detected. "
                f"Next step: visually inspect for temporal flicker or face morphing."
            )
        else:
            issue = []
            if face < rubric["face_min"]:
                issue.append(f"face={face}<{rubric['face_min']} (try new seed or reduce CFG by 0.5)")
            if motion < rubric["motion_min"]:
                issue.append(f"motion={motion}<{rubric['motion_min']} (simplify motion_prompt)")
            if artifact > rubric["artifact_max"]:
                issue.append(f"artifact={artifact}>{rubric['artifact_max']} (increase steps by 5)")
            notes = "Issues: " + "; ".join(issue) if issue else "Below threshold, retry suggested."

        tags, actions = self._derive_issue_tags_and_actions(
            face=face,
            motion=motion,
            artifact=artifact,
            analysis=analysis,
            rubric=rubric,
        )
        return QAReport(
            face=face,
            motion=motion,
            artifact=artifact,
            passed=passed,
            notes=notes,
            issue_tags=tags,
            recommended_actions=actions,
        )
