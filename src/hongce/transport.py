"""Mesoscopic corridor transport. All hydraulic curves are prescribed scenarios.

No shallow-water solver or calibrated vehicle/pedestrian safety thresholds are
claimed. A route is a whole corridor; its concurrent-vehicle limit aggregates
traffic, including returning vehicles. Shared intersections are not simulated.
"""
from __future__ import annotations
from dataclasses import dataclass
import math


def depth_at(route, minute):
    points = route.get('depth_profile', [])
    if not points:
        return 0.0
    if minute <= points[0][0]:
        return float(points[0][1])
    for (t0, d0), (t1, d1) in zip(points, points[1:]):
        if minute <= t1:
            return d0 + (d1-d0)*(minute-t0)/(t1-t0)
    return float(points[-1][1])


def route_window(route, minute, closure, occupied=0, loading=0):
    """Conservative whole-trip check of prescribed depth and closure windows."""
    limit = route.get('max_depth_m', .30)
    capacity = route.get('max_concurrent_vehicles', 8)
    if occupied >= capacity:
        return None, '道路通行容量已满'
    dep = minute + loading
    # Depth can slow travel; use fixed-point conservative maximum over the trip.
    travel = max(1, math.ceil(route['travel_minutes']))
    for _ in range(32):
        peak = max([depth_at(route, dep), depth_at(route, dep+travel)] +
                   [d for t, d in route.get('depth_profile', []) if dep <= t <= dep+travel])
        if peak >= limit:
            return None, '预计通行期间积水超过情景阈值'
        revised = math.ceil(route['travel_minutes'] / max(.25, 1-.65*peak/limit))
        if revised <= travel:
            break
        travel = revised
    else:
        return None, '积水减速迭代未收敛，保守暂停通行'
    close = route.get('closed_minute')
    if route.get('bridge_dependency'):
        close = min(close, closure) if close is not None else closure
    if close is not None and dep + travel > close:
        return None, '无法在封闭窗口前完成通行'
    return travel, ''


def default_transport(config):
    """Explicit synthetic corridors and receiving centers, editable in config."""
    shelters = config.get('shelters') or [
        {'id':'school_shelter', 'name':'北岸中学安置点', 'weight':.65, 'medical_slots':45},
        {'id':'gym_shelter', 'name':'南部体育馆安置点', 'weight':.35, 'medical_slots':15}]
    # One global bed budget is distributed, never added to the shelter capacities.
    total = config['shelter_beds']
    weight = sum(s.get('capacity', s.get('weight', 1)) for s in shelters)
    left = total
    normalized = []
    for i, s in enumerate(shelters):
        beds = left if i == len(shelters)-1 else math.floor(total*s.get('capacity',s.get('weight',1))/weight) if weight else 0
        left -= beds
        normalized.append({**s,'capacity':beds,'medical_slots':min(beds,s.get('medical_slots',s.get('care_capacity',30)))})
    routes = [dict(r) for r in config.get('routes', [])]
    destination_ids=[s['id'] for s in normalized]
    primary='school_shelter' if 'school_shelter' in destination_ids else destination_ids[0]
    alternate='gym_shelter' if 'gym_shelter' in destination_ids else next((s for s in destination_ids if s!=primary),None)
    defaults = {'nursing_home':26,'county_hospital':18,'north_valley':33,'south_valley':16,'qingyuan_town':17}
    for origin, travel in defaults.items():
        if not any(r['origin_id']==origin for r in routes):
            routes.append({'id':f'route-{origin}-{primary}','origin_id':origin,
                'shelter_id':primary,'travel_minutes':travel,
                'bridge_dependency':['bridge_east'] if origin=='nursing_home' else []})
        # Explicit synthetic detour to another center (not an inferred real road).
        if alternate and not any(r['origin_id']==origin and r.get('shelter_id')==alternate for r in routes):
            routes.append({'id':f'detour-{origin}-gym' if alternate=='gym_shelter' else f'detour-{origin}-{alternate}','origin_id':origin,'shelter_id':alternate,
                'travel_minutes':travel+18,'bridge_dependency':[], 'synthetic_detour':True})
    for r in routes:
        r.setdefault('shelter_id','school_shelter')
        r.setdefault('max_concurrent_vehicles',config['road_capacity'])
        r.setdefault('max_depth_m',config['road_depth_limit_m'])
        # Only low-lying corridors flood; elevated detours are a scenario assumption.
        r.setdefault('depth_profile', [[0,0],[max(1,config['danger_arrival_minute']-80),0],
            [config['danger_arrival_minute'], config['flood_peak_m']],
            [config['danger_arrival_minute']+60,config['flood_peak_m']*.65]]
            if r.get('crosses_high_risk') or r.get('bridge_dependency') else [])
    return {'routes':routes,'shelters':normalized,'loading_minutes':config['loading_minutes'],
            'dispatch_model':config.get('dispatch_model','positioned_fleet'),
            'dispatch_mode':config.get('dispatch_mode','policy_priority'),
            'fleet_base_id':config.get('fleet_base_id','school_shelter'),
            'unloading_minutes':5,'aging_minutes':config['queue_aging_minutes'],
            'hydrology':'prescribed_depth_curves_not_hydrodynamics'}


class TransportNetwork:
    def __init__(self, scenario):
        self.config = scenario.transport
        self.routes = self.config['routes']
        self.shelters = {s['id']:{**s,'reserved':0,'medical_reserved':0} for s in self.config['shelters']}
        self.trip_log = []
        self.blocked_returns = 0

    def dispatch(self, people, policy, minute, resources, closure, events, scenario):
        from .kernel import Trip, event
        from .models import EvacuationStatus as Status
        waiting = [p for p in people if p.waiting_minute is not None and p.transit_minute is None]
        aging = self.config['aging_minutes']
        def priority(p):
            age = minute-p.waiting_minute
            urgent = policy.dispatch_rule.value not in {'equal_allocation','first_come_first_served'}
            # Long waits eventually override vulnerability priority, not fixed quotas.
            return (0 if age>=aging else 1, -age if age>=aging else 0,
                    not p.base.is_vulnerable if urgent else False, p.waiting_minute, p.base.id)
        waiting.sort(key=priority)
        for p in waiting:
            p.status,p.reason = Status.RESOURCE_BLOCKED,'等待车辆、照护人员或担架'
        busy = {t.vehicle for t in resources.trips}
        care_left = resources.care_workers-sum(t.care for t in resources.trips)
        stretchers_left = resources.stretchers-sum(t.stretchers for t in resources.trips)
        occupancy = {r['id']:sum(t.route_id==r['id'] or t.return_route_id==r['id'] for t in resources.trips) for r in self.routes}
        for vehicle in range(resources.vehicles):
            if vehicle in busy or resources.vehicle_capacity<=0:
                continue
            selected = None
            passengers = []
            used_care = used_stretchers = 0
            load = self.config['loading_minutes']
            windows={r['id']:route_window(r,minute,closure,occupancy[r['id']],load) for r in self.routes}
            for p in waiting:
                if p.transit_minute is not None:
                    continue
                if resources.shelter_beds_remaining<=0:
                    p.status,p.reason=Status.UNSUITABLE_SHELTER,'安置床位总量不足'
                    continue
                candidates=[]
                reason='起点没有可用路线'
                for r in self.routes:
                    if r['origin_id']!=p.base.location_id or selected and r['id']!=selected[1]['id']:
                        continue
                    s=self.shelters.get(r['shelter_id'])
                    if not s or s['reserved']>=s['capacity'] or p.base.care_dependency=='full' and s['medical_reserved']>=s['medical_slots']:
                        reason='可达安置点床位或全照护接收名额不足'
                        continue
                    travel, blocked=windows[r['id']]
                    if travel is None:
                        reason=blocked
                        continue
                    candidates.append((travel,r,s))
                if not candidates:
                    if not selected:
                        p.status,p.reason=Status.ROUTE_BLOCKED,reason
                    continue
                choice=min(candidates,key=lambda c:(c[0],c[1]['id']))
                care=2 if p.base.care_dependency=='full' else int(p.base.care_dependency=='partial')
                stretcher=int(p.base.mobility=='bedridden')
                if care>care_left or stretcher>stretchers_left:
                    continue
                selected=choice
                travel,r,s=choice
                care_left-=care; stretchers_left-=stretcher
                used_care+=care; used_stretchers+=stretcher
                s['reserved']+=1; s['medical_reserved']+=int(p.base.care_dependency=='full')
                resources.shelter_beds_remaining-=1
                p.route_id=r['id'];p.shelter_id=s['id'];p.transit_minute=minute+load
                p.scheduled_arrival_minute=minute+load+travel
                p.status,p.reason=Status.IN_TRANSIT,'已派车，装载与运输按事件时刻推进'
                passengers.append(p)
                events.append(event(minute+load,'dispatch','vehicle departed',{'person':p.base.id,'vehicle':vehicle,
                    'route_id':r['id'],'shelter_id':s['id'],'arrival_minute':p.scheduled_arrival_minute,
                    'care_workers':care,'stretchers':stretcher}))
                if len(passengers)>=resources.vehicle_capacity:
                    break
            if not passengers:
                continue
            travel,r,s=selected
            arrival=minute+load+travel
            return_start=arrival+self.config['unloading_minutes']
            returns=[]
            for rr in self.routes:
                if rr['origin_id']==r['origin_id'] and rr['shelter_id']==s['id']:
                    rt,_=route_window(rr,return_start,closure,occupancy[rr['id']])
                    if rt is not None:
                        returns.append((rt,rr['id']))
            return_travel,return_id=min(returns) if returns else (None,None)
            release=return_start+return_travel if returns else scenario.hazard.end_minute+1
            if not returns:
                self.blocked_returns+=1
                events.append(event(return_start,'resource','vehicle return blocked',{'vehicle':vehicle,'route_id':r['id'],
                    'reason':'返程窗口不可行；本轮保守停留安置点，不重复使用车辆与随车人员'}))
            resources.trips.append(Trip(vehicle,passengers,arrival,release,used_care,used_stretchers,
                                       route_id=r['id'],return_route_id=return_id))
            occupancy[r['id']]+=1
            if return_id and return_id!=r['id']:
                occupancy[return_id]+=1
            self.trip_log.append({'vehicle':vehicle,'origin_id':r['origin_id'],'shelter_id':s['id'],
                'route_id':r['id'],'boarding_minute':minute,'departure_minute':minute+load,
                'arrival_minute':arrival,'return_start_minute':return_start,
                'release_minute':release if returns else None,'return_route_id':return_id,
                'passengers':[p.base.id for p in passengers], 'care_workers':used_care,'stretchers':used_stretchers})
        resources.peak_vehicles=max(resources.peak_vehicles,len(resources.trips))
        resources.peak_care=max(resources.peak_care,sum(t.care for t in resources.trips))
        resources.peak_stretchers=max(resources.peak_stretchers,sum(t.stretchers for t in resources.trips))

    def report(self):
        return {**self.config,'shelters':list(self.shelters.values()),'trips':self.trip_log,
                'blocked_returns':self.blocked_returns,'model':'mesoscopic_corridor_v3',
                'assumptions':['合成道路与备用通道','积水过程线为情景输入，未求解浅水方程',
                    '整条走廊容量约束，未解析交叉口排队','返程路径预判，无法返程则资源不再周转',
                    '照护人员随车返回；接收名额按全照护对象单独占用']}
