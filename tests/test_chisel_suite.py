import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from restoreproof.chisel.demo import run_suite, SCENARIOS
from restoreproof.chisel.journey import REQUIRED_CHECKS


def result(scenario, *, wrong_failure=False, interrupted=False):
    checks = [{'name': name, 'status': 'PASS'} for name in REQUIRED_CHECKS]
    for check in checks:
        if scenario == 'missing-data' and check['name'] == 'saved-brief-content':
            check['status'] = 'FAIL'
        if scenario == 'incompatible-schema' and check['name'] == 'recovered-write-cycle':
            check['status'] = 'FAIL'
    if scenario in {'auth-unavailable', 'missing-config'}:
        checks = [{'name': 'unauthenticated-denied', 'status': 'PASS'},
                  {'name': 'email-otp-login', 'status': 'INCOMPLETE', 'http': 503 if scenario == 'missing-config' else 502}]
    return {'status': SCENARIOS[scenario], 'cleanup': {'status': 'PASS'}, 'source_cleanup': {'status': 'PASS'},
            'report_path': 'unused-report.json', 'source_report_path': 'unused-source.json', 'checks': checks,
            'failure_phase': 'restore' if wrong_failure else 'application-journey',
            'error_type': 'KeyboardInterrupt' if interrupted else 'DependencyUnavailable',
            'fault_injection': {'observed_state': 'exited'}}


class SuiteVerdictTests(unittest.TestCase):
    def exercise(self, override):
        def demo(output, scenario, **kwargs):
            return result(scenario, **(override if scenario == 'auth-unavailable' else {}))
        with tempfile.TemporaryDirectory() as temp, patch('restoreproof.chisel.demo.prepare_images', return_value={}), \
                patch('restoreproof.chisel.demo.run_demo', demo):
            return run_suite(Path(temp))

    def test_expected_status_with_wrong_failure_cause_is_not_a_successful_negative_test(self):
        self.assertEqual(self.exercise({'wrong_failure': True})['status'], 'FAIL')

    def test_matching_causes_and_cleanup_make_suite_pass(self):
        self.assertEqual(self.exercise({})['status'], 'PASS')

    def test_interruption_stops_before_allocating_another_scenario(self):
        suite = self.exercise({'interrupted': True})
        self.assertEqual(suite['status'], 'INCOMPLETE')
        self.assertEqual(len(suite['scenarios']), 4)
