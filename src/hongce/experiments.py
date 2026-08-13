"""Batch policy experiments from actual simulation runs."""

from __future__ import annotations

import json
from pathlib import Path
from statistics import mean, median
from typing import Any

from .engine import RunResult, run_policy
from .models import MVP_POLICY_CONFIGS, PolicyId
from .scenario import generate_qingyuan


def run_policy_batch(
    policies: list[str] | None = None,
    seeds: list[int] | None = None,
    population: int = 2000,
    output_dir: str | Path = "outputs/experiments",
) -> dict[str, Any]:
    policies = policies or [PolicyId.S0.value, PolicyId.S3.value, PolicyId.S5.value]
    seeds = seeds or list(range(202608060, 202608110))
    root = Path(output_dir)
    runs_dir = root / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    all_rows: list[dict[str, Any]] = []
    for seed in seeds:
        scenario = generate_qingyuan(seed=seed, population=population)
        for policy in policies:
            result = run_policy(policy, seed=seed, population=population, output_dir=runs_dir, scenario=scenario)
            row = result.metrics.model_dump(mode="json")
            row["policy_name"] = MVP_POLICY_CONFIGS[PolicyId(policy)].name
            all_rows.append(row)

    summary = summarize_rows(all_rows)
    comparison = {"label": "SIMULATED", "population": population, "seeds": seeds, "runs": all_rows, "summary": summary}
    (root / "comparison_s0_s3_s5.json").write_text(json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8")
    return comparison


def run_named_experiments(
    seeds: list[int] | None = None,
    population: int = 2000,
    output_dir: str | Path = "outputs/experiments",
) -> dict[str, Any]:
    """Run Experiments A/B/C from actual simulation outputs.

    MVP mappings:
    - A money allocation: S1/S3/S5 compare facility, care/roster, and combined allocation.
    - B trigger timing: S0/S2/S3 compare one-way baseline, faster digital warning, and confirmed call-down.
    - C chain break: S5 compared with S0/S2/S3/S4 as structured ablations.
    """
    seeds = seeds or list(range(202608060, 202608110))
    root = Path(output_dir)
    experiments = {
        "A_money_allocation": ["S1", "S3", "S5"],
        "B_trigger_timing": ["S0", "S2", "S3"],
        "C_chain_breaks": ["S0", "S2", "S3", "S4", "S5"],
    }
    payload: dict[str, Any] = {"label": "SIMULATED", "population": population, "seeds": seeds, "experiments": {}}
    for name, policies in experiments.items():
        comparison = run_policy_batch(
            policies=policies,
            seeds=seeds,
            population=population,
            output_dir=root / name,
        )
        payload["experiments"][name] = {
            "policies": policies,
            "summary": comparison["summary"],
            "interpretation": interpret_experiment(name, comparison["summary"]),
        }
    path = root / "experiments_abc_summary.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def write_explanation_pack(result: RunResult, output_dir: str | Path) -> Path:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    vulnerable_examples = sorted(
        [p for p in result.people if p.base.is_vulnerable],
        key=lambda p: (p.status.value, -(p.harm_risk), p.base.id),
    )[:12]
    facilities = {
        "bridge_east": {
            "label": "SYNTHETIC",
            "role": "links nursing home and north valley to the school shelter",
            "observed_failure_mode": "route_blocked" if any(p.status.value == "route_blocked" for p in result.people) else "not binding in this run",
        },
        "comms_hill": {
            "label": "SYNTHETIC",
            "role": "affects warning and confirmation in valley villages",
            "observed_failure_mode": "contact_failed" if any(p.status.value == "contact_failed" for p in result.people) else "partially compensated",
        },
    }
    pack = {
        "label": "SIMULATED",
        "run_id": result.run.id,
        "policy_id": result.run.policy_id.value,
        "metrics": result.metrics.model_dump(mode="json"),
        "representative_people": [
            {
                "id": p.base.id,
                "age": p.base.age,
                "location": p.base.location_id,
                "vulnerable": p.base.is_vulnerable,
                "status": p.status.value,
                "reason": p.reason,
                "timeline": {
                    "contact": p.contact_minute,
                    "confirm": p.confirmed_minute,
                    "waiting": p.waiting_minute,
                    "transit": p.transit_minute,
                    "sheltered": p.sheltered_minute,
                },
                "matching_decision_traces": [
                    t.model_dump(mode="json") for t in result.traces if t.actor_id == p.base.id
                ][:3],
            }
            for p in vulnerable_examples
        ],
        "facilities": facilities,
        "policy_breakpoints": infer_breakpoints(result),
    }
    path = root / f"{result.run.id}_explanation.json"
    path.write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
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
    by_policy: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_policy.setdefault(row["policy_id"], []).append(row)
    summary: dict[str, Any] = {}
    for policy_id, policy_rows in by_policy.items():
        summary[policy_id] = {"runs": len(policy_rows)}
        for metric in metric_names:
            values = sorted(float(row[metric]) for row in policy_rows if row.get(metric) is not None)
            summary[policy_id][metric] = {
                "mean": mean(values) if values else None,
                "median": median(values) if values else None,
                "p05": percentile(values, 0.05) if values else None,
                "p95": percentile(values, 0.95) if values else None,
                "worst": min(values) if values and metric not in {"vulnerable_harm_risk", "missed_critical_action_rate", "group_safety_gap", "resource_queue_minutes_mean"} else (max(values) if values else None),
            }
    add_incremental_costs(summary)
    return summary


def interpret_experiment(name: str, summary: dict[str, Any]) -> list[str]:
    notes: list[str] = []
    if not summary:
        return notes
    best_safe = max(summary, key=lambda p: summary[p]["safe_before_danger_rate"]["mean"])
    best_closure = max(summary, key=lambda p: summary[p]["response_closure_rate"]["mean"])
    lowest_gap = min(summary, key=lambda p: abs(summary[p]["group_safety_gap"]["mean"]))
    notes.append(f"{name}: highest simulated safe-before-danger rate is {best_safe}.")
    notes.append(f"{name}: strongest response closure is {best_closure}.")
    notes.append(f"{name}: closest-to-zero group safety gap is {lowest_gap}.")
    notes.append("These are conditional simulation results, not claims of real-world causal proof.")
    return notes


def infer_breakpoints(result: RunResult) -> dict[str, int]:
    counts = {
        "registry_gap": 0,
        "contact_failure": 0,
        "refusal_or_distrust": 0,
        "resource_blocked": 0,
        "route_blocked": 0,
        "shelter_mismatch": 0,
    }
    for person in result.people:
        status = person.status.value
        if status == "unregistered":
            counts["registry_gap"] += 1
        elif status == "contact_failed":
            counts["contact_failure"] += 1
        elif status in {"refused", "distrusted", "misunderstood"}:
            counts["refusal_or_distrust"] += 1
        elif status == "resource_blocked":
            counts["resource_blocked"] += 1
        elif status == "route_blocked":
            counts["route_blocked"] += 1
        elif status == "unsuitable_shelter":
            counts["shelter_mismatch"] += 1
    return counts


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    pos = (len(values) - 1) * q
    lower = int(pos)
    upper = min(len(values) - 1, lower + 1)
    weight = pos - lower
    return values[lower] * (1 - weight) + values[upper] * weight


def add_incremental_costs(summary: dict[str, Any]) -> None:
    baseline = summary.get(PolicyId.S0.value)
    if not baseline:
        return
    baseline_safe = baseline["safe_before_danger_rate"]["mean"]
    baseline_cost = MVP_POLICY_CONFIGS[PolicyId.S0].budget_units
    for policy_id, policy_summary in summary.items():
        cost = MVP_POLICY_CONFIGS[PolicyId(policy_id)].budget_units
        safe = policy_summary["safe_before_danger_rate"]["mean"]
        delta_safe = max(0.0, safe - baseline_safe)
        policy_summary["incremental_cost_per_safe_rate_point"] = None if delta_safe == 0 else (cost - baseline_cost) / delta_safe
