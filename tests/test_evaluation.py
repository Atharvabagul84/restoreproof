"""Pure evaluation uses actual values, never mocked query behavior."""
import importlib
import unittest


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        try:
            self.contract = importlib.import_module("restoreproof.contract")
            self.evaluation = importlib.import_module("restoreproof.evaluation")
        except ImportError:
            self.fail("RestoreProof evaluation implementation is not available yet")

    def freshness(self):
        return self.contract.Freshness(sql="SELECT marker", incident_at="2026-10-06T12:00:00Z", max_data_age_seconds=60)

    def test_check_passes_equal_nested_json_and_reports_both_values(self):
        value = {"events": [1, "two", None], "valid": True}
        spec = self.contract.Check(name="data", sql="SELECT data", expected=value)
        result = self.evaluation.evaluate_check(spec, value)
        self.assertEqual(result, {"name": "data", "status": "PASS", "expected": value, "actual": value})

    def test_check_fails_different_values(self):
        spec = self.contract.Check(name="count", sql="SELECT count(*)", expected=3)
        self.assertEqual(self.evaluation.evaluate_check(spec, 2)["status"], "FAIL")

    def test_boolean_does_not_equal_a_number_at_any_depth(self):
        for expected, actual in ((True, 1), (False, 0), ({"x": [True]}, {"x": [1]})):
            spec = self.contract.Check(name="typed", sql="SELECT value", expected=expected)
            self.assertEqual(self.evaluation.evaluate_check(spec, actual)["status"], "FAIL")

    def test_check_rejects_non_json_actual_values(self):
        spec = self.contract.Check(name="value", sql="SELECT value", expected=None)
        for value in (float("nan"), float("inf"), {1: "bad"}, (1, 2)):
            with self.subTest(value=value):
                self.assertEqual(self.evaluation.evaluate_check(spec, value)["status"], "FAIL")

    def test_freshness_passes_at_exact_policy_boundary(self):
        result = self.evaluation.evaluate_freshness(self.freshness(), "2026-10-06T11:59:00Z")
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["age_seconds"], 60)
        self.assertEqual(result["max_data_age_seconds"], 60)

    def test_freshness_fails_a_stale_watermark(self):
        result = self.evaluation.evaluate_freshness(self.freshness(), "2026-10-06T11:58:59Z")
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["age_seconds"], 61)

    def test_timezone_offsets_are_compared_as_instants(self):
        result = self.evaluation.evaluate_freshness(self.freshness(), "2026-10-06T17:29:30+05:30")
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["age_seconds"], 30)

    def test_missing_malformed_and_naive_watermarks_are_incomplete(self):
        for value in (None, "", "yesterday", "2026-10-06T11:59:00", 123, True):
            with self.subTest(value=value):
                result = self.evaluation.evaluate_freshness(self.freshness(), value)
                self.assertEqual(result["status"], "INCOMPLETE")
                self.assertIsNone(result["age_seconds"])
                self.assertTrue(result["reason"])

    def test_future_watermark_is_not_an_automatic_pass(self):
        result = self.evaluation.evaluate_freshness(self.freshness(), "2026-10-06T12:00:01Z")
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertIsNone(result["age_seconds"])


if __name__ == "__main__":
    unittest.main()
