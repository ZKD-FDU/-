import unittest
from dataclasses import replace
from hongce.engine import run_policy
from hongce.kernel import draw
from hongce.models import MVP_POLICY_CONFIGS, PolicyId, NetworkEdge
from hongce.scenario import generate_qingyuan

class GovernanceTest(unittest.TestCase):
    def test_messages_follow_edges_with_delay_and_reveal_unregistered_people(self):
        s = generate_qingyuan(seed=42, population=120)
        people = [p.model_copy(update={'location_id': 'south_valley', 'institution_id': None}) for p in s.people[:3]]
        people.sort(key=lambda p: draw(42, p.id, 'registry'))
        source, target, _ = people
        coverage = (draw(42, source.id, 'registry') + draw(42, target.id, 'registry')) / 2
        s.people, s.institutions, s.network_edges = people, [], []
        policy = MVP_POLICY_CONFIGS[PolicyId.S4].model_copy(update={'registry_coverage': coverage})
        empty = run_policy('S4', seed=42, scenario=s, policy_config=policy)
        s.network_edges = [NetworkEdge(id='family-link', source_id=source.id, target_id=target.id,
            layer='family', trust_weight=1, speed_minutes=7, failure_probability=0)]
        linked = run_policy('S4', seed=42, scenario=s, policy_config=policy)
        a = next(p for p in empty.people if p.base.id == target.id)
        b = next(p for p in linked.people if p.base.id == target.id)
        sender = next(p for p in linked.people if p.base.id == source.id)
        self.assertIsNone(a.contact_minute)
        self.assertGreaterEqual(b.contact_minute, sender.contact_minute + 7)
        self.assertTrue(any(e['message']=='unregistered person discovered' for e in linked.events))

    def test_self_authorization_changes_institution_dispatch_window(self):
        s = generate_qingyuan(seed=42, population=220)
        s.hazard = replace(s.hazard, evacuation_order_minute=170)
        policy = MVP_POLICY_CONFIGS[PolicyId.S3]
        early = run_policy('S3', seed=42, scenario=s, policy_config=policy)
        late = run_policy('S3', seed=42, scenario=s,
                          policy_config=policy.model_copy(update={'institution_self_authorization': False}))
        self.assertGreater(early.metrics.safe_count, late.metrics.safe_count)
        self.assertTrue(any(t.actor_id=='worker_nursing_night' and t.action=='prepare_transfer' for t in early.traces))

    def test_cadre_assignments_respect_capacity_and_time(self):
        result = run_policy('S4', seed=42, population=400)
        availability = {}
        assignments = [e for e in result.events if e['message']=='confirmation workers assigned']
        self.assertTrue(assignments)
        for e in assignments:
            p = e['payload']
            self.assertLessEqual(p['workers'], 2)
            self.assertGreaterEqual(e['minute'], availability.get(p['actor'], 0))
            availability[p['actor']] = p['available_minute']

    def test_failed_edges_do_not_deliver(self):
        s = generate_qingyuan(seed=42, population=220)
        s.network_edges = [e.model_copy(update={'failure_probability': 1.0}) for e in s.network_edges]
        result = run_policy('S4', seed=42, scenario=s)
        self.assertFalse(any(r.acknowledged for r in result.receipts))

    def test_requested_population_is_exact(self):
        for n in [100, 120, 160, 500]:
            self.assertEqual(len(generate_qingyuan(population=n).people), n)
