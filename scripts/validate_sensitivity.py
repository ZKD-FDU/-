"""Same population and paired seeds; isolate transport assumptions on S5."""
from pathlib import Path
from hongce.evaluation import run_transport_sensitivity, write_json

if __name__=='__main__':
    result=run_transport_sensitivity()
    write_json(Path('data/validation/sensitivity_transport_v4.json'),result)
    for key,summary in result['summary'].items():
        print(key,summary['safe_before_danger_rate']['mean'],flush=True)
