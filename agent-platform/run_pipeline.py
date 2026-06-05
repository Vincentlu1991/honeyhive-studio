from __future__ import annotations

import argparse
import json

from multi_agent_video.chat_hub import create_runtime
from multi_agent_video.config import load_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run multi-agent ComfyUI video pipeline")
    parser.add_argument("brief", help="scene brief, e.g. cyberpunk girl in rainy night")
    parser.add_argument("--seed", type=int, default=42, help="base random seed")
    parser.add_argument(
        "--evidence-file",
        action="append",
        default=[],
        help="Optional text/markdown evidence file path. Repeat for multiple files.",
    )
    return parser.parse_args()


def _load_evidence_documents(paths: list[str]) -> list[dict[str, str]]:
    docs: list[dict[str, str]] = []
    for idx, path in enumerate(paths, start=1):
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError:
            continue
        docs.append(
            {
                "doc_id": f"cli_{idx}",
                "title": path,
                "source": "run_pipeline_cli",
                "text": text,
            }
        )
    return docs


def main() -> None:
    args = parse_args()
    config = load_config()

    runtime = create_runtime(config)
    app = runtime.build_pipeline().build()

    result = app.invoke(
        {
            "user_brief": args.brief,
            "seed": args.seed,
            "retry_count": 0,
            "evidence_documents": _load_evidence_documents(args.evidence_file),
        },
        config={"recursion_limit": 80},
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
