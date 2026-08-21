"""Decision-science layer for HongCe policy optimization.

This module keeps the reinforcement-learning framing explicit while using the
existing deterministic simulation kernel as the transition function. The first
implemented optimizer is intentionally transparent: it searches policy
parameters and scores every candidate from actual simulation runs.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import itertools
import random
from statistics import mean
from typing import Any, Iterable, Literal

from .engine import RunResult, run_policy
from .models import PolicyId
from .scenario import HazardConfig, ResourceProfile, SyntheticScenario, generate_qingyuan


@dataclass(frozen=True)
class MDPDefinition:
    """Formal decision contract used for POMDP/RL handoff."""

    observation_model: Literal["MDP", "POMDP"]
    state_variables: tuple[str, ...]
    action_variables: tuple[str, ...]
    reward_terms: dict[str, float]
    transition_source: str
    constraints: dict[str, float]
    calibration_sources: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": "MDP_CONTRACT",
            "observation_model": self.observation_model,
            "state_variables": list(self.state_variables),
            "action_variables": list(self.action_variables),
            "reward_terms": self.reward_terms,
            "transition_source": self.transition_source,
            "constraints": self.constraints,
            "calibration_sources": list(self.calibration_sources),
        }


@dataclass(frozen=True)
class PolicyParameterCandidate:
    warning_lead_minutes: int
    order_lead_minutes: int
    vehicle_multiplier: float
    vulnerable_priority_weight: float
    bridge_closure_threshold: float
    communication_repair_strength: float
    base_policy_id: str = "S5"

    def to_scenario_config(self, base: dict[str, Any]) -> dict[str, Any]:
        danger = int(base["danger_arrival_minute"])
        config = dict(base)
        warning = max(0, danger - self.warning_lead_minutes)
        order = max(warning, danger - self.order_lead_minutes)
        config["warning_minute"] = warning
        config["evacuation_order_minute"] = min(order, danger - 5)
        config["vehicles"] = max(1, round(int(base["vehicles"]) * self.vehicle_multiplier))
        config["care_workers"] = max(1, round(int(base["care_workers"]) * (1.0 + 0.25 * self.vulnerable_priority_weight)))
        config["stretchers"] = max(1, round(int(base["stretchers"]) * (1.0 + 0.18 * self.vulnerable_priority_weight)))
        config["communication_failure_rate"] = round(
            max(0.0, float(base["communication_failure_rate"]) * (1.0 - self.communication_repair_strength)),
            3,
        )
        closure_delay = round(45 * max(0.0, self.bridge_closure_threshold - 0.5))
        config["bridge_closure_minute"] = min(danger, max(warning, int(base["bridge_closure_minute"]) + closure_delay))
        return config

    def to_dict(self) -> dict[str, Any]:
        return {
            "warning_lead_minutes": self.warning_lead_minutes,
            "order_lead_minutes": self.order_lead_minutes,
            "vehicle_multiplier": self.vehicle_multiplier,
            "vulnerable_priority_weight": self.vulnerable_priority_weight,
            "bridge_closure_threshold": self.bridge_closure_threshold,
            "communication_repair_strength": self.communication_repair_strength,
            "base_policy_id": self.base_policy_id,
        }


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


def default_mdp_definition() -> MDPDefinition:
    return MDPDefinition(
        observation_model="POMDP",
        state_variables=(
            "minute",
            "rain_flood_risk_level",
            "communication_failure_rate",
            "bridge_state",
            "waiting_population_by_place",
            "vulnerable_population_by_place",
            "vehicle_slots_remaining",
            "shelter_beds_remaining",
            "care_slots_remaining",
            "public_trust_mean",
        ),
        action_variables=(
            "issue_warning_minute",
            "escalate_response",
            "dispatch_vehicle_to_place",
            "prioritize_nursing_home",
            "close_or_reroute_bridge",
            "activate_backup_shelter",
            "assign_grid_call_workers",
        ),
        reward_terms={
            "safe_before_danger_rate": 2.2,
            "vulnerable_harm_risk": -2.8,
            "lead_time_minutes_median": 0.015,
            "resource_queue_minutes_mean": -0.012,
            "group_safety_gap_abs": -1.4,
            "missed_critical_action_rate": -1.1,
            "trust_delta": 0.35,
        },
        transition_source="hongce.engine.run_policy actual multi-agent simulation",
        constraints={
            "max_vulnerable_harm_risk": 0.32,
            "max_abs_group_safety_gap": 0.18,
            "min_safe_before_danger_rate": 0.72,
            "max_resource_queue_minutes_mean": 90.0,
        },
        calibration_sources=(
            "MEM disaster case corpus parameter ranges",
            "QGIS spatial package route/risk/coverage metrics",
            "expert-reviewed hazard-factor priors",
            "S0-S5 simulation baselines and ablations",
        ),
    )


def evaluate_reward(metrics: dict[str, Any], definition: MDPDefinition | None = None) -> dict[str, Any]:
    definition = definition or default_mdp_definition()
    terms = {
        "safe_before_danger_rate": float(metrics.get("safe_before_danger_rate", 0.0)),
        "vulnerable_harm_risk": float(metrics.get("vulnerable_harm_risk", 0.0)),
        "lead_time_minutes_median": float(metrics.get("lead_time_minutes_median", 0.0)),
        "resource_queue_minutes_mean": float(metrics.get("resource_queue_minutes_mean", 0.0)),
        "group_safety_gap_abs": abs(float(metrics.get("group_safety_gap", 0.0))),
        "missed_critical_action_rate": float(metrics.get("missed_critical_action_rate", 0.0)),
        "trust_delta": float(metrics.get("trust_delta", 0.0)),
    }
    reward = sum(terms[name] * definition.reward_terms[name] for name in definition.reward_terms)
    violations = constraint_violations(metrics, definition)
    penalty = sum(violations.values()) * 2.0
    return {
        "reward": round(reward - penalty, 6),
        "raw_reward": round(reward, 6),
        "constraint_penalty": round(penalty, 6),
        "terms": terms,
        "violations": violations,
    }


def constraint_violations(metrics: dict[str, Any], definition: MDPDefinition | None = None) -> dict[str, float]:
    definition = definition or default_mdp_definition()
    constraints = definition.constraints
    values = {
        "max_vulnerable_harm_risk": float(metrics.get("vulnerable_harm_risk", 0.0)),
        "max_abs_group_safety_gap": abs(float(metrics.get("group_safety_gap", 0.0))),
        "min_safe_before_danger_rate": float(metrics.get("safe_before_danger_rate", 0.0)),
        "max_resource_queue_minutes_mean": float(metrics.get("resource_queue_minutes_mean", 0.0)),
    }
    violations: dict[str, float] = {}
    for key, bound in constraints.items():
        value = values[key]
        if key.startswith("min_"):
            amount = max(0.0, bound - value)
        else:
            amount = max(0.0, value - bound)
        if amount:
            violations[key] = round(amount, 6)
    return violations


def optimize_policy_parameters(
    seeds: list[int] | None = None,
    population: int = 500,
    method: Literal["grid", "random"] = "grid",
    max_candidates: int = 24,
    scenario_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    seeds = seeds or [202608060, 202608061, 202608062]
    base_config = {**DEFAULT_SCENARIO_CONFIG, **(scenario_overrides or {})}
    candidates = list(candidate_grid(base_config))
    if method == "random":
        rng = random.Random(20260821)
        rng.shuffle(candidates)
    candidates = candidates[:max_candidates]

    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        run_metrics = []
        rewards = []
        for seed in seeds:
            scenario_config = candidate.to_scenario_config(base_config)
            scenario = build_scenario_from_config(seed, population, scenario_config)
            result = run_policy(candidate.base_policy_id, seed=seed, population=population, scenario=scenario)
            metrics = result.metrics.model_dump(mode="json")
            scored = evaluate_reward(metrics)
            run_metrics.append(metrics)
            rewards.append(scored["reward"])
        aggregate = aggregate_metrics(run_metrics)
        scored_aggregate = evaluate_reward(aggregate)
        rows.append(
            {
                "candidate": candidate.to_dict(),
                "scenario_config": candidate.to_scenario_config(base_config),
                "reward_mean": round(mean(rewards), 6),
                "aggregate_reward": scored_aggregate["reward"],
                "metrics_mean": aggregate,
                "violations": scored_aggregate["violations"],
                "runs": len(run_metrics),
            }
        )
    rows.sort(key=lambda row: (not row["violations"], row["aggregate_reward"], row["reward_mean"]), reverse=True)
    return {
        "label": "SIMULATED_POLICY_OPTIMIZATION",
        "method": method,
        "population": population,
        "seeds": seeds,
        "mdp": default_mdp_definition().to_dict(),
        "best": rows[0] if rows else None,
        "candidates": rows,
        "note": "All candidate scores come from actual HongCe simulation runs.",
    }


def contextual_bandit_recommendation(
    context: dict[str, Any] | None = None,
    seeds: list[int] | None = None,
    population: int = 500,
) -> dict[str, Any]:
    """Small interpretable RL module: evaluate arms and choose best reward."""

    context = context or {}
    base = {**DEFAULT_SCENARIO_CONFIG, **context.get("scenario_overrides", {})}
    arms = [
        ("early_warning", PolicyParameterCandidate(150, 105, 1.0, 0.4, 0.55, 0.15)),
        ("add_vehicles", PolicyParameterCandidate(120, 90, 1.35, 0.2, 0.55, 0.10)),
        ("nursing_priority", PolicyParameterCandidate(120, 95, 1.12, 0.9, 0.60, 0.20)),
        ("backup_comms", PolicyParameterCandidate(120, 90, 1.0, 0.5, 0.55, 0.55)),
        ("bridge_reroute", PolicyParameterCandidate(115, 90, 1.08, 0.5, 0.85, 0.20)),
    ]
    results = []
    for arm_id, candidate in arms:
        optimized = optimize_policy_parameters(
            seeds=seeds,
            population=population,
            method="grid",
            max_candidates=1,
            scenario_overrides=candidate.to_scenario_config(base),
        )
        best = optimized["best"]
        results.append(
            {
                "arm_id": arm_id,
                "action": bandit_action_label(arm_id),
                "expected_reward": best["aggregate_reward"],
                "metrics_mean": best["metrics_mean"],
                "constraints": best["violations"],
                "scenario_config": best["scenario_config"],
            }
        )
    results.sort(key=lambda row: (not row["constraints"], row["expected_reward"]), reverse=True)
    return {
        "label": "CONTEXTUAL_BANDIT_POLICY_RECOMMENDATION",
        "context": context,
        "arms": results,
        "recommended": results[0],
        "safety_note": "Bandit arms are ranked only after hard-constraint penalties are applied.",
    }


def candidate_grid(base_config: dict[str, Any]) -> Iterable[PolicyParameterCandidate]:
    danger = int(base_config["danger_arrival_minute"])
    warning_leads = sorted({min(danger, value) for value in (90, 120, 150)})
    order_leads = sorted({min(danger - 5, value) for value in (60, 90, 110)})
    vehicle_multipliers = (1.0, 1.2, 1.4)
    priority_weights = (0.25, 0.65, 1.0)
    bridge_thresholds = (0.55, 0.75)
    comms_strengths = (0.0, 0.35, 0.6)
    for values in itertools.product(
        warning_leads,
        order_leads,
        vehicle_multipliers,
        priority_weights,
        bridge_thresholds,
        comms_strengths,
    ):
        warning, order, vehicles, priority, bridge, comms = values
        if warning <= order:
            yield PolicyParameterCandidate(warning, order, vehicles, priority, bridge, comms)


def build_scenario_from_config(seed: int, population: int, config: dict[str, Any]) -> SyntheticScenario:
    scenario = generate_qingyuan(seed=seed, population=population)
    scenario.hazard = HazardConfig(
        timestep_minutes=int(config["timestep_minutes"]),
        start_minute=0,
        end_minute=max(240, int(config["danger_arrival_minute"]) + 60),
        warning_minute=int(config["warning_minute"]),
        evacuation_order_minute=int(config["evacuation_order_minute"]),
        bridge_closure_minute=int(config["bridge_closure_minute"]),
        danger_arrival_minute=int(config["danger_arrival_minute"]),
        communication_failure_minute=int(config["communication_failure_minute"]),
        communication_failure_rate=float(config["communication_failure_rate"]),
    )
    scenario.resources = replace(
        ResourceProfile(),
        vehicles=int(config["vehicles"]),
        care_workers=int(config["care_workers"]),
        stretchers=int(config["stretchers"]),
        shelter_beds=int(config["shelter_beds"]),
    )
    return scenario


def aggregate_metrics(rows: list[dict[str, Any]]) -> dict[str, float]:
    metric_names = [
        "safe_before_danger_rate",
        "vulnerable_harm_risk",
        "lead_time_minutes_median",
        "response_closure_rate",
        "missed_critical_action_rate",
        "group_safety_gap",
        "trust_delta",
        "resource_queue_minutes_mean",
    ]
    return {
        name: round(mean(float(row.get(name, 0.0)) for row in rows), 6)
        for name in metric_names
    }


def bandit_action_label(arm_id: str) -> str:
    return {
        "early_warning": "提前发布预警并提前转移命令",
        "add_vehicles": "增加车辆与转运吞吐",
        "nursing_priority": "养老机构与脆弱人群优先",
        "backup_comms": "启用备用通信与网格叫应",
        "bridge_reroute": "提高桥涵阈值并提前绕行",
    }[arm_id]
