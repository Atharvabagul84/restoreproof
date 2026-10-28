"""Real PostgreSQL: opt in with RESTOREPROOF_INTEGRATION=1."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import uuid


@unittest.skipUnless(os.environ.get('RESTOREPROOF_INTEGRATION') == '1', 'requires Docker; opt in explicitly')
class DockerIntegrationTests(unittest.TestCase):
    def demo(self, scenario):
        result = subprocess.run([sys.executable, '-m', 'restoreproof', 'demo', '--scenario', scenario,
                                 '--output', str(self.root / scenario)], capture_output=True, text=True, timeout=240)
        self.assertTrue(result.stdout.strip(), result.stderr)
        summary = json.loads(result.stdout)
        self.assertIn('report_path', summary, summary)
        report = json.loads(Path(summary['report_path']).read_text(encoding='utf-8'))
        self.assertEqual(report['cleanup']['status'], 'PASS', report)
        self.assertEqual(report['cleanup']['remaining'], [])
        return result, summary, report

    def setUp(self):
        evidence = os.environ.get('RESTOREPROOF_EVIDENCE_DIR')
        if evidence:
            self.root = Path(evidence).resolve() / self.id().split('.')[-1]
            self.root.mkdir(parents=True, exist_ok=True)
            return
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_healthy_real_database_restore_passes(self):
        result, _, report = self.demo('healthy')
        self.assertEqual(result.returncode, 0, report)
        self.assertEqual(report['status'], 'PASS')

    def test_stale_real_backup_fails_recovery_policy(self):
        result, _, report = self.demo('stale')
        self.assertEqual(result.returncode, 1, report)
        self.assertEqual(next(c for c in report['checks'] if c['name'] == 'freshness')['status'], 'FAIL')

    def test_semantically_invalid_database_starts_but_fails_application_check(self):
        result, _, report = self.demo('inconsistent')
        self.assertEqual(result.returncode, 1, report)
        self.assertEqual(next(c for c in report['checks'] if c['name'] == 'revision-snapshots')['status'], 'FAIL')

    def test_matching_checksum_does_not_make_truncated_archive_restorable(self):
        result, _, report = self.demo('corrupt')
        self.assertEqual(result.returncode, 2, report)
        self.assertEqual(report['status'], 'INCOMPLETE')
        self.assertEqual(report['errors'][0]['phase'], 'restore')

    def test_live_target_has_declared_isolation_and_resource_limits(self):
        from restoreproof.contract import APPROVED_IMAGE
        from restoreproof.docker_postgres import DockerPostgres
        target = DockerPostgres(APPROVED_IMAGE, uuid.uuid4().hex)
        try:
            created = target.create()
            result = subprocess.run(['docker', 'inspect', created['container_id']],
                                    capture_output=True, text=True, check=True, timeout=15)
            inspected = json.loads(result.stdout)[0]
            host = inspected['HostConfig']
            self.assertEqual(host['NetworkMode'], 'none')
            self.assertFalse(host['PortBindings'])
            self.assertFalse(host['Binds'])
            self.assertEqual(host['Memory'], 512 * 1024 * 1024)
            self.assertEqual(host['NanoCpus'], 1000000000)
            self.assertEqual(host['PidsLimit'], 128)
            self.assertIn('/var/lib/postgresql/data', host['Tmpfs'])
            self.assertFalse(any(m['Type'] in {'bind', 'volume'} for m in inspected['Mounts']))
            evidence = {'container_id': created['container_id'], 'image_id': created['image_id'],
                        'network': host['NetworkMode'], 'ports': host['PortBindings'],
                        'memory_bytes': host['Memory'], 'nano_cpus': host['NanoCpus'],
                        'pids_limit': host['PidsLimit'], 'tmpfs': host['Tmpfs']}
            (self.root / 'isolation.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
        finally:
            self.assertEqual(target.cleanup()['status'], 'PASS')

    def test_crash_recovery_cleanup_is_repeatable_on_a_real_container(self):
        from restoreproof.contract import APPROVED_IMAGE
        from restoreproof.docker_postgres import DockerPostgres
        run_id = uuid.uuid4().hex
        target = DockerPostgres(APPROVED_IMAGE, run_id)
        try:
            target.create()
            recovered = DockerPostgres.cleanup_run(APPROVED_IMAGE, run_id)
            repeated = DockerPostgres.cleanup_run(APPROVED_IMAGE, run_id)
            self.assertEqual(recovered['status'], 'PASS')
            self.assertEqual(repeated['status'], 'PASS')
            (self.root / 'cleanup-recovery.json').write_text(
                json.dumps({'run_id': run_id, 'recovered': recovered, 'repeated': repeated}, indent=2), encoding='utf-8')
        finally:
            self.assertEqual(target.cleanup()['status'], 'PASS')


if __name__ == '__main__':
    unittest.main()
