"""Persisted history must survive failures, out-of-order completion and races."""
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import tempfile
import unittest

from botocore.response import StreamingBody
from botocore.stub import ANY, Stubber
from restoreproof.s3.client import create_client

try:
    from restoreproof.s3.evidence import publish_report, PublicationError
except ImportError:
    publish_report = PublicationError = None


def report_payload(run_id='a'*32, status='PASS', started=None):
    return dict(schema_version=1, role='s3-recovery', phase='complete', run_id=run_id,
                started_at=(started or datetime.now(timezone.utc)).isoformat(), status=status,
                cleanup={'status': 'PASS'}, checks=[], backup={}, implementation={}, errors=[],
                report_path='C:/private/local/path/report.json')


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(publish_report, 'remote recovery evidence publishing is not implemented')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'report.json'
        self.client = create_client(endpoint='http://127.0.0.1:5000')
        self.addCleanup(self.client.close)
        self.stub = Stubber(self.client)
        self.stub.activate()
        self.addCleanup(self.stub.deactivate)
        self.bucket, self.owner = 'restoreproof-test', '123456789012'
        self.history_request = dict(Bucket=self.bucket, Key='evidence/chisel/history.json', ExpectedBucketOwner=self.owner)

    def write_report(self, *, fresh_history=False, **changes):
        self.report = report_payload(**changes)
        self.path.write_text(json.dumps(self.report))
        self.stub.add_response('put_object', {}, dict(Bucket=self.bucket,
            Key='evidence/chisel/runs/' + self.report['run_id'] + '.json', ExpectedBucketOwner=self.owner,
            Body=ANY, ContentType='application/json', ServerSideEncryption='AES256', IfNoneMatch='*'))
        seed = {**self.history_request, 'Body': ANY, 'ContentType': 'application/json',
                'ServerSideEncryption': 'AES256', 'IfNoneMatch': '*'}
        if fresh_history:
            self.stub.add_response('put_object', {}, seed)
        else:
            self.stub.add_client_error('put_object', service_error_code='PreconditionFailed', expected_params=seed)

    def previous(self, history, etag='"old"'):
        data = json.dumps(history).encode()
        self.stub.add_response('get_object', dict(Body=StreamingBody(io.BytesIO(data), len(data)),
            ContentLength=len(data), ETag=etag), self.history_request)

    def publish(self):
        return publish_report(self.client, self.path, bucket=self.bucket, expected_bucket_owner=self.owner)

    def test_first_report_creates_history_without_overwriting_another_writer(self):
        self.write_report(fresh_history=True)
        # No ListBucket grant: seed conditionally before GET so a missing index cannot return 403.
        self.previous({'schema_version': 1, 'recent_runs': []})
        self.stub.add_response('put_object', {}, {**self.history_request, 'Body': ANY,
            'ContentType': 'application/json', 'ServerSideEncryption': 'AES256', 'IfMatch': '"old"'})
        history = self.publish()
        self.assertEqual(history['last_success']['run_id'], 'a'*32)
        self.stub.assert_no_pending_responses()

    def test_denied_history_read_does_not_reset_it(self):
        self.write_report()
        self.stub.add_client_error('get_object', service_error_code='AccessDenied', expected_params=self.history_request)
        with self.assertRaises(PublicationError):
            self.publish()
        self.stub.assert_no_pending_responses()

    def test_conditional_write_conflict_rereads_and_preserves_newer_success(self):
        from restoreproof.s3.history import summarize, merge_history
        now = datetime.now(timezone.utc)
        self.write_report(status='FAIL', started=now)
        old = merge_history({}, summarize(report_payload('b'*32, started=now - timedelta(days=1))))
        newer = merge_history(old, summarize(report_payload('c'*32, started=now + timedelta(seconds=1))))
        self.previous(old)
        params = {**self.history_request, 'Body': ANY, 'ContentType': 'application/json',
                  'ServerSideEncryption': 'AES256', 'IfMatch': '"old"'}
        self.stub.add_client_error('put_object', service_error_code='PreconditionFailed', expected_params=params)
        self.previous(newer, '"new"')
        self.stub.add_response('put_object', {}, {**params, 'IfMatch': '"new"'})
        history = self.publish()
        self.assertEqual(history['last_success']['run_id'], 'c'*32)
        self.assertEqual(history['latest_attempt']['run_id'], 'c'*32)
        self.assertEqual(len(history['recent_runs']), 3)

    def test_invalid_report_is_not_published(self):
        self.path.write_text('{"status":"PASS"}')
        with self.assertRaises(PublicationError):
            self.publish()

    def test_corrupt_history_is_not_overwritten(self):
        self.write_report()
        self.previous({'schema_version': 999, 'recent_runs': []})
        with self.assertRaises(PublicationError):
            self.publish()

    def test_cleanup_incomplete_is_not_last_success(self):
        from restoreproof.s3.history import summarize, merge_history
        report = report_payload()
        report['cleanup']['status'] = 'INCOMPLETE'
        history = merge_history({}, summarize(report))
        self.assertIsNone(history['last_success'])
