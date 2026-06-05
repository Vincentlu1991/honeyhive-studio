import json
import sys
from pathlib import Path


def analyze_workflow(workflow_path: str) -> None:
    """Analyze workflow JSON to identify key node IDs for mapping."""
    with Path(workflow_path).open("r", encoding="utf-8") as f:
        workflow = json.load(f)

    print(f"Workflow Analysis: {workflow_path}")
    print("=" * 60)

    # Find prompt nodes
    prompt_nodes = []
    sampler_nodes = []
    image_nodes = []

    for node_id, node in workflow.items():
        class_type = node.get("class_type", "")
        title = node.get("_meta", {}).get("title", "")

        if "CLIPTextEncode" in class_type:
            text = node.get("inputs", {}).get("text", "")[:50]
            prompt_nodes.append((node_id, title, text))
        elif "Sampler" in class_type or "KSampler" in class_type:
            sampler_nodes.append((node_id, title, class_type))
        elif "LoadImage" in class_type:
            image_nodes.append((node_id, title))

    print("\n[Prompt Nodes]")
    for node_id, title, text in prompt_nodes:
        print(f"  Node {node_id}: {title}")
        print(f"    Text: {text}...")

    print("\n[Sampler Nodes]")
    for node_id, title, class_type in sampler_nodes:
        print(f"  Node {node_id}: {title} ({class_type})")

    print("\n[Image Nodes]")
    for node_id, title in image_nodes:
        print(f"  Node {node_id}: {title}")

    print("\n[Suggested Mapping]")
    if len(prompt_nodes) >= 2:
        print(f"  positive_prompt_node: \"{prompt_nodes[0][0]}\"")
        print(f"  negative_prompt_node: \"{prompt_nodes[1][0]}\"")
    if sampler_nodes:
        print(f"  sampler_node: \"{sampler_nodes[0][0]}\"")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python workflow_analyzer.py <workflow.json>")
        sys.exit(1)

    analyze_workflow(sys.argv[1])
