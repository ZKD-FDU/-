import unittest

from hongce.engine import run_policy
from hongce.experiments import run_named_experiments, run_policy_batch, write_explanation_pack
from hongce.models import EvacuationStatus, PolicyId
from hongce.scenario import generate_qingyuan


class SimulationKernelTest(unittest.TestCase):
    def test_scenario_generation_is_reproducible(self) -> None:
        a = generate_qingyuan(seed=11, population=300)
        b = generate_qingyuan(seed=11, population=300)
        self.assertEqual([p.model_dump() for p in a.people[:10]], [p.model_dump() for p in b.people[:10]])
        self.assertGreaterEqual(len({edge.layer for edge in a.network_edges}), 4)

    def test_single_run_produces_simulated_metrics_and_events(self) -> None:
        result = run_policy("S0", seed=12, population=300)
        self.assertEqual(result.metrics.policy_id, PolicyId.S0)
        self.assertGreater(len(result.events), 0)
        self.assertGreaterEqual(result.metrics.safe_before_danger_rate, 0.0)
        self.assertLessEqual(result.metrics.safe_before_danger_rate, 1.0)

    def test_vulnerable_priority_changes_results_against_baseline(self) -> None:
        scenario = generate_qingyuan(seed=13, population=400)
        s0 = run_policy("S0", seed=13, population=400, scenario=scenario)
        s3 = run_policy("S3", seed=13, population=400, scenario=scenario)
        self.assertNotEqual(s0.metrics.safe_before_danger_rate, s3.metrics.safe_before_danger_rate)
        self.assertGreaterEqual(s3.metrics.response_closure_rate, s0.metrics.response_closure_rate)

    def test_bedridden_people_do_not_self_rescue_without_resources(self) -> None:
        result = run_policy("S0", seed=14, population=350)
        bedridden = [p for p in result.people if p.base.mobility == "bedridden"]
        self.assertTrue(bedridden)
        for person in bedridden:
            if person.status == EvacuationStatus.SHELTERED:
                self.assertIsNotNone(person.transit_minute)

    def test_batch_uses_actual_runs(self) -> None:
        result = run_policy_batch(policies=["S0", "S3", "S5"], seeds=[21, 22], population=250, output_dir="outputs/test_experiments")
        self.assertEqual(result["label"], "SIMULATED")
        self.assertEqual(len(result["runs"]), 6)
        self.assertEqual(result["summary"]["S0"]["runs"], 2)

    def test_all_policy_scenarios_run(self) -> None:
        scenario = generate_qingyuan(seed=30, population=250)
        rates = {}
        for policy in ["S0", "S1", "S2", "S3", "S4", "S5"]:
            rates[policy] = run_policy(policy, seed=30, population=250, scenario=scenario).metrics.safe_before_danger_rate
        self.assertEqual(set(rates), {"S0", "S1", "S2", "S3", "S4", "S5"})
        self.assertGreater(max(rates.values()), min(rates.values()))

    def test_named_experiments_and_explanation_are_simulated(self) -> None:
        experiments = run_named_experiments(seeds=[31], population=220, output_dir="outputs/test_named_experiments")
        self.assertEqual(experiments["label"], "SIMULATED")
        self.assertIn("A_money_allocation", experiments["experiments"])
        result = run_policy("S5", seed=31, population=220)
        path = write_explanation_pack(result, "outputs/test_named_experiments")
        self.assertTrue(path.exists())


if __name__ == "__main__":
    unittest.main()
