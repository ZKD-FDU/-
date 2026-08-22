from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from api import service
from hongce.spatial import derive_scenario_overrides, spatial_context


SPATIAL_PACKAGE = {
    "label": "SYNTHETIC_SPATIAL",
    "package_id": "test-qgis-package",
    "places": [
        {"id": "north_valley", "population": 220, "vulnerable_population": 90, "risk_score": 0.82},
        {"id": "qingyuan_town", "population": 530, "vulnerable_population": 110, "risk_score": 0.34},
        {"id": "south_valley", "population": 180, "vulnerable_population": 70, "risk_score": 0.68},
    ],
    "shelters": [
        {"id": "school", "capacity": 620},
        {"id": "gym", "capacity": 180},
    ],
    "coverage": {"coverage_rate": 0.667, "uncovered_place_count": 1},
    "routes": [
        {"origin_id": "north_valley", "shelter_id": "school", "travel_minutes": 72, "crosses_high_risk": True, "bridge_exposure_score": 0.8},
        {
            "origin_id": "qingyuan_town",
            "shelter_id": "school",
            "route_distance_m": 8300,
            "travel_minutes": 28,
            "risk_exposure_minutes": 4.2,
            "crosses_high_risk": False,
            "bridge_exposure_score": 0.2,
        },
        {"origin_id": "south_valley", "shelter_id": "gym", "travel_minutes": 46, "crosses_high_risk": True, "bridge_exposure_score": 0.4},
    ],
    "resources": {"timestep_minutes": 5, "vehicles": 12, "care_workers": 24, "stretchers": 10},
}


class SpatialIntegrationTest(unittest.TestCase):
    def test_spatial_package_derives_simulation_overrides(self) -> None:
        context = spatial_context(SPATIAL_PACKAGE)
        overrides = context["scenario_overrides"]
        self.assertEqual(context["summary"]["total_shelter_capacity"], 800)
        self.assertGreaterEqual(context["summary"]["spatial_quality_score"], 0.7)
        self.assertGreater(context["summary"]["mean_route_distance_m"], 0)
        self.assertEqual(overrides["shelter_beds"], 800)
        self.assertEqual(overrides["vehicles"], 12)
        self.assertGreater(overrides["communication_failure_rate"], 0.3)
        self.assertLess(overrides["warning_minute"], overrides["danger_arrival_minute"])

    def test_api_run_can_use_spatial_package_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "spatial_package.json").write_text(json.dumps(SPATIAL_PACKAGE), encoding="utf-8")
            derived = derive_scenario_overrides(SPATIAL_PACKAGE)
            response = service.run_simulation(
                {
                    "policy_id": "S5",
                    "seed": 20260821,
                    "population": 300,
                    "spatial_package_path": str(root),
                    "output_dir": str(root / "outputs"),
                }
            )
            self.assertEqual(response["status"], "succeeded")
            self.assertEqual(response["scenario_config"]["shelter_beds"], derived["shelter_beds"])
            self.assertEqual(response["spatial_context"]["package_id"], "test-qgis-package")
            self.assertGreaterEqual(response["metrics"]["safe_before_danger_rate"], 0)

    def test_qingyuan_sample_has_plausible_hydrology_topology(self) -> None:
        package = json.loads(Path("data/spatial/qingyuan/spatial_package.json").read_text(encoding="utf-8"))
        rivers = {river["id"]: river for river in package.get("rivers", [])}
        self.assertIn("main_river", rivers)
        self.assertIn("south_tributary", rivers)
        self.assertEqual(rivers["main_river"]["coordinates"][0], [121.305, 31.318])
        self.assertEqual(rivers["main_river"]["coordinates"][-1], [121.468, 31.205])

        bridges = {bridge["id"]: bridge for bridge in package["bridges"]}
        south_culvert = bridges["bridge_south"]
        self.assertEqual(south_culvert["bridge_type"], "tributary_culvert")
        self.assertIn([south_culvert["x"], south_culvert["y"]], rivers["south_tributary"]["coordinates"])

        risks = {place["id"]: place["risk_score"] for place in package["places"]}
        self.assertGreater(risks["nursing_home"], risks["qingyuan_town"])
        self.assertGreaterEqual(len(set(risks.values())), 2)

        routes = {route["origin_id"]: route for route in package["routes"]}
        self.assertIn("bridge_south", routes["south_valley"]["bridge_dependency"])
        self.assertIn("bridge_east", routes["north_valley"]["bridge_dependency"])


if __name__ == "__main__":
    unittest.main()
