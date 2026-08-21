"""Build a HongCe spatial package inside QGIS/PyQGIS.

Run with QGIS Python, for example:

    /Applications/QGIS.app/Contents/MacOS/bin/python3 scripts/qgis_build_spatial_package.py \
      --project data/qgis/hongce.qgz \
      --out data/spatial/qingyuan \
      --places villages \
      --shelters shelters \
      --risk-zones risk_zones \
      --roads roads \
      --bridges bridges

Expected fields:
- places: id/name/population/vulnerable_population
- shelters: id/name/capacity
- risk_zones: risk_score or level
- bridges: id/name/risk_score
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:  # pragma: no cover - only available in QGIS Python.
    from qgis.core import (
        QgsApplication,
        QgsDistanceArea,
        QgsFeature,
        QgsGeometry,
        QgsProject,
        QgsWkbTypes,
    )
    import processing
except ModuleNotFoundError:  # pragma: no cover
    QgsApplication = None
    QgsDistanceArea = None
    QgsFeature = None
    QgsGeometry = None
    QgsProject = None
    QgsWkbTypes = None
    processing = None


def main() -> int:
    args = parse_args()
    if QgsProject is None:
        raise SystemExit("PyQGIS is not available. Run this script with QGIS Python.")

    app = None
    if QgsApplication.instance() is None:
        app = QgsApplication([], False)
        app.initQgis()

    project = QgsProject.instance()
    if args.project:
        if not project.read(args.project):
            raise SystemExit(f"failed to read QGIS project: {args.project}")

    places_layer = require_layer(project, args.places)
    shelters_layer = require_layer(project, args.shelters)
    risk_layer = require_layer(project, args.risk_zones)
    roads_layer = find_layer(project, args.roads)
    bridges_layer = find_layer(project, args.bridges)

    distance = QgsDistanceArea()
    distance.setSourceCrs(places_layer.crs(), project.transformContext())
    distance.setEllipsoid(project.ellipsoid() or "WGS84")

    risk_zones = collect_risk_zones(risk_layer)
    shelters = collect_shelters(shelters_layer)
    bridges = collect_bridges(bridges_layer) if bridges_layer else []
    places = collect_places(places_layer, risk_zones)
    routes = build_routes(places_layer, shelters_layer, roads_layer, risk_zones, bridges, distance)
    coverage = build_coverage(places, routes, shelters, args.coverage_minutes)

    package = {
        "label": "SYNTHETIC_SPATIAL",
        "package_id": args.package_id,
        "source_project": str(args.project or ""),
        "method": {
            "route_engine": "qgis_shortest_path_or_straight_line",
            "coverage_minutes": args.coverage_minutes,
            "risk_overlay": "place centroid intersects risk zone",
        },
        "places": places,
        "shelters": shelters,
        "risk_zones": strip_private_geometry(risk_zones),
        "bridges": strip_private_geometry(bridges),
        "routes": routes,
        "coverage": coverage,
        "resources": {
            "timestep_minutes": args.timestep_minutes,
            "vehicles": args.vehicles,
            "care_workers": args.care_workers,
            "stretchers": args.stretchers,
        },
    }

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "spatial_package.json").write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out_dir / "spatial_package.json")

    if app is not None:
        app.exitQgis()
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build HongCe spatial package from QGIS layers.")
    parser.add_argument("--project", default="", help="Optional .qgz/.qgs project path.")
    parser.add_argument("--out", required=True, help="Output directory.")
    parser.add_argument("--package-id", default="qgis-qingyuan")
    parser.add_argument("--places", default="villages")
    parser.add_argument("--shelters", default="shelters")
    parser.add_argument("--risk-zones", default="risk_zones")
    parser.add_argument("--roads", default="roads")
    parser.add_argument("--bridges", default="bridges")
    parser.add_argument("--coverage-minutes", type=float, default=60)
    parser.add_argument("--timestep-minutes", type=int, default=5)
    parser.add_argument("--vehicles", type=int, default=0)
    parser.add_argument("--care-workers", type=int, default=0)
    parser.add_argument("--stretchers", type=int, default=0)
    return parser.parse_args()


def find_layer(project, name: str):
    matches = project.mapLayersByName(name)
    return matches[0] if matches else None


def require_layer(project, name: str):
    layer = find_layer(project, name)
    if layer is None:
        raise SystemExit(f"missing QGIS layer: {name}")
    return layer


def collect_places(layer, risk_zones: list[dict[str, Any]]) -> list[dict[str, Any]]:
    places = []
    for feature in layer.getFeatures():
        point = feature.geometry().centroid()
        risk_score = max((zone["risk_score"] for zone in risk_zones if intersects(point, zone["_geometry"])), default=0.0)
        places.append(
            {
                "id": field(feature, "id", f"place-{feature.id()}"),
                "name": field(feature, "name", f"place-{feature.id()}"),
                "population": int_float(field(feature, "population", 100)),
                "vulnerable_population": int_float(field(feature, "vulnerable_population", 25)),
                "risk_score": round(risk_score, 3),
                "x": round(point.asPoint().x(), 6),
                "y": round(point.asPoint().y(), 6),
            }
        )
    return places


def collect_shelters(layer) -> list[dict[str, Any]]:
    shelters = []
    for feature in layer.getFeatures():
        point = feature.geometry().centroid()
        shelters.append(
            {
                "id": field(feature, "id", f"shelter-{feature.id()}"),
                "name": field(feature, "name", f"shelter-{feature.id()}"),
                "capacity": int_float(field(feature, "capacity", 300)),
                "x": round(point.asPoint().x(), 6),
                "y": round(point.asPoint().y(), 6),
            }
        )
    return shelters


def collect_risk_zones(layer) -> list[dict[str, Any]]:
    zones = []
    for feature in layer.getFeatures():
        risk_score = float_field(feature, "risk_score", risk_from_level(field(feature, "level", "")))
        zones.append(
            {
                "id": field(feature, "id", f"risk-{feature.id()}"),
                "name": field(feature, "name", f"risk-{feature.id()}"),
                "risk_score": max(0.0, min(1.0, risk_score)),
                "_geometry": feature.geometry(),
            }
        )
    return zones


def collect_bridges(layer) -> list[dict[str, Any]]:
    bridges = []
    for feature in layer.getFeatures():
        point = feature.geometry().centroid()
        bridges.append(
            {
                "id": field(feature, "id", f"bridge-{feature.id()}"),
                "name": field(feature, "name", f"bridge-{feature.id()}"),
                "risk_score": float_field(feature, "risk_score", 0.45),
                "_geometry": point,
            }
        )
    return bridges


def build_routes(places_layer, shelters_layer, roads_layer, risk_zones, bridges, distance) -> list[dict[str, Any]]:
    routes = []
    shelters = list(shelters_layer.getFeatures())
    for place in places_layer.getFeatures():
        best = None
        for shelter in shelters:
            line, route_engine = shortest_path_geometry(roads_layer, place, shelter)
            if line is None:
                line = QgsGeometry.fromPolylineXY([place.geometry().centroid().asPoint(), shelter.geometry().centroid().asPoint()])
                route_engine = "straight_line"
            meters = distance.measureLength(line)
            travel_minutes = meters / 1000 / 25 * 60
            risk_score = max((zone["risk_score"] for zone in risk_zones if intersects(line, zone["_geometry"])), default=0.0)
            bridge_exposure = max((bridge["risk_score"] for bridge in bridges if intersects(line, bridge["_geometry"])), default=0.0)
            candidate = {
                "id": f"route-{field(place, 'id', place.id())}-{field(shelter, 'id', shelter.id())}",
                "origin_id": field(place, "id", f"place-{place.id()}"),
                "shelter_id": field(shelter, "id", f"shelter-{shelter.id()}"),
                "distance_meters": round(meters, 1),
                "travel_minutes": round(travel_minutes, 1),
                "risk_score": round(risk_score, 3),
                "bridge_exposure_score": round(bridge_exposure, 3),
                "crosses_high_risk": risk_score >= 0.65 or bridge_exposure >= 0.65,
                "route_engine": route_engine,
            }
            if best is None or candidate["travel_minutes"] < best["travel_minutes"]:
                best = candidate
        if best:
            routes.append(best)
    return routes


def shortest_path_geometry(roads_layer, place, shelter):
    if roads_layer is None or processing is None:
        return None, ""
    start = place.geometry().centroid().asPoint()
    end = shelter.geometry().centroid().asPoint()
    try:
        result = processing.run(
            "native:shortestpathpointtopoint",
            {
                "INPUT": roads_layer,
                "STRATEGY": 0,
                "DIRECTION_FIELD": "",
                "VALUE_FORWARD": "",
                "VALUE_BACKWARD": "",
                "VALUE_BOTH": "",
                "DEFAULT_DIRECTION": 2,
                "SPEED_FIELD": "",
                "DEFAULT_SPEED": 25,
                "TOLERANCE": 0,
                "START_POINT": f"{start.x()},{start.y()}",
                "END_POINT": f"{end.x()},{end.y()}",
                "OUTPUT": "TEMPORARY_OUTPUT",
            },
            feedback=None,
        )
    except Exception:
        return None, ""
    output = result.get("OUTPUT")
    if output is None:
        return None, ""
    for route in output.getFeatures():
        return route.geometry(), "qgis_shortest_path"
    return None, ""


def build_coverage(places: list[dict[str, Any]], routes: list[dict[str, Any]], shelters: list[dict[str, Any]], limit: float) -> dict[str, Any]:
    covered = {route["origin_id"] for route in routes if route["travel_minutes"] <= limit}
    return {
        "coverage_minutes": limit,
        "covered_place_count": len(covered),
        "uncovered_place_count": max(0, len(places) - len(covered)),
        "coverage_rate": round(len(covered) / max(1, len(places)), 3),
        "total_shelter_capacity": sum(int(shelter.get("capacity", 0)) for shelter in shelters),
    }


def strip_private_geometry(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{key: value for key, value in item.items() if not key.startswith("_")} for item in items]


def field(feature, name: str, default: Any) -> Any:
    return feature[name] if name in feature.fields().names() and feature[name] not in {None, ""} else default


def int_float(value: Any) -> int:
    return int(float(value or 0))


def float_field(feature, name: str, default: float) -> float:
    return float(field(feature, name, default) or default)


def risk_from_level(level: str) -> float:
    return {"low": 0.25, "medium": 0.5, "high": 0.75, "extreme": 0.95, "低": 0.25, "中": 0.5, "高": 0.75, "极高": 0.95}.get(str(level), 0.5)


def intersects(a, b) -> bool:
    return a.intersects(b) or b.intersects(a)


if __name__ == "__main__":
    raise SystemExit(main())
