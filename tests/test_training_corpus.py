import json
import subprocess
import sys
import unittest
from pathlib import Path


class TrainingCorpusTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        subprocess.run(
            [sys.executable, "scripts/build_hongce_training_corpus.py"],
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        )
        cls.payload = json.loads(Path("data/processed/hongce_training_case_corpus.json").read_text(encoding="utf-8"))
        cls.cases = cls.payload["cases"]

    def test_all_downloaded_reports_are_training_cases(self) -> None:
        self.assertEqual(self.payload["summary"]["case_count"], 28)
        self.assertEqual(len(self.cases), 28)
        self.assertTrue(all(case["source_label"] == "FACT" for case in self.cases))

    def test_cases_have_simulation_facing_fields(self) -> None:
        required = {
            "case_id",
            "case_name",
            "scenario_class",
            "actor_chain",
            "process_trace",
            "failure_modes",
            "intervention_points",
            "observed_outcomes",
            "metric_candidates",
            "simulation_modules",
            "policy_scenarios",
        }
        for case in self.cases:
            self.assertTrue(required.issubset(case))
            self.assertIn("S0", case["policy_scenarios"])
            self.assertIn("S5", case["policy_scenarios"])
            self.assertIn("case_retrieval_rag", case["simulation_modules"])
            self.assertIn("scenario_template_generator", case["simulation_modules"])

    def test_core_extreme_disaster_cases_keep_observed_outcomes(self) -> None:
        by_name = {case["case_name"]: case for case in self.cases}
        zhengzhou = by_name["“7·20”河南郑州特大暴雨灾害调查报告"]
        shangluo = by_name["陕西商洛“7·19”高速公路桥梁垮塌灾害调查评估报告"]
        miyun = by_name["北京密云太师屯镇养老照料中心“7·28”暴雨洪水特别重大灾害调查评估报告"]

        self.assertEqual(zhengzhou["observed_outcomes"]["deaths_or_dead_missing"], "398人")
        self.assertEqual(zhengzhou["observed_outcomes"]["direct_economic_loss"], "1200.6亿元")
        self.assertEqual(shangluo["observed_outcomes"]["deaths_or_dead_missing"], "62人")
        self.assertEqual(miyun["observed_outcomes"]["deaths_or_dead_missing"], "32人")

    def test_state_machine_and_bottom_up_branch_are_declared(self) -> None:
        summary = self.payload["summary"]
        self.assertIn("warning_release", summary["state_machine"])
        self.assertIn("grassroots_or_institution_confirmation", summary["state_machine"])
        self.assertIn("review_and_rectification", summary["state_machine"])
        self.assertIn("resident_or_frontline_detection", summary["bottom_up_branch"])


if __name__ == "__main__":
    unittest.main()
