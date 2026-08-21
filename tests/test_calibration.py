from __future__ import annotations

import unittest

from hongce.calibration import (
    build_parameter_library,
    load_case_corpus,
    scenario_config_from_parameters,
    select_parameter_set,
)


class CalibrationTest(unittest.TestCase):
    def test_build_parameter_library_from_mem_cases(self) -> None:
        library = build_parameter_library(load_case_corpus())
        self.assertEqual(library["label"], "FACT_DERIVED_PARAMETER_LIBRARY")
        self.assertGreaterEqual(library["quality"]["case_count"], 28)
        self.assertGreater(library["quality"]["parameter_estimate_count"], 250)
        self.assertIn("CASE_DERIVED", library["quality"]["source_label_counts"])
        self.assertIn("ALL_CASES", library["aggregates"])

    def test_case_parameters_include_sources_confidence_and_review_status(self) -> None:
        library = build_parameter_library(load_case_corpus())
        case = library["cases"][0]
        estimate = case["parameter_estimates"][0]
        self.assertIn("source_label", estimate)
        self.assertIn("confidence", estimate)
        self.assertIn("review_status", estimate)
        self.assertLessEqual(estimate["value_min"], estimate["value_max"])
        self.assertIn("missing_review_items", case["calibration_readiness"])

    def test_parameter_library_derives_scenario_config_suggestion(self) -> None:
        library = build_parameter_library(load_case_corpus())
        config = scenario_config_from_parameters(library, case_id="HC-MEM-001")
        self.assertIn("warning_minute", config)
        self.assertIn("evacuation_order_minute", config)
        self.assertIn("communication_failure_rate", config)
        self.assertLess(config["warning_minute"], config["evacuation_order_minute"])
        self.assertLessEqual(config["communication_failure_rate"], 0.95)

    def test_select_parameter_set_can_use_scenario_class_aggregate(self) -> None:
        library = build_parameter_library(load_case_corpus())
        parameters = select_parameter_set(library, scenario_class="极端降雨洪涝/山洪及基础设施失效")
        names = {item["name"] for item in parameters}
        self.assertIn("communication_failure_rate", names)
        self.assertIn("route_failure_probability", names)


if __name__ == "__main__":
    unittest.main()
