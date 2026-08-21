from __future__ import annotations

import unittest

from api import service
from hongce.decision import (
    contextual_bandit_recommendation,
    default_mdp_definition,
    optimize_policy_parameters,
)


class DecisionOptimizationTest(unittest.TestCase):
    def test_mdp_contract_declares_pomdp_state_actions_rewards_and_constraints(self) -> None:
        mdp = default_mdp_definition().to_dict()
        self.assertEqual(mdp["label"], "MDP_CONTRACT")
        self.assertEqual(mdp["observation_model"], "POMDP")
        self.assertIn("communication_failure_rate", mdp["state_variables"])
        self.assertIn("dispatch_vehicle_to_place", mdp["action_variables"])
        self.assertIn("safe_before_danger_rate", mdp["reward_terms"])
        self.assertIn("max_vulnerable_harm_risk", mdp["constraints"])
        self.assertIn("hongce.engine.run_policy", mdp["transition_source"])

    def test_policy_parameter_optimization_uses_actual_simulation_runs(self) -> None:
        result = optimize_policy_parameters(
            seeds=[202608060, 202608061],
            population=180,
            max_candidates=4,
            scenario_overrides={"danger_arrival_minute": 150, "vehicles": 12, "shelter_beds": 260},
        )
        self.assertEqual(result["label"], "SIMULATED_POLICY_OPTIMIZATION")
        self.assertEqual(len(result["candidates"]), 4)
        self.assertEqual(result["best"]["runs"], 2)
        self.assertIn("safe_before_danger_rate", result["best"]["metrics_mean"])
        self.assertIn("All candidate scores come from actual HongCe simulation runs", result["note"])

    def test_contextual_bandit_returns_interpretable_recommendation(self) -> None:
        result = contextual_bandit_recommendation(
            context={"scenario_overrides": {"vehicles": 10, "communication_failure_rate": 0.45}},
            seeds=[202608060],
            population=160,
        )
        self.assertEqual(result["label"], "CONTEXTUAL_BANDIT_POLICY_RECOMMENDATION")
        self.assertGreaterEqual(len(result["arms"]), 5)
        self.assertIn("action", result["recommended"])
        self.assertIn("metrics_mean", result["recommended"])

    def test_decision_api_endpoints_return_structured_results(self) -> None:
        mdp = service.get_decision_mdp()
        self.assertEqual(mdp["label"], "MDP_CONTRACT")
        optimized = service.run_policy_optimization(
            {
                "seeds": [202608060],
                "population": 160,
                "max_candidates": 2,
                "scenario_overrides": {"vehicles": 10},
            }
        )
        self.assertEqual(optimized["label"], "SIMULATED_POLICY_OPTIMIZATION")
        self.assertEqual(len(optimized["candidates"]), 2)


if __name__ == "__main__":
    unittest.main()
