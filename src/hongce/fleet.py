"""Positioned vehicle dispatch with timed shared-corridor reservations.

This is a mesoscopic graph, not microscopic traffic. Route windows use the
prescribed hazard forecast; there is no claim of optimal routing under forecast
error or non-FIFO travel times. All logic here is original implementation.
"""
from collections import Counter, defaultdict
import heapq
from .transport import TransportNetwork, route_window


class PositionedFleet(TransportNetwork):
    def __init__(self, scenario):
        super().__init__(scenario)
        self.positions = {}
        self.reservations = defaultdict(list)
        self.graph = defaultdict(list)
        self.route_by_id = {r['id']:r for r in self.routes}
        self.served = Counter()
        self.known = set()
        self.base = self.config.get('fleet_base_id') or next(iter(self.shelters))
        for r in self.routes:
            a,b=r['origin_id'],r['shelter_id']
            self.graph[a].append((b,r,False))
            if r.get('bidirectional',True):
                self.graph[b].append((a,r,True))

    def capacity_available(self, route, start, end, extra=()):
        """Half-open [start,end) intervals; opposite directions share capacity."""
        changes=[(start,1),(end,-1)]
        for segment in [*self.reservations[route['id']],*extra]:
            if segment['route_id']!=route['id']:
                continue
            lo,hi=max(start,segment['start_minute']),min(end,segment['end_minute'])
            if lo<hi:
                changes.extend([(lo,1),(hi,-1)])
        current=0
        for _,delta in sorted(changes):
            current+=delta
            if current>route.get('max_concurrent_vehicles',8):
                return False
        return True

    def path_to(self, start, target, minute, closure):
        if start==target:
            return []
        # Simple paths avoid loops; retain different arrival labels because the
        # prescribed depth curves may violate the FIFO assumption of Dijkstra.
        queue=[(minute,0,start,[],frozenset([start]))]
        serial=0
        while queue:
            time,_,node,path,visited=heapq.heappop(queue)
            if node==target:
                return path
            for dest,route,reverse in sorted(self.graph[node],key=lambda v:v[1]['id']):
                if dest in visited:
                    continue
                travel,_=route_window(route,time,closure)
                if travel is None or not self.capacity_available(route,time,time+travel,path):
                    continue
                segment={'route_id':route['id'],'from_id':node,'to_id':dest,'reverse':reverse,
                         'start_minute':time,'end_minute':time+travel,'phase':'pickup'}
                serial+=1
                heapq.heappush(queue,(time+travel,serial,dest,[*path,segment],visited|{dest}))
        return None

    def dispatch(self, people, policy, minute, resources, closure, events, scenario):
        from .kernel import Trip,event
        from .models import EvacuationStatus as Status
        waiting=[p for p in people if p.waiting_minute is not None and p.transit_minute is None]
        observed=[p for p in people if p.waiting_minute is not None]
        known=Counter(p.base.is_vulnerable for p in observed)
        busy={t.vehicle for t in resources.trips}
        care_left=resources.care_workers-sum(t.care for t in resources.trips)
        stretchers_left=resources.stretchers-sum(t.stretchers for t in resources.trips)
        balanced=self.config.get('dispatch_mode')=='balanced_coverage'
        for p in waiting:
            p.status,p.reason=Status.RESOURCE_BLOCKED,'等待有实际位置的车辆、随车照护与担架'
        for vehicle in range(resources.vehicles):
            if vehicle in busy or resources.vehicle_capacity<=0:
                continue
            location=self.positions.get(vehicle,self.base)
            def priority(p):
                age=minute-p.waiting_minute
                if balanced:
                    # Only observed, authorized requests enter this denominator.
                    coverage=self.served[p.base.is_vulnerable]/max(1,known[p.base.is_vulnerable])
                    return (coverage, p.waiting_minute,not p.base.is_vulnerable,p.base.id)
                urgent=policy.dispatch_rule.value not in {'equal_allocation','first_come_first_served'}
                aging=self.config['aging_minutes']
                return (0 if age>=aging else 1,-age if age>=aging else 0,
                        not p.base.is_vulnerable if urgent else False,p.waiting_minute,p.base.id)
            waiting.sort(key=priority)
            pickup_cache={}
            candidates_cache={}
            selected=None
            passengers=[]
            used_care=used_stretchers=0
            for person in waiting:
                if person.transit_minute is not None:
                    continue
                if resources.shelter_beds_remaining<=0:
                    person.status,person.reason=Status.UNSUITABLE_SHELTER,'安置床位总量不足'
                    continue
                origin=person.base.location_id
                if selected and origin!=selected['route']['origin_id']:
                    continue
                care=2 if person.base.care_dependency=='full' else int(person.base.care_dependency=='partial')
                stretcher=int(person.base.mobility=='bedridden')
                if care>care_left or stretcher>stretchers_left:
                    continue
                if origin not in pickup_cache:
                    pickup_cache[origin]=self.path_to(location,origin,minute,closure)
                pickup=pickup_cache[origin]
                if pickup is None:
                    person.status,person.reason=Status.ROUTE_BLOCKED,'现有车辆位置至该对象缺少可通行的接驳路径'
                    continue
                boarding=pickup[-1]['end_minute'] if pickup else minute
                depart=boarding+self.config['loading_minutes']
                if origin not in candidates_cache:
                    choices=[]
                    for route in self.routes:
                        if route['origin_id']!=origin:
                            continue
                        travel,_=route_window(route,depart,closure)
                        if travel is not None and self.capacity_available(route,depart,depart+travel,pickup):
                            choices.append({'route':route,'arrival':depart+travel,'pickup':pickup,
                                            'boarding':boarding,'departure':depart})
                    candidates_cache[origin]=sorted(choices,key=lambda c:(c['arrival'],c['route']['id']))
                choice=None
                for candidate in candidates_cache[origin]:
                    route=candidate['route']
                    if selected and route['id']!=selected['route']['id']:
                        continue
                    shelter=self.shelters.get(route['shelter_id'])
                    if shelter and shelter['reserved']<shelter['capacity'] and (care<2 or shelter['medical_reserved']<shelter['medical_slots']):
                        choice=candidate
                        break
                if choice is None:
                    if not selected:
                        person.status,person.reason=Status.ROUTE_BLOCKED,'接人后无可行转运窗口，或可达安置点接收名额不足'
                    continue
                selected=choice
                shelter=self.shelters[choice['route']['shelter_id']]
                shelter['reserved']+=1;shelter['medical_reserved']+=int(care==2)
                resources.shelter_beds_remaining-=1
                care_left-=care;stretchers_left-=stretcher
                used_care+=care;used_stretchers+=stretcher
                person.dispatch_minute=minute;person.boarding_minute=choice['boarding']
                person.transit_minute=choice['departure'];person.scheduled_arrival_minute=choice['arrival']
                person.route_id=choice['route']['id'];person.shelter_id=shelter['id']
                person.status,person.reason=Status.WAITING_TRANSFER,'已派车；等待空驶接人、装载与发车'
                passengers.append(person)
                self.served[person.base.is_vulnerable]+=1
                events.append(event(choice['departure'],'dispatch','vehicle departed',
                    {'person':person.base.id,'vehicle':vehicle,'route_id':person.route_id,'shelter_id':shelter['id'],
                     'arrival_minute':choice['arrival'],'care_workers':care,'stretchers':stretcher}))
                if len(passengers)>=resources.vehicle_capacity:
                    break
            if selected is None:
                continue
            route=selected['route'];shelter_id=route['shelter_id']
            release=selected['arrival']+self.config['unloading_minutes']
            segments=[*selected['pickup'],{'route_id':route['id'],'from_id':route['origin_id'],
                'to_id':shelter_id,'reverse':False,'start_minute':selected['departure'],
                'end_minute':selected['arrival'],'phase':'loaded'}]
            for segment in segments:
                self.reservations[segment['route_id']].append({**segment,'vehicle':vehicle})
            # Position is the next available position; busy vehicles cannot reuse it.
            self.positions[vehicle]=shelter_id
            resources.trips.append(Trip(vehicle,passengers,selected['arrival'],release,used_care,used_stretchers,
                                       route_id=route['id'],release_message='vehicle available at shelter',destination=shelter_id))
            trip={'vehicle':vehicle,'vehicle_origin_id':location,'origin_id':route['origin_id'],
                'shelter_id':shelter_id,'route_id':route['id'],'dispatch_minute':minute,
                'boarding_minute':selected['boarding'],'departure_minute':selected['departure'],
                'arrival_minute':selected['arrival'],'release_minute':release,
                'return_start_minute':release,'return_route_id':None,'segments':segments,
                'passengers':[p.base.id for p in passengers],'care_workers':used_care,'stretchers':used_stretchers,
                'dispatch_reason':'已知应转人群中覆盖较低的群体优先，同组按等待排序' if balanced else '按所选政策的脆弱性与等待顺序派车'}
            self.trip_log.append(trip)
            events.append(event(minute,'dispatch','vehicle assigned',{'vehicle':vehicle,'from':location,
                'origin_id':route['origin_id'],'people':trip['passengers'],'boarding_minute':selected['boarding'],
                'reason':trip['dispatch_reason']}))
        resources.peak_vehicles=max(resources.peak_vehicles,len(resources.trips))
        resources.peak_care=max(resources.peak_care,sum(t.care for t in resources.trips))
        resources.peak_stretchers=max(resources.peak_stretchers,sum(t.stretchers for t in resources.trips))

    def report(self):
        return {**self.config,'model':'positioned_fleet_v4','shelters':list(self.shelters.values()),
                'trips':self.trip_log,'road_reservations':dict(self.reservations),
                'empty_vehicle_minutes':sum(s['end_minute']-s['start_minute'] for t in self.trip_log for s in t['segments'] if s['phase']=='pickup'),
                'loaded_vehicle_minutes':sum(t['arrival_minute']-t['departure_minute'] for t in self.trip_log),
                'dispatch_mode':self.config.get('dispatch_mode','policy_priority'),
                'assumptions':['车辆从集结点出发，卸载后停在目的地；下轮先空驶接人',
                    '双向走廊共享分时预约容量，尚未解析跟驰和路口排队',
                    '未来积水过程作为已知情景输入，路由不是现实最优路线承诺',
                    '照护转运任务采用资源池，尚未跟踪每名随车人员位置',
                    '公平调度只使用已知且获授权的请求，不保证各群体均达到安全底线']}
