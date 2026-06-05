import sys
import os

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from multi_agent_video.agents import (
    ComfyUIBuilderAgent,
    ImageAnalysisAgent,
    ProductionPlannerAgent,
    StoryAgent,
    PromptEngineerAgent,
)
from multi_agent_video.models import PromptPack, SceneSpec


def test_story_agent():
    print("=" * 60)
    print("Testing Story Agent (No LLM)")
    print("=" * 60)
    
    agent = StoryAgent(llm=None)
    result = agent.run("赛博朋克少女站在雨夜，霓虹灯反射在积水路面")
    
    print(f"Scene: {result.scene}")
    print(f"Action: {result.action}")
    print(f"Mood: {result.mood}")
    assert result.scene
    assert result.action
    assert result.mood
    print("✓ Story Agent test passed\n")


def test_prompt_agent():
    print("=" * 60)
    print("Testing Prompt Engineer Agent (No LLM)")
    print("=" * 60)
    
    agent = PromptEngineerAgent(llm=None)
    scene = SceneSpec(
        scene="cyberpunk girl in rainy night",
        action="walking slowly",
        mood="melancholic"
    )
    result = agent.run(scene)
    
    print(f"Positive: {result.positive[:80]}...")
    print(f"Negative: {result.negative[:80]}...")
    print(f"Motion: {result.motion_prompt}")
    print(f"LoRA tags: {result.lora_tags}")
    assert "cyberpunk" in result.positive.lower() or "rainy" in result.positive.lower()
    assert result.negative
    assert result.motion_prompt
    print("✓ Prompt Agent test passed\n")


def test_builder_agent():
    print("=" * 60)
    print("Testing Builder Agent")
    print("=" * 60)
    
    agent = ComfyUIBuilderAgent()
    prompt_pack = PromptPack(
        positive="test positive",
        negative="test negative",
        motion_prompt="test motion",
        lora_tags=[]
    )
    
    result = agent.run("../workflow_test.json", prompt_pack, 42)
    assert result.workflow_path
    assert result.prompt_payload["seed"] == 42
    print(f"Workflow path: {result.workflow_path}")
    print(f"Seed: {result.prompt_payload['seed']}")
    print("✓ Builder Agent test passed\n")


def test_builder_agent_workflow_mapping_resolution():
    print("=" * 60)
    print("Testing Builder Agent Workflow Mapping Resolution")
    print("=" * 60)

    agent = ComfyUIBuilderAgent()
    prompt_pack = PromptPack(
        positive="test positive",
        negative="test negative",
        motion_prompt="test motion",
        lora_tags=[],
    )

    result = agent.run("../workflow_ltxv_img2video_test.json", prompt_pack, 55)
    mapping = result.prompt_payload["node_mapping"]

    assert mapping["positive_prompt_node"] == "3"
    assert mapping["negative_prompt_node"] == "4"
    assert mapping["sampler_node"] == "6"
    assert mapping["image_node"] == "1"
    print(f"Resolved mapping: {mapping}")
    print("✓ Builder mapping resolution test passed\n")


def test_image_analysis_agent():
    print("=" * 60)
    print("Testing Image Analysis Agent")
    print("=" * 60)

    from PIL import Image
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as tmp:
        image_path = os.path.join(tmp, "reference.png")
        Image.new("RGB", (320, 180), color=(40, 90, 160)).save(image_path)

        agent = ImageAnalysisAgent()
        result = agent.run(image_path, "blue cinematic car")

    assert result.width == 320
    assert result.height == 180
    assert result.orientation == "landscape"
    assert result.dominant_colors
    assert "uploaded reference image" in result.prompt_context
    print(f"Orientation: {result.orientation}")
    print(f"Colors: {result.dominant_colors}")
    print("✓ Image Analysis Agent test passed\n")


def test_builder_agent_image_injection():
    print("=" * 60)
    print("Testing Builder Agent Image Injection")
    print("=" * 60)

    agent = ComfyUIBuilderAgent()
    prompt_pack = PromptPack(
        positive="cinematic positive",
        negative="bad negative",
        motion_prompt="subtle motion",
        lora_tags=[],
    )
    workflow = {
        "1": {"class_type": "LoadImage", "inputs": {"image": "old.png"}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},
        "6": {"class_type": "LTXVSampler", "inputs": {"seed": 1}},
    }

    modified = agent.inject_to_workflow(workflow, prompt_pack, 123, image_filename="uploaded.png")
    assert modified["1"]["inputs"]["image"] == "uploaded.png"
    assert modified["3"]["inputs"]["text"] == "cinematic positive"
    assert modified["4"]["inputs"]["text"] == "bad negative"
    assert modified["6"]["inputs"]["seed"] == 123
    print("✓ Builder Agent image injection test passed\n")


def test_production_planner_agent():
    print("=" * 60)
    print("Testing Production Planner Agent")
    print("=" * 60)

    agent = ProductionPlannerAgent()
    plan = agent.run(
        "Create a portrait video for Reels",
        image_analysis={"orientation": "portrait"},
        requested_workflow="workflow_ltxv_img2video_test.json",
    )

    assert plan.workflow_type == "image-to-video"
    assert "vertical" in plan.target_format or "portrait" in plan.target_format
    assert plan.quality_risks
    assert plan.commercial_notes
    assert "Production plan" in plan.prompt_context
    print(f"Workflow type: {plan.workflow_type}")
    print(f"Target format: {plan.target_format}")
    print("✓ Production Planner Agent test passed\n")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("Multi-Agent Video Platform - Unit Tests")
    print("=" * 60 + "\n")
    
    try:
        test_story_agent()
        test_image_analysis_agent()
        test_production_planner_agent()
        test_prompt_agent()
        test_builder_agent()
        test_builder_agent_workflow_mapping_resolution()
        test_builder_agent_image_injection()
        
        print("=" * 60)
        print("All tests passed! ✓")
        print("=" * 60)
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
