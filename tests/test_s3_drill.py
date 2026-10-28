"""A retrieval failure cannot reach Chisel or overwrite the last success."""
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from botocore.response import StreamingBody
from botocore.stub import Stubber
from restoreproof.chisel.contract import SOURCE_COMMIT
from restoreproof.chisel.journey import REQUIRED_CHECKS
from restoreproof.s3.client import create_client

try:
    from restoreproof.s3.drill import run_drill
    from restoreproof.s3.history import read_history
except ImportError:
    run_drill = read_history = None

DATA = b'PGDMPtest-backup'


def plan_payload():
    return dict(version=1, application='chisel', source_commit=SOURCE_COMMIT,
        owner_id='11111111-1111-4111-8111-111111111111',
        workspace_id='22222222-2222-4222-8222-222222222222',
        outsider_workspace_id='33333333-3333-4333-8333-333333333333',
        brief_id='44444444-4444-4444-8444-444444444444', brief_sha256='a'*64,
        backup=dict(bucket='restoreproof-test', key='backups/chisel/test.dump', version_id='v1',
                    sha256=hashlib.sha256(DATA).hexdigest(), captured_at=datetime.now(timezone.utc).isoformat(),
                    max_age_seconds=3600, expected_bucket_owner='123456789012'))


def application_pass(contract, output, **kwargs):
    payload = json.loads(Path(contract).read_text())
    archive = Path(contract).parent / payload['backup']['path']
    assert archive.read_bytes() == DATA
    return dict(status='PASS', exit_code=0, run_id='a'*32, report_path=str(Path(output)/('a'*32)/'report.json'),
                checks=[{'name': name, 'status': 'PASS'} for name in sorted(REQUIRED_CHECKS | {'recovery-duration'})],
                cleanup={'status': 'PASS', 'remaining': []}, target={'database_id': 'b'*64})


class S3DrillTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(run_drill, 'S3 application recovery orchestration is not implemented')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.plan = self.root / 'contract.json'
        self.payload = plan_payload()
        self.plan.write_text(json.dumps(self.payload))
        self.output = self.root / 'runs'
        self.client = create_client(endpoint='http://127.0.0.1:5000')
        self.addCleanup(self.client.close)
        self.stub = Stubber(self.client)
        self.stub.activate()
        self.addCleanup(self.stub.deactivate)
        self.request = dict(Bucket='restoreproof-test', Key='backups/chisel/test.dump',
                            VersionId='v1', ExpectedBucketOwner='123456789012')

    def ready(self, data=DATA):
        self.stub.add_response('get_object', dict(Body=StreamingBody(io.BytesIO(data), len(data)),
            ContentLength=len(data), VersionId='v1', LastModified=datetime.now(timezone.utc)), self.request)

    def test_verified_backup_reaches_app_and_download_is_removed(self):
        self.ready()
        with patch('restoreproof.s3.drill.verify_app', side_effect=application_pass):
            report = run_drill(self.plan, self.output, client=self.client)
        self.assertEqual(report['status'], 'PASS', report)
        self.assertEqual(report['retrieval']['version_id'], 'v1')
        self.assertEqual(report['cleanup']['status'], 'PASS')
        self.assertFalse((Path(report['report_path']).parent / 'backup.dump').exists())
        self.assertEqual(len(report['implementation']['source_sha256']), 64)
        self.assertEqual(json.loads(Path(report['report_path']).read_text())['status'], 'PASS')
        self.assertTrue(Path(report['report_path']).with_name('junit.xml').exists())

    def test_checksum_failure_cannot_allocate_app(self):
        self.ready(b'PGDMPwrong')
        with patch('restoreproof.s3.drill.verify_app') as app:
            report = run_drill(self.plan, self.output, client=self.client)
        app.assert_not_called()
        self.assertEqual(report['status'], 'FAIL')
        self.assertEqual(report['failure_code'], 'checksum-mismatch')
        self.assertEqual(report['cleanup']['status'], 'PASS')

    def test_failed_run_does_not_replace_last_success(self):
        self.ready()
        with patch('restoreproof.s3.drill.verify_app', side_effect=application_pass):
            success = run_drill(self.plan, self.output, client=self.client)
        self.stub.add_client_error('get_object', service_error_code='AccessDenied', expected_params=self.request)
        failed = run_drill(self.plan, self.output, client=self.client)
        history = read_history(self.output)
        self.assertEqual(history['latest_attempt']['run_id'], failed['run_id'])
        self.assertEqual(history['last_success']['run_id'], success['run_id'])
        self.assertEqual(len(history['recent_runs']), 2)

    def test_app_failure_and_cleanup_failure_never_become_pass(self):
        for field in ('status', 'cleanup'):
            with self.subTest(field=field):
                self.ready()
                def incomplete(*args, **kwargs):
                    result = application_pass(*args, **kwargs)
                    if field == 'status':
                        result.update(status='FAIL', exit_code=1)
                        result['checks'][0]['status'] = 'FAIL'
                    else:
                        result['cleanup'] = {'status': 'INCOMPLETE', 'remaining': ['owned-container']}
                    return result
                with patch('restoreproof.s3.drill.verify_app', side_effect=incomplete):
                    report = run_drill(self.plan, self.output, client=self.client)
                self.assertNotEqual(report['status'], 'PASS')

    def test_partial_green_app_report_is_incomplete(self):
        self.ready()
        def partial(*args, **kwargs):
            result = application_pass(*args, **kwargs)
            result['checks'].pop()
            return result
        with patch('restoreproof.s3.drill.verify_app', side_effect=partial):
            report = run_drill(self.plan, self.output, client=self.client)
        self.assertEqual(report['status'], 'INCOMPLETE')

    def test_application_exception_does_not_claim_cleanup_was_verified(self):
        self.ready()
        with patch('restoreproof.s3.drill.verify_app', side_effect=RuntimeError('lost cleanup evidence')):
            report = run_drill(self.plan, self.output, client=self.client)
        self.assertEqual(report['status'], 'INCOMPLETE')
        self.assertEqual(report['cleanup']['status'], 'INCOMPLETE')

    def test_leftover_partial_download_makes_cleanup_incomplete(self):
        from restoreproof.s3.retrieval import RetrievalError
        def failed_download(client, spec, destination):
            destination.with_name('.s3-download-leftover').write_bytes(b'partial')
            raise RetrievalError('download-interrupted')
        with patch('restoreproof.s3.drill.retrieve', side_effect=failed_download):
            report = run_drill(self.plan, self.output, client=self.client)
        self.assertEqual(report['download_cleanup']['status'], 'INCOMPLETE')
        self.assertEqual(report['cleanup']['status'], 'INCOMPLETE')

    def test_invalid_and_duplicate_key_contracts_fail_before_download(self):
        for content in ['{"version":1,"version":1}', '{"version":NaN}', '{"backup":{"version_id":"null"}}']:
            self.plan.write_text(content)
            with patch('restoreproof.s3.drill.verify_app') as app:
                report = run_drill(self.plan, self.output, client=self.client)
            self.assertEqual(report['status'], 'INVALID')
            app.assert_not_called()

    def test_history_recognizes_interrupted_journal_without_claiming_success(self):
        folder = self.output / ('c'*32)
        folder.mkdir(parents=True)
        (folder / 'report.json').write_text(json.dumps(dict(schema_version=1, role='s3-recovery',
            run_id='c'*32, started_at=datetime.now(timezone.utc).isoformat(), status='INCOMPLETE',
            cleanup={'status': 'NOT_REQUIRED'}, backup=self.payload['backup'])))
        history = read_history(self.output)
        self.assertEqual(history['latest_attempt']['status'], 'INCOMPLETE')
        self.assertIsNone(history['last_success'])
