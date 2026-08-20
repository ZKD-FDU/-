from __future__ import annotations

import unittest

from api import service


class ApiServiceTest(unittest.TestCase):
    def test_health_reports_no_external_model_requirement(self) -> None:
        payload = service.health()
        self.assertEqual(payload["status"], "ok")
        self.assertFalse(payload["external_model_required"])
        self.assertGreaterEqual(payload["training_case_count"], 28)

    def test_validate_scenario_bounds(self) -> None:
        self.assertFalse(service.validate_scenario({"population": 20})["valid"])
        self.assertTrue(service.validate_scenario({"population": 120})["valid"])
        self.assertFalse(service.validate_scenario({"population": 6000})["valid"])
        self.assertFalse(
            service.validate_scenario(
                {
                    "population": 120,
                    "scenario_overrides": {
                        "warning_minute": 200,
                        "danger_arrival_minute": 100,
                    },
                }
            )["valid"]
        )

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

    def test_case_corpus_search_detail_and_scenario_template(self) -> None:
        cases = service.list_cases({"q": "养老", "limit": 10})
        self.assertGreaterEqual(cases["total"], 1)
        case_id = cases["cases"][0]["case_id"]

        detail = service.get_case(case_id)
        self.assertEqual(detail["case_id"], case_id)
        self.assertIn("process_trace", detail)

        template = service.generate_case_scenario(case_id)
        self.assertEqual(template["case_id"], case_id)
        self.assertEqual(template["label"], "FACT_DERIVED_TEMPLATE")
        self.assertIn("recommended_policies", template)
        self.assertIn("observed_outcomes", template)

    def test_run_simulation_can_attach_real_case_context(self) -> None:
        response = service.run_simulation(
            {
                "policy_id": "S5",
                "seed": 43,
                "population": 120,
                "case_id": "HC-MEM-001",
                "output_dir": "outputs/test_api",
            }
        )
        self.assertEqual(response["status"], "succeeded")
        self.assertEqual(response["case_context"]["case_id"], "HC-MEM-001")
        run = service.get_simulation(response["run_id"])
        self.assertEqual(run["case_context"]["case_name"], "“7·20”河南郑州特大暴雨灾害调查报告")

    def test_scenario_overrides_are_used_by_simulation(self) -> None:
        base = service.run_simulation(
            {
                "policy_id": "S5",
                "seed": 44,
                "population": 140,
                "case_id": "HC-MEM-002",
                "output_dir": "outputs/test_api",
            }
        )
        stressed = service.run_simulation(
            {
                "policy_id": "S5",
                "seed": 44,
                "population": 140,
                "case_id": "HC-MEM-002",
                "scenario_overrides": {
                    "vulnerable_ratio": 0.7,
                    "warning_minute": 80,
                    "evacuation_order_minute": 90,
                    "bridge_closure_minute": 95,
                    "danger_arrival_minute": 120,
                    "communication_failure_minute": 90,
                    "communication_failure_rate": 0.8,
                    "vehicles": 4,
                    "care_workers": 4,
                    "stretchers": 3,
                    "shelter_beds": 80,
                },
                "output_dir": "outputs/test_api",
            }
        )
        self.assertNotEqual(base["run_id"], stressed["run_id"])
        self.assertNotEqual(
            base["metrics"]["safe_before_danger_rate"],
            stressed["metrics"]["safe_before_danger_rate"],
        )
        self.assertEqual(stressed["scenario_config"]["vulnerable_ratio"], 0.7)

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
