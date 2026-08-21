"""Build a HongCe spatial package directly from GeoJSON layers.

This is the robust fallback when macOS QGIS GUI/PyQGIS cannot run headlessly.
It consumes the same layer names used by the QGIS project.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


def main() -> int:
    args = parse_args()
    layers = Path(args.layers_dir)
    places = load_features(layers / f"{args.places}.geojson")
    shelters = load_features(layers / f"{args.shelters}.geojson")
    risk_zones = load_features(layers / f"{args.risk_zones}.geojson")
    bridges = load_features(layers / f"{args.bridges}.geojson")

    place_rows = [place_row(feature, risk_zones) for feature in places]
    shelter_rows = [shelter_row(feature) for feature in shelters]
    risk_rows = [risk_row(feature) for feature in risk_zones]
    bridge_rows = [bridge_row(feature) for feature in bridges]
    routes = build_routes(places, shelters, risk_zones, bridges)
    coverage = build_coverage(place_rows, shelter_rows, routes, args.coverage_minutes)
    package = {
        "label": "SYNTHETIC_SPATIAL",
        "package_id": args.package_id,
        "source_project": args.source_project,
        "method": {
            "route_engine": "geojson_straight_line",
            "coverage_minutes": args.coverage_minutes,
            "risk_overlay": "centroid/line bbox intersects risk zone bbox",
        },
        "places": place_rows,
        "shelters": shelter_rows,
        "risk_zones": risk_rows,
        "bridges": bridge_rows,
        "routes": routes,
        "coverage": coverage,
        "resources": {
            "timestep_minutes": args.timestep_minutes,
            "vehicles": args.vehicles,
            "care_workers": args.care_workers,
            "stretchers": args.stretchers,
        },
    }
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "spatial_package.json"
    path.write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")
    print(path)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build HongCe spatial package from GeoJSON layers.")
    parser.add_argument("--layers-dir", default="data/qgis/layers")
    parser.add_argument("--out", default="data/spatial/qingyuan")
    parser.add_argument("--package-id", default="qgis-qingyuan")
    parser.add_argument("--source-project", default="data/qgis/hongce.qgz")
    parser.add_argument("--places", default="villages")
    parser.add_argument("--shelters", default="shelters")
    parser.add_argument("--risk-zones", default="risk_zones")
    parser.add_argument("--bridges", default="bridges")
    parser.add_argument("--coverage-minutes", type=float, default=60)
    parser.add_argument("--timestep-minutes", type=int, default=5)
    parser.add_argument("--vehicles", type=int, default=0)
    parser.add_argument("--care-workers", type=int, default=0)
    parser.add_argument("--stretchers", type=int, default=0)
    return parser.parse_args()


def load_features(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("features", [])


def place_row(feature: dict[str, Any], risks: list[dict[str, Any]]) -> dict[str, Any]:
    props = feature.get("properties", {})
    point = centroid(feature)
    risk_score = max((risk_score_of(risk) for risk in risks if point_in_bbox(point, bbox(risk))), default=0.0)
    return {
        "id": str(props.get("id")),
        "name": str(props.get("name")),
        "population": int(props.get("population", 100)),
        "vulnerable_population": int(props.get("vulnerable_population", 25)),
        "risk_score": round(risk_score, 3),
        "x": round(point[0], 6),
        "y": round(point[1], 6),
    }


def shelter_row(feature: dict[str, Any]) -> dict[str, Any]:
    props = feature.get("properties", {})
    point = centroid(feature)
    return {
        "id": str(props.get("id")),
        "name": str(props.get("name")),
        "capacity": int(props.get("capacity", 300)),
        "x": round(point[0], 6),
        "y": round(point[1], 6),
    }


def risk_row(feature: dict[str, Any]) -> dict[str, Any]:
    props = feature.get("properties", {})
    return {"id": str(props.get("id")), "name": str(props.get("name")), "risk_score": round(risk_score_of(feature), 3)}


def bridge_row(feature: dict[str, Any]) -> dict[str, Any]:
    props = feature.get("properties", {})
    point = centroid(feature)
    return {
        "id": str(props.get("id")),
        "name": str(props.get("name")),
        "risk_score": float(props.get("risk_score", 0.45)),
        "x": round(point[0], 6),
        "y": round(point[1], 6),
    }


def build_routes(places: list[dict[str, Any]], shelters: list[dict[str, Any]], risks: list[dict[str, Any]], bridges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for place in places:
        origin = centroid(place)
        best = None
        for shelter in shelters:
            target = centroid(shelter)
            meters = haversine_meters(origin, target)
            travel_minutes = meters / 1000 / 25 * 60
            line_box = bbox_from_points([origin, target])
            risk_score = max((risk_score_of(risk) for risk in risks if bbox_intersects(line_box, bbox(risk))), default=0.0)
            bridge_score = max((float(bridge.get("properties", {}).get("risk_score", 0.45)) for bridge in bridges if point_in_bbox(centroid(bridge), line_box)), default=0.0)
            candidate = {
                "id": f"route-{place['properties']['id']}-{shelter['properties']['id']}",
                "origin_id": place["properties"]["id"],
                "shelter_id": shelter["properties"]["id"],
                "distance_meters": round(meters, 1),
                "travel_minutes": round(travel_minutes, 1),
                "risk_score": round(risk_score, 3),
                "bridge_exposure_score": round(bridge_score, 3),
                "crosses_high_risk": risk_score >= 0.65 or bridge_score >= 0.65,
                "route_engine": "geojson_straight_line",
            }
            if best is None or candidate["travel_minutes"] < best["travel_minutes"]:
                best = candidate
        if best:
            rows.append(best)
    return rows


def build_coverage(places: list[dict[str, Any]], shelters: list[dict[str, Any]], routes: list[dict[str, Any]], limit: float) -> dict[str, Any]:
    covered = {route["origin_id"] for route in routes if route["travel_minutes"] <= limit}
    return {
        "coverage_minutes": limit,
        "covered_place_count": len(covered),
        "uncovered_place_count": max(0, len(places) - len(covered)),
        "coverage_rate": round(len(covered) / max(1, len(places)), 3),
        "total_shelter_capacity": sum(int(shelter["capacity"]) for shelter in shelters),
    }


def centroid(feature: dict[str, Any]) -> tuple[float, float]:
    geom = feature["geometry"]
    coords = geom["coordinates"]
    if geom["type"] == "Point":
        return float(coords[0]), float(coords[1])
    points = flatten_points(coords)
    return sum(x for x, _ in points) / len(points), sum(y for _, y in points) / len(points)


def flatten_points(coords) -> list[tuple[float, float]]:
    if isinstance(coords[0], (int, float)):
        return [(float(coords[0]), float(coords[1]))]
    points = []
    for item in coords:
        points.extend(flatten_points(item))
    return points


def bbox(feature: dict[str, Any]) -> tuple[float, float, float, float]:
    return bbox_from_points(flatten_points(feature["geometry"]["coordinates"]))


def bbox_from_points(points: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return min(xs), min(ys), max(xs), max(ys)


def bbox_intersects(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    return a[0] <= b[2] and a[2] >= b[0] and a[1] <= b[3] and a[3] >= b[1]


def point_in_bbox(point: tuple[float, float], box: tuple[float, float, float, float]) -> bool:
    return box[0] <= point[0] <= box[2] and box[1] <= point[1] <= box[3]


def risk_score_of(feature: dict[str, Any]) -> float:
    props = feature.get("properties", {})
    if props.get("risk_score") not in {None, ""}:
        return max(0.0, min(1.0, float(props["risk_score"])))
    return {"低": 0.25, "中": 0.5, "高": 0.75, "极高": 0.95, "low": 0.25, "medium": 0.5, "high": 0.75, "extreme": 0.95}.get(str(props.get("level")), 0.5)


def haversine_meters(a: tuple[float, float], b: tuple[float, float]) -> float:
    lon1, lat1 = map(math.radians, a)
    lon2, lat2 = map(math.radians, b)
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371000 * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


if __name__ == "__main__":
    raise SystemExit(main())
