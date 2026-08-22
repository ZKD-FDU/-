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
            feature("north_valley", "北谷村", [121.318, 31.318], population=220, vulnerable_population=90, elevation_m=52, river_distance_m=1200, hazard_exposure=0.18, administrative_level="village", evacuation_role="watch_pretransfer", transfer_trigger="vulnerable_pretransfer_or_isolation_risk"),
            feature("qingyuan_town", "清源镇", [121.388, 31.276], population=530, vulnerable_population=110, elevation_m=36, river_distance_m=760, hazard_exposure=0.22, administrative_level="town", evacuation_role="command_support_partial", transfer_trigger="low_lying_blocks_only"),
            feature("south_valley", "南谷村", [121.392, 31.206], population=180, vulnerable_population=70, elevation_m=23, river_distance_m=180, hazard_exposure=0.72, administrative_level="village", evacuation_role="priority_transfer", transfer_trigger="tributary_backwater_or_culvert_overtopping"),
            feature("nursing_home", "青松养老照料中心", [121.352, 31.248], population=69, vulnerable_population=55, elevation_m=18, river_distance_m=90, hazard_exposure=0.88, administrative_level="institution", evacuation_role="mandatory_priority_transfer", transfer_trigger="orange_response_or_water_level_warning"),
        ],
    )
    write_geojson(
        "shelters",
        "Point",
        [
            feature("school_shelter", "第二中学避难点（北岸高地）", [121.458, 31.284], capacity=620, service_radius_minutes=60, care_capacity=80, backup_power=True, medical_support=True),
            feature("gym_shelter", "县体育馆安置点（南部高地）", [121.432, 31.226], capacity=180, service_radius_minutes=45, care_capacity=28, backup_power=True, medical_support=False),
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
                    [121.300, 31.271],
                    [121.335, 31.269],
                    [121.372, 31.267],
                    [121.409, 31.265],
                    [121.444, 31.263],
                    [121.474, 31.259],
                    [121.474, 31.236],
                    [121.438, 31.238],
                    [121.402, 31.240],
                    [121.366, 31.242],
                    [121.331, 31.244],
                    [121.300, 31.248],
                    [121.300, 31.271],
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
                    [121.382, 31.199],
                    [121.398, 31.205],
                    [121.414, 31.216],
                    [121.432, 31.226],
                    [121.437, 31.236],
                    [121.421, 31.232],
                    [121.405, 31.220],
                    [121.389, 31.211],
                    [121.382, 31.199],
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
            line_feature("main_river", "清源河主槽", [[121.300, 31.255], [121.335, 31.256], [121.370, 31.255], [121.405, 31.253], [121.440, 31.251], [121.474, 31.248]], kind="main_channel", flow_direction="W-E", risk_score=0.82),
            line_feature("south_tributary", "南支沟", [[121.386, 31.199], [121.397, 31.207], [121.409, 31.218], [121.421, 31.229], [121.432, 31.226], [121.405, 31.253]], kind="tributary_culvert", flow_direction="S-N", risk_score=0.68),
        ],
    )
    write_geojson(
        "roads",
        "LineString",
        [
            line_feature("road_north_school", "北谷-北岸高地-学校道路", [[121.318, 31.318], [121.360, 31.312], [121.406, 31.298], [121.458, 31.284]], origin_id="north_valley", shelter_id="school_shelter", speed_kmh=24, road_class="upland_county"),
            line_feature("road_town_school", "清源镇-学校台地道路", [[121.388, 31.276], [121.421, 31.282], [121.458, 31.284]], origin_id="qingyuan_town", shelter_id="school_shelter", speed_kmh=28, road_class="urban_terrace"),
            line_feature("road_south_gym", "南谷-南涵洞-体育馆道路", [[121.392, 31.206], [121.409, 31.218], [121.421, 31.223], [121.432, 31.226]], origin_id="south_valley", shelter_id="gym_shelter", speed_kmh=22, road_class="township_culvert"),
            line_feature("road_nursing_school", "养老院-东桥-学校道路", [[121.352, 31.248], [121.382, 31.255], [121.421, 31.274], [121.458, 31.284]], origin_id="nursing_home", shelter_id="school_shelter", speed_kmh=20, road_class="care_transfer"),
        ],
    )
    write_geojson(
        "bridges",
        "Point",
        [
            feature("bridge_east", "东桥", [121.382, 31.255], risk_score=0.80, closure_threshold=0.62, bridge_type="main_river_bridge"),
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
