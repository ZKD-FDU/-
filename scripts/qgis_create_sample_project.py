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
    for name in ["villages", "shelters", "risk_zones", "roads", "bridges"]:
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
            feature("north_valley", "北谷村", [121.318, 31.305], population=220, vulnerable_population=90),
            feature("qingyuan_town", "清源镇", [121.392, 31.258], population=530, vulnerable_population=110),
            feature("south_valley", "南谷村", [121.428, 31.205], population=180, vulnerable_population=70),
            feature("nursing_home", "青松养老照料中心", [121.346, 31.282], population=69, vulnerable_population=55),
        ],
    )
    write_geojson(
        "shelters",
        "Point",
        [
            feature("school_shelter", "第二中学避难点", [121.46, 31.248], capacity=620),
            feature("gym_shelter", "县体育馆避难点", [121.405, 31.225], capacity=180),
        ],
    )
    write_geojson(
        "risk_zones",
        "Polygon",
        [
            polygon_feature(
                "floodplain_01",
                "河湾漫溢区",
                [
                    [121.30, 31.32],
                    [121.47, 31.29],
                    [121.45, 31.22],
                    [121.33, 31.20],
                    [121.30, 31.32],
                ],
                risk_score=0.82,
                level="高",
            )
        ],
    )
    write_geojson(
        "roads",
        "LineString",
        [
            line_feature("road_north_school", "北谷-学校道路", [[121.318, 31.305], [121.36, 31.29], [121.46, 31.248]]),
            line_feature("road_town_school", "清源镇-学校道路", [[121.392, 31.258], [121.46, 31.248]]),
            line_feature("road_south_gym", "南谷-体育馆道路", [[121.428, 31.205], [121.405, 31.225]]),
            line_feature("road_nursing_school", "养老院-学校道路", [[121.346, 31.282], [121.37, 31.27], [121.46, 31.248]]),
        ],
    )
    write_geojson(
        "bridges",
        "Point",
        [
            feature("bridge_east", "东桥", [121.372, 31.272], risk_score=0.80),
            feature("bridge_south", "南涵洞", [121.416, 31.214], risk_score=0.45),
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
