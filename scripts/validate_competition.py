"""Reproduce the competition evidence bundle without external model keys."""
from __future__ import annotations
import argparse
import json
import csv
from pathlib import Path
from time import perf_counter
from hongce.evaluation import run_policy_batch, run_named_experiments, write_json
from hongce.engine import RULE_VERSION

def compact(payload):
    if 'experiments' in payload:
        return {**payload,'experiments':{k:compact(v) for k,v in payload['experiments'].items()}}
    return {k:v for k,v in payload.items() if k!='runs'}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--seeds',type=int,default=50)
    parser.add_argument('--baseline-population',type=int,default=2000)
    parser.add_argument('--mechanism-population',type=int,default=500)
    parser.add_argument('--output',default='data/validation/competition_v3.json')
    args=parser.parse_args()
    seeds=list(range(202608060,202608060+args.seeds))
    start=perf_counter()
    print('Running paired S0/S3/S5 baseline...',flush=True)
    baseline=run_policy_batch(seeds=seeds,population=args.baseline_population,output_dir='outputs/validation/baseline')
    print(f'Baseline finished after {perf_counter()-start:.1f}s; running A/B/C...',flush=True)
    mechanisms=run_named_experiments(seeds=seeds,population=args.mechanism_population,output_dir='outputs/validation/mechanisms')
    stresses={}
    for name,overrides in [('early_bridge',{'bridge_closure_minute':70}),
                           ('communications_failure',{'communication_failure_minute':45,'communication_failure_rate':.8})]:
        print(f'Running stress scenario {name} after {perf_counter()-start:.1f}s...',flush=True)
        stresses[name]=compact(run_policy_batch(seeds=seeds,population=args.mechanism_population,
            output_dir=f'outputs/validation/{name}',scenario_config=overrides))
    bundle={'code_version':RULE_VERSION,'seeds':seeds,'baseline':compact(baseline),
            'mechanisms':compact(mechanisms),'stress_tests':stresses,
            'elapsed_seconds':round(perf_counter()-start,2),
            'scope':'Synthetic model verification, not historical calibration or evidence of real-world causal effects.',
            'run_count':len(seeds)*(3+22+6)}
    write_json(Path(args.output),bundle)
    write_run_table(Path(args.output).with_name('competition_v3_runs.csv'))
    print(json.dumps({'output':args.output,'run_count':bundle['run_count'],'seconds':bundle['elapsed_seconds']},ensure_ascii=False),flush=True)


def write_run_table(path):
    rows=[]
    for source in sorted(Path('outputs/validation').glob('**/comparison_s0_s3_s5.json')):
        if 'sensitivity' in source.parts:
            continue
        data=json.loads(source.read_text(encoding='utf-8'))
        if data.get('code_version')!=RULE_VERSION:
            continue
        group=str(source.parent.relative_to('outputs/validation')).replace('\\','/')
        rows.extend({'experiment':group,'code_version':RULE_VERSION,**row} for row in data['runs'])
    with path.open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=sorted({key for row in rows for key in row}))
        writer.writeheader();writer.writerows(rows)

if __name__=='__main__':
    main()
