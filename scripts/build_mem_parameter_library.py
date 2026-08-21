"""Build the HongCe MEM case-derived parameter library."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CALIBRATION_PATH = ROOT / "src/hongce/calibration.py"

spec = importlib.util.spec_from_file_location("hongce_calibration", CALIBRATION_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"failed to load calibration module: {CALIBRATION_PATH}")
calibration = importlib.util.module_from_spec(spec)
sys.modules["hongce_calibration"] = calibration
spec.loader.exec_module(calibration)


def main() -> int:
    args = parse_args()
    library = calibration.write_parameter_library(args.corpus, args.out)
    print(
        json.dumps(
            {
                "out": str(args.out),
                "case_count": library["quality"]["case_count"],
                "parameter_estimate_count": library["quality"]["parameter_estimate_count"],
                "mean_confidence": library["quality"]["mean_confidence"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build MEM case parameter library.")
    parser.add_argument("--corpus", default=ROOT / "data/processed/hongce_training_case_corpus.json")
    parser.add_argument("--out", default=ROOT / "data/parameters/mem_case_parameter_library.json")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
