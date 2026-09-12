"""Paired policy experiments with explicit interventions, budgets and uncertainty."""
from __future__ import annotations
from dataclasses import dataclass, field
import json
from pathlib import Path
import random
from statistics import mean, median
from typing import Any
from .configuration import normalize_scenario_config, validate_scenario_config, build_scenario
from .engine import RULE_VERSION, RunResult, run_policy
from .models import MVP_POLICY_CONFIGS, PolicyConfig, PolicyId, stable_config_hash

METRICS = ['safe_before_danger_rate', 'vulnerable_safe_before_danger_rate', 'general_safe_before_danger_rate',
           'vulnerable_harm_risk', 'lead_time_minutes_median', 'response_closure_rate',
           'missed_critical_action_rate', 'group_safety_gap', 'resource_queue_minutes_mean',
           'safe_count', 'target_count', 'vulnerable_safe_count', 'vulnerable_target_count', 'policy_cost']
LOWER_BETTER = {'vulnerable_harm_risk', 'missed_critical_action_rate', 'resource_queue_minutes_mean', 'policy_cost'}

@dataclass
class Variant:
    id: str
    name: str
    policy: PolicyConfig
    scenario_overrides: dict = field(default_factory=dict)
    changed_fields: list[str] = field(default_factory=list)
    budget_allocation: dict = field(default_factory=dict)

    def metadata(self):
        return {'id': self.id, 'name': self.name, 'policy': self.policy.model_dump(mode='json'),
                'scenario_overrides': self.scenario_overrides, 'changed_fields': self.changed_fields,
                'budget_allocation': self.budget_allocation}

def percentile(values, q):
    if not values:
        return None
    values = sorted(values)
    pos = (len(values) - 1) * q
    lo, hi = int(pos), min(len(values)-1, int(pos)+1)
    return values[lo] * (hi-pos) + values[hi] * (pos-lo) if hi != lo else values[lo]

def interval(values):
    values = [float(x) for x in values if x is not None]
    if not values:
        return {'mean': None, 'median': None, 'p05': None, 'p95': None, 'ci95_low': None, 'ci95_high': None, 'n': 0}
    rng = random.Random(816)
    boot = sorted(mean(rng.choices(values, k=len(values))) for _ in range(400)) if len(values) >= 2 else []
    return {'mean': mean(values), 'median': median(values), 'p05': percentile(values, .05),
            'p95': percentile(values, .95), 'ci95_low': percentile(boot, .025), 'ci95_high': percentile(boot, .975), 'n': len(values)}

def summarize_rows(rows):
    grouped = {}
    for row in rows:
        grouped.setdefault(row.get('variant_id', row['policy_id']), []).append(row)
    summary = {}
    for key, group in grouped.items():
        summary[key] = {'runs': len(group)}
        for metric in METRICS:
            values = [r.get(metric) for r in group if metric != 'group_safety_gap' or r.get('group_safety_gap_defined', True)]
            stats = interval(values)
            numeric = [float(v) for v in values if v is not None]
            stats['worst'] = (max(numeric, key=abs) if metric=='group_safety_gap' else
                              max(numeric) if metric in LOWER_BETTER else min(numeric)) if numeric else None
            summary[key][metric] = stats
        summary[key]['trust_delta'] = interval([])
    return summary

def execute_variants(variants, seeds, population, scenario_config, output_dir, baseline_id=None, retain_runs=False):
    base = normalize_scenario_config(scenario_config)
    error = validate_scenario_config(base)
    if error:
        raise ValueError(error)
    rows = []
    for seed in seeds:
        for v in variants:
            config = normalize_scenario_config({**base, **v.scenario_overrides})
            error = validate_scenario_config(config)
            if error:
                raise ValueError(f'{v.id}: {error}')
            scenario = build_scenario(seed, population, config)
            result = run_policy(v.policy.id, seed=seed, scenario=scenario, policy_config=v.policy,
                                output_dir=Path(output_dir)/'runs' if retain_runs else None)
            rows.append({**result.metrics.model_dump(mode='json'), 'variant_id': v.id, 'policy_name': v.name,
                         'scenario_hash': result.scenario_hash, 'policy_hash': v.policy.config_hash})
    summary = summarize_rows(rows)
    reference = baseline_id or variants[0].id
    reference_rows = {r['seed']: r for r in rows if r['variant_id']==reference}
    paired = {}
    for v in variants:
        group = [r for r in rows if r['variant_id']==v.id]
        paired[v.id] = {}
        for metric in ['safe_before_danger_rate', 'vulnerable_safe_before_danger_rate', 'safe_count']:
            paired[v.id][metric] = interval([r[metric]-reference_rows[r['seed']][metric] for r in group
                                            if r.get(metric) is not None and reference_rows[r['seed']].get(metric) is not None])
        additional = paired[v.id]['safe_count']['mean']
        cost_delta = summary[v.id]['policy_cost']['mean']-summary[reference]['policy_cost']['mean']
        summary[v.id]['incremental_cost_per_safe_transfer'] = cost_delta/additional if additional and additional > 0 else None
        summary[v.id]['incremental_cost_note'] = '相对基线每新增按时安全转移一人的合成预算单位；未增加人数时不定义'
        regrets = []
        for r in group:
            same_seed = [x['safe_before_danger_rate'] for x in rows if x['seed']==r['seed']]
            regrets.append(max(same_seed)-r['safe_before_danger_rate'])
        summary[v.id]['sampled_worst_case_regret'] = max(regrets) if regrets else None
    result = {'label': 'SIMULATED', 'code_version': RULE_VERSION, 'population': population, 'seeds': seeds,
              'scenario_config': base, 'scenario_config_hash': stable_config_hash(base), 'baseline_id': reference,
              'variants': [v.metadata() for v in variants], 'runs': rows, 'summary': summary, 'paired_differences': paired,
              'validation_level': 'validation' if len(seeds)>=50 else 'quick_demo',
              'interval_note': 'P05–P95 为模拟分布区间；CI95 为 400 次固定种子 bootstrap 均值置信区间。少于 50 个种子仅作快速演示。',
              'regret_note': '样本内后悔值只覆盖本次种子与候选方案，不代表现实最坏灾情。'}
    write_json(Path(output_dir)/'comparison_s0_s3_s5.json', result)
    return result

def run_policy_batch(policies=None, seeds=None, population=2000, output_dir='outputs/experiments', scenario_config=None, retain_runs=False):
    policies = policies or ['S0', 'S3', 'S5']
    seeds = seeds or list(range(202608060, 202608110))
    variants = [Variant(p, MVP_POLICY_CONFIGS[PolicyId(p)].name, MVP_POLICY_CONFIGS[PolicyId(p)]) for p in policies]
    return execute_variants(variants, seeds, population, scenario_config, output_dir, 'S0' if 'S0' in policies else policies[0], retain_runs)


def run_transport_sensitivity(seeds=None,population=500,output_dir='outputs/validation/sensitivity',scenario_config=None):
    policy=MVP_POLICY_CONFIGS[PolicyId.S5]
    variants=[Variant('reference','标准 S5',policy)]
    for key,label,changes in [
        ('road_capacity','道路容量设为 2',{'road_capacity':2}),
        ('flood_peak','峰值积水设为 0.80 m',{'flood_peak_m':.8}),
        ('loading','装载时间设为 10 min',{'loading_minutes':10}),
        ('zero_vehicles','零车辆负对照',{'vehicles':0}),
        ('aging','等待提权设为 15 min',{'queue_aging_minutes':15})]:
        variants.append(Variant(key,label,policy,changes,list(changes)))
    result=execute_variants(variants,seeds or list(range(202608060,202608110)),population,scenario_config,output_dir,'reference')
    result['title']='运输假设敏感性 · 同人口同种子'
    return result

def run_fleet_comparison(seeds=None,population=2000,output_dir='outputs/validation/fleet_v4',scenario_config=None):
    policy=MVP_POLICY_CONFIGS[PolicyId.S5]
    base=normalize_scenario_config(scenario_config)
    base.update(dispatch_model='positioned_fleet',dispatch_mode='policy_priority')
    variants=[Variant('reference','S5 / 实际位置车队',policy),
        Variant('balanced','S5 / 群体覆盖均衡',policy,{'dispatch_mode':'balanced_coverage'},['dispatch_mode']),
        Variant('legacy_corridor','旧走廊模型 / 结构对照',policy,{'dispatch_model':'corridor_v3'},['dispatch_model']),
        Variant('southern_depot','南部体育馆集结',policy,{'fleet_base_id':'gym_shelter'},['fleet_base_id']),
        Variant('road_capacity','走廊容量降至 2',policy,{'road_capacity':2},['road_capacity']),
        Variant('zero_vehicles','零车辆负对照',policy,{'vehicles':0},['vehicles'])]
    result=execute_variants(variants,seeds or list(range(202609110,202609160)),population,base,output_dir,'reference')
    result['title']='车队机制与公平策略 / 同人口同种子'
    return result


def experiment_designs(base_config):
    s0, s5 = MVP_POLICY_CONFIGS[PolicyId.S0], MVP_POLICY_CONFIGS[PolicyId.S5]
    # Budget costs are declared synthetic intervention assumptions, not market prices.
    allocations = [('A_engineering', '同预算 · 工程', {'bridge':50, 'vehicles':0, 'care':0, 'coordination':0}),
                   ('A_care', '同预算 · 照护运输', {'bridge':0, 'vehicles':25, 'care':25, 'coordination':0}),
                   ('A_integrated', '同预算 · 组织协同', {'bridge':15, 'vehicles':10, 'care':10, 'coordination':15})]
    a = []
    for key, name, money in allocations:
        coord = money['coordination'] > 0
        policy = s0.model_copy(update={'name': name, 'budget_units':150,
            'bridge_extension_minutes': round(money['bridge']*.7),
            'vehicle_multiplier':1+money['vehicles']/100, 'care_multiplier':1+money['care']/50,
            'confirmation_required':coord, 'institution_self_authorization':coord,
            'registry_mode':'dynamic' if coord else 'static', 'registry_coverage':.96 if coord else .82,
            'warning_channels':['department_push','cadre_call','neighbor_network'] if coord else ['department_push'],
            'preposition_care_resources':money['care']>0})
        a.append(Variant(key,name,policy,budget_allocation={'baseline':100,**money},changed_fields=list(money)))
    b = []
    danger = base_config['danger_arrival_minute']
    for lead in [min(135, danger), min(90, danger)]:
        for authorization in [False, True]:
            for memory in [0,2,5]:
                key = f'B_lead{lead}_auth{int(authorization)}_memory{memory}'
                overrides = {'warning_minute':danger-lead, 'evacuation_order_minute':max(danger-30,danger-lead),
                             'communication_failure_minute':max(base_config['communication_failure_minute'],danger-lead),
                             'false_alarm_memory':memory}
                b.append(Variant(key, f'提前 {lead} 分钟 · {"先行授权" if authorization else "等待命令"} · 误报 {memory} 次',
                    s5.model_copy(update={'institution_self_authorization':authorization}), overrides,
                    ['warning_minute','institution_self_authorization','false_alarm_memory']))
    c = [Variant('C_full','综合方案完整机制',s5)]
    removals = [('registry','关闭动态补登记',{'registry_mode':'static','registry_coverage':.82}),
                ('confirmation','关闭人工确认',{'confirmation_required':False}),
                ('neighbors','关闭邻里传播',{'warning_channels':[x for x in s5.warning_channels if x!='neighbor_network']}),
                ('backup','关闭备用通信',{'warning_channels':[x for x in s5.warning_channels if x!='backup_radio']}),
                ('bridge','取消桥梁加固',{'bridge_extension_minutes':0}),
                ('authority','取消先行授权',{'institution_self_authorization':False})]
    for key,name,changes in removals:
        c.append(Variant(f'C_no_{key}',name,s5.model_copy(update=changes),changed_fields=list(changes)))
    return {'A_money_allocation':a, 'B_trigger_timing':b, 'C_chain_breaks':c}

EXPERIMENT_LABELS = {'A_money_allocation':'实验 A · 同预算资源配置',
                     'B_trigger_timing':'实验 B · 预警与授权因子实验',
                     'C_chain_breaks':'实验 C · 单机制消融'}

def run_named_experiments(seeds=None,population=2000,output_dir='outputs/experiments',scenario_config=None):
    seeds = seeds or list(range(202608060,202608110))
    base = normalize_scenario_config(scenario_config)
    payload = {'label':'SIMULATED','code_version':RULE_VERSION,'population':population,'seeds':seeds,
               'scenario_config':base,'scenario_config_hash':stable_config_hash(base),'experiments':{}}
    for key,variants in experiment_designs(base).items():
        comparison = execute_variants(variants,seeds,population,base,Path(output_dir)/key,
                                      'C_full' if key=='C_chain_breaks' else None)
        comparison['title'] = EXPERIMENT_LABELS[key]
        comparison['interpretation'] = interpret_experiment(key,comparison['summary'])
        payload['experiments'][key] = comparison
    write_json(Path(output_dir)/'experiments_abc_summary.json',payload)
    return payload

def interpret_experiment(name,summary):
    if not summary:
        return []
    best = max(summary,key=lambda key: summary[key]['safe_before_danger_rate']['mean'])
    return [f'{EXPERIMENT_LABELS.get(name,name)}：样本内按时安全转移率最高为 {best}。',
            '结果受合成行为、资源与灾害假设限制；请结合区间、配对差值及失败情境。']

def infer_breakpoints(result):
    mapping = {'unregistered':'registry_gap','contact_failed':'contact_failure',
               'refused':'refusal_or_distrust','misunderstood':'refusal_or_distrust',
               'resource_blocked':'resource_blocked','route_blocked':'route_blocked',
               'authorization_wait':'authorization_wait','unsuitable_shelter':'shelter_mismatch'}
    counts = {key:0 for key in set(mapping.values())}
    for p in result.people:
        if p.status.value in mapping:
            counts[mapping[p.status.value]] += 1
    return counts

def write_explanation_pack(result: RunResult,output_dir):
    pack = {'label':'SIMULATED','run_id':result.run.id,'scenario_hash':result.scenario_hash,
            'metrics':result.metrics.model_dump(mode='json'),'policy_config':result.policy_config,
            'policy_breakpoints':infer_breakpoints(result),
            'representative_people':[p for p in result.to_dict()['agents'] if p['is_vulnerable']][:12],
            'organization_traces':[t.model_dump(mode='json') for t in result.traces if not t.actor_id.startswith('p')],
            'resource_audit':result.resource_audit}
    path = Path(output_dir)/f'{result.run.id}_explanation.json'
    write_json(path,pack)
    return path

def write_json(path,payload):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
