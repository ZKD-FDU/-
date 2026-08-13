"""Synthetic Qingyuan county generation.

The generator is deterministic for a fixed seed. It creates synthetic people,
institutions, infrastructure, multilayer relations, and resource totals. No real
personal data or sensitive facility coordinates are used.
"""

from __future__ import annotations

from dataclasses import dataclass
import random

from .models import Household, InfrastructureNode, Institution, NetworkEdge, PersonAgent


@dataclass(frozen=True)
class HazardConfig:
    timestep_minutes: int = 5
    start_minute: int = 0
    end_minute: int = 240
    warning_minute: int = 45
    evacuation_order_minute: int = 75
    bridge_closure_minute: int = 120
    danger_arrival_minute: int = 180
    communication_failure_minute: int = 90
    communication_failure_rate: float = 0.30


@dataclass(frozen=True)
class ResourceProfile:
    vehicles: int = 18
    vehicle_capacity: int = 4
    stretchers: int = 18
    care_workers: int = 34
    shelter_beds: int = 700
    hospital_beds: int = 90


@dataclass
class SyntheticScenario:
    seed: int
    county_name: str
    people: list[PersonAgent]
    households: list[Household]
    institutions: list[Institution]
    infrastructure: list[InfrastructureNode]
    network_edges: list[NetworkEdge]
    hazard: HazardConfig
    resources: ResourceProfile

    @property
    def person_by_id(self) -> dict[str, PersonAgent]:
        return {person.id: person for person in self.people}


LOCATIONS = (
    "qingyuan_town",
    "nursing_home",
    "county_hospital",
    "county_school",
    "north_valley",
    "south_valley",
)


def generate_qingyuan(seed: int = 20260806, population: int = 2000) -> SyntheticScenario:
    rng = random.Random(seed)
    people: list[PersonAgent] = []
    households: list[Household] = []
    edges: list[NetworkEdge] = []

    nursing_count = min(69, max(20, population // 25))
    hospital_patient_count = max(30, population // 80)
    school_count = max(80, population // 20)

    def add_person(
        idx: int,
        location_id: str,
        age: int,
        mobility: str,
        care_dependency: str,
        institution_id: str | None = None,
        household_id: str | None = None,
    ) -> None:
        chronic = age >= 70 and rng.random() < 0.45
        digital_base = 0.25 if age >= 70 else 0.75
        if location_id in {"north_valley", "south_valley"}:
            digital_base -= 0.15
        people.append(
            PersonAgent(
                id=f"p{idx:05d}",
                age=age,
                sex=rng.choice(["female", "male"]),
                household_id=household_id,
                institution_id=institution_id,
                location_id=location_id,
                mobility=mobility,  # type: ignore[arg-type]
                chronic_condition=chronic,
                care_dependency=care_dependency,  # type: ignore[arg-type]
                income_level=rng.choices(["low", "middle", "high"], weights=[0.36, 0.52, 0.12])[0],
                digital_access=clamp(rng.gauss(digital_base, 0.18)),
                official_trust=clamp(rng.betavariate(3.2, 2.4)),
                cadre_trust=clamp(rng.betavariate(3.6, 2.2)),
                neighbor_trust=clamp(rng.betavariate(4.0, 2.0)),
                false_alarm_memory=rng.choices([0, 1, 2, 5], weights=[0.45, 0.25, 0.2, 0.1])[0],
                risk_perception=clamp(rng.betavariate(2.2, 3.2)),
                conformity=clamp(rng.betavariate(2.8, 2.8)),
                transfer_cost=clamp(rng.betavariate(2.2, 3.0)),
                refusal_tendency=clamp(rng.betavariate(1.6, 5.0)),
                has_private_transport=rng.random() < 0.32,
                care_support_available=rng.random() < 0.55,
            )
        )

    idx = 1
    nursing_ids: list[str] = []
    for i in range(nursing_count):
        if i < 15:
            mobility, dependency = "bedridden", "full"
        elif i < 55:
            mobility, dependency = "limited", "partial"
        else:
            mobility, dependency = "independent", "none"
        add_person(idx, "nursing_home", rng.randint(68, 96), mobility, dependency, "inst_nursing")
        nursing_ids.append(f"p{idx:05d}")
        idx += 1

    hospital_ids: list[str] = []
    for _ in range(hospital_patient_count):
        age = rng.choices([rng.randint(25, 64), rng.randint(65, 88)], weights=[0.55, 0.45])[0]
        mobility = rng.choices(["independent", "limited", "bedridden"], weights=[0.45, 0.45, 0.10])[0]
        dependency = "full" if mobility == "bedridden" else ("partial" if mobility == "limited" else "none")
        add_person(idx, "county_hospital", age, mobility, dependency, "inst_hospital")
        hospital_ids.append(f"p{idx:05d}")
        idx += 1

    for _ in range(school_count):
        add_person(idx, "county_school", rng.randint(7, 17), "independent", "none", "inst_school")
        idx += 1

    remaining = population - len(people)
    household_id = 1
    while remaining > 0:
        size = min(remaining, rng.choices([1, 2, 3, 4, 5], weights=[0.24, 0.30, 0.24, 0.16, 0.06])[0])
        location = rng.choices(
            ["qingyuan_town", "north_valley", "south_valley"],
            weights=[0.62, 0.20, 0.18],
        )[0]
        hid = f"h{household_id:05d}"
        member_ids: list[str] = []
        for _ in range(size):
            age = rng.choices(
                [rng.randint(18, 59), rng.randint(60, 91), rng.randint(0, 17)],
                weights=[0.57, 0.25, 0.18],
            )[0]
            mobility = "independent"
            dependency = "none"
            if age >= 75 and rng.random() < 0.35:
                mobility = rng.choice(["limited", "bedridden"])
                dependency = "full" if mobility == "bedridden" else "partial"
            elif age >= 65 and rng.random() < 0.25:
                mobility = "limited"
                dependency = "partial"
            add_person(idx, location, age, mobility, dependency, household_id=hid)
            member_ids.append(f"p{idx:05d}")
            idx += 1
            remaining -= 1
        households.append(Household(id=hid, member_ids=member_ids, location_id=location, has_vehicle=rng.random() < 0.38))
        household_id += 1

    institutions = [
        Institution(
            id="inst_nursing",
            kind="nursing_home",
            name="清源县青松养老照料中心",
            resident_ids=nursing_ids,
            responsible_actor_id="worker_nursing_night",
            preparation_minutes=45,
            beds_available=0,
        ),
        Institution(
            id="inst_hospital",
            kind="hospital",
            name="清源县人民医院",
            resident_ids=hospital_ids,
            responsible_actor_id="worker_hospital_ops",
            preparation_minutes=35,
            beds_available=90,
        ),
        Institution(
            id="inst_school",
            kind="school",
            name="清源县第二中学临时安置点",
            resident_ids=[],
            responsible_actor_id="worker_school_shelter",
            preparation_minutes=25,
            beds_available=700,
        ),
    ]

    infrastructure = [
        InfrastructureNode(
            id="bridge_east",
            kind="bridge",
            health=0.42,
            last_inspection_day=-120,
            defect_level=3,
            repair_cost=45,
            repair_duration_hours=36,
            affected_population_ids=[p.id for p in people if p.location_id in {"nursing_home", "north_valley"}],
            related_route_ids=["route_nursing_to_school", "route_north_valley_to_school"],
        ),
        InfrastructureNode(
            id="road_valley_south",
            kind="road",
            health=0.55,
            last_inspection_day=-90,
            defect_level=2,
            repair_cost=25,
            repair_duration_hours=18,
            affected_population_ids=[p.id for p in people if p.location_id == "south_valley"],
            related_route_ids=["route_south_valley_to_school"],
        ),
        InfrastructureNode(
            id="comms_hill",
            kind="communications",
            health=0.50,
            last_inspection_day=-180,
            defect_level=3,
            repair_cost=20,
            repair_duration_hours=12,
            affected_population_ids=[p.id for p in people if p.location_id in {"north_valley", "south_valley"}],
        ),
        InfrastructureNode(
            id="levee_riverbend",
            kind="levee",
            health=0.58,
            last_inspection_day=-60,
            defect_level=2,
            repair_cost=60,
            repair_duration_hours=48,
            affected_population_ids=[p.id for p in people if p.location_id in {"qingyuan_town", "nursing_home"}],
        ),
    ]

    edge_id = 1
    for household in households:
        for source in household.member_ids:
            for target in household.member_ids:
                if source != target:
                    edges.append(
                        NetworkEdge(
                            id=f"e{edge_id:06d}",
                            source_id=source,
                            target_id=target,
                            layer="family",
                            trust_weight=0.9,
                            speed_minutes=5,
                            failure_probability=0.05,
                            responsibility="household care",
                        )
                    )
                    edge_id += 1

    by_location: dict[str, list[str]] = {}
    for person in people:
        by_location.setdefault(person.location_id, []).append(person.id)
    for location, ids in by_location.items():
        sample_ids = ids[:]
        rng.shuffle(sample_ids)
        for source in sample_ids:
            neighbors = rng.sample(sample_ids, min(4, max(0, len(sample_ids) - 1)))
            for target in neighbors:
                if source != target:
                    edges.append(
                        NetworkEdge(
                            id=f"e{edge_id:06d}",
                            source_id=source,
                            target_id=target,
                            layer="neighbor",
                            trust_weight=0.55 if location == "qingyuan_town" else 0.72,
                            speed_minutes=10,
                            failure_probability=0.18,
                            responsibility=None,
                        )
                    )
                    edge_id += 1

    for inst in institutions:
        for person_id in inst.resident_ids[:120]:
            edges.append(
                NetworkEdge(
                    id=f"e{edge_id:06d}",
                    source_id=inst.responsible_actor_id,
                    target_id=person_id,
                    layer="institution",
                    trust_weight=0.75,
                    speed_minutes=5,
                    failure_probability=0.04,
                    responsibility=f"{inst.name} roster",
                )
            )
            edge_id += 1

    for location in ["north_valley", "south_valley", "nursing_home", "qingyuan_town"]:
        for person_id in by_location.get(location, [])[:120]:
            edges.append(
                NetworkEdge(
                    id=f"e{edge_id:06d}",
                    source_id=f"cadre_{location}",
                    target_id=person_id,
                    layer="administrative",
                    trust_weight=0.7,
                    speed_minutes=15,
                    failure_probability=0.12,
                    responsibility="cadre call-down",
                )
            )
            edge_id += 1

    return SyntheticScenario(
        seed=seed,
        county_name="清源县",
        people=people,
        households=households,
        institutions=institutions,
        infrastructure=infrastructure,
        network_edges=edges,
        hazard=HazardConfig(),
        resources=ResourceProfile(),
    )


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return min(high, max(low, value))
