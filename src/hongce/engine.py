"""Deterministic simulation engine for the S0/S3/S5 MVP."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import math
import random
from pathlib import Path
from statistics import median
from typing import Any

from .models import (
    DataLabel,
    DecisionTrace,
    EvacuationStatus,
    MessageReceipt,
    MetricRecord,
    MVP_POLICY_CONFIGS,
    PersonAgent,
    PolicyConfig,
    PolicyId,
    SimulationRun,
    WarningEvent,
    stable_config_hash,
)
from .scenario import SyntheticScenario, generate_qingyuan

RULE_VERSION = "hongce-rule-kernel-v1"


@dataclass
class MutablePerson:
    base: PersonAgent
    status: EvacuationStatus = EvacuationStatus.UNCONTACTED
    contact_minute: int | None = None
    confirmed_minute: int | None = None
    waiting_minute: int | None = None
    transit_minute: int | None = None
    sheltered_minute: int | None = None
    harm_risk: float = 0.0
    trust_delta: float = 0.0
    assigned_resource_wait: int = 0
    reason: str = ""


@dataclass
class RunResult:
    run: SimulationRun
    metrics: MetricRecord
    people: list[MutablePerson]
    events: list[dict[str, Any]]
    receipts: list[MessageReceipt]
    traces: list[DecisionTrace]

    def to_dict(self) -> dict[str, Any]:
        return {
            "run": self.run.model_dump(mode="json"),
            "metrics": self.metrics.model_dump(mode="json"),
            "agents": [serialize_person(p) for p in self.people],
            "events": self.events,
            "receipts": [r.model_dump(mode="json") for r in self.receipts],
            "traces": [t.model_dump(mode="json") for t in self.traces],
        }


def run_policy(
    policy_id: PolicyId | str,
    seed: int = 20260806,
    population: int = 2000,
    output_dir: str | Path | None = None,
    scenario: SyntheticScenario | None = None,
) -> RunResult:
    policy = MVP_POLICY_CONFIGS[PolicyId(policy_id)]
    scenario = scenario or generate_qingyuan(seed=seed, population=population)
    rng = random.Random(stable_config_hash({"seed": seed, "policy": policy.id.value}))
    people = [MutablePerson(base=p, status=p.status) for p in scenario.people]
    by_id = {p.base.id: p for p in people}
    vulnerable_ids = {p.base.id for p in people if p.base.is_vulnerable}
    registered_ids = build_registry(people, policy, rng)
    comms_failed_ids: set[str] = set()
    receipts: list[MessageReceipt] = []
    traces: list[DecisionTrace] = []
    events: list[dict[str, Any]] = []
    resource_state = ResourceState.from_policy(scenario, policy)
    route_state = RouteState.from_policy(scenario, policy)

    scenario_signature = stable_config_hash(
        {
            "policy": policy.id.value,
            "seed": seed,
            "population": len(scenario.people),
            "hazard": scenario.hazard.__dict__,
            "resources": scenario.resources.__dict__,
            "vulnerable_count": len(vulnerable_ids),
        }
    )
    run_id = f"{policy.id.value.lower()}-{seed}-{scenario_signature}"
    run = SimulationRun(
        id=run_id,
        policy_id=policy.id,
        seed=seed,
        code_version=RULE_VERSION,
        config_hash=policy.config_hash,
        started_at=datetime.now(timezone.utc),
        model_versions={"agent_adapter": "RuleBasedAgentAdapter"},
        prompt_versions={},
        status="running",
    )

    warning = WarningEvent(
        id=f"warn-{run_id}",
        source_actor_id="county_emergency_office",
        sent_minute=scenario.hazard.warning_minute,
        scope_ids=list(registered_ids),
        credibility=0.68 if policy.id == PolicyId.S0 else 0.82,
        content_type="official",
        risk_level="evacuate",
    )

    for minute in range(scenario.hazard.start_minute, scenario.hazard.end_minute + 1, scenario.hazard.timestep_minutes):
        if minute == scenario.hazard.communication_failure_minute:
            comms_failed_ids = choose_comms_failures(people, scenario.hazard.communication_failure_rate, policy, rng)
            events.append(event(minute, "facility", "communications degraded", {"affected": len(comms_failed_ids)}))
        if minute == route_state.bridge_closure_minute:
            route_state.bridge_closed = True
            events.append(event(minute, "facility", "bridge_east closed", {"route": "route_nursing_to_school"}))

        if minute == warning.sent_minute:
            events.append(event(minute, "warning", "official warning issued", {"policy": policy.id.value}))

        for person in people:
            if person.status == EvacuationStatus.SHELTERED:
                continue
            apply_contact_and_confirmation(
                person=person,
                policy=policy,
                warning=warning,
                minute=minute,
                registered_ids=registered_ids,
                comms_failed_ids=comms_failed_ids,
                receipts=receipts,
                events=events,
                rng=rng,
            )
            if person.status in {EvacuationStatus.CONTACTED, EvacuationStatus.CONFIRMED, EvacuationStatus.REFUSED, EvacuationStatus.DISTRUSTED}:
                decide_evacuation(person, policy, minute, scenario.hazard.danger_arrival_minute, traces, rng)

        create_waiting_tasks(people, policy, minute, events)
        dispatch_waiting_people(people, policy, minute, resource_state, route_state, events)
        update_exposure(people, minute, scenario.hazard.danger_arrival_minute)
        spread_neighbor_influence(people, by_id, policy, minute, rng)

    run.status = "succeeded"
    metric = compute_metrics(run_id, policy, seed, people, scenario.hazard.danger_arrival_minute, resource_state)
    result = RunResult(run=run, metrics=metric, people=people, events=events, receipts=receipts, traces=traces)
    if output_dir is not None:
        write_run_result(result, output_dir)
    return result


@dataclass
class ResourceState:
    vehicle_slots_per_step: int
    care_slots_per_step: int
    stretcher_slots_per_step: int
    shelter_beds_remaining: int
    total_policy_cost: float
    queue_wait_minutes: list[int] = field(default_factory=list)

    @classmethod
    def from_policy(cls, scenario: SyntheticScenario, policy: PolicyConfig) -> "ResourceState":
        vehicle_multiplier = 1.0
        care_multiplier = 1.0
        if policy.id == PolicyId.S3:
            vehicle_multiplier = 1.18
            care_multiplier = 1.40
        elif policy.id == PolicyId.S4:
            vehicle_multiplier = 1.08
            care_multiplier = 1.10
        elif policy.id == PolicyId.S5:
            vehicle_multiplier = 1.25
            care_multiplier = 1.55
        return cls(
            vehicle_slots_per_step=max(1, int(scenario.resources.vehicles * scenario.resources.vehicle_capacity * vehicle_multiplier / 4)),
            care_slots_per_step=max(1, int(scenario.resources.care_workers * care_multiplier / 3)),
            stretcher_slots_per_step=max(1, int(scenario.resources.stretchers * care_multiplier / 3)),
            shelter_beds_remaining=scenario.resources.shelter_beds,
            total_policy_cost=policy.budget_units,
        )


@dataclass
class RouteState:
    bridge_closure_minute: int
    bridge_closed: bool = False

    @classmethod
    def from_policy(cls, scenario: SyntheticScenario, policy: PolicyConfig) -> "RouteState":
        closure = scenario.hazard.bridge_closure_minute
        if policy.id == PolicyId.S1:
            closure += 35
        elif policy.id == PolicyId.S5:
            closure += 45
        return cls(bridge_closure_minute=closure)


def requires_transfer(person: MutablePerson | PersonAgent) -> bool:
    base = person.base if isinstance(person, MutablePerson) else person
    if base.location_id == "county_school":
        return False
    if base.location_id in {"nursing_home", "south_valley"}:
        return True
    if base.location_id == "north_valley":
        return base.is_vulnerable
    if base.location_id == "qingyuan_town":
        return base.is_vulnerable and base.mobility != "independent"
    if base.location_id == "county_hospital":
        return base.is_vulnerable
    return base.is_vulnerable


def build_registry(people: list[MutablePerson], policy: PolicyConfig, rng: random.Random) -> set[str]:
    registered: set[str] = set()
    coverage = {
        PolicyId.S0: 0.82,
        PolicyId.S1: 0.82,
        PolicyId.S2: 0.84,
        PolicyId.S3: 0.96,
        PolicyId.S4: 0.94,
        PolicyId.S5: 0.985,
    }[policy.id]
    for person in people:
        base_prob = coverage
        if person.base.institution_id == "inst_nursing" and policy.id == PolicyId.S0:
            base_prob -= 0.20
        if person.base.location_id in {"north_valley", "south_valley"} and policy.id == PolicyId.S0:
            base_prob -= 0.10
        if person.base.is_vulnerable:
            base_prob += 0.05 if policy.registry_mode == "dynamic" else -0.04
        if rng.random() < max(0.0, min(1.0, base_prob)):
            registered.add(person.base.id)
        else:
            person.status = EvacuationStatus.UNREGISTERED
            person.reason = "not visible in the policy registry"
    return registered


def choose_comms_failures(
    people: list[MutablePerson], base_rate: float, policy: PolicyConfig, rng: random.Random
) -> set[str]:
    rate = base_rate
    if "backup_radio" in policy.warning_channels:
        rate *= 0.35
    elif "multi_channel" in policy.warning_channels:
        rate *= 0.65
    failed = set()
    for person in people:
        loc_multiplier = 1.5 if person.base.location_id in {"north_valley", "south_valley"} else 1.0
        if rng.random() < min(0.95, rate * loc_multiplier):
            failed.add(person.base.id)
    return failed


def apply_contact_and_confirmation(
    person: MutablePerson,
    policy: PolicyConfig,
    warning: WarningEvent,
    minute: int,
    registered_ids: set[str],
    comms_failed_ids: set[str],
    receipts: list[MessageReceipt],
    events: list[dict[str, Any]],
    rng: random.Random,
) -> None:
    if person.base.id not in registered_ids:
        return
    if minute < warning.sent_minute:
        return
    if person.status in {
        EvacuationStatus.CONFIRMED,
        EvacuationStatus.WAITING_TRANSFER,
        EvacuationStatus.IN_TRANSIT,
        EvacuationStatus.SHELTERED,
        EvacuationStatus.RESOURCE_BLOCKED,
        EvacuationStatus.ROUTE_BLOCKED,
    }:
        return

    channels = len(policy.warning_channels)
    reach = 0.55 + 0.08 * channels + 0.25 * person.base.digital_access
    if person.base.id in comms_failed_ids and "backup_radio" not in policy.warning_channels:
        reach -= 0.42
    if "cadre_call" in policy.warning_channels and person.base.is_vulnerable:
        reach += 0.25
    if rng.random() > max(0.05, min(0.98, reach)):
        if person.status in {EvacuationStatus.UNCONTACTED, EvacuationStatus.UNREGISTERED}:
            person.status = EvacuationStatus.CONTACT_FAILED
            person.reason = "warning did not reach the person"
        return

    understood = rng.random() < (0.64 + 0.28 * person.base.digital_access + (0.12 if "cadre_call" in policy.warning_channels else 0.0))
    trusted = rng.random() < (0.42 + 0.38 * person.base.official_trust + 0.18 * person.base.cadre_trust - 0.06 * person.base.false_alarm_memory)
    receipt = MessageReceipt(
        id=f"receipt-{warning.id}-{person.base.id}",
        warning_event_id=warning.id,
        recipient_id=person.base.id,
        received_minute=minute,
        understood=understood,
        trusted=trusted,
        acknowledged=policy.confirmation_required and understood and trusted,
        converted_to_task=False,
        path=["department_push"] + (["cadre_call"] if "cadre_call" in policy.warning_channels else []),
    )
    receipts.append(receipt)
    person.contact_minute = person.contact_minute or minute
    if not understood:
        person.status = EvacuationStatus.MISUNDERSTOOD
        person.reason = "message received but not understood"
    elif not trusted:
        person.status = EvacuationStatus.DISTRUSTED
        person.reason = "message received but not trusted"
    else:
        person.status = EvacuationStatus.CONFIRMED if policy.confirmation_required else EvacuationStatus.CONTACTED
        person.confirmed_minute = minute if policy.confirmation_required else None
        receipt.converted_to_task = True
        events.append(event(minute, "message", "warning converted to evacuation consideration", {"person": person.base.id}))


def decide_evacuation(
    person: MutablePerson,
    policy: PolicyConfig,
    minute: int,
    danger_minute: int,
    traces: list[DecisionTrace],
    rng: random.Random,
) -> None:
    time_pressure = max(0.0, min(1.0, (danger_minute - minute) / 120.0))
    direct_call = 1.0 if policy.confirmation_required and person.status == EvacuationStatus.CONFIRMED else 0.15
    assistance = 1.0 if person.base.care_support_available or policy.preposition_care_resources else 0.25
    route_obstacle = 0.0
    if minute >= 110 and person.base.location_id == "nursing_home":
        route_obstacle = 0.25
    elif minute >= 125 and person.base.location_id == "south_valley":
        route_obstacle = 0.18
    factors = {
        "risk_perception": 1.45 * (person.base.risk_perception + (1.0 - time_pressure) * 0.55),
        "official_trust": 0.95 * person.base.official_trust,
        "neighbor_action": 0.35 * person.base.neighbor_trust,
        "direct_call": 1.15 * direct_call,
        "available_assistance": 0.95 * assistance,
        "transfer_cost": -1.00 * person.base.transfer_cost,
        "false_alarm_fatigue": -0.20 * person.base.false_alarm_memory,
        "route_obstacle": -1.05 * route_obstacle,
        "refusal_tendency": -1.15 * person.base.refusal_tendency,
    }
    logit = -1.25 + sum(factors.values())
    probability = 1 / (1 + math.exp(-logit))
    draw = rng.random()
    traces.append(
        DecisionTrace(
            id=f"trace-{person.base.id}-{minute}",
            actor_id=person.base.id,
            minute=minute,
            factors=factors,
            action="evacuate" if draw < probability else "wait_or_refuse",
            rule_version=RULE_VERSION,
            model_version="RuleBasedAgentAdapter",
            sampled_probability=probability,
            random_draw=draw,
        )
    )
    if draw < probability:
        if person.status in {EvacuationStatus.CONTACTED, EvacuationStatus.DISTRUSTED, EvacuationStatus.REFUSED}:
            person.status = EvacuationStatus.CONFIRMED
            person.confirmed_minute = minute
        person.reason = top_factor(factors)
    elif person.status != EvacuationStatus.REFUSED:
        person.status = EvacuationStatus.REFUSED
        person.reason = "negative factors dominated: " + top_negative_factor(factors)


def create_waiting_tasks(people: list[MutablePerson], policy: PolicyConfig, minute: int, events: list[dict[str, Any]]) -> None:
    for person in people:
        if person.status != EvacuationStatus.CONFIRMED:
            continue
        if not requires_transfer(person):
            continue
        if policy.confirmation_required or minute >= 90:
            person.status = EvacuationStatus.WAITING_TRANSFER
            person.waiting_minute = minute
            events.append(event(minute, "task", "evacuation task created", {"person": person.base.id, "vulnerable": person.base.is_vulnerable}))


def dispatch_waiting_people(
    people: list[MutablePerson],
    policy: PolicyConfig,
    minute: int,
    resources: ResourceState,
    routes: RouteState,
    events: list[dict[str, Any]],
) -> None:
    waiting = [p for p in people if p.status in {EvacuationStatus.WAITING_TRANSFER, EvacuationStatus.RESOURCE_BLOCKED, EvacuationStatus.ROUTE_BLOCKED}]
    if not waiting:
        return
    if policy.dispatch_rule.value == "equal_allocation":
        waiting.sort(key=lambda p: (p.waiting_minute or minute, p.base.id))
    elif policy.dispatch_rule.value == "vulnerable_first":
        waiting.sort(key=lambda p: (not p.base.is_vulnerable, p.waiting_minute or minute, p.base.id))
    else:
        waiting.sort(key=lambda p: (not p.base.is_vulnerable, route_urgency(p, routes), p.waiting_minute or minute, p.base.id))

    vehicle_slots = resources.vehicle_slots_per_step
    care_slots = resources.care_slots_per_step
    stretcher_slots = resources.stretcher_slots_per_step
    for person in waiting:
        if resources.shelter_beds_remaining <= 0:
            person.status = EvacuationStatus.UNSUITABLE_SHELTER
            continue
        if routes.bridge_closed and person.base.location_id == "nursing_home":
            person.status = EvacuationStatus.ROUTE_BLOCKED
            person.reason = "bridge_east closed before transfer"
            continue
        needed_vehicle = 1
        needed_care = 1 if person.base.care_dependency in {"partial", "full"} else 0
        needed_stretcher = 1 if person.base.mobility == "bedridden" else 0
        if vehicle_slots < needed_vehicle or care_slots < needed_care or stretcher_slots < needed_stretcher:
            person.status = EvacuationStatus.RESOURCE_BLOCKED
            person.assigned_resource_wait += 5
            resources.queue_wait_minutes.append(person.assigned_resource_wait)
            person.reason = "waiting for vehicle/care/stretcher capacity"
            continue
        vehicle_slots -= needed_vehicle
        care_slots -= needed_care
        stretcher_slots -= needed_stretcher
        resources.shelter_beds_remaining -= 1
        person.status = EvacuationStatus.IN_TRANSIT
        person.transit_minute = minute
        travel = 20 if person.base.location_id == "qingyuan_town" else 35
        if policy.id == PolicyId.S5 and person.base.location_id in {"nursing_home", "south_valley"}:
            travel -= 10
        if minute + travel <= 240:
            person.status = EvacuationStatus.SHELTERED
            person.sheltered_minute = minute + travel
            events.append(event(minute, "dispatch", "person sheltered", {"person": person.base.id, "travel_minutes": travel}))


def update_exposure(people: list[MutablePerson], minute: int, danger_minute: int) -> None:
    if minute < danger_minute:
        return
    for person in people:
        if person.status == EvacuationStatus.SHELTERED and (person.sheltered_minute or 99999) <= danger_minute:
            continue
        vulnerability = 0.035
        if person.base.mobility == "limited":
            vulnerability += 0.025
        if person.base.mobility == "bedridden":
            vulnerability += 0.060
        if person.base.age >= 75:
            vulnerability += 0.025
        if person.base.location_id in {"nursing_home", "south_valley"}:
            vulnerability += 0.020
        person.harm_risk += vulnerability


def spread_neighbor_influence(
    people: list[MutablePerson],
    by_id: dict[str, MutablePerson],
    policy: PolicyConfig,
    minute: int,
    rng: random.Random,
) -> None:
    if "neighbor_network" not in policy.warning_channels or minute % 15 != 0:
        return
    sheltered_by_location: dict[str, int] = {}
    total_by_location: dict[str, int] = {}
    for p in people:
        total_by_location[p.base.location_id] = total_by_location.get(p.base.location_id, 0) + 1
        if p.status == EvacuationStatus.SHELTERED:
            sheltered_by_location[p.base.location_id] = sheltered_by_location.get(p.base.location_id, 0) + 1
    for p in people:
        if p.status in {EvacuationStatus.CONTACTED, EvacuationStatus.DISTRUSTED, EvacuationStatus.REFUSED}:
            share = sheltered_by_location.get(p.base.location_id, 0) / max(1, total_by_location[p.base.location_id])
            p.base.risk_perception = min(1.0, p.base.risk_perception + share * p.base.neighbor_trust * 0.12 + rng.random() * 0.02)


def compute_metrics(
    run_id: str,
    policy: PolicyConfig,
    seed: int,
    people: list[MutablePerson],
    danger_minute: int,
    resources: ResourceState,
) -> MetricRecord:
    vulnerable = [p for p in people if p.base.is_vulnerable]
    general = [p for p in people if not p.base.is_vulnerable]
    should_transfer = [p for p in people if requires_transfer(p)]
    safe = [p for p in should_transfer if p.status == EvacuationStatus.SHELTERED and (p.sheltered_minute or 99999) <= danger_minute]
    vulnerable_safe = [p for p in vulnerable if p.status == EvacuationStatus.SHELTERED and (p.sheltered_minute or 99999) <= danger_minute]
    general_safe = [p for p in general if p.status == EvacuationStatus.SHELTERED and (p.sheltered_minute or 99999) <= danger_minute]
    confirmed = [p for p in should_transfer if p.confirmed_minute is not None]
    contacted = [p for p in should_transfer if p.contact_minute is not None]
    missed = [p for p in should_transfer if p.status in {EvacuationStatus.CONTACT_FAILED, EvacuationStatus.UNREGISTERED, EvacuationStatus.RESOURCE_BLOCKED, EvacuationStatus.ROUTE_BLOCKED}]
    lead_times = [danger_minute - (p.sheltered_minute or danger_minute) for p in safe]
    vulnerable_rate = len(vulnerable_safe) / max(1, len(vulnerable))
    general_rate = len(general_safe) / max(1, len(general))
    return MetricRecord(
        policy_id=policy.id,
        run_id=run_id,
        seed=seed,
        safe_before_danger_rate=len(safe) / max(1, len(should_transfer)),
        vulnerable_harm_risk=sum(p.harm_risk for p in vulnerable) / max(1, len(vulnerable)),
        lead_time_minutes_median=float(median(lead_times)) if lead_times else 0.0,
        response_closure_rate=len(confirmed) / max(1, len(should_transfer)),
        missed_critical_action_rate=len(missed) / max(1, len(should_transfer)),
        group_safety_gap=general_rate - vulnerable_rate,
        incremental_cost_per_safe_transfer=None,
        worst_case_regret=None,
        trust_delta=sum(p.trust_delta for p in people) / max(1, len(people)),
        resource_queue_minutes_mean=sum(resources.queue_wait_minutes) / max(1, len(resources.queue_wait_minutes)),
    )


def write_run_result(result: RunResult, output_dir: str | Path) -> Path:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{result.run.id}.json"
    path.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    result.run.output_paths.append(str(path))
    return path


def run_and_write(policy: str, seed: int, population: int, output_dir: str | Path) -> Path:
    result = run_policy(policy, seed=seed, population=population, output_dir=output_dir)
    return Path(output_dir) / f"{result.run.id}.json"


def serialize_person(person: MutablePerson) -> dict[str, Any]:
    return {
        "id": person.base.id,
        "label": DataLabel.SIMULATED.value,
        "age": person.base.age,
        "location_id": person.base.location_id,
        "is_vulnerable": person.base.is_vulnerable,
        "mobility": person.base.mobility,
        "care_dependency": person.base.care_dependency,
        "status": person.status.value,
        "contact_minute": person.contact_minute,
        "confirmed_minute": person.confirmed_minute,
        "waiting_minute": person.waiting_minute,
        "transit_minute": person.transit_minute,
        "sheltered_minute": person.sheltered_minute,
        "harm_risk": person.harm_risk,
        "resource_wait_minutes": person.assigned_resource_wait,
        "reason": person.reason,
    }


def event(minute: int, kind: str, message: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {"label": DataLabel.SIMULATED.value, "minute": minute, "kind": kind, "message": message, "payload": payload}


def route_urgency(person: MutablePerson, routes: RouteState) -> int:
    if person.base.location_id == "nursing_home":
        return routes.bridge_closure_minute
    if person.base.location_id == "south_valley":
        return routes.bridge_closure_minute + 15
    return 999


def top_factor(factors: dict[str, float]) -> str:
    positives = {k: v for k, v in factors.items() if v >= 0}
    if not positives:
        return "no strong positive factor"
    key = max(positives, key=positives.get)
    return f"positive factor: {key}"


def top_negative_factor(factors: dict[str, float]) -> str:
    negatives = {k: v for k, v in factors.items() if v < 0}
    if not negatives:
        return "no strong negative factor"
    key = min(negatives, key=negatives.get)
    return key
