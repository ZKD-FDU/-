import unittest
from dataclasses import replace
from hongce.configuration import normalize_scenario_config, build_scenario, validate_scenario_config
from hongce.kernel import MutablePerson, ResourceState, run_policy
from hongce.models import MVP_POLICY_CONFIGS, PolicyId
from hongce.transport import TransportNetwork, depth_at, route_window


class TransportTest(unittest.TestCase):
    def setup_network(self, capacity=100, slots=20):
        cfg=normalize_scenario_config({'loading_minutes':5})
        s=build_scenario(42,220,cfg)
        s.resources=replace(s.resources,vehicles=2,vehicle_capacity=4,care_workers=20,stretchers=20,shelter_beds=100)
        s.transport={'loading_minutes':5,'unloading_minutes':5,'aging_minutes':30,
            'shelters':[{'id':'a','capacity':capacity,'medical_slots':slots},{'id':'b','capacity':100,'medical_slots':20}],
            'routes':[{'id':'fast','origin_id':'nursing_home','shelter_id':'a','travel_minutes':10,'max_concurrent_vehicles':1},
                      {'id':'detour','origin_id':'nursing_home','shelter_id':'b','travel_minutes':20,'max_concurrent_vehicles':1}]}
        people=[MutablePerson(p,waiting_minute=0,confirmed_minute=0) for p in s.people if p.location_id=='nursing_home'][:8]
        policy=MVP_POLICY_CONFIGS[PolicyId.S0]
        return s,people,policy,ResourceState.from_policy(s,policy),TransportNetwork(s)

    def test_depth_interpolation_and_future_closure(self):
        r={'travel_minutes':10,'depth_profile':[[0,0],[100,.4]],'max_depth_m':.3}
        self.assertAlmostEqual(depth_at(r,50),.2)
        self.assertGreater(route_window(r,10,200)[0],10)
        self.assertIsNone(route_window(r,70,200)[0])
        self.assertIsNone(route_window({'travel_minutes':10,'closed_minute':15},10,200)[0])

    def test_congestion_routes_second_vehicle_to_detour(self):
        s,people,p,r,n=self.setup_network()
        n.dispatch(people,p,0,r,120,[],s)
        self.assertEqual({t['route_id'] for t in n.trip_log},{'fast','detour'})
        self.assertEqual(sum(len(t['passengers']) for t in n.trip_log),8)
        self.assertTrue(all(t['departure_minute']==5 for t in n.trip_log))
        self.assertTrue(all(t['release_minute']>t['arrival_minute'] for t in n.trip_log))

    def test_full_shelter_and_medical_slots_choose_alternative(self):
        for beds,slots in [(0,20),(100,0)]:
            s,people,p,r,n=self.setup_network(beds,slots)
            people=[x for x in people if x.base.care_dependency=='full']
            self.assertTrue(people)
            n.dispatch(people,p,0,r,120,[],s)
            self.assertTrue(all(t['shelter_id']=='b' for t in n.trip_log))
            self.assertEqual(n.shelters['a']['reserved'],0)

    def test_closed_route_changes_destination(self):
        s,people,p,r,n=self.setup_network()
        n.routes[0]['closed_minute']=5
        n.dispatch(people,p,0,r,120,[],s)
        self.assertTrue(n.trip_log)
        self.assertTrue(all(t['route_id']=='detour' for t in n.trip_log))

    def test_blocked_return_does_not_release_resources(self):
        s,people,p,r,n=self.setup_network()
        n.routes=n.routes[:1]
        n.routes[0]['closed_minute']=20
        n.dispatch(people,p,0,r,120,[],s)
        self.assertIsNone(n.trip_log[0]['release_minute'])
        self.assertEqual(n.blocked_returns,1)
        r.advance(100,[])
        self.assertEqual(len(r.trips),1)

    def test_config_rejects_bad_curves(self):
        c=normalize_scenario_config({'routes':[{'id':'bad','origin_id':'x','travel_minutes':10,'depth_profile':[[10,0],[5,1]]}]})
        self.assertIsNotNone(validate_scenario_config(c))

    def test_network_reproducibility_and_all_capacities(self):
        s=build_scenario(42,500,normalize_scenario_config({}))
        a=run_policy('S5',seed=42,scenario=s)
        b=run_policy('S5',seed=42,scenario=s)
        self.assertEqual(a.metrics,b.metrics)
        self.assertEqual(a.transport,b.transport)
        self.assertTrue(a.transport['trips'])
        self.assertEqual(sum(len(t['passengers']) for t in a.transport['trips']),sum(x.transit_minute is not None for x in a.people))
        for shelter in a.transport['shelters']:
            self.assertLessEqual(shelter['reserved'],shelter['capacity'])
            self.assertLessEqual(shelter['medical_reserved'],shelter['medical_slots'])
        for key,total in [('peak_vehicles','vehicles'),('peak_care_workers','care_workers'),('peak_stretchers','stretchers')]:
            self.assertLessEqual(a.resource_audit[key],a.resource_audit[total])

    def test_long_wait_overtakes_fresh_priority(self):
        s,people,p,r,n=self.setup_network()
        r.vehicles=1;r.vehicle_capacity=1
        old=people[0];old.base=old.base.model_copy(update={'age':35,'mobility':'independent','care_dependency':'none','chronic_condition':False})
        fresh=people[1];fresh.waiting_minute=49
        n.dispatch([fresh,old],MVP_POLICY_CONFIGS[PolicyId.S5],50,r,120,[],s)
        self.assertIsNotNone(old.transit_minute)
        self.assertIsNone(fresh.transit_minute)

if __name__=='__main__': unittest.main()
