from __future__ import annotations

from collections import Counter
from pathlib import Path

from PIL import Image, ImageStat

from multi_agent_video.models import ImageAnalysis


class ImageAnalysisAgent:
    """Analyze an input image and convert it into video-generation context."""

    def __init__(self, llm=None) -> None:
        self.llm = llm

    def run(self, image_path: str, user_brief: str = "") -> ImageAnalysis:
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Input image not found: {image_path}")

        with Image.open(path) as image:
            rgb = image.convert("RGB")
            width, height = rgb.size
            orientation = self._orientation(width, height)
            colors = self._dominant_colors(rgb)
            brightness = self._brightness(rgb)

        subject_hint = self._subject_hint(user_brief)
        composition = self._composition(width, height, brightness)
        opportunities = self._video_opportunities(subject_hint, brightness, orientation)
        prompt_context = self._prompt_context(
            subject_hint=subject_hint,
            orientation=orientation,
            colors=colors,
            brightness=brightness,
            composition=composition,
            opportunities=opportunities,
            user_brief=user_brief,
        )

        return ImageAnalysis(
            image_path=str(path),
            width=width,
            height=height,
            orientation=orientation,
            dominant_colors=colors,
            brightness=brightness,
            composition=composition,
            subject_hint=subject_hint,
            video_opportunities=opportunities,
            prompt_context=prompt_context,
        )

    def _orientation(self, width: int, height: int) -> str:
        ratio = width / max(height, 1)
        if ratio > 1.2:
            return "landscape"
        if ratio < 0.85:
            return "portrait"
        return "square"

    def _dominant_colors(self, image: Image.Image) -> list[str]:
        small = image.resize((64, 64))
        quantized = small.quantize(colors=5).convert("RGB")
        counts = Counter(quantized.getdata())
        return [self._rgb_to_hex(rgb) for rgb, _ in counts.most_common(5)]

    def _brightness(self, image: Image.Image) -> str:
        gray = image.convert("L")
        mean = ImageStat.Stat(gray).mean[0]
        if mean < 75:
            return "low-key dark"
        if mean > 180:
            return "bright high-key"
        return "balanced mid-tone"

    def _composition(self, width: int, height: int, brightness: str) -> str:
        orientation = self._orientation(width, height)
        if orientation == "portrait":
            frame = "portrait framing, likely character or subject-forward composition"
        elif orientation == "landscape":
            frame = "wide framing, likely environment-forward composition"
        else:
            frame = "square framing, balanced subject and background composition"
        return f"{frame}, {brightness} lighting profile"

    def _subject_hint(self, user_brief: str) -> str:
        brief = user_brief.strip()
        if brief:
            return brief
        return "the main subject from the uploaded reference image"

    def _video_opportunities(self, subject_hint: str, brightness: str, orientation: str) -> list[str]:
        motion = [
            "preserve the uploaded image identity and visual style",
            "add subtle natural motion without changing the subject",
            "use stable camera movement with temporal consistency",
        ]
        if "dark" in brightness:
            motion.append("animate small highlights, reflections, or rim light")
        if orientation == "portrait":
            motion.append("use micro-expression, hair, cloth, or breathing motion")
        elif orientation == "landscape":
            motion.append("use atmospheric movement such as mist, rain, light, or parallax")
        if any(k in subject_hint.lower() for k in ("face", "person", "girl", "boy", "woman", "man", "portrait")):
            motion.append("prioritize face consistency and avoid identity drift")
        return motion

    def _prompt_context(
        self,
        subject_hint: str,
        orientation: str,
        colors: list[str],
        brightness: str,
        composition: str,
        opportunities: list[str],
        user_brief: str,
    ) -> str:
        color_text = ", ".join(colors)
        motion_text = "; ".join(opportunities)
        brief = user_brief.strip() or "animate the uploaded reference image"
        return (
            f"Use the uploaded reference image as the visual anchor. User intent: {brief}. "
            f"Subject hint: {subject_hint}. Composition: {composition}. "
            f"Orientation: {orientation}. Dominant colors: {color_text}. "
            f"Brightness: {brightness}. Video direction: {motion_text}."
        )

    def _rgb_to_hex(self, rgb: tuple[int, int, int]) -> str:
        return "#{:02x}{:02x}{:02x}".format(*rgb)
