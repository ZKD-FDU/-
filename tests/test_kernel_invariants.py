import unittest
from dataclasses import replace
from hongce.engine import run_policy, requires_transfer, MutablePerson, ResourceState, compute_metrics, update_exposure
from hongce.models import MVP_POLICY_CONFIGS, PolicyId, EvacuationStatus as Status
from hongce.scenario import generate_qingyuan


class KernelInvariantsTest(unittest.TestCase):
    def test_input_is_immutable_and_runs_are_order_independent(self):
        s = generate_qingyuan(seed=42, population=220)
        before = [p.model_dump() for p in s.people]
        a = run_policy('S5', seed=42, scenario=s)
        run_policy('S4', seed=42, scenario=s)
        b = run_policy('S5', seed=42, scenario=s)
        self.assertEqual(before, [p.model_dump() for p in s.people])
        self.assertEqual(a.metrics, b.metrics)
        self.assertEqual(a.events, b.events)

    def test_off_grid_events_and_order_are_effective(self):
        s = generate_qingyuan(seed=42, population=220)
        s.hazard = replace(s.hazard, bridge_closure_minute=121, communication_failure_minute=91)
        early = run_policy('S0', seed=42, scenario=s)
        self.assertIn(121, [e['minute'] for e in early.events if e['message'] == 'bridge_east closed'])
        self.assertIn(91, [e['minute'] for e in early.events if e['message'] == 'communications degraded'])
        s.hazard = replace(s.hazard, evacuation_order_minute=175)
        late = run_policy('S0', seed=42, scenario=s)
        self.assertTrue(all(p.transit_minute >= 175 for p in late.people if p.transit_minute is not None))
        self.assertGreater(early.metrics.safe_count, late.metrics.safe_count)

    def test_zero_resources_and_capacity_conservation(self):
        s = generate_qingyuan(seed=42, population=220)
        for policy in ['S0', 'S5']:
            result = run_policy(policy, seed=42, scenario=s)
            audit = result.resource_audit
            for peak, total in [('peak_vehicles', 'vehicles'), ('peak_care_workers', 'care_workers'), ('peak_stretchers', 'stretchers')]:
                self.assertLessEqual(audit[peak], audit[total])
        s.resources = replace(s.resources, vehicles=0, care_workers=0, stretchers=0)
        result = run_policy('S5', seed=42, scenario=s)
        self.assertFalse(any(p.transit_minute is not None for p in result.people))

    def test_arrivals_happen_after_departure_and_resources_return(self):
        result = run_policy('S5', seed=42, population=220)
        self.assertTrue(any(p.sheltered_minute is not None for p in result.people))
        for p in result.people:
            if p.sheltered_minute is not None:
                self.assertGreater(p.sheltered_minute, p.transit_minute)
                arrival = next(e for e in result.events if e['message']=='person sheltered' and e['payload']['person']==p.base.id)
                self.assertEqual(arrival['minute'], p.sheltered_minute)
        by_vehicle = {}
        for e in result.events:
            if e['message'] == 'vehicle departed':
                by_vehicle.setdefault(e['payload']['vehicle'], set()).add((e['minute'], e['payload']['arrival_minute']))
        for trips in by_vehicle.values():
            trips = sorted(trips)
            for (depart, arrive), (next_depart, _) in zip(trips, trips[1:]):
                self.assertGreaterEqual(next_depart, arrive + (arrive-depart) + 5)

    def test_group_denominators_only_include_targets(self):
        s = generate_qingyuan(seed=42, population=400)
        people = [MutablePerson(p) for p in s.people]
        for p in people:
            if requires_transfer(p):
                p.status, p.sheltered_minute = Status.SHELTERED, 100
        policy = MVP_POLICY_CONFIGS[PolicyId.S0]
        m = compute_metrics('test', policy, 42, people, 180, ResourceState.from_policy(s, policy))
        self.assertEqual(m.safe_before_danger_rate, 1)
        self.assertEqual(m.vulnerable_safe_before_danger_rate, 1)
        self.assertEqual(m.general_safe_before_danger_rate, 1)
        self.assertEqual(m.group_safety_gap, 0)
        self.assertIsNone(m.trust_delta)

    def test_exposure_stops_at_arrival_and_ignores_non_targets(self):
        s = generate_qingyuan(seed=42, population=220)
        target = MutablePerson(next(p for p in s.people if requires_transfer(p)))
        safe = MutablePerson(next(p for p in s.people if not requires_transfer(p)))
        update_exposure([target, safe], 10)
        self.assertGreater(target.harm_risk, 0)
        self.assertEqual(safe.harm_risk, 0)
        before = target.harm_risk
        target.status = Status.SHELTERED
        update_exposure([target], 10)
        self.assertEqual(before, target.harm_risk)

    def test_fingerprint_includes_individual_state(self):
        s = generate_qingyuan(seed=42, population=220)
        a = run_policy('S0', seed=42, scenario=s)
        s.people[0].official_trust = 0
        b = run_policy('S0', seed=42, scenario=s)
        self.assertNotEqual(a.run.id, b.run.id)


if __name__ == '__main__':
    unittest.main()
