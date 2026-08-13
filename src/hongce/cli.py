"""Command-line interface for HongCe."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .engine import run_policy
from .experiments import run_named_experiments, run_policy_batch, write_explanation_pack
from .models import PolicyId
from .scenario import generate_qingyuan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hongce", description="HongCe simulation CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    scenario_cmd = sub.add_parser("generate-scenario")
    scenario_cmd.add_argument("--seed", type=int, default=20260806)
    scenario_cmd.add_argument("--population", type=int, default=2000)
    scenario_cmd.add_argument("--out", default="data/generated/qingyuan_scenario_summary.json")

    run_cmd = sub.add_parser("run")
    run_cmd.add_argument("--policy", choices=[p.value for p in PolicyId], default="S0")
    run_cmd.add_argument("--seed", type=int, default=20260806)
    run_cmd.add_argument("--population", type=int, default=2000)
    run_cmd.add_argument("--out-dir", default="outputs/demo")

    batch_cmd = sub.add_parser("batch")
    batch_cmd.add_argument("--policies", default="S0,S3,S5")
    batch_cmd.add_argument("--seeds", default="202608060:202608110")
    batch_cmd.add_argument("--population", type=int, default=2000)
    batch_cmd.add_argument("--out-dir", default="outputs/experiments")

    experiments_cmd = sub.add_parser("experiments")
    experiments_cmd.add_argument("--seeds", default="202608060:202608110")
    experiments_cmd.add_argument("--population", type=int, default=2000)
    experiments_cmd.add_argument("--out-dir", default="outputs/experiments")

    explain_cmd = sub.add_parser("explain")
    explain_cmd.add_argument("--policy", choices=[p.value for p in PolicyId], default="S5")
    explain_cmd.add_argument("--seed", type=int, default=20260806)
    explain_cmd.add_argument("--population", type=int, default=2000)
    explain_cmd.add_argument("--out-dir", default="outputs/demo")

    args = parser.parse_args(argv)
    if args.command == "generate-scenario":
        scenario = generate_qingyuan(seed=args.seed, population=args.population)
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "label": "SYNTHETIC",
            "seed": scenario.seed,
            "county_name": scenario.county_name,
            "people": len(scenario.people),
            "households": len(scenario.households),
            "institutions": [i.model_dump(mode="json") for i in scenario.institutions],
            "infrastructure": [i.model_dump(mode="json") for i in scenario.infrastructure],
            "network_edges": len(scenario.network_edges),
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(path)
        return 0
    if args.command == "run":
        result = run_policy(args.policy, seed=args.seed, population=args.population, output_dir=args.out_dir)
        print(json.dumps(result.metrics.model_dump(mode="json"), ensure_ascii=False, indent=2))
        return 0
    if args.command == "batch":
        policies = [p.strip() for p in args.policies.split(",") if p.strip()]
        seeds = parse_seeds(args.seeds)
        result = run_policy_batch(policies=policies, seeds=seeds, population=args.population, output_dir=args.out_dir)
        print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
        return 0
    if args.command == "experiments":
        result = run_named_experiments(
            seeds=parse_seeds(args.seeds),
            population=args.population,
            output_dir=args.out_dir,
        )
        print(json.dumps(result["experiments"], ensure_ascii=False, indent=2))
        return 0
    if args.command == "explain":
        result = run_policy(args.policy, seed=args.seed, population=args.population)
        path = write_explanation_pack(result, args.out_dir)
        print(path)
        return 0
    return 1


def parse_seeds(value: str) -> list[int]:
    if ":" in value:
        start, end = value.split(":", 1)
        return list(range(int(start), int(end)))
    return [int(v.strip()) for v in value.split(",") if v.strip()]


if __name__ == "__main__":
    raise SystemExit(main())
