from __future__ import annotations

import argparse
import sys
from pathlib import Path

V2_ROOT = Path(__file__).resolve().parents[1]
if str(V2_ROOT) in sys.path:
    sys.path.remove(str(V2_ROOT))
sys.path.insert(0, str(V2_ROOT))

from core.pipeline import V2Pipeline  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run V2 semantic-scene-graph dynamic SVG generation."
    )
    parser.add_argument("--prompt", required=True, help="Infographic request.")
    parser.add_argument("--model-id", default=None, help="Model profile id from root config.py.")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory. Defaults to 版本2/outputs.",
    )
    parser.add_argument(
        "--default-motion",
        action="store_true",
        help="Skip LLM MotionPlanner and use deterministic scene-order motion.",
    )
    parser.add_argument(
        "--no-repair",
        action="store_true",
        help="Skip the browser-feedback static SVG repair pass.",
    )
    args = parser.parse_args()

    pipeline = V2Pipeline(
        model_id=args.model_id,
        output_dir=Path(args.output_dir) if args.output_dir else None,
    )
    result = pipeline.run(
        args.prompt,
        use_llm_motion=not args.default_motion,
        repair_static=not args.no_repair,
    )
    print(f"SVG: {result.svg_path}")
    print(f"PNG: {result.png_path}")
    print(f"JSON: {result.json_path}")
    print(f"Metrics: {result.metrics.model_dump_json()}")


if __name__ == "__main__":
    main()
