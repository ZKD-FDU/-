"""Frozen Phase 0 domain contracts for HongCe.

These models intentionally define the minimum stable vocabulary before the
simulation engine is implemented. Safety-critical transitions stay deterministic
and testable; later LLM/YuLan adapters may explain or enrich decisions, but they
must not bypass these contracts.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from hashlib import sha256
import json
from typing import Any, Literal

from pydantic import BaseModel, Field, computed_field


class DataLabel(str, Enum):
    FACT = "FACT"
    SYNTHETIC = "SYNTHETIC"
    SIMULATED = "SIMULATED"


class ActorType(str, Enum):
    RESIDENT = "resident"
    INSTITUTION = "institution"
    COMMUNITY_WORKER = "community_worker"
    GOVERNMENT = "government"
    PROFESSIONAL_DEPARTMENT = "professional_department"
    RESCUE_FORCE = "rescue_force"


class EvacuationStatus(str, Enum):
    UNCONTACTED = "uncontacted"
    CONTACTED = "contacted"
    CONFIRMED = "confirmed"
    WAITING_TRANSFER = "waiting_transfer"
    IN_TRANSIT = "in_transit"
    SHELTERED = "sheltered"
    UNREGISTERED = "unregistered"
    CONTACT_FAILED = "contact_failed"
    MISUNDERSTOOD = "misunderstood"
    DISTRUSTED = "distrusted"
    REFUSED = "refused"
    RESOURCE_BLOCKED = "resource_blocked"
    ROUTE_BLOCKED = "route_blocked"
    AUTHORIZATION_WAIT = "authorization_wait"
    UNSUITABLE_SHELTER = "unsuitable_shelter"


class TransitionError(ValueError):
    """Raised when an evacuation status transition violates the frozen state machine."""


ALLOWED_TRANSITIONS: dict[EvacuationStatus, set[EvacuationStatus]] = {
    EvacuationStatus.UNREGISTERED: {
        EvacuationStatus.UNCONTACTED,
        EvacuationStatus.CONTACT_FAILED,
    },
    EvacuationStatus.UNCONTACTED: {
        EvacuationStatus.CONTACTED,
        EvacuationStatus.CONTACT_FAILED,
    },
    EvacuationStatus.CONTACT_FAILED: {
        EvacuationStatus.CONTACTED,
        EvacuationStatus.UNCONTACTED,
    },
    EvacuationStatus.CONTACTED: {
        EvacuationStatus.MISUNDERSTOOD,
        EvacuationStatus.DISTRUSTED,
        EvacuationStatus.CONFIRMED,
        EvacuationStatus.REFUSED,
    },
    EvacuationStatus.MISUNDERSTOOD: {
        EvacuationStatus.CONTACTED,
        EvacuationStatus.CONFIRMED,
        EvacuationStatus.REFUSED,
    },
    EvacuationStatus.DISTRUSTED: {
        EvacuationStatus.CONFIRMED,
        EvacuationStatus.REFUSED,
    },
    EvacuationStatus.REFUSED: {
        EvacuationStatus.CONFIRMED,
        EvacuationStatus.CONTACTED,
    },
    EvacuationStatus.CONFIRMED: {
        EvacuationStatus.WAITING_TRANSFER,
        EvacuationStatus.RESOURCE_BLOCKED,
        EvacuationStatus.AUTHORIZATION_WAIT,
    },
    EvacuationStatus.AUTHORIZATION_WAIT: {
        EvacuationStatus.WAITING_TRANSFER,
        EvacuationStatus.RESOURCE_BLOCKED,
    },
    EvacuationStatus.RESOURCE_BLOCKED: {
        EvacuationStatus.WAITING_TRANSFER,
        EvacuationStatus.ROUTE_BLOCKED,
    },
    EvacuationStatus.WAITING_TRANSFER: {
        EvacuationStatus.IN_TRANSIT,
        EvacuationStatus.RESOURCE_BLOCKED,
        EvacuationStatus.ROUTE_BLOCKED,
    },
    EvacuationStatus.ROUTE_BLOCKED: {
        EvacuationStatus.WAITING_TRANSFER,
        EvacuationStatus.IN_TRANSIT,
    },
    EvacuationStatus.IN_TRANSIT: {
        EvacuationStatus.SHELTERED,
        EvacuationStatus.ROUTE_BLOCKED,
        EvacuationStatus.UNSUITABLE_SHELTER,
    },
    EvacuationStatus.UNSUITABLE_SHELTER: {
        EvacuationStatus.SHELTERED,
        EvacuationStatus.WAITING_TRANSFER,
    },
    EvacuationStatus.SHELTERED: set(),
}


def can_transition(source: EvacuationStatus, target: EvacuationStatus) -> bool:
    return target in ALLOWED_TRANSITIONS[source]


def require_transition(source: EvacuationStatus, target: EvacuationStatus) -> None:
    if not can_transition(source, target):
        raise TransitionError(f"illegal evacuation transition: {source.value} -> {target.value}")


class PersonAgent(BaseModel):
    id: str
    label: DataLabel = DataLabel.SYNTHETIC
    actor_type: Literal[ActorType.RESIDENT] = ActorType.RESIDENT
    age: int = Field(ge=0, le=120)
    sex: Literal["female", "male", "other", "unknown"] = "unknown"
    household_id: str | None = None
    institution_id: str | None = None
    location_id: str
    mobility: Literal["independent", "limited", "bedridden"]
    chronic_condition: bool = False
    care_dependency: Literal["none", "partial", "full"] = "none"
    income_level: Literal["low", "middle", "high"] = "middle"
    digital_access: float = Field(ge=0.0, le=1.0)
    official_trust: float = Field(ge=0.0, le=1.0)
    cadre_trust: float = Field(ge=0.0, le=1.0)
    neighbor_trust: float = Field(ge=0.0, le=1.0)
    false_alarm_memory: int = Field(default=0, ge=0)
    risk_perception: float = Field(default=0.0, ge=0.0, le=1.0)
    conformity: float = Field(default=0.5, ge=0.0, le=1.0)
    transfer_cost: float = Field(default=0.0, ge=0.0, le=1.0)
    refusal_tendency: float = Field(default=0.0, ge=0.0, le=1.0)
    has_private_transport: bool = False
    care_support_available: bool = False
    status: EvacuationStatus = EvacuationStatus.UNCONTACTED

    @computed_field
    @property
    def is_vulnerable(self) -> bool:
        return (
            self.age >= 65
            or self.mobility != "independent"
            or self.care_dependency != "none"
            or self.chronic_condition
            or self.digital_access < 0.35
        )


class Household(BaseModel):
    id: str
    label: DataLabel = DataLabel.SYNTHETIC
    member_ids: list[str]
    location_id: str
    has_vehicle: bool = False


class Institution(BaseModel):
    id: str
    label: DataLabel = DataLabel.SYNTHETIC
    kind: Literal["nursing_home", "hospital", "school"]
    name: str
    resident_ids: list[str] = Field(default_factory=list)
    responsible_actor_id: str
    preparation_minutes: int = Field(ge=0)
    beds_available: int = Field(default=0, ge=0)


class NetworkEdge(BaseModel):
    id: str
    label: DataLabel = DataLabel.SYNTHETIC
    source_id: str
    target_id: str
    layer: Literal["family", "neighbor", "institution", "administrative", "volunteer", "online"]
    trust_weight: float = Field(ge=0.0, le=1.0)
    speed_minutes: int = Field(ge=0)
    failure_probability: float = Field(ge=0.0, le=1.0)
    responsibility: str | None = None


class InfrastructureNode(BaseModel):
    id: str
    label: DataLabel = DataLabel.SYNTHETIC
    kind: Literal["levee", "bridge", "road", "communications", "power", "shelter"]
    health: float = Field(ge=0.0, le=1.0)
    last_inspection_day: int | None = None
    defect_level: int = Field(default=0, ge=0, le=5)
    repair_cost: float = Field(default=0.0, ge=0.0)
    repair_duration_hours: float = Field(default=0.0, ge=0.0)
    affected_population_ids: list[str] = Field(default_factory=list)
    related_route_ids: list[str] = Field(default_factory=list)
    failed: bool = False


class WarningEvent(BaseModel):
    id: str
    label: DataLabel = DataLabel.SIMULATED
    source_actor_id: str
    sent_minute: int = Field(ge=0)
    scope_ids: list[str]
    credibility: float = Field(ge=0.0, le=1.0)
    content_type: Literal["official", "cadre_call", "institution_notice", "villager_report", "neighbor_forward", "rumor"]
    risk_level: Literal["watch", "warning", "evacuate"]


class MessageReceipt(BaseModel):
    id: str
    label: DataLabel = DataLabel.SIMULATED
    warning_event_id: str
    recipient_id: str
    received_minute: int | None = Field(default=None, ge=0)
    understood: bool = False
    trusted: bool = False
    acknowledged: bool = False
    converted_to_task: bool = False
    path: list[str] = Field(default_factory=list)


class EvacuationTask(BaseModel):
    id: str
    label: DataLabel = DataLabel.SIMULATED
    subject_id: str
    responsible_actor_id: str
    deadline_minute: int = Field(ge=0)
    status: EvacuationStatus
    priority: float = Field(ge=0.0)
    required_resources: dict[str, int] = Field(default_factory=dict)
    assigned_resource_ids: list[str] = Field(default_factory=list)
    route_id: str | None = None
    event_log: list[str] = Field(default_factory=list)


class ResourceUnit(BaseModel):
    id: str
    label: DataLabel = DataLabel.SYNTHETIC
    kind: Literal["vehicle", "stretcher", "care_worker", "rescue_team", "hospital_bed", "shelter_bed"]
    capacity: int = Field(ge=1)
    location_id: str
    available_minute: int = Field(default=0, ge=0)


class DecisionTrace(BaseModel):
    id: str
    label: DataLabel = DataLabel.SIMULATED
    actor_id: str
    minute: int = Field(ge=0)
    observed_information_ids: list[str] = Field(default_factory=list)
    factors: dict[str, float] = Field(default_factory=dict)
    action: str
    rule_version: str
    model_version: str | None = None
    prompt_version: str | None = None
    sampled_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    random_draw: float | None = Field(default=None, ge=0.0, le=1.0)


class PolicyId(str, Enum):
    S0 = "S0"
    S1 = "S1"
    S2 = "S2"
    S3 = "S3"
    S4 = "S4"
    S5 = "S5"


class DispatchRule(str, Enum):
    EQUAL = "equal_allocation"
    FIRST_COME_FIRST_SERVED = "first_come_first_served"
    VULNERABLE_FIRST = "vulnerable_first"
    RISK_TIME_WINDOW = "risk_time_window"
    RESILIENCE = "resilience"


class PolicyConfig(BaseModel):
    id: PolicyId
    label: DataLabel = DataLabel.SYNTHETIC
    name: str
    registry_mode: Literal["static", "dynamic"]
    warning_channels: list[
        Literal["department_push", "multi_channel", "cadre_call", "neighbor_network", "backup_radio"]
    ]
    confirmation_required: bool
    dispatch_rule: DispatchRule
    preposition_care_resources: bool = False
    pre_disaster_maintenance: dict[str, float] = Field(default_factory=dict)
    budget_units: float = Field(default=0.0, ge=0.0)

    @computed_field
    @property
    def config_hash(self) -> str:
        payload = json.dumps(
            self.model_dump(mode="json", exclude={"config_hash"}),
            ensure_ascii=False,
            sort_keys=True,
        )
        return sha256(payload.encode("utf-8")).hexdigest()[:16]


class MetricRecord(BaseModel):
    label: DataLabel = DataLabel.SIMULATED
    policy_id: PolicyId
    run_id: str
    seed: int
    safe_before_danger_rate: float = Field(ge=0.0, le=1.0)
    vulnerable_harm_risk: float = Field(ge=0.0)
    lead_time_minutes_median: float
    response_closure_rate: float = Field(ge=0.0, le=1.0)
    missed_critical_action_rate: float = Field(ge=0.0, le=1.0)
    group_safety_gap: float
    incremental_cost_per_safe_transfer: float | None = None
    worst_case_regret: float | None = None
    trust_delta: float = 0.0
    resource_queue_minutes_mean: float = Field(default=0.0, ge=0.0)


class SimulationRun(BaseModel):
    id: str
    label: DataLabel = DataLabel.SIMULATED
    policy_id: PolicyId
    seed: int
    code_version: str
    config_hash: str
    started_at: datetime
    model_versions: dict[str, str] = Field(default_factory=dict)
    prompt_versions: dict[str, str] = Field(default_factory=dict)
    output_paths: list[str] = Field(default_factory=list)
    status: Literal["pending", "running", "succeeded", "failed", "cancelled"] = "pending"
    failure_reason: str | None = None


MVP_POLICY_CONFIGS: dict[PolicyId, PolicyConfig] = {
    PolicyId.S0: PolicyConfig(
        id=PolicyId.S0,
        name="现状基线",
        registry_mode="static",
        warning_channels=["department_push"],
        confirmation_required=False,
        dispatch_rule=DispatchRule.EQUAL,
        preposition_care_resources=False,
        pre_disaster_maintenance={"routine_inspection": 1.0},
        budget_units=100.0,
    ),
    PolicyId.S1: PolicyConfig(
        id=PolicyId.S1,
        name="工程优先",
        registry_mode="static",
        warning_channels=["department_push"],
        confirmation_required=False,
        dispatch_rule=DispatchRule.EQUAL,
        preposition_care_resources=False,
        pre_disaster_maintenance={"bridge_reinforcement": 1.0, "levee_repair": 1.0},
        budget_units=150.0,
    ),
    PolicyId.S2: PolicyConfig(
        id=PolicyId.S2,
        name="数字预警优先",
        registry_mode="static",
        warning_channels=["department_push", "multi_channel"],
        confirmation_required=False,
        dispatch_rule=DispatchRule.FIRST_COME_FIRST_SERVED,
        preposition_care_resources=False,
        pre_disaster_maintenance={"routine_inspection": 1.0},
        budget_units=120.0,
    ),
    PolicyId.S3: PolicyConfig(
        id=PolicyId.S3,
        name="脆弱群体优先",
        registry_mode="dynamic",
        warning_channels=["department_push", "cadre_call"],
        confirmation_required=True,
        dispatch_rule=DispatchRule.VULNERABLE_FIRST,
        preposition_care_resources=True,
        pre_disaster_maintenance={"routine_inspection": 1.0},
        budget_units=125.0,
    ),
    PolicyId.S4: PolicyConfig(
        id=PolicyId.S4,
        name="社区互助优先",
        registry_mode="dynamic",
        warning_channels=["department_push", "cadre_call", "neighbor_network", "backup_radio"],
        confirmation_required=True,
        dispatch_rule=DispatchRule.RISK_TIME_WINDOW,
        preposition_care_resources=False,
        pre_disaster_maintenance={"communications_backup": 1.0, "routine_inspection": 1.0},
        budget_units=125.0,
    ),
    PolicyId.S5: PolicyConfig(
        id=PolicyId.S5,
        name="综合韧性",
        registry_mode="dynamic",
        warning_channels=[
            "department_push",
            "multi_channel",
            "cadre_call",
            "neighbor_network",
            "backup_radio",
        ],
        confirmation_required=True,
        dispatch_rule=DispatchRule.RESILIENCE,
        preposition_care_resources=True,
        pre_disaster_maintenance={
            "bridge_reinforcement": 1.0,
            "communications_backup": 1.0,
            "routine_inspection": 1.0,
        },
        budget_units=150.0,
    ),
}


EVACUATION_PROBABILITY_FACTORS: tuple[str, ...] = (
    "risk_perception",
    "official_trust",
    "neighbor_action",
    "direct_call",
    "available_assistance",
    "transfer_cost",
    "false_alarm_fatigue",
    "route_obstacle",
)


def stable_config_hash(value: BaseModel | dict[str, Any]) -> str:
    if isinstance(value, BaseModel):
        payload = json.dumps(value.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
    else:
        payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return sha256(payload.encode("utf-8")).hexdigest()[:16]
