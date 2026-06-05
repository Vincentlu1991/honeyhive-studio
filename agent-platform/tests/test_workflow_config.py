"""Test workflow configuration loader."""
import sys
import os

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from multi_agent_video.workflow_config import WorkflowConfigManager, get_workflow_manager


def test_workflow_config_loading() -> None:
    print("=" * 60)
    print("Testing Workflow Configuration Loader")
    print("=" * 60)

    manager = WorkflowConfigManager()

    # Test 1: List all workflows
    all_workflows = manager.list_workflows()
    print(f"\n✓ Found {len(all_workflows)} workflows:")
    for wf in all_workflows:
        print(f"  - {wf.name}: {wf.description}")
        print(f"    Tags: {', '.join(wf.tags)}")
        print(f"    File: {wf.file_path}")

    # Test 2: Get specific workflow
    sd15_anim = manager.get_workflow("sd15_animatediff")
    assert sd15_anim.name == "sd15_animatediff"
    assert "animation" in sd15_anim.tags
    print(f"\n✓ Retrieved workflow: {sd15_anim.name}")

    # Test 3: Get node mapping
    mapping = sd15_anim.get_node_mapping()
    assert "positive_prompt_node" in mapping
    assert "negative_prompt_node" in mapping
    assert "sampler_node" in mapping
    print(f"✓ Node mapping: {mapping}")

    # Test 4: Get parameters
    params = manager.workflow_to_parameters("sd15_animatediff")
    assert params["steps"] == 25
    assert params["cfg"] == 7.5
    print(f"✓ Parameters: steps={params['steps']}, cfg={params['cfg']}")

    # Test 5: Filter by tag
    animation_workflows = manager.list_workflows(tag="animation")
    assert len(animation_workflows) > 0
    print(f"\n✓ Found {len(animation_workflows)} animation workflows")

    # Test 6: Suggest by tags
    suggested = manager.suggest_workflow_by_tags(["video", "image2video"])
    if suggested:
        print(f"✓ Suggested workflow for [video, image2video]: {suggested.name}")

    # Test 7: Get preferred/fallback
    preferred = manager.get_preferred_workflow()
    fallback = manager.get_fallback_workflow()
    print(f"\n✓ Preferred workflow: {preferred.name}")
    print(f"✓ Fallback workflow: {fallback.name}")

    # Test 8: Global singleton
    manager2 = get_workflow_manager()
    assert manager2 is not None
    assert len(manager2.workflows) > 0
    print(f"\n✓ Global manager singleton works, contains {len(manager2.workflows)} workflows")

    print("\n✅ All workflow config tests passed!")


if __name__ == "__main__":
    try:
        test_workflow_config_loading()
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
