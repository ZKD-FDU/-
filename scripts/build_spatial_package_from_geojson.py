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
    roads = load_optional_features(layers / f"{args.roads}.geojson")
    rivers = load_optional_features(layers / f"{args.rivers}.geojson")

    place_rows = [place_row(feature, risk_zones) for feature in places]
    shelter_rows = [shelter_row(feature) for feature in shelters]
    risk_rows = [risk_row(feature) for feature in risk_zones]
    bridge_rows = [bridge_row(feature) for feature in bridges]
    river_rows = [river_row(feature) for feature in rivers]
    routes = build_routes(places, shelters, roads, risk_zones, bridges)
    coverage = build_coverage(place_rows, shelter_rows, routes, args.coverage_minutes)
    package = {
        "label": "SYNTHETIC_SPATIAL",
        "package_id": args.package_id,
        "source_project": args.source_project,
        "method": {
            "route_engine": "geojson_polyline_route" if roads else "geojson_straight_line",
            "coverage_minutes": args.coverage_minutes,
            "risk_overlay": "point-in-polygon and route bbox/risk-zone intersection",
            "hydrology": "river and tributary lines are exported as spatial features with upstream-to-downstream coordinates",
        },
        "places": place_rows,
        "shelters": shelter_rows,
        "rivers": river_rows,
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
    parser.add_argument("--roads", default="roads")
    parser.add_argument("--rivers", default="rivers")
    parser.add_argument("--bridge-snap-meters", type=float, default=650)
    parser.add_argument("--coverage-minutes", type=float, default=60)
    parser.add_argument("--timestep-minutes", type=int, default=5)
    parser.add_argument("--vehicles", type=int, default=0)
    parser.add_argument("--care-workers", type=int, default=0)
    parser.add_argument("--stretchers", type=int, default=0)
    return parser.parse_args()


def load_features(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("features", [])


def load_optional_features(path: Path) -> list[dict[str, Any]]:
    return load_features(path) if path.exists() else []


def place_row(feature: dict[str, Any], risks: list[dict[str, Any]]) -> dict[str, Any]:
    props = feature.get("properties", {})
    point = centroid(feature)
    risk_score = max((risk_score_of(risk) for risk in risks if point_in_feature(point, risk)), default=0.0)
    return {
        "id": str(props.get("id")),
        "name": str(props.get("name")),
        "population": int(props.get("population", 100)),
        "vulnerable_population": int(props.get("vulnerable_population", 25)),
        "risk_score": round(risk_score, 3),
        "elevation_m": optional_float(props.get("elevation_m")),
        "river_distance_m": optional_float(props.get("river_distance_m")),
        "hazard_exposure": optional_float(props.get("hazard_exposure")),
        "administrative_level": str(props.get("administrative_level", "")),
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
        "service_radius_minutes": float(props.get("service_radius_minutes", 60)),
        "care_capacity": int(props.get("care_capacity", 0)),
        "backup_power": bool(props.get("backup_power", False)),
        "medical_support": bool(props.get("medical_support", False)),
        "x": round(point[0], 6),
        "y": round(point[1], 6),
    }


def risk_row(feature: dict[str, Any]) -> dict[str, Any]:
    props = feature.get("properties", {})
    return {
        "id": str(props.get("id")),
        "name": str(props.get("name")),
        "hazard_type": str(props.get("hazard_type", "flood")),
        "risk_score": round(risk_score_of(feature), 3),
        "depth_m": optional_float(props.get("depth_m")),
        "velocity_mps": optional_float(props.get("velocity_mps")),
        "geometry": feature.get("geometry", {}),
        "polygon": flatten_points(feature["geometry"]["coordinates"]),
    }


def bridge_row(feature: dict[str, Any]) -> dict[str, Any]:
    props = feature.get("properties", {})
    point = centroid(feature)
    return {
        "id": str(props.get("id")),
        "name": str(props.get("name")),
        "risk_score": float(props.get("risk_score", 0.45)),
        "closure_threshold": float(props.get("closure_threshold", 0.65)),
        "bridge_type": str(props.get("bridge_type", "")),
        "x": round(point[0], 6),
        "y": round(point[1], 6),
    }


def river_row(feature: dict[str, Any]) -> dict[str, Any]:
    props = feature.get("properties", {})
    coordinates = feature["geometry"]["coordinates"]
    return {
        "id": str(props.get("id")),
        "name": str(props.get("name")),
        "kind": str(props.get("kind", "river")),
        "flow_direction": str(props.get("flow_direction", "upstream_to_downstream")),
        "risk_score": float(props.get("risk_score", 0.5)),
        "coordinates": coordinates,
    }


def build_routes(
    places: list[dict[str, Any]],
    shelters: list[dict[str, Any]],
    roads: list[dict[str, Any]],
    risks: list[dict[str, Any]],
    bridges: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = []
    for place in places:
        origin = centroid(place)
        best = None
        origin_roads = [road for road in roads if road.get("properties", {}).get("origin_id") == str(place["properties"]["id"])]
        for shelter in shelters:
            target = centroid(shelter)
            road = matching_road(roads, str(place["properties"]["id"]), str(shelter["properties"]["id"]))
            if origin_roads and road is None:
                continue
            coordinates = road["geometry"]["coordinates"] if road else [list(origin), list(target)]
            meters = polyline_length_meters(coordinates)
            travel_minutes = meters / 1000 / 25 * 60
            route_points = [(float(x), float(y)) for x, y in coordinates]
            line_box = bbox_from_points(route_points)
            exposed_risks = [risk for risk in risks if route_intersects_feature(route_points, risk)]
            dependent_bridges = [bridge for bridge in bridges if distance_point_to_polyline_meters(centroid(bridge), route_points) <= 650]
            risk_score = max((risk_score_of(risk) for risk in exposed_risks), default=0.0)
            bridge_score = max((float(bridge.get("properties", {}).get("risk_score", 0.45)) for bridge in dependent_bridges), default=0.0)
            risk_exposure_minutes = travel_minutes * min(1.0, max(risk_score, bridge_score))
            candidate = {
                "id": f"route-{place['properties']['id']}-{shelter['properties']['id']}",
                "origin_id": place["properties"]["id"],
                "shelter_id": shelter["properties"]["id"],
                "distance_meters": round(meters, 1),
                "route_distance_m": round(meters, 1),
                "travel_minutes": round(travel_minutes, 1),
                "risk_exposure_minutes": round(risk_exposure_minutes, 1),
                "risk_score": round(risk_score, 3),
                "bridge_exposure_score": round(bridge_score, 3),
                "bridge_dependency": [bridge["properties"]["id"] for bridge in dependent_bridges],
                "risk_zone_dependency": [risk["properties"]["id"] for risk in exposed_risks],
                "crosses_high_risk": risk_score >= 0.65 or bridge_score >= 0.65,
                "route_engine": "geojson_polyline_route" if road else "geojson_straight_line",
                "coordinates": coordinates,
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
        "total_care_capacity": sum(int(shelter.get("care_capacity", 0)) for shelter in shelters),
    }


def matching_road(roads: list[dict[str, Any]], origin_id: str, shelter_id: str) -> dict[str, Any] | None:
    for road in roads:
        props = road.get("properties", {})
        if props.get("origin_id") == origin_id and props.get("shelter_id") == shelter_id:
            return road
    return None


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


def point_in_feature(point: tuple[float, float], feature: dict[str, Any]) -> bool:
    geometry = feature.get("geometry", {})
    if geometry.get("type") != "Polygon":
        return point_in_bbox(point, bbox(feature))
    ring = flatten_points(geometry["coordinates"][0])
    return point_in_polygon(point, ring)


def point_in_polygon(point: tuple[float, float], polygon: list[tuple[float, float]]) -> bool:
    x, y = point
    inside = False
    j = len(polygon) - 1
    for i, (xi, yi) in enumerate(polygon):
        xj, yj = polygon[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def route_intersects_feature(route_points: list[tuple[float, float]], feature: dict[str, Any]) -> bool:
    route_box = bbox_from_points(route_points)
    if not bbox_intersects(route_box, bbox(feature)):
        return False
    geometry = feature.get("geometry", {})
    if geometry.get("type") != "Polygon":
        return True
    ring = flatten_points(geometry["coordinates"][0])
    if any(point_in_polygon(point, ring) for point in route_points):
        return True
    for i in range(1, len(route_points)):
        for j in range(1, len(ring)):
            if segments_intersect(route_points[i - 1], route_points[i], ring[j - 1], ring[j]):
                return True
    return False


def segments_intersect(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
    d: tuple[float, float],
) -> bool:
    def orient(p, q, r) -> float:
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    def on_segment(p, q, r) -> bool:
        return min(p[0], r[0]) <= q[0] <= max(p[0], r[0]) and min(p[1], r[1]) <= q[1] <= max(p[1], r[1])

    o1 = orient(a, b, c)
    o2 = orient(a, b, d)
    o3 = orient(c, d, a)
    o4 = orient(c, d, b)
    if o1 * o2 < 0 and o3 * o4 < 0:
        return True
    eps = 1e-12
    return (
        abs(o1) < eps and on_segment(a, c, b)
        or abs(o2) < eps and on_segment(a, d, b)
        or abs(o3) < eps and on_segment(c, a, d)
        or abs(o4) < eps and on_segment(c, b, d)
    )


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


def polyline_length_meters(points: list[list[float]]) -> float:
    return sum(haversine_meters((points[i - 1][0], points[i - 1][1]), (points[i][0], points[i][1])) for i in range(1, len(points)))


def distance_point_to_polyline_meters(point: tuple[float, float], line: list[tuple[float, float]]) -> float:
    if not line:
        return float("inf")
    px, py = lonlat_to_local_meters(point, point)
    best = float("inf")
    for i in range(1, len(line)):
        ax, ay = lonlat_to_local_meters(line[i - 1], point)
        bx, by = lonlat_to_local_meters(line[i], point)
        best = min(best, distance_point_to_segment(px, py, ax, ay, bx, by))
    return best


def lonlat_to_local_meters(coord: tuple[float, float], origin: tuple[float, float]) -> tuple[float, float]:
    lon, lat = coord
    origin_lon, origin_lat = origin
    x = math.radians(lon - origin_lon) * 6371000 * math.cos(math.radians(origin_lat))
    y = math.radians(lat - origin_lat) * 6371000
    return x, y


def distance_point_to_segment(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    dx = bx - ax
    dy = by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def optional_float(value: Any) -> float | None:
    return None if value in {None, ""} else float(value)


if __name__ == "__main__":
    raise SystemExit(main())
