import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from xml.etree import ElementTree

try:
    from restoreproof.engine import verify
except ImportError:
    verify = None


def contract_file(folder):
    archive = folder / 'backup.dump'
    archive.write_bytes(b'PGDMPsynthetic-unit-test-archive')
    contract = {
        'version': 1,
        'backup': {'path': 'backup.dump', 'sha256': hashlib.sha256(archive.read_bytes()).hexdigest()},
        'checks': [{'name': 'snapshot', 'sql': "SELECT 'true'::json", 'expected': True}],
        'freshness': {'sql': 'SELECT checkpoint', 'incident_at': '2026-01-01T00:01:00Z', 'max_data_age_seconds': 60},
        'max_restore_seconds': 300,
    }
    path = folder / 'contract.json'
    path.write_text(json.dumps(contract), encoding='utf-8')
    return path


class MemoryTarget:
    """No Docker: controlled external boundary for engine failure handling."""
    def __init__(self, actual=True, watermark='2026-01-01T00:00:30Z', failure=None):
        self.actual, self.watermark, self.failure = actual, watermark, failure
        self.cleaned = False
        self.created = False

    def create(self):
        self.created = True
        if self.failure == 'create':
            raise RuntimeError('allocation unavailable')
        return {'container_id': 'unit-target', 'image_id': 'unit-image'}

    def restore(self, archive, expected_sha256):
        if self.failure == 'interrupt':
            raise KeyboardInterrupt()
        if self.failure == 'restore':
            raise RuntimeError('restore unavailable')

    def query(self, sql):
        return self.watermark if sql == 'SELECT checkpoint' else self.actual

    def cleanup(self):
        self.cleaned = True
        if self.failure == 'cleanup':
            return {'status': 'INCOMPLETE', 'remaining': ['unit-target'], 'message': 'engine unavailable'}
        return {'status': 'PASS', 'remaining': [], 'message': 'verified absent'}


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(verify, 'verification engine is not implemented')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.contract = contract_file(self.root)

    def run_target(self, target):
        return verify(self.contract, self.root / 'reports', backend_factory=lambda **kwargs: target)

    def test_healthy_restore_writes_consistent_reports_and_verifies_cleanup(self):
        target = MemoryTarget()
        report = self.run_target(target)
        self.assertEqual(report['status'], 'PASS')
        self.assertTrue(target.cleaned)
        self.assertEqual(report['exit_code'], 0)
        saved = json.loads(Path(report['report_path']).read_text(encoding='utf-8'))
        self.assertEqual(saved['status'], 'PASS')
        xml = ElementTree.parse(Path(report['report_path']).with_name('junit.xml'))
        self.assertEqual(xml.getroot().get('failures'), '0')

    def test_started_database_with_wrong_application_data_fails(self):
        report = self.run_target(MemoryTarget(actual=False))
        self.assertEqual(report['status'], 'FAIL')
        self.assertEqual(report['exit_code'], 1)
        self.assertEqual(report['cleanup']['status'], 'PASS')

    def test_stale_watermark_fails_even_when_application_checks_pass(self):
        report = self.run_target(MemoryTarget(watermark='2025-12-31T23:00:00Z'))
        self.assertEqual(report['status'], 'FAIL')
        self.assertEqual(next(c for c in report['checks'] if c['name'] == 'freshness')['status'], 'FAIL')

    def test_unknown_watermark_never_becomes_success(self):
        self.assertEqual(self.run_target(MemoryTarget(watermark=None))['status'], 'INCOMPLETE')

    def test_cleanup_failure_overrides_success(self):
        report = self.run_target(MemoryTarget(failure='cleanup'))
        self.assertEqual(report['status'], 'INCOMPLETE')
        self.assertEqual(report['exit_code'], 2)
        self.assertEqual(report['cleanup']['remaining'], ['unit-target'])

    def test_restore_failure_still_cleans_allocated_target(self):
        target = MemoryTarget(failure='restore')
        self.assertEqual(self.run_target(target)['status'], 'INCOMPLETE')
        self.assertTrue(target.cleaned)

    def test_failed_allocation_still_attempts_owned_cleanup(self):
        target = MemoryTarget(failure='create')
        self.assertEqual(self.run_target(target)['status'], 'INCOMPLETE')
        self.assertTrue(target.cleaned)

    def test_keyboard_interrupt_writes_partial_report_and_cleans(self):
        target = MemoryTarget(failure='interrupt')
        report = self.run_target(target)
        self.assertEqual(report['status'], 'INCOMPLETE')
        self.assertTrue(target.cleaned)
        self.assertTrue(Path(report['report_path']).is_file())

    def test_checksum_mismatch_does_not_construct_backend(self):
        (self.root / 'backup.dump').write_bytes(b'PGDMPmodified')
        def forbidden(**kwargs):
            self.fail('backend must not be constructed for invalid archive')
        report = verify(self.contract, self.root / 'reports', backend_factory=forbidden)
        self.assertEqual(report['status'], 'INVALID')
        self.assertEqual(report['exit_code'], 3)

    def test_repeated_runs_preserve_separate_evidence(self):
        first = self.run_target(MemoryTarget())
        second = self.run_target(MemoryTarget(actual=False))
        self.assertNotEqual(first['run_id'], second['run_id'])
        self.assertEqual(json.loads(Path(first['report_path']).read_text())['status'], 'PASS')


if __name__ == '__main__':
    unittest.main()
