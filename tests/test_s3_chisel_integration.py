"""Full free local benchmark: versioned object -> Chisel -> evidence -> cleanup."""
import json
import os
from pathlib import Path
import unittest


@unittest.skipUnless(os.environ.get('RESTOREPROOF_S3_APP_INTEGRATION') == '1', 'requires Docker and local Moto')
class S3ChiselTests(unittest.TestCase):
    def test_real_recovery_and_five_retrieval_failure_causes(self):
        try:
            from restoreproof.s3.demo import run_demo
        except ImportError:
            self.fail('S3-to-Chisel showcase is not implemented')
        suite = run_demo(Path('runs/s3-chisel'))
        self.assertEqual(suite['status'], 'PASS', suite)
        self.assertEqual(suite['source_cleanup']['status'], 'PASS')
        self.assertEqual(suite['storage_cleanup'], 'PASS')
        self.assertEqual(len(suite['scenarios']), 6)
        healthy = suite['scenarios'][0]
        self.assertEqual(healthy['scenario'], 'healthy')
        report = json.loads(Path(healthy['report_path']).read_text())
        self.assertEqual(report['retrieval']['version_id'], suite['original_version_id'])
        self.assertNotEqual(suite['original_version_id'], suite['newer_version_id'])
        self.assertEqual(report['status'], 'PASS')
        checks = {item['name']: item for item in report['checks']}
        self.assertEqual(checks['recovered-write-cycle']['stale_write_http'], 409)
        self.assertEqual(set(report['target']['observed_isolation']), {'database', 'mail', 'gateway', 'auth', 'rest', 'app'})
        for scenario in suite['scenarios'][1:]:
            failed = json.loads(Path(scenario['report_path']).read_text())
            self.assertEqual(failed['failure_code'], scenario['scenario'])
            self.assertEqual(failed['target'], {})
            self.assertEqual(failed['cleanup']['status'], 'PASS')
            self.assertEqual(failed['download_cleanup']['status'], 'PASS')
        self.assertEqual(suite['history']['last_success']['run_id'], report['run_id'])
        self.assertEqual(len(suite['history']['recent_runs']), 6)
        from restoreproof.reporting.export import write_html
        rendered = write_html([Path(suite['summary_path']).parent], Path(suite['summary_path']).with_name('report.html'))
        self.assertEqual(rendered['run_count'], 6)
        self.assertEqual(rendered['scopes'][0]['scope'], 'local')
        self.assertEqual(rendered['scopes'][0]['last_success']['run_id'], report['run_id'])
        self.assertEqual(rendered['scopes'][0]['latest_attempt']['status'], 'INCOMPLETE')
