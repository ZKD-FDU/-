"""Create a minimal QGIS project for HongCe spatial integration demos.

Run with QGIS Python:

    /Applications/QGIS-final-4_2_0.app/Contents/MacOS/python scripts/qgis_create_sample_project.py
"""

from __future__ import annotations

import json
from pathlib import Path

from qgis.core import QgsApplication, QgsProject, QgsVectorLayer


ROOT = Path(__file__).resolve().parents[1]
QGIS_DIR = ROOT / "data" / "qgis"
LAYERS_DIR = QGIS_DIR / "layers"
PROJECT_PATH = QGIS_DIR / "hongce.qgs"
CRS = "EPSG:4326"


def main() -> int:
    app = QgsApplication.instance()
    created_app = False
    if app is None:
        app = QgsApplication([], False)
        app.initQgis()
        created_app = True

    write_layers()
    project = QgsProject.instance()
    project.clear()
    project.setCrs(QgsVectorLayer(str(LAYERS_DIR / "villages.geojson"), "villages", "ogr").crs())
    for name in ["villages", "shelters", "risk_zones", "rivers", "roads", "bridges"]:
        layer = QgsVectorLayer(str(LAYERS_DIR / f"{name}.geojson"), name, "ogr")
        if not layer.isValid():
            raise SystemExit(f"invalid layer: {name}")
        project.addMapLayer(layer)
    QGIS_DIR.mkdir(parents=True, exist_ok=True)
    if not project.write(str(PROJECT_PATH)):
        raise SystemExit(f"failed to write {PROJECT_PATH}")
    print(PROJECT_PATH)

    if created_app:
        app.exitQgis()
    return 0


def write_layers() -> None:
    LAYERS_DIR.mkdir(parents=True, exist_ok=True)
    write_geojson(
        "villages",
        "Point",
        [
            feature("north_valley", "北谷村", [121.316, 31.318], population=220, vulnerable_population=90, elevation_m=48, river_distance_m=920, hazard_exposure=0.32, administrative_level="village"),
            feature("qingyuan_town", "清源镇", [121.388, 31.276], population=530, vulnerable_population=110, elevation_m=30, river_distance_m=620, hazard_exposure=0.46, administrative_level="town"),
            feature("south_valley", "南谷村", [121.392, 31.206], population=180, vulnerable_population=70, elevation_m=36, river_distance_m=520, hazard_exposure=0.52, administrative_level="village"),
            feature("nursing_home", "青松养老照料中心", [121.350, 31.292], population=69, vulnerable_population=55, elevation_m=24, river_distance_m=280, hazard_exposure=0.74, administrative_level="institution"),
        ],
    )
    write_geojson(
        "shelters",
        "Point",
        [
            feature("school_shelter", "第二中学避难点", [121.456, 31.266], capacity=620, service_radius_minutes=60, care_capacity=80, backup_power=True, medical_support=True),
            feature("gym_shelter", "县体育馆避难点", [121.432, 31.236], capacity=180, service_radius_minutes=45, care_capacity=28, backup_power=True, medical_support=False),
        ],
    )
    write_geojson(
        "risk_zones",
        "Polygon",
        [
            polygon_feature(
                "floodplain_01",
                "主河道漫溢区",
                [
                    [121.300, 31.326],
                    [121.329, 31.306],
                    [121.358, 31.291],
                    [121.390, 31.274],
                    [121.420, 31.250],
                    [121.472, 31.211],
                    [121.464, 31.199],
                    [121.433, 31.219],
                    [121.402, 31.241],
                    [121.377, 31.260],
                    [121.346, 31.275],
                    [121.318, 31.295],
                    [121.298, 31.313],
                    [121.300, 31.326],
                ],
                risk_score=0.82,
                level="高",
                hazard_type="river_floodplain",
                depth_m=1.4,
                velocity_mps=1.1,
            ),
            polygon_feature(
                "tributary_ponding_01",
                "南支沟倒灌积水区",
                [
                    [121.384, 31.202],
                    [121.403, 31.213],
                    [121.421, 31.229],
                    [121.433, 31.236],
                    [121.426, 31.244],
                    [121.408, 31.229],
                    [121.393, 31.215],
                    [121.379, 31.207],
                    [121.384, 31.202],
                ],
                risk_score=0.68,
                level="中",
                hazard_type="tributary_backwater",
                depth_m=0.8,
                velocity_mps=0.55,
            )
        ],
    )
    write_geojson(
        "rivers",
        "LineString",
        [
            line_feature("main_river", "清源河主槽", [[121.305, 31.318], [121.330, 31.300], [121.356, 31.285], [121.383, 31.268], [121.410, 31.245], [121.438, 31.222], [121.468, 31.205]], kind="main_channel", flow_direction="NW-SE", risk_score=0.82),
            line_feature("south_tributary", "南支沟", [[121.385, 31.201], [121.397, 31.209], [121.409, 31.218], [121.421, 31.229], [121.432, 31.236], [121.410, 31.245]], kind="tributary_culvert", flow_direction="S-N", risk_score=0.68),
        ],
    )
    write_geojson(
        "roads",
        "LineString",
        [
            line_feature("road_north_school", "北谷-东桥-学校道路", [[121.316, 31.318], [121.338, 31.302], [121.348, 31.294], [121.382, 31.269], [121.421, 31.264], [121.456, 31.266]], origin_id="north_valley", shelter_id="school_shelter", speed_kmh=24, road_class="county"),
            line_feature("road_town_school", "清源镇-学校台地道路", [[121.388, 31.276], [121.421, 31.272], [121.456, 31.266]], origin_id="qingyuan_town", shelter_id="school_shelter", speed_kmh=28, road_class="urban"),
            line_feature("road_south_gym", "南谷-南涵洞-体育馆道路", [[121.392, 31.206], [121.409, 31.218], [121.421, 31.228], [121.432, 31.236]], origin_id="south_valley", shelter_id="gym_shelter", speed_kmh=22, road_class="township"),
            line_feature("road_nursing_school", "养老院-东桥-学校道路", [[121.350, 31.292], [121.382, 31.269], [121.421, 31.264], [121.456, 31.266]], origin_id="nursing_home", shelter_id="school_shelter", speed_kmh=20, road_class="care_transfer"),
        ],
    )
    write_geojson(
        "bridges",
        "Point",
        [
            feature("bridge_east", "东桥", [121.382, 31.269], risk_score=0.80, closure_threshold=0.62, bridge_type="main_river_bridge"),
            feature("bridge_south", "南涵洞", [121.409, 31.218], risk_score=0.68, closure_threshold=0.58, bridge_type="tributary_culvert"),
        ],
    )


def write_geojson(name: str, geometry_type: str, features: list[dict]) -> None:
    payload = {
        "type": "FeatureCollection",
        "name": name,
        "crs": {"type": "name", "properties": {"name": f"urn:ogc:def:crs:{CRS.replace(':', '::')}"}},
        "features": features,
    }
    (LAYERS_DIR / f"{name}.geojson").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def feature(identifier: str, name: str, coordinates: list[float], **properties) -> dict:
    return {
        "type": "Feature",
        "properties": {"id": identifier, "name": name, **properties},
        "geometry": {"type": "Point", "coordinates": coordinates},
    }


def polygon_feature(identifier: str, name: str, coordinates: list[list[float]], **properties) -> dict:
    return {
        "type": "Feature",
        "properties": {"id": identifier, "name": name, **properties},
        "geometry": {"type": "Polygon", "coordinates": [coordinates]},
    }


def line_feature(identifier: str, name: str, coordinates: list[list[float]], **properties) -> dict:
    return {
        "type": "Feature",
        "properties": {"id": identifier, "name": name, **properties},
        "geometry": {"type": "LineString", "coordinates": coordinates},
    }


if __name__ == "__main__":
    raise SystemExit(main())
