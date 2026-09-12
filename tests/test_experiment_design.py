import unittest
import tempfile
from api import service
from hongce.configuration import normalize_scenario_config, build_scenario
from hongce.evaluation import experiment_designs, run_policy_batch
from hongce.decision import candidate_grid, DEFAULT_SCENARIO_CONFIG
from hongce.engine import run_policy

class ExperimentDesignTest(unittest.TestCase):
    def test_equal_budget_and_single_mechanism_ablations(self):
        designs = experiment_designs(normalize_scenario_config({}))
        for v in designs['A_money_allocation']:
            self.assertEqual(sum(v.budget_allocation.values()), 150)
            self.assertEqual(v.policy.budget_units, 150)
        variants = designs['C_chain_breaks']
        full = variants[0].policy.model_dump(exclude={'config_hash'})
        for v in variants[1:]:
            differences = {key for key,value in v.policy.model_dump(exclude={'config_hash'}).items() if value != full[key]}
            self.assertEqual(differences, set(v.changed_fields))
        self.assertEqual(len(designs['B_trigger_timing']), 12)

    def test_batch_preserves_single_run_scenario_and_paired_seeds(self):
        config = normalize_scenario_config({'vehicles':7,'evacuation_order_minute':110})
        with tempfile.TemporaryDirectory() as out:
            batch = run_policy_batch(['S0','S3'], [41,42], 220, out, config)
        single = run_policy('S0',seed=41,scenario=build_scenario(41,220,config))
        row = batch['runs'][0]
        self.assertEqual(row['scenario_hash'], single.scenario_hash)
        self.assertEqual(row['safe_count'], single.metrics.safe_count)
        self.assertEqual(batch['paired_differences']['S0']['safe_count']['mean'], 0)
        self.assertEqual(batch['validation_level'], 'quick_demo')

    def test_api_experiments_do_not_collide_when_config_changes(self):
        with tempfile.TemporaryDirectory() as out:
            request = {'population':120,'seeds':[11], 'policies':['S0'], 'output_dir':out}
            first = service.run_experiment(request)
            second = service.run_experiment({**request,'scenario_overrides':{'vehicles':0}})
        self.assertNotEqual(first['experiment_id'],second['experiment_id'])
        self.assertEqual(second['comparison']['scenario_config']['vehicles'],0)

    def test_grid_contains_early_warnings_and_valid_order(self):
        candidates = list(candidate_grid(DEFAULT_SCENARIO_CONFIG))
        self.assertEqual({c.warning_lead_minutes for c in candidates},{90,120,150})
        self.assertTrue(all(c.warning_lead_minutes >= c.order_lead_minutes for c in candidates))

    def test_api_fleet_comparison_preserves_budget_and_negative_control(self):
        with tempfile.TemporaryDirectory() as out:
            result=service.run_experiment({'experiment':'transport_sensitivity','population':120,
                'seeds':[42], 'scenario_overrides':{'dispatch_mode':'balanced_coverage'},'output_dir':out})
        data=result['comparison']
        self.assertEqual(data['scenario_config']['dispatch_mode'],'policy_priority')
        self.assertIn('balanced',data['summary'])
        self.assertEqual(data['summary']['zero_vehicles']['safe_count']['mean'],0)
        self.assertEqual(data['summary']['balanced']['policy_cost'],data['summary']['reference']['policy_cost'])
        rows={r['variant_id']:r for r in data['runs']}
        self.assertNotEqual(rows['balanced']['scenario_hash'],rows['reference']['scenario_hash'])

    def test_route_duration_reaches_real_arrival_times(self):
        config = normalize_scenario_config({'routes':[{'id':'south','origin_id':'south_valley','travel_minutes':11}]})
        result = run_policy('S5',seed=42,scenario=build_scenario(42,500,config))
        people = [p for p in result.people if p.route_id=='south' and p.sheltered_minute is not None]
        self.assertTrue(people)
        self.assertTrue(all(p.sheltered_minute-p.transit_minute==11 for p in people))
