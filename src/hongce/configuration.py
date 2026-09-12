"""Shared scenario configuration used by single runs, experiments and optimization."""
from dataclasses import replace
from typing import Any
from .scenario import SyntheticScenario, HazardConfig, ResourceProfile, generate_qingyuan

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
    "false_alarm_memory": -1,
    "routes": [],
    "transport_mode": "network",
    "shelters": [],
    "road_capacity": 8,
    "loading_minutes": 5,
    "queue_aging_minutes": 45,
    "flood_peak_m": 0.45,
    "road_depth_limit_m": 0.30,
    "dispatch_model": "positioned_fleet",
    "dispatch_mode": "policy_priority",
    "fleet_base_id": "school_shelter",
}


def normalize_scenario_config(overrides: dict[str, Any] | None) -> dict[str, Any]:
    overrides = overrides or {}
    config = dict(DEFAULT_SCENARIO_CONFIG)
    for key in config:
        if key in overrides and overrides[key] is not None and overrides[key] != "":
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
        "false_alarm_memory",
        "road_capacity", "loading_minutes", "queue_aging_minutes",
    }:
        config[key] = int(float(config[key]))
    for key in {"vulnerable_ratio", "communication_failure_rate", "flood_peak_m", "road_depth_limit_m"}:
        config[key] = float(config[key])
    shelters=config['shelters']
    if not overrides.get('fleet_base_id') and isinstance(shelters,list) and shelters and all(isinstance(s,dict) and isinstance(s.get('id'),str) for s in shelters):
        ids=[s['id'] for s in shelters]
        config['fleet_base_id']='school_shelter' if 'school_shelter' in ids else ids[0]
    return config


def validate_scenario_config(config: dict[str, Any]) -> str | None:
    import math
    if any(not math.isfinite(config[k]) for k in ('vulnerable_ratio','communication_failure_rate','flood_peak_m','road_depth_limit_m')):
        return "参数必须为有限数值"
    if config['transport_mode'] not in {'network','legacy'}:
        return '未知运输模式'
    if config['dispatch_model'] not in {'positioned_fleet','corridor_v3'} or config['dispatch_mode'] not in {'policy_priority','balanced_coverage'}:
        return '未知车队模型或调度策略'
    if not isinstance(config['fleet_base_id'],str) or not config['fleet_base_id']:
        return '车辆集结点编号必须为非空字符串'
    for k, low, high in [('road_capacity',1,300),('loading_minutes',0,30),('queue_aging_minutes',5,180),('flood_peak_m',0,5),('road_depth_limit_m',.05,1)]:
        if not low<=config[k]<=high:
            return f'{k} 必须在 {low} 到 {high} 之间'
    if not isinstance(config['shelters'],list):
        return '安置点必须为列表'
    shelter_ids=set()
    for s in config['shelters']:
        if not isinstance(s,dict) or not s.get('id') or s['id'] in shelter_ids:
            return '安置点编号必须唯一且非空'
        shelter_ids.add(s['id'])
        for key in ('capacity','medical_slots','care_capacity'):
            if key in s and (not isinstance(s[key],(int,float)) or not math.isfinite(s[key]) or s[key]<0):
                return '安置点容量必须为非负有限数值'
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
        if not 0 <= config[key] <= 300:
            label = {"vehicles": "转运车辆", "care_workers": "照护人员", "stretchers": "担架数量"}[key]
            return f"{label}必须在 0 到 300 之间"
    if not 0 <= config["shelter_beds"] <= 5000:
        return "避难床位必须在 0 到 5000 之间"
    if not -1 <= config["false_alarm_memory"] <= 20:
        return "误报记忆必须为 -1（合成分布）或 0 到 20 次"
    if not isinstance(config["routes"], list):
        return "路线配置必须为列表"
    route_ids=set()
    for route in config['routes']:
        if not isinstance(route, dict) or not {'id', 'origin_id', 'travel_minutes'}.issubset(route):
            return "路线缺少编号、起点或旅行时间"
        try:
            if route['id'] in route_ids or not route['id']:
                return '路线编号必须唯一且非空'
            route_ids.add(route['id'])
            if not 0 < float(route['travel_minutes']) <= 600:
                return "路线旅行时间必须在 0 到 600 分钟之间"
        except (TypeError, ValueError):
            return "路线旅行时间必须为数值"
        profile=route.get('depth_profile',[])
        if not isinstance(profile,list):
            return '积水过程线必须为 [分钟, 水深米] 列表'
        previous=-1
        for point in profile:
            if not isinstance(point,list) or len(point)!=2 or any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in point) or point[0]<=previous or point[1]<0:
                return '积水过程线时刻须严格递增，水深须非负且有限'
            previous=point[0]
        for key in ('max_concurrent_vehicles','max_depth_m'):
            if key in route and (not isinstance(route[key],(int,float)) or not math.isfinite(route[key]) or route[key]<=0):
                return f'路线 {key} 必须为正数'
        if 'closed_minute' in route and (not isinstance(route['closed_minute'],(int,float)) or not math.isfinite(route['closed_minute']) or route['closed_minute']<0):
            return '道路封闭分钟必须非负且有限'
    destinations=shelter_ids or {'school_shelter','gym_shelter'}
    nodes = {'nursing_home','county_hospital','north_valley','south_valley','qingyuan_town'} | destinations
    for route in config['routes']:
        nodes.add(route['origin_id'])
        nodes.add(route.get('shelter_id','school_shelter'))
        if route.get('shelter_id','school_shelter') not in destinations:
            return '路线目的地必须为已配置的安置点'
        if 'bidirectional' in route and not isinstance(route['bidirectional'],bool):
            return '道路双向标记必须为布尔值'
    if config['fleet_base_id'] not in nodes:
        return '车辆集结点必须为路网中的地点或安置点'
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
    scenario.routes = list(scenario_config.get('routes', []))
    if scenario_config['transport_mode']=='network':
        from .transport import default_transport
        scenario.transport=default_transport(scenario_config)
    if scenario_config.get('false_alarm_memory', -1) >= 0:
        scenario.people = [p.model_copy(update={'false_alarm_memory': scenario_config['false_alarm_memory']}) for p in scenario.people]
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
