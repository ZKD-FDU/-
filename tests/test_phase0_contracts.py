import unittest

from pydantic import ValidationError

from hongce.models import (
    DataLabel,
    EvacuationStatus,
    MVP_POLICY_CONFIGS,
    PersonAgent,
    PolicyId,
    TransitionError,
    can_transition,
    require_transition,
)


class Phase0ContractsTest(unittest.TestCase):
    def test_evacuation_state_machine_happy_path(self) -> None:
        path = [
            EvacuationStatus.UNCONTACTED,
            EvacuationStatus.CONTACTED,
            EvacuationStatus.CONFIRMED,
            EvacuationStatus.WAITING_TRANSFER,
            EvacuationStatus.IN_TRANSIT,
            EvacuationStatus.SHELTERED,
        ]
        for source, target in zip(path, path[1:]):
            self.assertTrue(can_transition(source, target))
            require_transition(source, target)

    def test_evacuation_state_machine_rejects_skipped_confirmation(self) -> None:
        with self.assertRaises(TransitionError):
            require_transition(EvacuationStatus.CONTACTED, EvacuationStatus.IN_TRANSIT)

    def test_message_contact_and_action_are_separate_states(self) -> None:
        self.assertFalse(can_transition(EvacuationStatus.CONTACTED, EvacuationStatus.SHELTERED))
        self.assertFalse(can_transition(EvacuationStatus.UNCONTACTED, EvacuationStatus.WAITING_TRANSFER))

    def test_vulnerable_person_is_flagged_by_mobility_and_digital_access(self) -> None:
        person = PersonAgent(
            id="p1",
            age=42,
            sex="female",
            location_id="qingyuan_nursing_home",
            mobility="bedridden",
            care_dependency="full",
            digital_access=0.1,
            official_trust=0.6,
            cadre_trust=0.7,
            neighbor_trust=0.5,
        )
        self.assertEqual(person.label, DataLabel.SYNTHETIC)
        self.assertTrue(person.is_vulnerable)

    def test_person_bounds_are_enforced(self) -> None:
        with self.assertRaises(ValidationError):
            PersonAgent(
                id="p2",
                age=200,
                location_id="x",
                mobility="independent",
                digital_access=1.5,
                official_trust=0.5,
                cadre_trust=0.5,
                neighbor_trust=0.5,
            )

    def test_policy_set_contains_full_scenarios_while_mvp_focuses_s0_s3_s5(self) -> None:
        self.assertTrue({PolicyId.S0, PolicyId.S3, PolicyId.S5}.issubset(set(MVP_POLICY_CONFIGS)))
        self.assertFalse(MVP_POLICY_CONFIGS[PolicyId.S0].confirmation_required)
        self.assertTrue(MVP_POLICY_CONFIGS[PolicyId.S3].confirmation_required)
        self.assertIn("bridge_reinforcement", MVP_POLICY_CONFIGS[PolicyId.S5].pre_disaster_maintenance)

    def test_policy_hash_is_stable(self) -> None:
        first = MVP_POLICY_CONFIGS[PolicyId.S5].config_hash
        second = MVP_POLICY_CONFIGS[PolicyId.S5].config_hash
        self.assertEqual(first, second)
        self.assertEqual(len(first), 16)


if __name__ == "__main__":
    unittest.main()
