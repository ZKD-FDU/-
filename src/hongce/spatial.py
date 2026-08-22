"""Spatial package adapter for QGIS/PyQGIS outputs.

The adapter intentionally reads a small JSON contract instead of importing
QGIS. QGIS/PyQGIS produces the spatial package; the simulation API consumes it
without a desktop GIS dependency.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from statistics import mean
from typing import Any


SPATIAL_PACKAGE_FILE = "spatial_package.json"


def load_spatial_package(path: str | Path) -> dict[str, Any]:
    root = Path(path)
    package_path = root / SPATIAL_PACKAGE_FILE if root.is_dir() else root
    if not package_path.exists():
        raise FileNotFoundError(f"spatial package not found: {package_path}")
    data = json.loads(package_path.read_text(encoding="utf-8"))
    validate_spatial_package(data)
    return data


def validate_spatial_package(data: dict[str, Any]) -> None:
    required = {"label", "places", "routes", "shelters", "coverage"}
    missing = sorted(required - set(data))
    if missing:
        raise ValueError(f"spatial package missing fields: {', '.join(missing)}")
    if not isinstance(data["places"], list) or not data["places"]:
        raise ValueError("spatial package must contain at least one place")
    if not isinstance(data["shelters"], list) or not data["shelters"]:
        raise ValueError("spatial package must contain at least one shelter")
    if not isinstance(data["routes"], list):
        raise ValueError("spatial package routes must be a list")


def summarize_spatial_package(data: dict[str, Any]) -> dict[str, Any]:
    validate_spatial_package(data)
    routes = data.get("routes", [])
    shelters = data.get("shelters", [])
    places = data.get("places", [])
    rivers = data.get("rivers", [])
    coverage = data.get("coverage", {})
    route_minutes = [float(route.get("travel_minutes", 0)) for route in routes if route.get("travel_minutes") is not None]
    route_distances = [
        float(route.get("route_distance_m", route.get("distance_meters", 0)))
        for route in routes
        if route.get("route_distance_m", route.get("distance_meters")) is not None
    ]
    exposure_minutes = [
        float(route.get("risk_exposure_minutes", 0))
        for route in routes
        if route.get("risk_exposure_minutes") is not None
    ]
    risk_scores = [float(place.get("risk_score", 0)) for place in places]
    blocked = [route for route in routes if route.get("crosses_high_risk") or route.get("bridge_exposure_score", 0) >= 0.65]
    care_capacity = sum_int(shelter.get("care_capacity", 0) for shelter in shelters)
    quality = data.get("quality", {})
    return {
        "label": data.get("label", "SYNTHETIC_SPATIAL"),
        "package_id": data.get("package_id", "qgis-spatial-package"),
        "place_count": len(places),
        "route_count": len(routes),
        "shelter_count": len(shelters),
        "river_count": len(rivers),
        "total_shelter_capacity": sum_int(shelter.get("capacity") for shelter in shelters),
        "total_shelter_care_capacity": care_capacity,
        "mean_route_minutes": round(mean(route_minutes), 2) if route_minutes else 0,
        "max_route_minutes": round(max(route_minutes), 2) if route_minutes else 0,
        "mean_route_distance_m": round(mean(route_distances), 1) if route_distances else 0,
        "mean_risk_exposure_minutes": round(mean(exposure_minutes), 2) if exposure_minutes else 0,
        "mean_risk_score": round(mean(risk_scores), 3) if risk_scores else 0,
        "high_risk_route_share": round(len(blocked) / max(1, len(routes)), 3),
        "uncovered_place_count": int(coverage.get("uncovered_place_count", 0)),
        "coverage_rate": float(coverage.get("coverage_rate", 0)),
        "spatial_quality_score": float(quality.get("spatial_quality_score", estimate_spatial_quality(data))),
        "route_engine": data.get("method", {}).get("route_engine", "unknown"),
    }


def derive_scenario_overrides(data: dict[str, Any]) -> dict[str, Any]:
    validate_spatial_package(data)
    summary = summarize_spatial_package(data)
    places = data.get("places", [])
    resources = data.get("resources", {})
    vulnerable_population = sum_int(place.get("vulnerable_population") for place in places)
    total_population = sum_int(place.get("population") for place in places)
    vulnerable_ratio = vulnerable_population / total_population if total_population else 0.32
    mean_risk = summary["mean_risk_score"]
    high_risk_route_share = summary["high_risk_route_share"]
    max_route_minutes = summary["max_route_minutes"]
    mean_risk_exposure = summary.get("mean_risk_exposure_minutes", 0)
    coverage_gap = 1.0 - summary["coverage_rate"]

    danger_arrival = clamp_int(round(210 - 70 * mean_risk - 25 * high_risk_route_share - 0.6 * mean_risk_exposure), 90, 300)
    warning_minute = clamp_int(round(danger_arrival - max(75, max_route_minutes + 35)), 0, danger_arrival - 30)
    evacuation_order = clamp_int(round(warning_minute + 25), warning_minute, danger_arrival - 10)
    bridge_closure = clamp_int(round(danger_arrival - 55 + 25 * high_risk_route_share - 0.4 * mean_risk_exposure), warning_minute, danger_arrival)
    comms_failure_rate = clamp_float(0.18 + 0.45 * mean_risk + 0.20 * coverage_gap, 0.05, 0.95)
    comms_failure_minute = clamp_int(round(warning_minute + 35), warning_minute, danger_arrival)
    shelter_beds = summary["total_shelter_capacity"] or int(resources.get("shelter_beds", 700) or 700)

    return {
        "vulnerable_ratio": round(clamp_float(vulnerable_ratio, 0.05, 0.85), 3),
        "timestep_minutes": int(resources.get("timestep_minutes", 5) or 5),
        "warning_minute": warning_minute,
        "evacuation_order_minute": evacuation_order,
        "bridge_closure_minute": bridge_closure,
        "danger_arrival_minute": danger_arrival,
        "communication_failure_minute": comms_failure_minute,
        "communication_failure_rate": round(comms_failure_rate, 3),
        "vehicles": int(resources.get("vehicles") or estimate_vehicle_need(total_population, max_route_minutes)),
        "care_workers": int(resources.get("care_workers") or max(12, math.ceil(vulnerable_population / 10))),
        "stretchers": int(resources.get("stretchers") or max(6, math.ceil(vulnerable_population / 24))),
        "shelter_beds": int(shelter_beds),
    }


def spatial_context(data: dict[str, Any]) -> dict[str, Any]:
    validate_spatial_package(data)
    return {
        "label": data.get("label", "SYNTHETIC_SPATIAL"),
        "package_id": data.get("package_id", "qgis-spatial-package"),
        "summary": summarize_spatial_package(data),
        "scenario_overrides": derive_scenario_overrides(data),
        "quality": data.get("quality", {"spatial_quality_score": estimate_spatial_quality(data)}),
    }


def estimate_vehicle_need(total_population: int, max_route_minutes: float) -> int:
    demand = max(50, total_population)
    cycle_penalty = max(1.0, max_route_minutes / 35.0)
    return clamp_int(math.ceil(demand * cycle_penalty / 90), 4, 300)


def estimate_spatial_quality(data: dict[str, Any]) -> float:
    routes = data.get("routes", [])
    places = data.get("places", [])
    shelters = data.get("shelters", [])
    score = 0.25
    if routes and all(route.get("route_engine") == "qgis_shortest_path" for route in routes):
        score += 0.25
    elif routes:
        score += 0.12
    if places and all(place.get("population") is not None and place.get("vulnerable_population") is not None for place in places):
        score += 0.18
    if shelters and all(shelter.get("capacity") is not None for shelter in shelters):
        score += 0.12
    if data.get("risk_zones"):
        score += 0.15
    if data.get("bridges"):
        score += 0.10
    if data.get("rivers"):
        score += 0.08
    if any(route.get("risk_exposure_minutes") is not None for route in routes):
        score += 0.08
    return round(clamp_float(score, 0.0, 1.0), 3)


def sum_int(values) -> int:
    total = 0
    for value in values:
        if value in {None, ""}:
            continue
        total += int(float(value))
    return total


def clamp_float(value: float, low: float, high: float) -> float:
    return min(high, max(low, float(value)))


def clamp_int(value: int, low: int, high: int) -> int:
    return min(high, max(low, int(value)))
