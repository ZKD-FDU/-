"""Auditable evacuation kernel with timed arrivals and conserved resources."""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import blake2b
import json
import math
from pathlib import Path
from statistics import median
from typing import Any
from .adapters import DecisionContext, RuleBasedAgentAdapter
from .models import (DecisionTrace, EvacuationStatus as Status, MetricRecord,
                     MVP_POLICY_CONFIGS, PersonAgent, PolicyConfig, PolicyId, SimulationRun,
                     MessageReceipt, stable_config_hash)
from .scenario import SyntheticScenario, generate_qingyuan

RULE_VERSION = "hongce-positioned-kernel-v4"

def draw(seed: int, *keys: Any) -> float:
    """Common random numbers keyed by person/event, never policy or loop order."""
    raw = json.dumps([seed, *keys], ensure_ascii=False, separators=(",", ":")).encode()
    return int.from_bytes(blake2b(raw, digest_size=8).digest(), "big") / 2**64

@dataclass
class MutablePerson:
    base: PersonAgent
    status: Status = Status.UNCONTACTED
    contact_minute: int | None = None
    confirmed_minute: int | None = None
    acknowledged_minute: int | None = None
    waiting_minute: int | None = None
    transit_minute: int | None = None
    sheltered_minute: int | None = None
    scheduled_arrival_minute: int | None = None
    harm_risk: float = 0.0
    assigned_resource_wait: int = 0
    reason: str = ""
    responsible_actor_id: str = "county_emergency_office"
    information_ids: list[str] = field(default_factory=list)
    neighbor_action_rate: float = 0.0
    route_id: str | None = None
    shelter_id: str | None = None
    dispatch_minute: int | None = None
    boarding_minute: int | None = None

@dataclass
class RunResult:
    run: SimulationRun
    metrics: MetricRecord
    people: list[MutablePerson]
    events: list[dict[str, Any]]
    receipts: list[MessageReceipt]
    traces: list[DecisionTrace]
    scenario_hash: str = ""
    policy_config: dict[str, Any] = field(default_factory=dict)
    resource_audit: dict[str, Any] = field(default_factory=dict)
    transport: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"run": self.run.model_dump(mode="json"), "metrics": self.metrics.model_dump(mode="json"),
                "agents": [serialize_person(p) for p in self.people], "events": self.events,
                "receipts": [r.model_dump(mode="json") for r in self.receipts],
                "traces": [t.model_dump(mode="json") for t in self.traces],
                "scenario_hash": self.scenario_hash, "policy_config": self.policy_config,
                "resource_audit": self.resource_audit,
                "transport": self.transport,
                "metric_notes": {"vulnerable_harm_risk": "累计暴露风险指数，非伤亡概率",
                                 "group_safety_gap": "两组均以各自应转人口为分母；缺组时不定义",
                                 "trust_delta": "未校准，暂不计算"}}

def requires_transfer(person: MutablePerson | PersonAgent) -> bool:
    base = person.base if isinstance(person, MutablePerson) else person
    if base.location_id == "county_school":
        return False
    if base.location_id in {"nursing_home", "south_valley"}:
        return True
    if base.location_id == "qingyuan_town":
        return base.is_vulnerable and base.mobility != "independent"
    return base.is_vulnerable

@dataclass
class Trip:
    vehicle: int
    people: list[MutablePerson]
    arrival: int
    release: int
    care: int
    stretchers: int
    arrived: bool = False
    route_id: str | None = None
    return_route_id: str | None = None
    release_message: str = 'vehicle returned'
    destination: str | None = None

@dataclass
class ResourceState:
    vehicles: int
    vehicle_capacity: int
    care_workers: int
    stretchers: int
    shelter_beds_remaining: int
    total_policy_cost: float
    trips: list[Trip] = field(default_factory=list)
    peak_vehicles: int = 0
    peak_care: int = 0
    peak_stretchers: int = 0

    @classmethod
    def from_policy(cls, scenario: SyntheticScenario, policy: PolicyConfig) -> ResourceState:
        r = scenario.resources
        return cls(int(r.vehicles * policy.vehicle_multiplier), r.vehicle_capacity,
                   int(r.care_workers * policy.care_multiplier), int(r.stretchers * policy.care_multiplier),
                   r.shelter_beds, policy.budget_units)

    def advance(self, minute: int, events: list[dict[str, Any]]) -> None:
        for trip in self.trips:
            if not trip.arrived:
                for person in trip.people:
                    if person.transit_minute is not None and minute >= person.transit_minute:
                        person.status,person.reason=Status.IN_TRANSIT,'车辆转运中'
                    elif person.boarding_minute is not None and minute>=person.boarding_minute:
                        person.reason='车辆到达接人地点，正在装载'
            if not trip.arrived and minute >= trip.arrival:
                trip.arrived = True
                for person in trip.people:
                    person.status = Status.SHELTERED
                    person.sheltered_minute = trip.arrival
                    person.reason = "已到达安全安置点"
                    events.append(event(trip.arrival, "arrival", "person sheltered",
                                        {"person": person.base.id, "vehicle": trip.vehicle, "route_id": person.route_id}))
            if minute == trip.release:
                events.append(event(minute, "resource", trip.release_message, {"vehicle": trip.vehicle,'location_id':trip.destination}))
        self.trips = [trip for trip in self.trips if trip.release > minute]

def event(minute: int, kind: str, message: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {"label": "SIMULATED", "minute": minute, "kind": kind, "message": message, "payload": payload}

def scenario_fingerprint(scenario: SyntheticScenario) -> str:
    return stable_config_hash(asdict(scenario))

def run_policy(policy_id: PolicyId | str, seed: int = 20260806, population: int = 2000,
               output_dir: str | Path | None = None, scenario: SyntheticScenario | None = None,
               policy_config: PolicyConfig | None = None) -> RunResult:
    policy = (policy_config or MVP_POLICY_CONFIGS[PolicyId(policy_id)]).model_copy(deep=True)
    scenario = scenario or generate_qingyuan(seed=seed, population=population)
    h = scenario.hazard
    if h.timestep_minutes <= 0 or h.end_minute < h.start_minute:
        raise ValueError("Invalid simulation time range")
    if min(asdict(scenario.resources).values()) < 0:
        raise ValueError("Resource counts must be nonnegative")
    people = [MutablePerson(base=p.model_copy(deep=True)) for p in scenario.people]
    targets = [p for p in people if requires_transfer(p)]
    by_id = {p.base.id: p for p in people}
    registered = {p.base.id for p in people if draw(seed, p.base.id, "registry") < policy.registry_coverage}
    for p in people:
        if p.base.id not in registered:
            p.status, p.reason = Status.UNREGISTERED, "未进入初始风险名册"
    scenario_hash = scenario_fingerprint(scenario)
    run_id = f"{policy.id.value.lower()}-{seed}-{stable_config_hash({'scenario': scenario_hash, 'policy': policy.config_hash, 'version': RULE_VERSION})}"
    run = SimulationRun(id=run_id, policy_id=policy.id, seed=seed, code_version=RULE_VERSION,
                        config_hash=policy.config_hash, started_at=datetime.now(timezone.utc),
                        model_versions={"agent_adapter": "RuleBasedAgentAdapter"}, status="running")
    resources = ResourceState.from_policy(scenario, policy)
    from .transport import TransportNetwork
    from .fleet import PositionedFleet
    network_class=PositionedFleet if scenario.transport.get('dispatch_model')=='positioned_fleet' else TransportNetwork
    network = network_class(scenario) if scenario.transport else None
    events: list[dict[str, Any]] = []
    receipts: list[MessageReceipt] = []
    traces: list[DecisionTrace] = []
    closure = h.bridge_closure_minute + policy.bridge_extension_minutes
    adapter = RuleBasedAgentAdapter()
    from .governance import GovernanceProcess
    governance = GovernanceProcess(scenario, policy, seed, by_id, registered, events, receipts, traces)
    for minute in range(h.start_minute, h.end_minute + 1):
        resources.advance(minute, events)
        governance.advance(minute)
        if minute == closure:
            events.append(event(minute, "facility", "bridge_east closed", {"route": "route_nursing_to_school"}))
        if minute == h.communication_failure_minute:
            events.append(event(minute, "facility", "communications degraded", {"failure_rate": h.communication_failure_rate}))
        if minute == h.warning_minute:
            events.append(event(minute, "warning", "official warning issued", {"policy": policy.id.value}))
        if minute == h.evacuation_order_minute:
            events.append(event(minute, "organization", "evacuation order issued", {"actor": "county_emergency_office"}))
        if minute >= h.warning_minute and (minute - h.start_minute) % h.timestep_minutes == 0:
            for p in people:
                if p.base.id in registered and p.contact_minute is None:
                    failure = minute >= h.communication_failure_minute and draw(seed, p.base.id, "comms") < h.communication_failure_rate
                    reach = 0.45 + 0.35 * p.base.digital_access + (0.15 if "multi_channel" in policy.warning_channels else 0)
                    if failure and "backup_radio" not in policy.warning_channels:
                        reach *= 0.15
                    if draw(seed, p.base.id, "reach", minute) < reach:
                        contact_person(p, minute, "department_push", "county_emergency_office", receipts, events)
                    else:
                        p.status, p.reason = Status.CONTACT_FAILED, "等待有效信息触达"
            for p in targets:
                if p.contact_minute is not None and p.confirmed_minute is None:
                    decide_person(p, minute, h.danger_arrival_minute, policy, seed, adapter, traces)
                if p.confirmed_minute is not None and p.waiting_minute is None:
                    if governance.ready_for_dispatch(p, minute):
                        p.waiting_minute, p.status = minute, Status.WAITING_TRANSFER
                        events.append(event(minute, "task", "evacuation task created", {"person": p.base.id}))
                    else:
                        p.status, p.reason = Status.AUTHORIZATION_WAIT, "等待组织授权或照护转移准备完成"
            if network:
                network.dispatch(targets, policy, minute, resources, closure, events, scenario)
            else:
                dispatch_waiting_people(targets, policy, minute, resources, closure, events, scenario)
        # Exposure on [minute, minute+1); arrivals at this minute are already safe.
        if minute >= h.danger_arrival_minute and minute < h.end_minute:
            update_exposure(targets, 1)
    for p in targets:
        if p.waiting_minute is not None:
            p.assigned_resource_wait = (p.transit_minute if p.transit_minute is not None else h.end_minute) - p.waiting_minute
    run.status = "succeeded"
    events.sort(key=lambda e:e['minute'])
    events[:] = [e for e in events if e['minute'] <= h.end_minute]
    metrics = compute_metrics(run_id, policy, seed, people, h.danger_arrival_minute, resources, h.warning_minute)
    result = RunResult(run, metrics, people, events, receipts, traces, scenario_hash,
                       policy.model_dump(mode="json"),
                       {"vehicles": resources.vehicles, "care_workers": resources.care_workers,
                        "stretchers": resources.stretchers, "peak_vehicles": resources.peak_vehicles,
                        "peak_care_workers": resources.peak_care, "peak_stretchers": resources.peak_stretchers,
                        "shelter_beds_remaining": resources.shelter_beds_remaining},
                       network.report() if network else {})
    if output_dir is not None:
        write_run_result(result, output_dir)
    return result

def contact_person(p: MutablePerson, minute: int, channel: str, source: str,
                   receipts: list[MessageReceipt], events: list[dict[str, Any]], acknowledged: bool = False) -> None:
    if p.contact_minute is None:
        p.contact_minute, p.status = minute, Status.CONTACTED
    if acknowledged and p.acknowledged_minute is None:
        p.acknowledged_minute, p.responsible_actor_id = minute, source
    rid = f"receipt-{source}-{p.base.id}-{minute}-{len(receipts)}"
    p.information_ids.append(rid)
    receipts.append(MessageReceipt(id=rid, warning_event_id="official-warning", recipient_id=p.base.id,
                                   received_minute=minute, understood=acknowledged, trusted=acknowledged,
                                   acknowledged=acknowledged, path=[source, channel, p.base.id]))
    events.append(event(minute, "message", "warning received", {"person": p.base.id, "source": source,
                                                                "channel": channel, "acknowledged": acknowledged}))

def decide_person(p: MutablePerson, minute: int, danger: int, policy: PolicyConfig, seed: int,
                  adapter: RuleBasedAgentAdapter, traces: list[DecisionTrace]) -> None:
    b = p.base
    context = DecisionContext(actor_id=b.id, minute=minute, danger_arrival_minute=danger,
        risk_perception=min(1.0, b.risk_perception + max(0, minute - (danger - 120)) / 240),
        official_trust=b.official_trust, cadre_trust=b.cadre_trust, neighbor_trust=b.neighbor_trust,
        neighbor_action_rate=p.neighbor_action_rate, digital_access=b.digital_access,
        transfer_cost=b.transfer_cost, refusal_tendency=b.refusal_tendency, false_alarm_memory=b.false_alarm_memory,
        mobility=b.mobility, care_dependency=b.care_dependency, has_private_transport=b.has_private_transport)
    decision = adapter.decide(context, policy)
    understood = p.acknowledged_minute is not None or draw(seed, b.id, "understand", minute) < 0.55 + 0.4 * b.digital_access
    sample = draw(seed, b.id, "decision", minute)
    accepted = understood and sample < decision.evacuate_probability
    reason = ("接受转移安排" if accepted else "仍在权衡风险、照护与转移成本") if understood else "需要人工解释预警"
    traces.append(DecisionTrace(id=f"trace-{b.id}-{minute}", actor_id=b.id, minute=minute,
        observed_information_ids=p.information_ids[-5:], factors=decision.factors,
        action="evacuate" if accepted else "wait_or_refuse", reason=reason,
        rule_version=RULE_VERSION, model_version=adapter.name,
        sampled_probability=decision.evacuate_probability, random_draw=sample))
    p.reason = reason
    if accepted:
        p.confirmed_minute, p.status = minute, Status.CONFIRMED
    else:
        p.status = Status.REFUSED if understood else Status.MISUNDERSTOOD

def route_for(p: MutablePerson, scenario: SyntheticScenario, closure: int) -> tuple[str, int, int | None]:
    candidates = [r for r in getattr(scenario, "routes", []) if r.get("origin_id") == p.base.location_id]
    if candidates:
        route = min(candidates, key=lambda r: float(r.get("travel_minutes", 35)))
        return route["id"], max(1, math.ceil(float(route.get("travel_minutes", 35)))), closure if route.get("bridge_dependency") else None
    loc = p.base.location_id
    return f"route-{loc}", 20 if loc == "qingyuan_town" else 35, closure if loc == "nursing_home" else None

def dispatch_waiting_people(people: list[MutablePerson], policy: PolicyConfig, minute: int,
                            resources: ResourceState, closure: int, events: list[dict[str, Any]],
                            scenario: SyntheticScenario) -> None:
    waiting = [p for p in people if p.waiting_minute is not None and p.transit_minute is None]
    def priority(p: MutablePerson):
        ready = p.waiting_minute if p.waiting_minute is not None else minute
        if policy.dispatch_rule.value in {"equal_allocation", "first_come_first_served"}:
            return (0, 0, ready, p.base.id)
        deadline = route_for(p, scenario, closure)[2] or scenario.hazard.danger_arrival_minute
        return (not p.base.is_vulnerable, deadline if policy.dispatch_rule.value != "vulnerable_first" else 0, ready, p.base.id)
    waiting.sort(key=priority)
    busy = {trip.vehicle for trip in resources.trips}
    care_left = resources.care_workers - sum(t.care for t in resources.trips)
    stretchers_left = resources.stretchers - sum(t.stretchers for t in resources.trips)
    for p in waiting:
        p.status, p.reason = Status.RESOURCE_BLOCKED, "等待可用车辆、照护人员或担架"
    for vehicle in range(resources.vehicles):
        if vehicle in busy or resources.vehicle_capacity <= 0:
            continue
        passengers: list[MutablePerson] = []
        used_care = used_stretchers = 0
        trip_route = None
        for p in waiting:
            if p.transit_minute is not None:
                continue
            if resources.shelter_beds_remaining <= 0:
                p.status, p.reason = Status.UNSUITABLE_SHELTER, "安置床位不足"
                continue
            route = route_for(p, scenario, closure)
            if route[2] is not None and minute + route[1] > route[2]:
                p.status, p.reason = Status.ROUTE_BLOCKED, "无法在道路窗口关闭前完成通行"
                continue
            if trip_route is not None and route[0] != trip_route[0]:
                continue
            care = 2 if p.base.care_dependency == "full" else int(p.base.care_dependency == "partial")
            stretcher = int(p.base.mobility == "bedridden")
            if care > care_left or stretcher > stretchers_left:
                continue
            care_left -= care
            stretchers_left -= stretcher
            used_care += care
            used_stretchers += stretcher
            resources.shelter_beds_remaining -= 1
            trip_route = route
            p.route_id, p.transit_minute, p.scheduled_arrival_minute = route[0], minute, minute + route[1]
            p.status, p.reason = Status.IN_TRANSIT, "车辆转运中"
            passengers.append(p)
            events.append(event(minute, "dispatch", "vehicle departed", {"person": p.base.id, "vehicle": vehicle,
                               "route_id": route[0], "arrival_minute": p.scheduled_arrival_minute,
                               "care_workers": care, "stretchers": stretcher}))
            if len(passengers) >= resources.vehicle_capacity:
                break
        if passengers and trip_route:
            travel = trip_route[1]
            resources.trips.append(Trip(vehicle, passengers, minute + travel, minute + 2 * travel + 5,
                                        used_care, used_stretchers))
    resources.peak_vehicles = max(resources.peak_vehicles, len(resources.trips))
    resources.peak_care = max(resources.peak_care, sum(t.care for t in resources.trips))
    resources.peak_stretchers = max(resources.peak_stretchers, sum(t.stretchers for t in resources.trips))

def update_exposure(people: list[MutablePerson], elapsed_minutes: int) -> None:
    for p in people:
        if p.status == Status.SHELTERED or not requires_transfer(p):
            continue
        # Synthetic per-minute index; transit exposure ends at actual arrival.
        per_five = 0.035 + 0.025 * (p.base.mobility == "limited") + 0.060 * (p.base.mobility == "bedridden")
        per_five += 0.025 * (p.base.age >= 75) + 0.020 * (p.base.location_id in {"nursing_home", "south_valley"})
        p.harm_risk += per_five * elapsed_minutes / 5

def compute_metrics(run_id: str, policy: PolicyConfig, seed: int, people: list[MutablePerson],
                    danger_minute: int, resources: ResourceState, warning_minute: int = 45) -> MetricRecord:
    target = [p for p in people if requires_transfer(p)]
    vulnerable = [p for p in target if p.base.is_vulnerable]
    general = [p for p in target if not p.base.is_vulnerable]
    def safe(p):
        return p.sheltered_minute is not None and p.sheltered_minute <= danger_minute
    safe_people = [p for p in target if safe(p)]
    vs, gs = sum(safe(p) for p in vulnerable), sum(safe(p) for p in general)
    vr, gr = (vs / len(vulnerable) if vulnerable else None), (gs / len(general) if general else None)
    confirmed = sum(p.acknowledged_minute is not None for p in target)
    deadline = min(danger_minute, warning_minute + policy.confirmation_deadline_minutes)
    missed = sum(int(p.contact_minute is None or p.contact_minute > deadline)
                 + int(p.confirmed_minute is None or p.confirmed_minute > danger_minute)
                 + int(p.transit_minute is None or p.transit_minute > danger_minute) for p in target)
    waits = [p.assigned_resource_wait for p in target if p.waiting_minute is not None]
    return MetricRecord(policy_id=policy.id, run_id=run_id, seed=seed,
        safe_before_danger_rate=len(safe_people) / len(target) if target else 0,
        vulnerable_safe_before_danger_rate=vr, general_safe_before_danger_rate=gr,
        target_count=len(target), safe_count=len(safe_people), vulnerable_target_count=len(vulnerable),
        vulnerable_safe_count=vs, general_target_count=len(general), general_safe_count=gs,
        confirmed_count=confirmed, required_action_count=3 * len(target), missed_action_count=missed,
        vulnerable_harm_risk=sum(p.harm_risk for p in vulnerable) / max(1, len(vulnerable)),
        lead_time_minutes_median=float(median([danger_minute - p.sheltered_minute for p in safe_people])) if safe_people else 0,
        response_closure_rate=confirmed / max(1, len(target)), missed_critical_action_rate=missed / max(1, 3 * len(target)),
        group_safety_gap=gr - vr if gr is not None and vr is not None else 0,
        group_safety_gap_defined=gr is not None and vr is not None,
        policy_cost=resources.total_policy_cost, trust_delta=None,
        resource_queue_minutes_mean=sum(waits) / max(1, len(waits)))

def serialize_person(p: MutablePerson) -> dict[str, Any]:
    return {"id": p.base.id, "label": "SIMULATED", "age": p.base.age, "location_id": p.base.location_id,
            "is_vulnerable": p.base.is_vulnerable, "requires_transfer": requires_transfer(p),
            "mobility": p.base.mobility, "care_dependency": p.base.care_dependency, "status": p.status.value,
            "contact_minute": p.contact_minute, "confirmed_minute": p.confirmed_minute,
            "acknowledged_minute": p.acknowledged_minute, "waiting_minute": p.waiting_minute,
            "transit_minute": p.transit_minute, "sheltered_minute": p.sheltered_minute,
            "dispatch_minute": p.dispatch_minute, "boarding_minute": p.boarding_minute,
            "scheduled_arrival_minute": p.scheduled_arrival_minute, "route_id": p.route_id,
            "shelter_id": p.shelter_id,
            "harm_risk": p.harm_risk, "resource_wait_minutes": p.assigned_resource_wait,
            "reason": p.reason, "responsible_actor_id": p.responsible_actor_id}

def write_run_result(result: RunResult, output_dir: str | Path) -> Path:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{result.run.id}.json"
    if str(path) not in result.run.output_paths:
        result.run.output_paths.append(str(path))
    path.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path

def run_and_write(policy: str, seed: int, population: int, output_dir: str | Path) -> Path:
    return write_run_result(run_policy(policy, seed=seed, population=population), output_dir)
