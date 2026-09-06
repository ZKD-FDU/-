"""Directed network messages and capacity-limited organizational decisions."""
from __future__ import annotations
from collections import defaultdict
import heapq
import math
from .models import DecisionTrace


class GovernanceProcess:
    def __init__(self, scenario, policy, seed, by_id, registered, events, receipts, traces):
        # Local import avoids a circular public engine API.
        from .kernel import contact_person, draw, event, RULE_VERSION
        self.contact, self.draw, self.event, self.version = contact_person, draw, event, RULE_VERSION
        self.scenario, self.policy, self.seed = scenario, policy, seed
        self.people, self.registered = by_id, registered
        self.events, self.receipts, self.traces = events, receipts, traces
        self.queue, self.sent, self.actor_available = [], set(), {}
        self.peer_edges, self.worker_edges = [], defaultdict(list)
        self.inbound = defaultdict(list)
        self.institution_ready, self.actor_actions = {}, {}
        self.preparation_start = {}
        self.sequence = 0
        if policy.network_enabled:
            for edge in sorted(scenario.network_edges, key=lambda e: e.id):
                if edge.target_id not in by_id:
                    continue
                if edge.layer in {'administrative', 'institution', 'volunteer'}:
                    if policy.confirmation_required:
                        self.worker_edges[edge.source_id].append(edge)
                elif edge.source_id in by_id:
                    if edge.layer == 'neighbor' and 'neighbor_network' not in policy.warning_channels:
                        continue
                    self.peer_edges.append(edge)
                    self.inbound[edge.target_id].append(edge)

    def organization_step(self, minute):
        h, p = self.scenario.hazard, self.policy
        if minute < h.warning_minute:
            return
        for inst in self.scenario.institutions:
            if not inst.resident_ids:
                continue
            actor = inst.responsible_actor_id
            members = [self.people[x] for x in inst.resident_ids if x in self.people]
            care_demand = sum(2 if x.base.care_dependency == 'full' else int(x.base.care_dependency == 'partial') for x in members)
            formal = minute >= h.evacuation_order_minute
            # Authority is an explicit policy variable; staff need five minutes to verify the warning.
            early = p.institution_self_authorization and minute >= h.warning_minute + 5
            if formal or early:
                if inst.id not in self.preparation_start:
                    self.preparation_start[inst.id] = minute
                    duration = math.ceil(inst.preparation_minutes * (0.5 if p.preposition_care_resources else 1))
                    self.institution_ready[inst.id] = minute + duration
                action = 'prepare_transfer' if minute < self.institution_ready[inst.id] else 'request_dispatch'
                reason = '依正式命令组织转移' if formal else '依据先行授权提前准备照护转移'
            else:
                action, reason = 'wait_authorization', '已知风险，但尚无先行授权；请求上级确认'
            if self.actor_actions.get(actor) != action:
                self.actor_actions[actor] = action
                self.events.append(self.event(minute, 'organization', action,
                    {'actor': actor, 'institution': inst.id, 'reason': reason, 'care_demand': care_demand,
                     'ready_minute': self.institution_ready.get(inst.id)}))
                self.traces.append(DecisionTrace(id=f'org-{actor}-{minute}', actor_id=actor, minute=minute,
                    observed_information_ids=['official-warning'] + (['county-order'] if formal else []),
                    factors={'formal_order': float(formal), 'early_authority': float(early),
                             'care_demand': care_demand, 'prepositioned_care': float(p.preposition_care_resources)},
                    action=action, reason=reason, rule_version=self.version, model_version='InstitutionRuleV1'))

    def ready_for_dispatch(self, person, minute):
        if person.base.institution_id in {i.id for i in self.scenario.institutions if i.resident_ids}:
            return minute >= self.institution_ready.get(person.base.institution_id, float('inf'))
        return minute >= self.scenario.hazard.evacuation_order_minute

    def advance(self, minute):
        h, p = self.scenario.hazard, self.policy
        self.organization_step(minute)
        while self.queue and self.queue[0][0] <= minute:
            _, _, edge, ack = heapq.heappop(self.queue)
            target = self.people[edge.target_id]
            if target.contact_minute is not None and (not ack or target.acknowledged_minute is not None):
                continue
            if self.draw(self.seed, edge.id, 'edge_failure') < edge.failure_probability:
                self.events.append(self.event(minute, 'network', 'message delivery failed',
                    {'person': edge.target_id, 'source': edge.source_id, 'edge_id': edge.id, 'layer': edge.layer}))
                continue
            # Digital edges degrade under communications failure; doorstep/family contact does not.
            if edge.layer == 'online' and minute >= h.communication_failure_minute and 'backup_radio' not in p.warning_channels:
                if self.draw(self.seed, edge.target_id, 'comms') < h.communication_failure_rate:
                    continue
            self.contact(target, minute, edge.layer, edge.source_id, self.receipts, self.events, ack)
            if target.base.id not in self.registered and p.registry_mode == 'dynamic':
                self.registered.add(target.base.id)
                self.events.append(self.event(minute, 'registry', 'unregistered person discovered',
                    {'person': target.base.id, 'source': edge.source_id, 'edge_id': edge.id}))
        if minute < h.warning_minute:
            return
        for edge in self.peer_edges:
            if edge.id in self.sent:
                continue
            source = self.people[edge.source_id]
            if source.contact_minute is not None:
                self.schedule(minute, edge, edge.layer == 'family')
        for actor, edges in self.worker_edges.items():
            if minute < self.actor_available.get(actor, h.warning_minute):
                continue
            pending = [e for e in edges if e.id not in self.sent and self.people[e.target_id].acknowledged_minute is None]
            pending.sort(key=lambda e: (not self.people[e.target_id].base.is_vulnerable,
                                        self.people[e.target_id].contact_minute is not None, e.target_id))
            workers = p.cadre_workers_per_location
            chosen = pending[:workers]
            for edge in chosen:
                self.schedule(minute, edge, True)
            if chosen:
                duration = max(max(1, e.speed_minutes) for e in chosen)
                self.actor_available[actor] = minute + duration
                self.events.append(self.event(minute, 'organization', 'confirmation workers assigned',
                    {'actor': actor, 'people': [e.target_id for e in chosen], 'workers': len(chosen),
                     'available_minute': minute + duration, 'pending_count': len(pending) - len(chosen)}))
        if minute % h.timestep_minutes == 0:
            for target_id, edges in self.inbound.items():
                total = sum(e.trust_weight for e in edges)
                acting = sum(e.trust_weight for e in edges if self.people[e.source_id].transit_minute is not None
                             and self.people[e.source_id].transit_minute <= minute)
                self.people[target_id].neighbor_action_rate = acting / total if total else 0

    def schedule(self, minute, edge, acknowledged):
        self.sent.add(edge.id)
        self.sequence += 1
        heapq.heappush(self.queue, (minute + max(1, edge.speed_minutes), self.sequence, edge, acknowledged))
