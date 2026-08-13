from __future__ import annotations

import unittest

from api import service


class ApiServiceTest(unittest.TestCase):
    def test_health_reports_no_external_model_requirement(self) -> None:
        payload = service.health()
        self.assertEqual(payload["status"], "ok")
        self.assertFalse(payload["external_model_required"])

    def test_validate_scenario_bounds(self) -> None:
        self.assertFalse(service.validate_scenario({"population": 20})["valid"])
        self.assertTrue(service.validate_scenario({"population": 120})["valid"])
        self.assertFalse(service.validate_scenario({"population": 6000})["valid"])

    def test_run_simulation_and_fetch_trace(self) -> None:
        response = service.run_simulation(
            {
                "policy_id": "S3",
                "seed": 42,
                "population": 120,
                "output_dir": "outputs/test_api",
            }
        )
        self.assertEqual(response["status"], "succeeded")
        self.assertGreater(response["metrics"]["safe_before_danger_rate"], 0)

        run = service.get_simulation(response["run_id"])
        self.assertEqual(run["run"]["id"], response["run_id"])
        events = service.get_events(response["run_id"])
        self.assertGreater(len(events["events"]), 0)

        agent_id = run["agents"][0]["id"]
        trace = service.get_agent_trace(response["run_id"], agent_id)
        self.assertEqual(trace["agent"]["id"], agent_id)
        self.assertGreaterEqual(len(trace["traces"]), 1)

    def test_experiment_endpoint_uses_simulated_runs(self) -> None:
        response = service.run_experiment(
            {
                "experiment": "s0_s3_s5",
                "seeds": [71, 72],
                "population": 120,
                "output_dir": "outputs/test_api_experiments",
            }
        )
        self.assertEqual(response["status"], "succeeded")
        self.assertEqual(response["comparison"]["label"], "SIMULATED")
        self.assertIn("S0", response["comparison"]["summary"])
        self.assertIn("S3", response["comparison"]["summary"])
        self.assertIn("S5", response["comparison"]["summary"])


if __name__ == "__main__":
    unittest.main()
