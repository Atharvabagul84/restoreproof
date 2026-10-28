"""Opt-in recovery of unchanged Chisel and genuine Auth/PostgREST services."""
import os
import json
from pathlib import Path
import unittest


@unittest.skipUnless(os.environ.get('RESTOREPROOF_APP_INTEGRATION') == '1', 'requires the prepared Chisel Docker stack')
class ChiselRecoveryTests(unittest.TestCase):
    def test_five_recovery_outcomes_and_resource_cleanup(self):
        try:
            from restoreproof.chisel.demo import run_suite
        except ImportError:
            self.fail('real application recovery suite is missing')
        suite = run_suite(Path('runs/chisel-ci'))
        self.assertEqual(suite['status'], 'PASS', suite)
        self.assertEqual(len(suite['scenarios']), 5)
        for result in suite['scenarios']:
            with self.subTest(scenario=result['scenario']):
                self.assertEqual(result['actual'], result['expected'])
                self.assertEqual(result['cleanup'], 'PASS')
                self.assertEqual(result['source_cleanup'], 'PASS')
                report = json.loads(Path(result['report_path']).read_text())
                source = json.loads(Path(result['source_report_path']).read_text())
                self.assertNotEqual(report['run_id'], source['run_id'])
                self.assertNotEqual(report['target']['database_id'], source['target']['database_id'])
                for captured in (source, report):
                    self.assertEqual(set(captured['target']['observed_isolation']),
                                     {'database', 'mail', 'gateway', 'auth', 'rest', 'app'})
                    for component in captured['target']['observed_isolation'].values():
                        self.assertEqual(component['host_mounts'], [])
                        self.assertEqual(component['published_ports'], [])
                checks = {check['name']: check for check in report['checks']}
                if result['scenario'] in {'missing-data', 'incompatible-schema'}:
                    failed = {name for name, check in checks.items() if check['status'] == 'FAIL'}
                    expected_failure = 'saved-brief-content' if result['scenario'] == 'missing-data' else 'recovered-write-cycle'
                    self.assertEqual(failed, {expected_failure})
                    self.assertEqual(checks['restored-identity']['status'], 'PASS')
                if result['scenario'] in {'auth-unavailable', 'missing-config'}:
                    self.assertEqual(report['failure_phase'], 'application-journey')
                    self.assertEqual(report['error_type'], 'DependencyUnavailable')
                    self.assertEqual(checks['email-otp-login']['status'], 'INCOMPLETE')
                if result['scenario'] == 'missing-config':
                    self.assertEqual(checks['email-otp-login']['http'], 503)
                if result['scenario'] == 'auth-unavailable':
                    self.assertEqual(report['fault_injection']['observed_state'], 'exited')
                if result['scenario'] == 'healthy':
                    self.assertEqual(checks['recovered-write-cycle']['stale_write_http'], 409)
