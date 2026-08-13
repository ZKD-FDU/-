from __future__ import annotations

import unittest

from hongce.adapters import DecisionContext, RuleBasedAgentAdapter, YulanOneSimAdapter
from hongce.models import MVP_POLICY_CONFIGS, PolicyId


class AdapterContractTest(unittest.TestCase):
    def test_rule_adapter_is_offline_and_structured(self) -> None:
        adapter = RuleBasedAgentAdapter()
        decision = adapter.decide(
            DecisionContext(
                actor_id="p1",
                minute=80,
                danger_arrival_minute=180,
                risk_perception=0.8,
                official_trust=0.7,
                cadre_trust=0.8,
                neighbor_trust=0.6,
                neighbor_action_rate=0.5,
                digital_access=0.4,
                transfer_cost=0.2,
                refusal_tendency=0.1,
                false_alarm_memory=0,
                mobility="limited",
                care_dependency="partial",
                has_private_transport=False,
            ),
            MVP_POLICY_CONFIGS[PolicyId.S5],
        )
        self.assertGreaterEqual(decision.evacuate_probability, 0.0)
        self.assertLessEqual(decision.evacuate_probability, 1.0)
        self.assertIn(decision.action, {"confirm_evacuation", "delay_or_refuse"})
        self.assertEqual(decision.adapter, "RuleBasedAgentAdapter")

    def test_yulan_adapter_declares_payload_but_does_not_block_offline_mvp(self) -> None:
        adapter = YulanOneSimAdapter(endpoint="https://www.yulan-onesim.cn")
        context = DecisionContext(
            actor_id="p2",
            minute=45,
            danger_arrival_minute=180,
            risk_perception=0.5,
            official_trust=0.5,
            cadre_trust=0.5,
            neighbor_trust=0.5,
            neighbor_action_rate=0.2,
            digital_access=0.9,
            transfer_cost=0.1,
            refusal_tendency=0.1,
            false_alarm_memory=1,
            mobility="independent",
            care_dependency="none",
            has_private_transport=True,
        )
        payload = adapter.payload_for(context, MVP_POLICY_CONFIGS[PolicyId.S0])
        self.assertEqual(payload["adapter"], "YulanOneSimAdapter")
        with self.assertRaises(RuntimeError):
            adapter.decide(context, MVP_POLICY_CONFIGS[PolicyId.S0])


if __name__ == "__main__":
    unittest.main()
