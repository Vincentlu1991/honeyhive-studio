from __future__ import annotations

from multi_agent_video.models import SceneSpec
from multi_agent_video.local_llm import extract_json_object


# ---------------------------------------------------------------------------
# Cinematic vocabulary libraries — based on professional filmmaking standards
# ---------------------------------------------------------------------------

SHOT_TYPES = {
    "ECU": "extreme close-up, fills frame with single feature",
    "CU":  "close-up, head and shoulders",
    "MCU": "medium close-up, chest and up",
    "MS":  "medium shot, waist and up (most common for character)",
    "MLS": "medium long shot, knees and up",
    "LS":  "long shot, full body with environment context",
    "ELS": "extreme long shot, subject small in landscape",
}

CAMERA_MOVEMENTS = [
    "static shot",             # no camera movement (best for AnimateDiff stability)
    "slow push in",            # slowly zooming toward subject
    "slow pull back",          # slowly zooming away
    "slow pan left/right",     # horizontal rotation
    "slight dutch angle",      # tilted for tension
    "low angle heroic",        # looking up at subject
    "high angle vulnerable",   # looking down at subject
]

COLOR_PALETTES = {
    "cyberpunk":   "teal-orange grade, neon magenta-cyan accent, deep shadow",
    "noir":        "high contrast black-white, single warm key light, heavy shadow",
    "golden_hour": "warm amber-gold, long shadows, lens flare, 3200K color temp",
    "cold_blue":   "desaturated cool blue, clinical precision, muted tones",
    "cinematic":   "teal shadows cyan highlights, 2.35:1 anamorphic look",
    "natural":     "faithful color, gentle contrast, soft diffused light",
}

LIGHTING_SETUPS = {
    "Rembrandt":   "45° side key light, triangle shadow on cheek, deep contrast",
    "three-point": "key + fill + back rim, balanced professional look",
    "neon":        "multiple colored practical lights, high contrast, wet surfaces",
    "backlit":     "silhouette with rim light, golden/moody atmosphere",
    "overcast":    "soft diffused wrap-around light, minimal shadows, neutral mood",
}


class StoryAgent:
    """电影级场景分析Agent — 专业叙事与镜头语言大师

    知识基础 (引用来源):
    ┌─────────────────────────────────────────────────────────────────────┐
    │ 好莱坞编剧指导 → 三幕结构、场景节拍分析、人物目标驱动              │
    │ 专业摄影术语  → 景别系统(ECU/CU/MS/LS)、摄影机运动分类            │
    │ 电影色彩理论  → 颜色心理学、调色板命名、光照设置                    │
    │ AnimateDiff限制 → 2-3秒单动作、避免多角度切换、静态镜头最稳定     │
    └─────────────────────────────────────────────────────────────────────┘

    输出规范:
    - scene: 环境 + 景别 + 摄影机 + 光照 + 色调
    - action: 具体动词 + 方向 + 速度 (适合 0-3 秒)
    - mood: 情绪标签 + 调色板参考 + 摄影风格
    """

    def __init__(self, llm=None) -> None:
        self.llm = llm

    def _detect_palette(self, brief: str) -> str:
        b = brief.lower()
        if any(k in b for k in ("cyberpunk", "neon", "sci-fi", "futuristic")):
            return COLOR_PALETTES["cyberpunk"]
        if any(k in b for k in ("noir", "shadow", "detective", "mystery")):
            return COLOR_PALETTES["noir"]
        if any(k in b for k in ("sunset", "golden hour", "warm", "desert")):
            return COLOR_PALETTES["golden_hour"]
        if any(k in b for k in ("rain", "city", "street", "night")):
            return COLOR_PALETTES["cinematic"]
        if any(k in b for k in ("nature", "forest", "outdoor", "landscape")):
            return COLOR_PALETTES["natural"]
        return COLOR_PALETTES["cinematic"]

    def _detect_shot(self, brief: str) -> str:
        b = brief.lower()
        if any(k in b for k in ("face", "portrait", "close", "detail")):
            return "MCU"    # medium close-up for character emotion
        if any(k in b for k in ("landscape", "city", "wide", "panorama")):
            return "ELS"    # extreme long shot for scale
        if any(k in b for k in ("full body", "action", "walk", "dance")):
            return "MS"     # medium shot for full action
        return "MS"          # medium shot — most versatile default

    def _build_system_prompt(self) -> str:
        return (
            "You are a master Story Agent — a professional cinematographer, "
            "screenwriter, and visual director specialized in AI video generation.\n\n"
            "=== CINEMATOGRAPHY VOCABULARY ===\n"
            "Shot types: ECU (extreme close-up) | CU (close-up) | MCU (medium CU) | "
            "MS (medium) | MLS (medium long) | LS (long) | ELS (extreme long)\n\n"
            "Camera movements (AnimateDiff-friendly):\n"
            "  GOOD: 'static shot', 'slow push in', 'subtle pan left'\n"
            "  AVOID: 'rapid cut', 'jump cut', 'handheld shaky' (breaks temporal consistency)\n\n"
            "Color palettes: teal-orange (cinematic) | warm amber (golden hour) | "
            "cool blue (clinical) | high-contrast B&W (noir)\n\n"
            "Lighting setups: Rembrandt | three-point | neon practical | backlit | overcast\n\n"
            "=== TEMPORAL CONSTRAINT (CRITICAL) ===\n"
            "AnimateDiff at 16 frames = ~2 seconds of action.\n"
            "The action field must describe ONLY what physically happens in 2 seconds:\n"
            "  GOOD: 'slow forward walk, 2 steps, head turns slightly left'\n"
            "  GOOD: 'exhales visible breath, hair catches wind, eyes scan horizon'\n"
            "  BAD: 'walks across the city exploring the environment'\n"
            "  BAD: 'fights enemies and escapes'\n\n"
            "=== OUTPUT FORMAT ===\n"
            "Return strict JSON with exactly 3 keys:\n"
            "  scene: '[shot type] [subject] [in/at setting], [lighting setup], "
            "[color palette], [camera movement]'\n"
            "  action: '[verb 1], [direction/speed], [verb 2], [physical detail]' "
            "(max 2 actions, 2-second window)\n"
            "  mood: '[emotion], [color grade reference], [cinematographer/film style]'\n\n"
            "Examples:\n"
            "  scene: 'MCU young woman with violet hair standing on wet rooftop at night, "
            "Rembrandt neon lighting from left, teal-orange grade, static shot'\n"
            "  action: 'slow exhale, visible breath mist, head turns 15° left, "
            "wet hair strand moves in wind'\n"
            "  mood: 'melancholic wonder, teal-orange cinematics, "
            "Roger Deakins Blade Runner 2049 style'"
        )

    def run(self, user_brief: str) -> SceneSpec:
        brief = user_brief.strip() or "a young woman standing on a rainy cyberpunk street"

        palette = self._detect_palette(brief)
        shot = self._detect_shot(brief)

        if self.llm is not None:
            system_prompt = self._build_system_prompt()
            user_prompt = (
                f"Analyze this brief and create a professional cinematic scene breakdown:\n\n"
                f"BRIEF: {brief}\n\n"
                f"Context hints (use if relevant):\n"
                f"  Detected shot type: {shot} ({SHOT_TYPES[shot]})\n"
                f"  Suggested palette: {palette}\n\n"
                f"Remember: action must fit in exactly 2 seconds of video (16 frames at 8fps).\n"
                f"Be specific, visual, and cinematically professional."
            )
            try:
                raw = self.llm.chat(system_prompt=system_prompt, user_prompt=user_prompt, temperature=0.15)
                parsed = extract_json_object(raw)
                if parsed is not None:
                    spec = SceneSpec.model_validate(parsed)
                    # Ensure minimum quality
                    if len(spec.scene) > 20 and len(spec.action) > 10:
                        return spec
            except Exception:
                pass

        # Master-level fallback (cinematically precise, no LLM needed)
        return SceneSpec(
            scene=(
                f"{shot} {brief}, "
                f"static shot, "
                f"{LIGHTING_SETUPS.get('three-point', 'professional lighting')}, "
                f"{palette}"
            ),
            action=(
                "subtle weight shift, gentle breath movement, "
                "slight head micro-adjustment, ambient cloth physics response"
            ),
            mood=(
                f"cinematic contemplation, {palette}, "
                "Roger Deakins inspired composition, anamorphic lens character"
            ),
        )
