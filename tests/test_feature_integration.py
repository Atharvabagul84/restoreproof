"""End-to-end public CLI checks for application and ledger recovery demos."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


@unittest.skipUnless(os.environ.get('RESTOREPROOF_INTEGRATION') == '1', 'requires Docker; opt in explicitly')
class FeatureIntegrationTests(unittest.TestCase):
    def scenario(self, scenario):
        evidence = os.environ.get('RESTOREPROOF_EVIDENCE_DIR')
        if evidence:
            output = Path(evidence).resolve() / self.id().split('.')[-1]
        else:
            temporary = tempfile.TemporaryDirectory()
            self.addCleanup(temporary.cleanup)
            output = Path(temporary.name)
        result = subprocess.run([sys.executable, '-m', 'restoreproof', 'demo', '--scenario', scenario,
                                 '--output', str(output)], capture_output=True, text=True, timeout=240)
        self.assertTrue(result.stdout.strip(), 'CLI must implement the requested recovery scenario')
        summary = json.loads(result.stdout)
        self.assertIn('report_path', summary)
        report = json.loads(Path(summary['report_path']).read_text(encoding='utf-8'))
        self.assertEqual(report['cleanup']['status'], 'PASS')
        self.assertEqual(report['cleanup']['remaining'], [])
        self.assertEqual(result.returncode, report['exit_code'])
        return report

    def test_complete_ledger_passes(self):
        report = self.scenario('ledger-healthy')
        self.assertEqual(report['status'], 'PASS', report)
        ledger = next(c for c in report['checks'] if c['name'] == 'committed-write-ledger')
        self.assertEqual(ledger['status'], 'PASS')
        self.assertEqual([ledger[k] for k in ('expected_count', 'recovered_count', 'matched_count')], [3, 3, 3])

    def test_interior_write_loss_fails_while_latest_checkpoint_passes(self):
        report = self.scenario('ledger-gap')
        self.assertEqual(report['status'], 'FAIL', report)
        self.assertEqual(next(c for c in report['checks'] if c['name'] == 'freshness')['status'], 'PASS')
        ledger = next(c for c in report['checks'] if c['name'] == 'committed-write-ledger')
        self.assertEqual(ledger['status'], 'FAIL')
        self.assertEqual([ledger[k] for k in ('expected_count', 'recovered_count', 'matched_count')], [3, 2, 2])
        self.assertEqual(ledger['missing_count'], 1)
        self.assertEqual(ledger['missing_write_ids'], ['write-002'])
        for category in ('unexpected', 'duplicate_id', 'duplicate_sequence', 'payload_mismatch',
                         'sequence_mismatch', 'acknowledged_at_mismatch'):
            self.assertEqual(ledger[category + '_count'], 0, ledger)

    def test_restored_application_supports_authorized_read_and_write(self):
        report = self.scenario('application')
        self.assertEqual(report['status'], 'PASS', report)
        journey = [c for c in report['checks'] if c['name'].startswith('application-')]
        self.assertGreaterEqual(len(journey), 5)
        self.assertTrue(all(c['status'] == 'PASS' for c in journey))

    def test_database_checks_pass_but_missing_required_order_fails_journey(self):
        report = self.scenario('application-broken')
        self.assertEqual(report['status'], 'FAIL', report)
        self.assertEqual(next(c for c in report['checks'] if c['name'] == 'snapshot-data')['status'], 'PASS')
        self.assertTrue(any(c['status'] == 'FAIL' for c in report['checks'] if c['name'].startswith('application-')))
