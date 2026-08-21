"""Case-derived parameter calibration for HongCe.

This module turns the processed Ministry of Emergency Management case corpus
into a structured parameter library. The estimates are intentionally ranges,
not point truths: most source reports do not expose every variable needed by
the simulator, so each estimate carries a source label and confidence.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import re
from pathlib import Path
from statistics import mean
from typing import Any


CASE_CORPUS_PATH = Path("data/processed/hongce_training_case_corpus.json")
PARAMETER_LIBRARY_PATH = Path("data/parameters/mem_case_parameter_library.json")
SCHEMA_VERSION = "0.2"


SOURCE_FACT_DERIVED = "CASE_DERIVED"
SOURCE_EXPERT_PRIOR = "EXPERT_PRIOR"
SOURCE_QGIS_DERIVED = "QGIS_DERIVED"
SOURCE_SYNTHETIC = "SYNTHETIC_ASSUMPTION"


PARAMETER_DEFINITIONS: dict[str, dict[str, str]] = {
    "warning_lead_minutes": {
        "unit": "minutes",
        "description": "Time between first actionable warning and danger arrival.",
    },
    "evacuation_order_delay_minutes": {
        "unit": "minutes",
        "description": "Delay from warning release to explicit evacuation/transfer order.",
    },
    "response_activation_delay_minutes": {
        "unit": "minutes",
        "description": "Delay from risk detection to graded response activation.",
    },
    "communication_failure_rate": {
        "unit": "share",
        "description": "Share of target population missed or delayed by channel degradation.",
    },
    "grassroots_call_strength": {
        "unit": "0-1",
        "description": "Intensity of grid/community confirmation and call-to-response work.",
    },
    "vulnerable_priority_weight": {
        "unit": "multiplier",
        "description": "Priority weight applied to older, disabled, institutional or digitally excluded people.",
    },
    "bridge_closure_threshold": {
        "unit": "risk_score",
        "description": "Risk score at which bridge/culvert closure or reroute is triggered.",
    },
    "route_failure_probability": {
        "unit": "share",
        "description": "Probability that an assigned transfer route becomes blocked or requires rerouting.",
    },
    "shelter_capacity_pressure": {
        "unit": "demand/capacity",
        "description": "Expected pressure on formal shelter capacity.",
    },
    "public_trust_delta_prior": {
        "unit": "delta",
        "description": "Prior change in trust/satisfaction caused by warning credibility and transfer burden.",
    },
    "casualty_rate_anchor": {
        "unit": "per_1000_exposed",
        "description": "Outcome anchor derived from reported casualties when exposed population is unknown.",
    },
    "property_loss_rate_anchor": {
        "unit": "normalized_index",
        "description": "Outcome anchor derived from reported direct economic loss.",
    },
}


SCENARIO_PRIORS: dict[str, dict[str, tuple[float, float, str]]] = {
    "极端降雨洪涝/山洪及基础设施失效": {
        "warning_lead_minutes": (45, 180, SOURCE_FACT_DERIVED),
        "evacuation_order_delay_minutes": (15, 75, SOURCE_FACT_DERIVED),
        "response_activation_delay_minutes": (10, 60, SOURCE_FACT_DERIVED),
        "communication_failure_rate": (0.18, 0.55, SOURCE_FACT_DERIVED),
        "bridge_closure_threshold": (0.55, 0.78, SOURCE_QGIS_DERIVED),
        "route_failure_probability": (0.12, 0.38, SOURCE_QGIS_DERIVED),
        "shelter_capacity_pressure": (0.85, 1.45, SOURCE_EXPERT_PRIOR),
    },
    "地质灾害/堆填体滑坡": {
        "warning_lead_minutes": (10, 90, SOURCE_FACT_DERIVED),
        "evacuation_order_delay_minutes": (5, 45, SOURCE_FACT_DERIVED),
        "response_activation_delay_minutes": (10, 80, SOURCE_FACT_DERIVED),
        "communication_failure_rate": (0.12, 0.40, SOURCE_EXPERT_PRIOR),
        "route_failure_probability": (0.20, 0.55, SOURCE_QGIS_DERIVED),
    },
    "人员密集或脆弱机构场所": {
        "warning_lead_minutes": (5, 90, SOURCE_FACT_DERIVED),
        "evacuation_order_delay_minutes": (5, 45, SOURCE_FACT_DERIVED),
        "communication_failure_rate": (0.08, 0.32, SOURCE_FACT_DERIVED),
        "vulnerable_priority_weight": (1.8, 3.2, SOURCE_FACT_DERIVED),
        "shelter_capacity_pressure": (0.75, 1.35, SOURCE_EXPERT_PRIOR),
    },
    "道路交通/通道安全": {
        "warning_lead_minutes": (0, 60, SOURCE_FACT_DERIVED),
        "route_failure_probability": (0.18, 0.48, SOURCE_QGIS_DERIVED),
        "bridge_closure_threshold": (0.50, 0.75, SOURCE_QGIS_DERIVED),
    },
}


DEFAULT_PRIORS: dict[str, tuple[float, float, str]] = {
    "warning_lead_minutes": (15, 120, SOURCE_FACT_DERIVED),
    "evacuation_order_delay_minutes": (10, 60, SOURCE_FACT_DERIVED),
    "response_activation_delay_minutes": (10, 70, SOURCE_FACT_DERIVED),
    "communication_failure_rate": (0.10, 0.42, SOURCE_EXPERT_PRIOR),
    "grassroots_call_strength": (0.30, 0.85, SOURCE_EXPERT_PRIOR),
    "vulnerable_priority_weight": (1.2, 2.6, SOURCE_EXPERT_PRIOR),
    "bridge_closure_threshold": (0.55, 0.80, SOURCE_QGIS_DERIVED),
    "route_failure_probability": (0.08, 0.35, SOURCE_QGIS_DERIVED),
    "shelter_capacity_pressure": (0.70, 1.30, SOURCE_EXPERT_PRIOR),
    "public_trust_delta_prior": (-0.08, 0.08, SOURCE_EXPERT_PRIOR),
}


def load_case_corpus(path: str | Path = CASE_CORPUS_PATH) -> dict[str, Any]:
    corpus_path = Path(path)
    return json.loads(corpus_path.read_text(encoding="utf-8"))


def load_parameter_library(path: str | Path = PARAMETER_LIBRARY_PATH) -> dict[str, Any]:
    library_path = Path(path)
    if library_path.exists():
        return json.loads(library_path.read_text(encoding="utf-8"))
    return build_parameter_library(load_case_corpus())


def write_parameter_library(
    corpus_path: str | Path = CASE_CORPUS_PATH,
    output_path: str | Path = PARAMETER_LIBRARY_PATH,
) -> dict[str, Any]:
    library = build_parameter_library(load_case_corpus(corpus_path))
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(library, ensure_ascii=False, indent=2), encoding="utf-8")
    return library


def build_parameter_library(corpus: dict[str, Any]) -> dict[str, Any]:
    cases = [case_parameter_record(case) for case in corpus.get("cases", [])]
    aggregates = aggregate_parameter_records(cases)
    parameter_index = build_parameter_index(cases)
    quality = summarize_parameter_library({"cases": cases, "aggregates": aggregates, "parameter_index": parameter_index})
    return {
        "label": "FACT_DERIVED_PARAMETER_LIBRARY",
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_corpus": str(CASE_CORPUS_PATH),
        "source_summary": corpus.get("summary", {}),
        "parameter_definitions": PARAMETER_DEFINITIONS,
        "source_labels": {
            SOURCE_FACT_DERIVED: "Extracted or inferred from MEM case reports.",
            SOURCE_QGIS_DERIVED: "Requires QGIS spatial package or route/risk overlay for final value.",
            SOURCE_EXPERT_PRIOR: "Expert-review prior range awaiting calibration.",
            SOURCE_SYNTHETIC: "Temporary assumption used only when no case evidence exists.",
        },
        "quality": quality,
        "aggregates": aggregates,
        "parameter_index": parameter_index,
        "cases": cases,
        "usage_note": "Use ranges for sensitivity analysis and policy optimization; do not cite automatic extraction without PDF/source review.",
    }


def case_parameter_record(case: dict[str, Any]) -> dict[str, Any]:
    scenario_class = case.get("scenario_class", "")
    parameter_estimates = estimate_case_parameters(case)
    outcomes = parse_observed_outcomes(case.get("observed_outcomes", {}))
    readiness = calibration_readiness(case, parameter_estimates, outcomes)
    return {
        "case_id": case.get("case_id"),
        "case_name": case.get("case_name"),
        "scenario_class": scenario_class,
        "source_report_role": case.get("source_report_role"),
        "source_url": case.get("source_url"),
        "pdf_url": case.get("pdf_url"),
        "hazard_trigger": case.get("hazard_trigger", []),
        "affected_setting": case.get("affected_setting", []),
        "actor_chain": case.get("actor_chain", []),
        "state_machine": [step.get("state") for step in case.get("process_trace", []) if step.get("state")],
        "bottom_up_signals": case.get("bottom_up_signals", []),
        "failure_modes": case.get("failure_modes", []),
        "intervention_points": case.get("intervention_points", []),
        "metric_candidates": case.get("metric_candidates", []),
        "observed_outcomes": case.get("observed_outcomes", {}),
        "parsed_outcomes": outcomes,
        "parameter_estimates": parameter_estimates,
        "calibration_readiness": readiness,
    }


def estimate_case_parameters(case: dict[str, Any]) -> list[dict[str, Any]]:
    scenario_priors = dict(DEFAULT_PRIORS)
    scenario_priors.update(SCENARIO_PRIORS.get(case.get("scenario_class", ""), {}))
    failure_modes = " ".join(case.get("failure_modes", []))
    intervention_points = " ".join(case.get("intervention_points", []))
    affected_setting = " ".join(case.get("affected_setting", []))
    outcomes = parse_observed_outcomes(case.get("observed_outcomes", {}))
    estimates: list[dict[str, Any]] = []

    for name, (low, high, source) in scenario_priors.items():
        adj_low, adj_high = adjust_range(name, low, high, failure_modes, intervention_points, affected_setting, outcomes)
        estimates.append(
            parameter_estimate(
                name=name,
                value_min=adj_low,
                value_max=adj_high,
                source_label=source,
                confidence=confidence_for(case, name, source, outcomes),
                rationale=rationale_for(case, name),
                evidence_keys=evidence_keys_for(case, name),
            )
        )

    estimates.append(
        parameter_estimate(
            name="casualty_rate_anchor",
            value_min=outcomes["casualty_anchor_min"],
            value_max=outcomes["casualty_anchor_max"],
            source_label=SOURCE_FACT_DERIVED if outcomes["casualties"] is not None else SOURCE_SYNTHETIC,
            confidence=0.62 if outcomes["casualties"] is not None else 0.18,
            rationale="Reported deaths/dead-missing are normalized as an outcome anchor because exposed population is often unavailable.",
            evidence_keys=["observed_outcomes.deaths_or_dead_missing", "observed_outcomes.missing", "observed_outcomes.injured"],
        )
    )
    estimates.append(
        parameter_estimate(
            name="property_loss_rate_anchor",
            value_min=outcomes["loss_anchor_min"],
            value_max=outcomes["loss_anchor_max"],
            source_label=SOURCE_FACT_DERIVED if outcomes["loss_yuan"] is not None else SOURCE_SYNTHETIC,
            confidence=0.58 if outcomes["loss_yuan"] is not None else 0.16,
            rationale="Direct economic loss is normalized to a severity index until local exposure assets are calibrated.",
            evidence_keys=["observed_outcomes.direct_economic_loss"],
        )
    )
    return estimates


def parameter_estimate(
    name: str,
    value_min: float,
    value_max: float,
    source_label: str,
    confidence: float,
    rationale: str,
    evidence_keys: list[str],
) -> dict[str, Any]:
    definition = PARAMETER_DEFINITIONS.get(name, {})
    return {
        "name": name,
        "value_min": round(value_min, 4),
        "value_max": round(max(value_min, value_max), 4),
        "unit": definition.get("unit", ""),
        "source_label": source_label,
        "confidence": round(max(0.0, min(1.0, confidence)), 3),
        "rationale": rationale,
        "evidence_keys": evidence_keys,
        "review_status": "needs_human_review" if confidence < 0.70 else "usable_with_source_check",
    }


def adjust_range(
    name: str,
    low: float,
    high: float,
    failure_modes: str,
    intervention_points: str,
    affected_setting: str,
    outcomes: dict[str, Any],
) -> tuple[float, float]:
    casualty_factor = min(1.35, 1.0 + (outcomes.get("casualties") or 0) / 600)
    if name == "communication_failure_rate" and any(term in failure_modes for term in ["预警", "通信", "叫应", "报告"]):
        high *= 1.22
    if name == "grassroots_call_strength" and any(term in intervention_points for term in ["基层", "网格", "确认", "闭环"]):
        low += 0.12
        high += 0.08
    if name == "vulnerable_priority_weight" and any(term in affected_setting for term in ["养老", "医院", "学校", "人员密集"]):
        low += 0.25
        high += 0.35
    if name == "route_failure_probability" and any(term in affected_setting for term in ["桥梁", "高速", "隧道", "山丘", "河道"]):
        low *= 1.25
        high *= 1.30
    if name in {"warning_lead_minutes", "response_activation_delay_minutes", "evacuation_order_delay_minutes"}:
        high *= casualty_factor
    if name == "public_trust_delta_prior" and outcomes.get("casualties"):
        low -= min(0.10, outcomes["casualties"] / 2500)
    return low, high


def confidence_for(case: dict[str, Any], name: str, source: str, outcomes: dict[str, Any]) -> float:
    confidence = {
        SOURCE_FACT_DERIVED: 0.54,
        SOURCE_QGIS_DERIVED: 0.42,
        SOURCE_EXPERT_PRIOR: 0.34,
        SOURCE_SYNTHETIC: 0.18,
    }[source]
    if case.get("source_report_role") == "灾害事故调查":
        confidence += 0.06
    if case.get("process_trace"):
        confidence += 0.04
    if name in {"casualty_rate_anchor", "property_loss_rate_anchor"} and outcomes.get("casualties"):
        confidence += 0.08
    if case.get("observed_outcomes", {}).get("transfer_or_evacuation_data", "").startswith("未稳定抽取"):
        confidence -= 0.08
    return confidence


def rationale_for(case: dict[str, Any], name: str) -> str:
    scenario = case.get("scenario_class", "unknown scenario")
    if name in {"bridge_closure_threshold", "route_failure_probability"}:
        return f"{scenario} case requires route/risk overlay; range is refined by QGIS bridge, road and hazard-zone exposure."
    if name == "vulnerable_priority_weight":
        return "Priority reflects institutional, older-age, mobility and care-dependency exposure found in the case tags."
    if name == "grassroots_call_strength":
        return "Range reflects whether the report contains grassroots confirmation, grid call-response or bottom-up reporting signals."
    return f"Range is inferred from {scenario} reports and adjusted by observed failure modes and outcomes."


def evidence_keys_for(case: dict[str, Any], name: str) -> list[str]:
    keys = ["scenario_class", "failure_modes", "intervention_points"]
    if name in {"bridge_closure_threshold", "route_failure_probability"}:
        keys.extend(["affected_setting", "QGIS.roads", "QGIS.bridges", "QGIS.risk_zones"])
    if name in {"casualty_rate_anchor", "property_loss_rate_anchor"}:
        keys.append("observed_outcomes")
    if case.get("bottom_up_signals"):
        keys.append("bottom_up_signals")
    return keys


def parse_observed_outcomes(outcomes: dict[str, Any]) -> dict[str, Any]:
    deaths = parse_people(outcomes.get("deaths_or_dead_missing"))
    missing = parse_people(outcomes.get("missing"))
    injured = parse_people(outcomes.get("injured"))
    loss_yuan = parse_money_yuan(outcomes.get("direct_economic_loss"))
    casualties = sum(value for value in [deaths, missing, injured] if value is not None)
    if casualties == 0:
        casualties = None
    casualty_anchor = min(180.0, max(0.2, (casualties or 1) * 0.9))
    loss_anchor = 0.05 if loss_yuan is None else min(1.0, max(0.05, loss_yuan / 12_000_000_000))
    return {
        "deaths_or_dead_missing": deaths,
        "missing": missing,
        "injured": injured,
        "casualties": casualties,
        "loss_yuan": loss_yuan,
        "casualty_anchor_min": casualty_anchor * 0.75,
        "casualty_anchor_max": casualty_anchor * 1.25,
        "loss_anchor_min": loss_anchor * 0.75,
        "loss_anchor_max": min(1.0, loss_anchor * 1.25),
    }


def parse_people(value: Any) -> int | None:
    if value in {None, ""}:
        return None
    match = re.search(r"([\d.]+)\s*人", str(value))
    if not match:
        return None
    return int(float(match.group(1)))


def parse_money_yuan(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    text = str(value).replace(",", "")
    match = re.search(r"([\d.]+)\s*(亿元|万元|元)", text)
    if not match:
        return None
    amount = float(match.group(1))
    unit = match.group(2)
    if unit == "亿元":
        return amount * 100_000_000
    if unit == "万元":
        return amount * 10_000
    return amount


def calibration_readiness(
    case: dict[str, Any], parameter_estimates: list[dict[str, Any]], outcomes: dict[str, Any]
) -> dict[str, Any]:
    confidence_values = [item["confidence"] for item in parameter_estimates]
    reviewed = sum(1 for item in parameter_estimates if item["review_status"] == "usable_with_source_check")
    missing = []
    if outcomes["casualties"] is None:
        missing.append("casualty_numeric_value")
    if outcomes["loss_yuan"] is None:
        missing.append("direct_economic_loss_numeric_value")
    if case.get("observed_outcomes", {}).get("transfer_or_evacuation_data", "").startswith("未稳定抽取"):
        missing.append("transfer_or_evacuation_count")
    return {
        "mean_confidence": round(mean(confidence_values), 3) if confidence_values else 0,
        "usable_parameter_count": reviewed,
        "parameter_count": len(parameter_estimates),
        "missing_review_items": missing,
        "next_review_action": "Return to source PDF for transfer counts and timing evidence." if missing else "Expert range review and QGIS overlay calibration.",
    }


def aggregate_parameter_records(cases: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    grouped["ALL_CASES"] = list(cases)
    for case in cases:
        grouped[case["scenario_class"]].append(case)

    aggregates = {}
    for group, records in grouped.items():
        estimates_by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for record in records:
            for estimate in record["parameter_estimates"]:
                estimates_by_name[estimate["name"]].append(estimate)
        aggregates[group] = {
            "case_count": len(records),
            "parameters": [
                aggregate_estimates(name, estimates)
                for name, estimates in sorted(estimates_by_name.items())
            ],
        }
    return aggregates


def aggregate_estimates(name: str, estimates: list[dict[str, Any]]) -> dict[str, Any]:
    weights = [max(0.05, estimate["confidence"]) for estimate in estimates]
    low = weighted_mean([estimate["value_min"] for estimate in estimates], weights)
    high = weighted_mean([estimate["value_max"] for estimate in estimates], weights)
    sources = Counter(estimate["source_label"] for estimate in estimates)
    return {
        "name": name,
        "value_min": round(low, 4),
        "value_max": round(max(low, high), 4),
        "unit": PARAMETER_DEFINITIONS.get(name, {}).get("unit", ""),
        "mean_confidence": round(mean(estimate["confidence"] for estimate in estimates), 3),
        "support_case_count": len(estimates),
        "dominant_source_label": sources.most_common(1)[0][0],
    }


def weighted_mean(values: list[float], weights: list[float]) -> float:
    total_weight = sum(weights)
    return sum(value * weight for value, weight in zip(values, weights)) / total_weight


def build_parameter_index(cases: list[dict[str, Any]]) -> dict[str, list[str]]:
    index: dict[str, list[str]] = defaultdict(list)
    for record in cases:
        for estimate in record["parameter_estimates"]:
            index[estimate["name"]].append(record["case_id"])
    return dict(sorted(index.items()))


def summarize_parameter_library(library: dict[str, Any]) -> dict[str, Any]:
    cases = library.get("cases", [])
    estimates = [estimate for case in cases for estimate in case.get("parameter_estimates", [])]
    by_source = Counter(estimate["source_label"] for estimate in estimates)
    by_review = Counter(estimate["review_status"] for estimate in estimates)
    return {
        "case_count": len(cases),
        "parameter_estimate_count": len(estimates),
        "source_label_counts": dict(sorted(by_source.items())),
        "review_status_counts": dict(sorted(by_review.items())),
        "mean_confidence": round(mean(estimate["confidence"] for estimate in estimates), 3) if estimates else 0,
        "missing_review_item_counts": dict(
            Counter(item for case in cases for item in case.get("calibration_readiness", {}).get("missing_review_items", []))
        ),
    }


def scenario_config_from_parameters(
    library: dict[str, Any],
    case_id: str | None = None,
    scenario_class: str | None = None,
) -> dict[str, Any]:
    parameters = select_parameter_set(library, case_id=case_id, scenario_class=scenario_class)
    midpoint = {item["name"]: (item["value_min"] + item["value_max"]) / 2 for item in parameters}
    danger_arrival = 180
    warning_lead = int(midpoint.get("warning_lead_minutes", 90))
    order_delay = int(midpoint.get("evacuation_order_delay_minutes", 35))
    return {
        "warning_minute": max(0, danger_arrival - warning_lead),
        "evacuation_order_minute": min(danger_arrival - 10, max(0, danger_arrival - warning_lead + order_delay)),
        "communication_failure_rate": round(min(0.95, max(0.0, midpoint.get("communication_failure_rate", 0.30))), 3),
        "bridge_closure_threshold": round(midpoint.get("bridge_closure_threshold", 0.65), 3),
        "route_failure_probability": round(midpoint.get("route_failure_probability", 0.20), 3),
        "vulnerable_priority_weight": round(midpoint.get("vulnerable_priority_weight", 1.8), 3),
        "grassroots_call_strength": round(midpoint.get("grassroots_call_strength", 0.55), 3),
        "parameter_source": "mem_case_parameter_library",
    }


def select_parameter_set(
    library: dict[str, Any],
    case_id: str | None = None,
    scenario_class: str | None = None,
) -> list[dict[str, Any]]:
    if case_id:
        for case in library.get("cases", []):
            if case.get("case_id") == case_id:
                return case.get("parameter_estimates", [])
    group = scenario_class or "ALL_CASES"
    aggregate = library.get("aggregates", {}).get(group) or library.get("aggregates", {}).get("ALL_CASES", {})
    return aggregate.get("parameters", [])
