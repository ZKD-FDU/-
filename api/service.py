"""API service functions shared by FastAPI and the no-dependency demo server."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from typing import Any

from hongce.engine import run_policy
from hongce.experiments import run_named_experiments, run_policy_batch, write_explanation_pack
from hongce.models import PolicyId
from hongce.scenario import HazardConfig, ResourceProfile, SyntheticScenario, generate_qingyuan


RUN_CACHE: dict[str, dict[str, Any]] = {}
EXPERIMENT_CACHE: dict[str, dict[str, Any]] = {}
CASE_CORPUS_CACHE: dict[str, Any] | None = None
CASE_CORPUS_PATH = Path("data/processed/hongce_training_case_corpus.json")


def health() -> dict[str, Any]:
    case_count = load_case_corpus().get("summary", {}).get("case_count", 0)
    return {
        "status": "ok",
        "core": "RuleBasedAgentAdapter",
        "external_model_required": False,
        "data_labels": ["FACT", "SYNTHETIC", "SIMULATED"],
        "training_case_count": case_count,
    }


def validate_scenario(payload: dict[str, Any]) -> dict[str, Any]:
    population = int(payload.get("population", 2000))
    if population < 50:
        return {"valid": False, "reason": "人口数量至少为 50 才能进行有效仿真"}
    if population > 5000:
        return {"valid": False, "reason": "当前版本人口上限为 5000"}
    case_id = payload.get("case_id")
    case_context = build_case_context(case_id) if case_id else None
    if case_id and not case_context:
        return {"valid": False, "reason": f"未知的训练案例：{case_id}"}
    scenario_config = normalize_scenario_config(payload.get("scenario_overrides", {}))
    error = validate_scenario_config(scenario_config)
    if error:
        return {"valid": False, "reason": error}
    return {
        "valid": True,
        "label": "SYNTHETIC",
        "population": population,
        "case_context": case_context,
        "scenario_config": scenario_config,
    }


def run_simulation(payload: dict[str, Any]) -> dict[str, Any]:
    policy = payload.get("policy_id", "S0")
    seed = int(payload.get("seed", 20260806))
    population = int(payload.get("population", 2000))
    output_dir = payload.get("output_dir", "outputs/api")
    case_id = payload.get("case_id")
    case_context = build_case_context(case_id) if case_id else None
    if case_id and not case_context:
        return {"status": "failed", "error": f"unknown training case: {case_id}"}
    scenario_config = normalize_scenario_config(payload.get("scenario_overrides", {}))
    error = validate_scenario_config(scenario_config)
    if error:
        return {"status": "failed", "error": error}
    scenario = build_scenario(seed=seed, population=population, scenario_config=scenario_config)
    result = run_policy(policy, seed=seed, population=population, output_dir=output_dir, scenario=scenario)
    data = result.to_dict()
    if case_context:
        data["case_context"] = case_context
    data["scenario_config"] = scenario_config
    RUN_CACHE[result.run.id] = data
    write_explanation_pack(result, output_dir)
    return {
        "run_id": result.run.id,
        "status": result.run.status,
        "metrics": data["metrics"],
        "output_paths": result.run.output_paths,
        "case_context": case_context,
        "scenario_config": scenario_config,
    }


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


def load_case_corpus() -> dict[str, Any]:
    global CASE_CORPUS_CACHE
    if CASE_CORPUS_CACHE is None:
        if CASE_CORPUS_PATH.exists():
            CASE_CORPUS_CACHE = json.loads(CASE_CORPUS_PATH.read_text(encoding="utf-8"))
        else:
            CASE_CORPUS_CACHE = {"summary": {"case_count": 0}, "cases": []}
    return CASE_CORPUS_CACHE


def list_cases(filters: dict[str, Any] | None = None) -> dict[str, Any]:
    filters = filters or {}
    corpus = load_case_corpus()
    cases = corpus.get("cases", [])
    query = str(filters.get("q", "")).strip().lower()
    scenario_class = str(filters.get("scenario_class", "")).strip()
    module = str(filters.get("module", "")).strip()
    policy = str(filters.get("policy", "")).strip().upper()
    limit = int(filters.get("limit", 50))

    matched = []
    for case in cases:
        if query and query not in searchable_case_text(case).lower():
            continue
        if scenario_class and case.get("scenario_class") != scenario_class:
            continue
        if module and module not in case.get("simulation_modules", []):
            continue
        if policy and policy not in case.get("policy_scenarios", []):
            continue
        matched.append(summarize_case(case))

    return {
        "label": "FACT",
        "total": len(matched),
        "returned": min(len(matched), limit),
        "summary": corpus.get("summary", {}),
        "cases": matched[:limit],
    }


def get_case(case_id: str) -> dict[str, Any]:
    case = find_case(case_id)
    if not case:
        return {"error": "case not found", "case_id": case_id}
    return case


def generate_case_scenario(case_id: str) -> dict[str, Any]:
    case = find_case(case_id)
    if not case:
        return {"error": "case not found", "case_id": case_id}
    return {
        "label": "FACT_DERIVED_TEMPLATE",
        "case_id": case["case_id"],
        "case_name": case["case_name"],
        "scenario_class": case["scenario_class"],
        "hazard_trigger": case["hazard_trigger"],
        "affected_setting": case["affected_setting"],
        "actor_chain": case["actor_chain"],
        "state_machine": [step["state"] for step in case["process_trace"] if "state" in step],
        "bottom_up_signals": case["bottom_up_signals"],
        "failure_modes": case["failure_modes"],
        "intervention_points": case["intervention_points"],
        "recommended_policies": case["policy_scenarios"],
        "metric_candidates": case["metric_candidates"],
        "observed_outcomes": case["observed_outcomes"],
        "simulation_note": "该模板由真实报告训练语料生成；后续政策比较仍必须调用仿真内核实际运行。",
    }


def build_case_context(case_id: str | None) -> dict[str, Any] | None:
    if not case_id:
        return None
    case = find_case(case_id)
    if not case:
        return None
    return {
        "label": "FACT",
        "case_id": case["case_id"],
        "case_name": case["case_name"],
        "scenario_class": case["scenario_class"],
        "failure_modes": case["failure_modes"],
        "intervention_points": case["intervention_points"],
        "policy_scenarios": case["policy_scenarios"],
        "observed_outcomes": case["observed_outcomes"],
    }


def find_case(case_id: str) -> dict[str, Any] | None:
    for case in load_case_corpus().get("cases", []):
        if case.get("case_id") == case_id:
            return case
    return None


def summarize_case(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": case["case_id"],
        "case_name": case["case_name"],
        "source_report_role": case["source_report_role"],
        "scenario_class": case["scenario_class"],
        "affected_setting": case["affected_setting"],
        "failure_modes": case["failure_modes"],
        "intervention_points": case["intervention_points"],
        "metric_candidates": case["metric_candidates"],
        "simulation_modules": case["simulation_modules"],
        "policy_scenarios": case["policy_scenarios"],
        "observed_outcomes": case["observed_outcomes"],
    }


def searchable_case_text(case: dict[str, Any]) -> str:
    parts = [
        case.get("case_id", ""),
        case.get("case_name", ""),
        case.get("scenario_class", ""),
        " ".join(case.get("hazard_trigger", [])),
        " ".join(case.get("affected_setting", [])),
        " ".join(case.get("actor_chain", [])),
        " ".join(case.get("failure_modes", [])),
        " ".join(case.get("intervention_points", [])),
        " ".join(case.get("metric_candidates", [])),
    ]
    return " ".join(parts)


DEFAULT_SCENARIO_CONFIG: dict[str, Any] = {
    "vulnerable_ratio": 0.32,
    "timestep_minutes": 5,
    "warning_minute": 45,
    "evacuation_order_minute": 75,
    "bridge_closure_minute": 120,
    "danger_arrival_minute": 180,
    "communication_failure_minute": 90,
    "communication_failure_rate": 0.30,
    "vehicles": 18,
    "care_workers": 34,
    "stretchers": 18,
    "shelter_beds": 700,
}


def normalize_scenario_config(overrides: dict[str, Any] | None) -> dict[str, Any]:
    overrides = overrides or {}
    config = dict(DEFAULT_SCENARIO_CONFIG)
    for key in config:
        if key in overrides and overrides[key] not in {"", None}:
            config[key] = overrides[key]
    for key in {
        "timestep_minutes",
        "warning_minute",
        "evacuation_order_minute",
        "bridge_closure_minute",
        "danger_arrival_minute",
        "communication_failure_minute",
        "vehicles",
        "care_workers",
        "stretchers",
        "shelter_beds",
    }:
        config[key] = int(float(config[key]))
    for key in {"vulnerable_ratio", "communication_failure_rate"}:
        config[key] = float(config[key])
    return config


def validate_scenario_config(config: dict[str, Any]) -> str | None:
    if not 0.05 <= config["vulnerable_ratio"] <= 0.85:
        return "脆弱人口比例必须在 0.05 到 0.85 之间"
    if config["timestep_minutes"] not in {5, 10, 15}:
        return "时间步长只能是 5、10 或 15 分钟"
    if not 0 <= config["warning_minute"] < config["danger_arrival_minute"]:
        return "预警时刻必须早于危险到达时刻"
    if not config["warning_minute"] <= config["evacuation_order_minute"] <= config["danger_arrival_minute"]:
        return "转移命令时刻必须位于预警时刻与危险到达时刻之间"
    if not config["warning_minute"] <= config["communication_failure_minute"] <= config["danger_arrival_minute"]:
        return "通信失败时刻必须位于预警时刻与危险到达时刻之间"
    if not 0 <= config["bridge_closure_minute"] <= config["danger_arrival_minute"]:
        return "桥梁封闭时刻不能晚于危险到达时刻"
    if not 0 <= config["communication_failure_rate"] <= 0.95:
        return "通信失败率必须在 0 到 0.95 之间"
    for key in {"vehicles", "care_workers", "stretchers"}:
        if not 1 <= config[key] <= 300:
            label = {"vehicles": "转运车辆", "care_workers": "照护人员", "stretchers": "担架数量"}[key]
            return f"{label}必须在 1 到 300 之间"
    if not 50 <= config["shelter_beds"] <= 5000:
        return "避难床位必须在 50 到 5000 之间"
    return None


def build_scenario(seed: int, population: int, scenario_config: dict[str, Any]) -> SyntheticScenario:
    scenario = generate_qingyuan(seed=seed, population=population)
    scenario.hazard = HazardConfig(
        timestep_minutes=scenario_config["timestep_minutes"],
        start_minute=0,
        end_minute=max(240, scenario_config["danger_arrival_minute"] + 60),
        warning_minute=scenario_config["warning_minute"],
        evacuation_order_minute=scenario_config["evacuation_order_minute"],
        bridge_closure_minute=scenario_config["bridge_closure_minute"],
        danger_arrival_minute=scenario_config["danger_arrival_minute"],
        communication_failure_minute=scenario_config["communication_failure_minute"],
        communication_failure_rate=scenario_config["communication_failure_rate"],
    )
    scenario.resources = replace(
        ResourceProfile(),
        vehicles=scenario_config["vehicles"],
        care_workers=scenario_config["care_workers"],
        stretchers=scenario_config["stretchers"],
        shelter_beds=scenario_config["shelter_beds"],
    )
    scenario.people = tune_vulnerable_ratio(scenario, scenario_config["vulnerable_ratio"])
    return scenario


def tune_vulnerable_ratio(scenario: SyntheticScenario, target_ratio: float):
    target = round(len(scenario.people) * target_ratio)
    people = list(scenario.people)
    vulnerable = [person for person in people if person.is_vulnerable]
    if len(vulnerable) == target:
        return people
    if len(vulnerable) < target:
        need = target - len(vulnerable)
        tuned = 0
        new_people = []
        for person in people:
            if tuned < need and not person.is_vulnerable:
                person = person.model_copy(
                    update={
                        "age": max(person.age, 76),
                        "mobility": "limited",
                        "care_dependency": "partial",
                        "digital_access": min(person.digital_access, 0.28),
                        "chronic_condition": True,
                    }
                )
                tuned += 1
            new_people.append(person)
        return new_people

    excess = len(vulnerable) - target
    tuned = 0
    new_people = []
    for person in people:
        if tuned < excess and person.is_vulnerable and not person.institution_id:
            person = person.model_copy(
                update={
                    "age": min(person.age, 58),
                    "mobility": "independent",
                    "care_dependency": "none",
                    "digital_access": max(person.digital_access, 0.72),
                    "chronic_condition": False,
                }
            )
            tuned += 1
        new_people.append(person)
    return new_people
