import unittest
from hongce.fleet import PositionedFleet
from hongce.configuration import normalize_scenario_config, validate_scenario_config, build_scenario
from hongce.kernel import run_policy
import test_transport_network as fixtures


class PositionedFleetTest(unittest.TestCase):
    def fixture(self):
        s,people,p,r,_=fixtures.TransportTest().setup_network()
        s.transport.update(fleet_base_id='a',dispatch_model='positioned_fleet',dispatch_mode='policy_priority')
        s.transport['routes']=s.transport['routes'][:1]
        r.vehicles=1
        return s,people,p,r,PositionedFleet(s)

    def test_empty_pickup_loading_and_destination_continuity(self):
        s,people,p,r,n=self.fixture()
        events=[]
        n.dispatch(people,p,0,r,120,events,s)
        first=n.trip_log[0]
        self.assertEqual((first['dispatch_minute'],first['boarding_minute'],first['departure_minute'],first['arrival_minute'],first['release_minute']),(0,10,15,25,30))
        self.assertEqual(first['segments'][0]['from_id'],'a')
        self.assertTrue(first['segments'][0]['reverse'])
        self.assertTrue(all(x.sheltered_minute is None for x in people))
        r.advance(25,events)
        self.assertEqual(sum(x.sheltered_minute==25 for x in people),4)
        r.advance(30,events)
        n.dispatch(people,p,30,r,120,events,s)
        second=n.trip_log[1]
        self.assertEqual(second['vehicle_origin_id'],first['shelter_id'])
        self.assertGreaterEqual(second['dispatch_minute'],first['release_minute'])
        self.assertEqual(second['boarding_minute'],40)

    def test_no_teleport_through_closed_or_one_way_pickup(self):
        for change in [{'closed_minute':5},{'bidirectional':False}]:
            s,people,p,r,_=self.fixture()
            s.transport['routes'][0].update(change)
            n=PositionedFleet(s)
            n.dispatch(people,p,0,r,120,[],s)
            self.assertFalse(n.trip_log)
            self.assertTrue(all(x.transit_minute is None for x in people))

    def test_opposite_directions_share_half_open_capacity(self):
        s,people,p,r,n=self.fixture()
        n.dispatch(people,p,0,r,120,[],s)
        route=n.routes[0]
        self.assertFalse(n.capacity_available(route,5,9))
        self.assertTrue(n.capacity_available(route,10,15))
        self.assertFalse(n.capacity_available(route,14,16))
        self.assertTrue(n.capacity_available(route,25,30))

    def test_balanced_order_uses_observed_coverage(self):
        s,people,p,r,n=self.fixture()
        r.vehicle_capacity=1
        ordinary=people[0]
        ordinary.base=ordinary.base.model_copy(update={'age':35,'mobility':'independent','care_dependency':'none','chronic_condition':False,'digital_access':1})
        vulnerable=people[1]
        self.assertFalse(ordinary.base.is_vulnerable)
        self.assertTrue(vulnerable.base.is_vulnerable)
        n.config['dispatch_mode']='balanced_coverage'
        n.served[True]=1
        n.dispatch([vulnerable,ordinary],p,0,r,120,[],s)
        self.assertEqual(n.trip_log[0]['passengers'],[ordinary.base.id])

    def test_all_recorded_segments_obey_capacity_and_vehicle_position(self):
        result=run_policy('S5',seed=93,scenario=build_scenario(93,500,normalize_scenario_config({})))
        previous={}
        for trip in result.transport['trips']:
            v=trip['vehicle']
            if v in previous:
                self.assertEqual(trip['vehicle_origin_id'],previous[v]['shelter_id'])
                self.assertGreaterEqual(trip['dispatch_minute'],previous[v]['release_minute'])
            previous[v]=trip
        self.assertTrue(previous)
        for route in result.transport['routes']:
            segments=result.transport['road_reservations'].get(route['id'],[])
            for minute in range(301):
                count=sum(s['start_minute']<=minute<s['end_minute'] for s in segments)
                self.assertLessEqual(count,route['max_concurrent_vehicles'])

    def test_invalid_depot_rejected(self):
        self.assertIsNotNone(validate_scenario_config(normalize_scenario_config({'fleet_base_id':'missing'})))

    def test_custom_shelters_do_not_create_phantom_destinations(self):
        cfg=normalize_scenario_config({'shelters':[{'id':'custom','capacity':100}]})
        self.assertEqual(cfg['fleet_base_id'],'custom')
        self.assertIsNone(validate_scenario_config(cfg))
        scenario=build_scenario(42,120,cfg)
        self.assertEqual({r['shelter_id'] for r in scenario.transport['routes']},{'custom'})
        bad=normalize_scenario_config({'routes':[{'id':'r','origin_id':'nursing_home','shelter_id':'missing','travel_minutes':10}]})
        self.assertIsNotNone(validate_scenario_config(bad))


if __name__=='__main__': unittest.main()
