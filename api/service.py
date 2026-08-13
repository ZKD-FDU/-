"""API service functions shared by FastAPI and the no-dependency demo server."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hongce.engine import run_policy
from hongce.experiments import run_named_experiments, run_policy_batch, write_explanation_pack
from hongce.models import PolicyId


RUN_CACHE: dict[str, dict[str, Any]] = {}
EXPERIMENT_CACHE: dict[str, dict[str, Any]] = {}


def health() -> dict[str, Any]:
    return {"status": "ok", "core": "RuleBasedAgentAdapter", "external_model_required": False, "data_labels": ["SYNTHETIC", "SIMULATED"]}


def validate_scenario(payload: dict[str, Any]) -> dict[str, Any]:
    population = int(payload.get("population", 2000))
    if population < 50:
        return {"valid": False, "reason": "population must be at least 50 for meaningful simulation"}
    if population > 5000:
        return {"valid": False, "reason": "MVP population limit is 5000"}
    return {"valid": True, "label": "SYNTHETIC", "population": population}


def run_simulation(payload: dict[str, Any]) -> dict[str, Any]:
    policy = payload.get("policy_id", "S0")
    seed = int(payload.get("seed", 20260806))
    population = int(payload.get("population", 2000))
    output_dir = payload.get("output_dir", "outputs/api")
    result = run_policy(policy, seed=seed, population=population, output_dir=output_dir)
    data = result.to_dict()
    RUN_CACHE[result.run.id] = data
    write_explanation_pack(result, output_dir)
    return {"run_id": result.run.id, "status": result.run.status, "metrics": data["metrics"], "output_paths": result.run.output_paths}


def get_simulation(run_id: str) -> dict[str, Any]:
    if run_id in RUN_CACHE:
        return RUN_CACHE[run_id]
    for path in Path("outputs").glob(f"**/{run_id}.json"):
        return json.loads(path.read_text(encoding="utf-8"))
    return {"error": "run not found", "run_id": run_id}


def get_events(run_id: str) -> dict[str, Any]:
    data = get_simulation(run_id)
    return {"run_id": run_id, "events": data.get("events", [])}


def get_agent_trace(run_id: str, agent_id: str) -> dict[str, Any]:
    data = get_simulation(run_id)
    traces = [trace for trace in data.get("traces", []) if trace.get("actor_id") == agent_id]
    agents = [agent for agent in data.get("agents", []) if agent.get("id") == agent_id]
    return {"run_id": run_id, "agent": agents[0] if agents else None, "traces": traces}


def run_experiment(payload: dict[str, Any]) -> dict[str, Any]:
    population = int(payload.get("population", 2000))
    seeds = payload.get("seeds")
    if isinstance(seeds, str):
        seeds = [int(s.strip()) for s in seeds.split(",") if s.strip()]
    elif not seeds:
        seeds = list(range(202608060, 202608110))
    output_dir = payload.get("output_dir", "outputs/api_experiments")
    experiment = payload.get("experiment", "s0_s3_s5")
    if experiment == "abc":
        data = run_named_experiments(seeds=seeds, population=population, output_dir=output_dir)
    else:
        policies = payload.get("policies", [PolicyId.S0.value, PolicyId.S3.value, PolicyId.S5.value])
        data = run_policy_batch(policies=policies, seeds=seeds, population=population, output_dir=output_dir)
    experiment_id = f"exp-{experiment}-{population}-{len(seeds)}"
    EXPERIMENT_CACHE[experiment_id] = data
    return {"experiment_id": experiment_id, "status": "succeeded", "comparison": data}


def get_experiment_comparison(experiment_id: str) -> dict[str, Any]:
    if experiment_id in EXPERIMENT_CACHE:
        return EXPERIMENT_CACHE[experiment_id]
    path = Path("outputs/experiments/experiments_abc_summary.json")
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    path = Path("outputs/experiments/comparison_s0_s3_s5.json")
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"error": "experiment not found", "experiment_id": experiment_id}
