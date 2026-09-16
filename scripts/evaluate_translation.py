"""Run a sourced, local translation comparison and create a new JSON report."""

import argparse
import json
from pathlib import Path

from isc_helwigii.local_translation import default_model_dir, model_status
from isc_helwigii.translation_evaluation import evaluate_translation_set


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--model-dir", type=Path, default=default_model_dir())
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output must be a new file.")
    status = model_status(args.model_dir)
    if not status["installed"]:
        parser.error(status["error"])
    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    result = evaluate_translation_set(dataset, model_dir=args.model_dir)
    with args.output.open("x", encoding="utf-8") as output:
        output.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
