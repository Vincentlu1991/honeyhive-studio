from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

from multi_agent_video.models import PromptPack, SceneSpec
from multi_agent_video.local_llm import extract_json_object


# ---------------------------------------------------------------------------
# Master-level prompt templates based on:
#   - AUTOMATIC1111 SD WebUI wiki (attention syntax, prompt editing, BREAK)
#   - Dalabad stable-diffusion-prompt-templates (style categories)
#   - ComfyUI-AnimateDiff-Evolved README (motion module best practices)
#   - Civitai community knowledge (quality tags, negative prompts)
# ---------------------------------------------------------------------------

# SD1.5 CLIP has a 75-token hard limit per chunk; keep quality prefix tight
_QUALITY_CORE = (
    "(best quality:1.1), (ultra detailed:1.05), "
    "photorealistic, natural skin texture, realistic lighting, "
)

# Cinematography modifiers — applied after subject (separate BREAK chunk)
_CINEMA_SUFFIX = (
    "BREAK "
    "cinematic lighting, volumetric light, film grain, "
    "(shallow depth of field:1.1), bokeh, anamorphic lens flare, "
    "professional color grading, HDR, sharp focus"
)

# AnimateDiff temporal consistency anchors — must appear in positive prompt
_TEMPORAL_ANCHORS = (
    "temporally consistent, stable identity, coherent motion, "
    "no flickering, smooth frame transition"
)

# Comprehensive negative — covers anatomy, video, aesthetics
_NEG_ANATOMY = (
    "bad anatomy, bad hands, missing fingers, extra fingers, fused fingers, "
    "too many fingers, bad proportions, malformed limbs, mutated hands, "
    "poorly drawn hands, poorly drawn face, mutation, deformed, ugly, "
    "blurry face, extra limbs, extra arms, extra legs, cloned face, "
    "disfigured, gross proportions, short neck, long neck"
)
_NEG_VIDEO = (
    "frame flickering, temporal inconsistency, jittering, warping, morphing, "
    "teleporting, sudden pose change, abrupt transition, ghost artifact, "
    "duplicate frames, strobing, tearing, screen tearing, frame blending"
)
_NEG_QUALITY = (
    "low quality, lowres, normal quality, worst quality, jpeg artifacts, "
    "compression artifacts, noise, grainy, pixelated, overexposed, underexposed, "
    "oversaturated, washed out, color bleeding, chromatic aberration"
)
_NEG_MISC = (
    "text, watermark, logo, signature, username, artist name, copyright mark, "
    "nsfw, cartoon, anime, sketch, painting, drawing, 3d render"
)

# Style templates adapted from Dalabad prompt-templates + Civitai community
_STYLE_TEMPLATES: dict[str, str] = {
    "cyberpunk": (
        "cinematic photo portrait, {subject}, "
        "cyberpunk night city, heavy rain, wet streets, neon reflections, "
        "rooftop, futuristic Tokyo, sci-fi atmosphere, intricate neon signage, "
        "HDR, anamorphic, teal-orange color grade, "
        "35mm film, professional photography, realistic human proportions"
    ),
    "portrait": (
        "portrait photo, {subject}, "
        "highly detailed face, (sharp facial features:1.2), "
        "moody light, Rembrandt lighting, golden hour, "
        "by Dan Winters and Steve McCurry, "
        "centered composition, Nikon D850 85mm f/1.4, award winning photography"
    ),
    "cinematic": (
        "cinematic still, {subject}, "
        "epic cinematic composition, dramatic lighting, film look, "
        "anamorphic bokeh, lens flare, teal-orange grade, "
        "movie still from high-budget production, "
        "by Roger Deakins cinematography"
    ),
    "landscape": (
        "{subject}, "
        "cinematic wide shot, birds-eye perspective, "
        "volumetric fog, god rays, dramatic sky, "
        "photorealistic landscape, by Andrew McCarthy photography, "
        "national geographic quality, 4k ultra wide"
    ),
    "default": (
        "cinematic photo, {subject}, "
        "professional photography, dramatic lighting, "
        "film look, 35mm, ultra detailed"
    ),
}


class PromptEngineerAgent:
    """大师级提示词工程Agent — SD1.5 + AnimateDiff 专家系统

    知识基础 (引用来源):
    ┌─────────────────────────────────────────────────────────────────┐
    │ SD WebUI Wiki  → attention syntax (word:1.3), BREAK keyword,   │
    │                  token limit (75/chunk), prompt editing          │
    │ Dalabad Templates → style categories, scene-specific structure  │
    │ AnimateDiff-Evolved → motion module best practices, beta_sched  │
    │ Civitai Community → quality tags, CFG guidelines, neg prompts  │
    └─────────────────────────────────────────────────────────────────┘

    核心规则:
    1. 质量标签必须在最前（CLIP 权重衰减影响靠后 token）
    2. 重要属性用 (word:1.2) 增强，最大 1.5 避免过曝
    3. BREAK 关键词分隔主体与风格（避免跨 75 token 边界混合）
    4. 负向提示词分三类: 解剖缺陷、视频特效问题、质量问题
    5. AnimateDiff 运动描述: 具体动词 + 方向 + 速度，避免抽象词
    6. 推荐参数: CFG 6.0-8.0, steps 25-35, DPM++ 2M Karras
    """

    def __init__(
        self,
        llm=None,
        rewrite_rules_path: str | None = None,
        enable_online_research: bool = False,
        online_research_base_url: str = "https://api.openalex.org",
        online_research_timeout_seconds: int = 5,
        online_research_max_results: int = 3,
    ) -> None:
        self.llm = llm
        self._rewrite_rules_path = rewrite_rules_path
        self._rewrite_rules = self._load_rewrite_rules(rewrite_rules_path)
        self._research_refs = self._load_research_refs()
        self._enable_online_research = enable_online_research
        self._online_research_base_url = online_research_base_url.rstrip("/")
        self._online_research_timeout_seconds = max(2, int(online_research_timeout_seconds))
        self._online_research_max_results = max(1, int(online_research_max_results))
        self._online_research_cache: dict[str, list[dict[str, Any]]] = {}

    def reload_rewrite_rules(self) -> int:
        """Reload rewrite rules from disk and return total loaded tag rules."""
        self._rewrite_rules = self._load_rewrite_rules(self._rewrite_rules_path)
        return len(self._rewrite_rules)

    def get_rewrite_rules_summary(self) -> dict[str, object]:
        return {
            "rule_count": len(self._rewrite_rules),
            "tags": sorted(self._rewrite_rules.keys()),
        }

    def get_research_refs_summary(self) -> dict[str, object]:
        domains = sorted(
            {
                str(item.get("domain", "")).strip().lower()
                for item in self._research_refs
                if isinstance(item, dict) and str(item.get("domain", "")).strip()
            }
        )
        return {
            "ref_count": len(self._research_refs),
            "domains": domains,
            "online_enabled": self._enable_online_research,
        }

    def _build_online_query(self, scene_spec: SceneSpec, issue_tags: list[str] | None) -> str:
        chunks = [
            str(scene_spec.action or ""),
            str(scene_spec.mood or ""),
            str(scene_spec.scene or ""),
            " ".join(str(t) for t in (issue_tags or [])),
            "human acting movement body language performance",
        ]
        query = " ".join(chunks).strip().lower()
        # keep query compact to reduce noisy retrieval
        return " ".join(query.split())[:240]

    def _abstract_from_inverted_index(self, data: object) -> str:
        if not isinstance(data, dict):
            return ""
        pairs: list[tuple[int, str]] = []
        for token, positions in data.items():
            if not isinstance(token, str) or not isinstance(positions, list):
                continue
            for pos in positions:
                if isinstance(pos, int):
                    pairs.append((pos, token))
        if not pairs:
            return ""
        pairs.sort(key=lambda x: x[0])
        words = [w for _, w in pairs]
        return " ".join(words)

    def _cues_from_abstract(self, abstract: str) -> list[str]:
        text = (abstract or "").lower()
        cues: list[str] = []
        if any(k in text for k in ("gait", "stride", "walking")):
            cues.append("gait rhythm and stride length are explicit and consistent")
        if any(k in text for k in ("posture", "torso", "pelvis", "shoulder")):
            cues.append("posture and torso-pelvis-shoulder coordination stay coherent")
        if any(k in text for k in ("emotion", "affect", "facial", "expression")):
            cues.append("emotion appears in face, gaze, and body timing simultaneously")
        if any(k in text for k in ("timing", "transition", "sequence", "phase")):
            cues.append("motion has phase sequence with clear transitions and recoveries")
        return cues[:3]

    def _search_online_research_refs(
        self,
        scene_spec: SceneSpec,
        issue_tags: list[str] | None,
        top_k: int,
    ) -> list[dict[str, Any]]:
        if not self._enable_online_research:
            return []

        query = self._build_online_query(scene_spec, issue_tags)
        if not query:
            return []

        if query in self._online_research_cache:
            return self._online_research_cache[query]

        mailto = os.getenv("OPENALEX_MAILTO", "")
        params = [
            f"search={quote_plus(query)}",
            f"per-page={min(top_k, self._online_research_max_results)}",
            "sort=relevance_score:desc",
        ]
        if mailto:
            params.append(f"mailto={quote_plus(mailto)}")

        url = f"{self._online_research_base_url}/works?{'&'.join(params)}"
        req = Request(url, headers={"User-Agent": "multi-agent-video/0.1 research"})

        try:
            with urlopen(req, timeout=self._online_research_timeout_seconds) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception:
            self._online_research_cache[query] = []
            return []

        results = payload.get("results", []) if isinstance(payload, dict) else []
        refs: list[dict[str, Any]] = []
        for item in results[:top_k]:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", "")).strip()
            if not title:
                continue
            year = str(item.get("publication_year", "")).strip()
            source_url = ""
            primary = item.get("primary_location", {})
            if isinstance(primary, dict):
                source_url = str(primary.get("landing_page_url", "") or primary.get("pdf_url", "")).strip()
            abstract = self._abstract_from_inverted_index(item.get("abstract_inverted_index"))
            cues = self._cues_from_abstract(abstract)
            refs.append(
                {
                    "id": str(item.get("id", "")).strip(),
                    "title": f"{title} ({year})" if year else title,
                    "domain": "online-paper",
                    "source_url": source_url,
                    "keywords": [],
                    "cues": cues,
                }
            )

        self._online_research_cache[query] = refs
        return refs

    def _load_rewrite_rules(self, rewrite_rules_path: str | None) -> dict[str, dict[str, object]]:
        default_path = Path(__file__).resolve().parents[2] / "config" / "prompt_rewrite_rules.json"
        path = Path(rewrite_rules_path) if rewrite_rules_path else default_path

        if not path.exists():
            return {}

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

        if not isinstance(data, dict):
            return {}

        sanitized: dict[str, dict[str, object]] = {}
        for key, value in data.items():
            if not isinstance(key, str) or not isinstance(value, dict):
                continue
            sanitized[key.strip().lower()] = value
        return sanitized

    def _load_research_refs(self) -> list[dict[str, Any]]:
        path = Path(__file__).resolve().parents[2] / "config" / "acting_research_refs.json"
        if not path.exists():
            return []

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []

        if not isinstance(data, list):
            return []

        sanitized: list[dict[str, Any]] = []
        for entry in data:
            if not isinstance(entry, dict):
                continue
            title = str(entry.get("title", "")).strip()
            if not title:
                continue
            keywords = entry.get("keywords", [])
            cues = entry.get("cues", [])
            sanitized.append(
                {
                    "id": str(entry.get("id", "")).strip(),
                    "title": title,
                    "domain": str(entry.get("domain", "")).strip(),
                    "source_url": str(entry.get("source_url", "")).strip(),
                    "keywords": [str(k).strip().lower() for k in keywords if str(k).strip()],
                    "cues": [str(c).strip() for c in cues if str(c).strip()],
                }
            )
        return sanitized

    def _select_research_refs(
        self,
        scene_spec: SceneSpec,
        issue_tags: list[str] | None,
        top_k: int = 3,
    ) -> list[dict[str, Any]]:
        online_refs = self._search_online_research_refs(scene_spec, issue_tags, top_k)

        if not self._research_refs and not online_refs:
            return []

        text = " ".join(
            [
                str(scene_spec.scene or ""),
                str(scene_spec.action or ""),
                str(scene_spec.mood or ""),
                " ".join(str(t) for t in (issue_tags or [])),
            ]
        ).lower()

        scored: list[tuple[int, dict[str, Any]]] = []
        for entry in self._research_refs:
            keywords = entry.get("keywords", [])
            score = sum(1 for kw in keywords if kw and kw in text)
            if score > 0:
                scored.append((score, entry))

        if not scored:
            merged = online_refs + self._research_refs
            return merged[:top_k]

        scored.sort(key=lambda x: x[0], reverse=True)
        local_selected = [entry for _, entry in scored[:top_k]]
        merged = online_refs + local_selected

        dedup: list[dict[str, Any]] = []
        seen: set[str] = set()
        for entry in merged:
            key = str(entry.get("title", "")).strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            dedup.append(entry)
        return dedup[:top_k]

    def _apply_research_cues(
        self,
        positive: str,
        motion_prompt: str,
        refs: list[dict[str, Any]],
    ) -> tuple[str, str]:
        if not refs:
            return positive, motion_prompt

        motion_cues: list[str] = []
        positive_cues: list[str] = []
        for ref in refs:
            for cue in ref.get("cues", []):
                c = str(cue).strip()
                if not c:
                    continue
                motion_cues.append(c)
                positive_cues.append(c)

        return (
            self._append_unique_phrases(positive, positive_cues[:4]),
            self._append_unique_phrases(motion_prompt, motion_cues[:6]),
        )

    def _format_research_refs_for_prompt(self, refs: list[dict[str, Any]]) -> str:
        if not refs:
            return "- none"

        lines = []
        for ref in refs:
            title = str(ref.get("title", "")).strip()
            domain = str(ref.get("domain", "")).strip()
            source = str(ref.get("source_url", "")).strip()
            if source:
                lines.append(f"- {title} [{domain}] ({source})")
            else:
                lines.append(f"- {title} [{domain}]")
        return "\n".join(lines)

    def _workflow_policy(self, workflow_type: str | None) -> dict[str, str | int]:
        wt = (workflow_type or "").lower()
        if "ltxv" in wt or "ltx" in wt or "video" in wt:
            return {
                "name": "ltxv_video",
                "positive_density": "long_descriptive",
                "motion_style": "single_clear_motion",
                "max_positive_chars": 900,
            }
        if "image-to-video" in wt or "i2v" in wt:
            return {
                "name": "i2v_identity_first",
                "positive_density": "balanced",
                "motion_style": "micro_motion",
                "max_positive_chars": 700,
            }
        return {
            "name": "default_sd15",
            "positive_density": "balanced",
            "motion_style": "steady",
            "max_positive_chars": 650,
        }

    def _apply_issue_tag_rewrites(
        self,
        positive: str,
        negative: str,
        motion_prompt: str,
        issue_tags: list[str] | None,
    ) -> tuple[str, str, str]:
        tags = [str(t).strip().lower() for t in (issue_tags or []) if str(t).strip()]
        if not tags:
            return positive, negative, motion_prompt

        pos = positive
        neg = negative
        motion = motion_prompt

        def _append_list(base: str, items: object) -> str:
            if not isinstance(items, list):
                return base
            cleaned = [str(x).strip() for x in items if str(x).strip()]
            if not cleaned:
                return base
            return self._append_unique_phrases(base, cleaned)

        for tag in tags:
            rule = self._rewrite_rules.get(tag)
            if not isinstance(rule, dict):
                continue

            pos = _append_list(pos, rule.get("positive_append"))
            neg = _append_list(neg, rule.get("negative_append"))

            motion_override = rule.get("motion_override")
            if isinstance(motion_override, str) and motion_override.strip():
                motion = motion_override.strip()

            motion_append = rule.get("motion_append")
            if isinstance(motion_append, str) and motion_append.strip():
                motion = self._append_unique_phrases(motion, [motion_append.strip()])

        return pos, neg, motion

    def _apply_policy_constraints(
        self,
        positive: str,
        motion_prompt: str,
        policy: dict[str, str | int],
    ) -> tuple[str, str]:
        p = positive
        m = motion_prompt

        if policy.get("positive_density") == "long_descriptive":
            if "cinematic continuity" not in p:
                p = self._append_unique_phrases(
                    p,
                    ["cinematic continuity", "coherent scene evolution"],
                )

        if policy.get("motion_style") == "single_clear_motion":
            m = self._append_unique_phrases(
                m,
                [
                    "one dominant motion only",
                    "avoid multi-action choreography",
                    "maintain stable camera",
                ],
            )
        elif policy.get("motion_style") == "micro_motion":
            m = self._append_unique_phrases(
                m,
                [
                    "controlled full-body coordination",
                    "small but clear motion amplitude",
                    "preserve identity from reference",
                ],
            )

        max_len = int(policy.get("max_positive_chars", 700))
        if len(p) > max_len:
            p = p[:max_len].rstrip(", ")

        return p, m

    def _infer_gait(self, action: str, mood: str) -> str:
        text = f"{action} {mood}".lower()
        if any(k in text for k in ("nervous", "anxious", "紧张", "慌", "fear")):
            return "small quick steps, short stride, slightly forward center of mass"
        if any(k in text for k in ("confident", "heroic", "自信", "坚定", "powerful")):
            return "stable long stride, grounded heel-to-toe walk, chest open posture"
        if any(k in text for k in ("happy", "joy", "开心", "轻快", "playful")):
            return "light springy gait, elastic ankle push-off, rhythmic step cadence"
        if any(k in text for k in ("sad", "tired", "疲惫", "失落", "melancholy")):
            return "slow sustained gait, reduced stride length, lowered torso energy"
        return "natural readable gait with clear foot placement and center-of-mass transfer"

    def _infer_emotion_physicalization(self, mood: str) -> str:
        text = (mood or "").lower()
        if any(k in text for k in ("confident", "自信", "坚定")):
            return "chin slightly up, open chest, decisive eye focus"
        if any(k in text for k in ("nervous", "anxious", "紧张", "不安")):
            return "quicker breathing rhythm, shoulder micro-tension, fast glance shifts"
        if any(k in text for k in ("happy", "joy", "开心", "兴奋")):
            return "lifted cheeks, relaxed shoulders, buoyant torso rhythm"
        if any(k in text for k in ("sad", "伤感", "悲伤")):
            return "reduced eye energy, slightly closed chest, slower gesture recovery"
        return "emotion is visible through posture, gaze, breath rhythm, and timing"

    def _derive_action_chain(self, action: str) -> str:
        a = (action or "").lower()
        if any(k in a for k in ("turn", "转身", "回头")):
            return "action chain: settle stance -> rotate upper torso -> hips follow -> footwork aligns"
        if any(k in a for k in ("walk", "run", "走", "跑")):
            return "action chain: weight shift -> lead foot contact -> pelvis transfer -> shoulder counter-swing"
        if any(k in a for k in ("jump", "跃", "跳")):
            return "action chain: preload knees -> core brace -> takeoff -> airborne balance -> soft landing"
        if any(k in a for k in ("wave", "招手", "挥手")):
            return "action chain: elbow lift -> wrist lead -> finger finish -> arm recovery"
        return "action chain: preparation -> initiation -> peak action -> follow-through -> settle"

    def _multi_character_priority(self, scene: str, action: str) -> str:
        text = f"{scene} {action}".lower()
        multi_markers = (
            "two", "three", "group", "crowd", "多人", "两人", "三人", "群像", "with"
        )
        if any(k in text for k in multi_markers):
            return (
                "multi-character blocking: main actor gets detailed action and expression, "
                "supporting actors use simplified complementary motion, background keeps natural low-amplitude behavior"
            )
        return "single-character focus with readable full-body motion arc"

    def _apply_performance_motion_techniques(
        self,
        scene_spec: SceneSpec,
        positive: str,
        motion_prompt: str,
    ) -> tuple[str, str]:
        gait = self._infer_gait(scene_spec.action, scene_spec.mood)
        linkage = (
            "full-body linkage: shoulder swing coordinated with pelvis-driven weight transfer, "
            "spine and head follow momentum naturally"
        )
        emotion = self._infer_emotion_physicalization(scene_spec.mood)
        chain = self._derive_action_chain(scene_spec.action)
        role_priority = self._multi_character_priority(scene_spec.scene, scene_spec.action)

        enriched_motion = self._append_unique_phrases(
            motion_prompt,
            [
                gait,
                linkage,
                emotion,
                chain,
                role_priority,
                "avoid mannequin motion, avoid frozen torso, avoid disconnected limb movement",
            ],
        )
        enriched_positive = self._append_unique_phrases(
            positive,
            [
                "clear body mechanics",
                "readable silhouette during movement",
                "coordinated timing across head torso hips and limbs",
            ],
        )
        return enriched_positive, enriched_motion

    def _seedance_camera_profile(self, action: str) -> str:
        a = (action or "").lower()
        if any(k in a for k in ("dance", "jump", "spin", "舞", "跳", "旋转")):
            return (
                "shot language: medium-wide establish -> three-quarter full-body -> slight crane-up finish, "
                "camera remains stable and keeps full body readable"
            )
        if any(k in a for k in ("walk", "run", "走", "跑")):
            return (
                "shot language: medium-wide track -> side follow -> front settle, "
                "camera movement smooth with consistent subject scale"
            )
        return (
            "shot language: establish -> action emphasis -> resolve, "
            "camera motion minimal and cinematic"
        )

    def _seedance_shot_plan(self, scene_spec: SceneSpec, motion_prompt: str) -> str:
        action = scene_spec.action or "subject performs clear body motion"
        scene = scene_spec.scene or "cinematic scene"
        return (
            "shot plan: "
            f"[beat-1] Camera: medium-wide establish; Action: prepare with visible weight shift; Effect: lock environment cues from {scene}. "
            f"[beat-2] Camera: three-quarter full-body; Action: {action}; Effect: peak motion with coherent limbs and torso. "
            "[beat-3] Camera: slight pull-up or settle; Action: follow-through and recovery; "
            f"Effect: preserve temporal continuity and scene identity. Motion notes: {motion_prompt}"
        )

    def _apply_seedance_prompt_format(
        self,
        scene_spec: SceneSpec,
        positive: str,
        motion_prompt: str,
    ) -> tuple[str, str]:
        style_line = (
            "format block [Style]: photorealistic real-human cinematic look, "
            "high dynamic range, physically plausible lighting and reflections"
        )
        protagonist_line = (
            "format block [Protagonist note]: keep one consistent real person identity, "
            "natural face proportions, stable hairstyle and outfit"
        )
        scene_line = f"format block [Scene]: {scene_spec.scene}"
        camera_line = self._seedance_camera_profile(scene_spec.action)
        shot_plan = self._seedance_shot_plan(scene_spec, motion_prompt)

        formatted_positive = self._append_unique_phrases(
            positive,
            [
                style_line,
                protagonist_line,
                scene_line,
                camera_line,
            ],
        )
        formatted_motion = self._append_unique_phrases(
            motion_prompt,
            [
                "format block [Duration]: short clip with clear 3-beat action progression",
                shot_plan,
            ],
        )
        return formatted_positive, formatted_motion

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

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _detect_style(self, scene: str, mood: str) -> str:
        """Detect best style template from scene keywords."""
        text = (scene + " " + mood).lower()
        if any(k in text for k in ("cyberpunk", "neon", "sci-fi", "futuristic", "dystopian")):
            return "cyberpunk"
        if any(k in text for k in ("portrait", "face", "close-up", "headshot")):
            return "portrait"
        if any(k in text for k in ("landscape", "nature", "mountain", "ocean", "forest")):
            return "landscape"
        if any(k in text for k in ("cinematic", "film", "movie", "dramatic", "epic")):
            return "cinematic"
        return "default"

    def _build_positive(self, scene: str, action: str, mood: str) -> str:
        """Construct a 75-token-aware positive prompt with BREAK chunking."""
        style_key = self._detect_style(scene, mood)
        template = _STYLE_TEMPLATES[style_key]
        subject = f"{scene}, {action}, {mood}"
        core = template.format(subject=subject)
        return (
            f"{_QUALITY_CORE}"
            f"{core}, "
            f"{_TEMPORAL_ANCHORS}, "
            f"{_CINEMA_SUFFIX}"
        )

    def _build_negative(self, style_key: str = "default") -> str:
        """Build comprehensive negative prompt with video-specific additions."""
        return (
            f"{_NEG_ANATOMY}, "
            f"{_NEG_VIDEO}, "
            f"{_NEG_QUALITY}, "
            f"{_NEG_MISC}"
        )

    def _build_motion_prompt(self, action: str, scene: str) -> str:
        """AnimateDiff motion description following evolved-node best practices.

        Rules (from ComfyUI-AnimateDiff-Evolved README):
        - mm_sd_v15_v2 works best with moderate motion, clear direction
        - Use concrete verbs: 'slow walk', 'head turns', 'hair sways'
        - Specify temporal anchors: 'stable face', 'consistent background'
        - Avoid abstract: 'moving', 'dynamic', 'animated'
        """
        return (
            f"{action}, "
            "smooth natural motion, stable facial identity, "
            "consistent environment lighting, "
            "subtle hair and cloth physics, "
            "no camera shake, steady shot, "
            "temporal coherence across all frames"
        )

    def _build_system_prompt(self) -> str:
        return (
            "You are a master Prompt Engineer for Stable Diffusion 1.5 + AnimateDiff video generation.\n\n"
            "=== KNOWLEDGE BASE ===\n"
            "Source 1 - SD WebUI Wiki (AUTOMATIC1111):\n"
            "  • Token limit: 75 per chunk; use BREAK to separate chunks cleanly\n"
            "  • Attention syntax: (word:1.3) boosts, [word] reduces; max safe = 1.5\n"
            "  • Quality tags first — CLIP weight decays for later tokens\n"
            "  • Prompt editing: [from:to:0.5] to blend at specific denoising steps\n\n"
            "Source 2 - Dalabad Style Templates:\n"
            "  • Cyberpunk: 'heavy raining futuristic tokyo, neon light, rooftop'\n"
            "  • Portrait: 'by Dan Winters, Russell James, Steve McCurry, Nikon D850'\n"
            "  • Landscape: 'by Andrew McCarthy, birds in sky, octane render, 8k'\n"
            "  • Always add camera spec: '35mm photograph, film, bokeh, professional'\n\n"
            "Source 3 - AnimateDiff-Evolved (Kosinkadink):\n"
            "  • mm_sd_v15_v2 needs beta_schedule='sqrt_linear (AnimateDiff)'\n"
            "  • Context_length=16 frames recommended for 512px\n"
            "  • Motion LoRA available for: pan left/right, zoom in/out, roll\n"
            "  • Temporal consistency: add 'temporally consistent' to positive prompt\n"
            "  • FreeNoise=true helps reduce flickering for >24 frames\n\n"
            "Source 4 - Expert CFG Guidelines:\n"
            "  • CFG 6.0-7.0: creative, slightly loose\n"
            "  • CFG 7.5-8.5: balanced quality (recommended)\n"
            "  • CFG 9.0+: may cause over-saturation/burnt colors\n"
            "  • DPM++ 2M Karras: best quality/speed ratio for 20-30 steps\n\n"
            "Source 5 - Acting and movement references:\n"
            "  • Laban Movement Analysis (Body/Effort/Shape/Space) for gait and body dynamics\n"
            "  • Stanislavski physical actions and task chains for believable action progression\n"
            "  • FACS action units for visible emotion cues in face/head timing\n\n"
            "=== TASK ===\n"
            "Build expert-level prompts. Use (emphasis:1.2) for key features.\n"
            "Use BREAK to separate quality prefix from main content.\n"
            "Adopt Seedance-style prompt structure with sections: [Style], [Protagonist note], [Scene], and shot-by-shot Camera/Action/Effect progression.\n"
            "Motion formula must include: precise gait + full-body linkage + emotional state + action chain + role priority.\n"
            "Return strict JSON: {positive, negative, motion_prompt, lora_tags, "
            "recommended_cfg, recommended_steps, recommended_sampler, notes}\n"
            "notes should explain key prompt decisions made."
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        scene_spec: SceneSpec,
        workflow_type: str | None = None,
        issue_tags: list[str] | None = None,
        retry_hint: str | None = None,
        strict_mode: bool = False,
    ) -> PromptPack:
        style_key = self._detect_style(scene_spec.scene, scene_spec.mood)
        policy = self._workflow_policy(workflow_type)
        research_refs = self._select_research_refs(scene_spec, issue_tags)

        if self.llm is not None:
            system_prompt = self._build_system_prompt()
            user_prompt = (
                f"Create master-level SD1.5+AnimateDiff prompts for:\n\n"
                f"Scene: {scene_spec.scene}\n"
                f"Action: {scene_spec.action}\n"
                f"Mood: {scene_spec.mood}\n"
                f"Detected style: {style_key}\n\n"
                f"Workflow policy: {policy}\n"
                f"Issue tags from previous QA (if any): {issue_tags or []}\n"
                f"Retry hint (if any): {retry_hint or ''}\n\n"
                f"Selected acting/movement references:\n"
                f"{self._format_research_refs_for_prompt(research_refs)}\n\n"
                f"Requirements:\n"
                f"- Use (attention:weight) syntax for key subject features\n"
                f"- BREAK after quality prefix, before main content\n"
                f"- motion_prompt must use AnimateDiff concrete verb syntax\n"
                f"- negative must cover anatomy + video artifacts + quality issues\n"
                f"- Include motion formula: precise gait, full-body linkage, emotional physicalization, action chain, and role priority\n"
                f"- Format prompts with Seedance-style blocks: [Style], [Protagonist note], [Scene], and 3-beat Camera/Action/Effect plan"
            )
            try:
                raw = self.llm.chat(system_prompt=system_prompt, user_prompt=user_prompt, temperature=0.2)
                parsed = extract_json_object(raw)
                if parsed is not None:
                    # Only extract the 4 fields PromptPack needs
                    pack_data = {
                        "positive": parsed.get("positive", ""),
                        "negative": parsed.get("negative", ""),
                        "motion_prompt": parsed.get("motion_prompt", ""),
                        "lora_tags": parsed.get("lora_tags", []),
                    }
                    if pack_data["positive"] and pack_data["negative"]:
                        pos, neg, motion = self._apply_issue_tag_rewrites(
                            pack_data["positive"],
                            pack_data["negative"],
                            pack_data["motion_prompt"],
                            issue_tags,
                        )
                        if retry_hint:
                            motion = f"{motion}, {retry_hint}"
                        pos, motion = self._apply_policy_constraints(pos, motion, policy)
                        pos, motion = self._apply_research_cues(pos, motion, research_refs)
                        pos, motion = self._apply_performance_motion_techniques(
                            scene_spec,
                            pos,
                            motion,
                        )
                        pos, motion = self._apply_seedance_prompt_format(
                            scene_spec,
                            pos,
                            motion,
                        )
                        if strict_mode:
                            pos, neg, motion = self._apply_strict_reference_mode(pos, neg, motion)
                        pack_data["positive"] = pos
                        pack_data["negative"] = neg
                        pack_data["motion_prompt"] = motion
                        return PromptPack.model_validate(pack_data)
            except Exception:
                pass

        # Expert-level fallback (no LLM)
        positive = self._build_positive(scene_spec.scene, scene_spec.action, scene_spec.mood)
        negative = self._build_negative(style_key)
        motion_prompt = self._build_motion_prompt(scene_spec.action, scene_spec.scene)
        positive, negative, motion_prompt = self._apply_issue_tag_rewrites(
            positive,
            negative,
            motion_prompt,
            issue_tags,
        )
        if retry_hint:
            motion_prompt = f"{motion_prompt}, {retry_hint}"
        positive, motion_prompt = self._apply_policy_constraints(positive, motion_prompt, policy)
        positive, motion_prompt = self._apply_research_cues(
            positive,
            motion_prompt,
            research_refs,
        )
        positive, motion_prompt = self._apply_performance_motion_techniques(
            scene_spec,
            positive,
            motion_prompt,
        )
        positive, motion_prompt = self._apply_seedance_prompt_format(
            scene_spec,
            positive,
            motion_prompt,
        )
        if strict_mode:
            positive, negative, motion_prompt = self._apply_strict_reference_mode(
                positive,
                negative,
                motion_prompt,
            )

        return PromptPack(
            positive=positive,
            negative=negative,
            motion_prompt=motion_prompt,
            lora_tags=[],
        )

    def _apply_strict_reference_mode(
        self,
        positive: str,
        negative: str,
        motion_prompt: str,
    ) -> tuple[str, str, str]:
        pos = self._append_unique_phrases(
            positive,
            [
                "same person as uploaded reference photo",
                "preserve facial geometry",
                "preserve hairstyle and outfit",
                "identity lock",
            ],
        )
        neg = self._append_unique_phrases(
            negative,
            [
                "identity drift",
                "face swap",
                "different person",
                "outfit inconsistency",
                "hairstyle change",
            ],
        )
        # Keep the original motion prompt so the character actually moves as requested.
        return pos[:700].rstrip(", "), neg[:1000].rstrip(", "), motion_prompt
