"""Version-pinned downloads, bounded failure behavior, and no cloud fallback."""
from datetime import datetime, timedelta, timezone
import hashlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from botocore.response import StreamingBody
from botocore.stub import Stubber

try:
    from restoreproof.s3.contract import S3Backup
    from restoreproof.s3.client import create_client
    from restoreproof.s3.retrieval import retrieve, RetrievalError
except ImportError:
    S3Backup = create_client = retrieve = RetrievalError = None

NOW = datetime(2026, 10, 7, 12, tzinfo=timezone.utc)
DATA = b'PGDMPversion-one'


def backup_payload(**changes):
    return dict(bucket='restoreproof-test', key='backups/chisel.dump', version_id='version-one',
                sha256=hashlib.sha256(DATA).hexdigest(), captured_at=NOW.isoformat(),
                max_age_seconds=3600, expected_bucket_owner='123456789012', **changes)


class RetrievalTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(retrieve, 'version-pinned S3 retrieval is not implemented')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'backup.dump'
        self.spec = S3Backup.model_validate(backup_payload())
        self.client = create_client(mode='local', endpoint='http://127.0.0.1:5000', region='us-east-1')
        self.addCleanup(self.client.close)
        self.stub = Stubber(self.client)
        self.stub.activate()
        self.addCleanup(self.stub.deactivate)
        self.request = dict(Bucket=self.spec.bucket, Key=self.spec.key, VersionId=self.spec.version_id,
                            ExpectedBucketOwner=self.spec.expected_bucket_owner)

    def response(self, data=DATA, **changes):
        self.raw = io.BytesIO(data)
        response = dict(Body=StreamingBody(self.raw, len(data)), ContentLength=len(data),
                        VersionId='version-one', LastModified=NOW)
        response.update(changes)
        self.stub.add_response('get_object', response, self.request)

    def rejected(self, code):
        with self.assertRaises(RetrievalError) as caught:
            retrieve(self.client, self.spec, self.path, now=NOW)
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(list(self.path.parent.iterdir()), [])
        return caught.exception

    def test_exact_version_owner_and_hash_are_recorded_and_body_closed(self):
        self.response()
        receipt = retrieve(self.client, self.spec, self.path, now=NOW)
        self.assertEqual(self.path.read_bytes(), DATA)
        self.assertEqual(receipt['version_id'], 'version-one')
        self.assertEqual(receipt['sha256'], hashlib.sha256(DATA).hexdigest())
        self.assertEqual(receipt['size_bytes'], len(DATA))
        self.assertEqual(datetime.fromisoformat(receipt['captured_at']), NOW)
        self.assertTrue(self.raw.closed)
        self.stub.assert_no_pending_responses()

    def test_checksum_mismatch_removes_partial_file(self):
        self.response(b'PGDMPchanged')
        self.assertEqual(self.rejected('checksum-mismatch').status, 'FAIL')
        self.assertTrue(self.raw.closed)

    def test_server_cannot_substitute_another_version(self):
        self.response(VersionId='version-two')
        self.rejected('version-mismatch')
        self.assertTrue(self.raw.closed)

    def test_oversize_header_is_rejected_before_reading_body(self):
        self.response(ContentLength=64 * 1024 * 1024 + 1)
        self.rejected('archive-too-large')

    def test_truncated_body_is_not_committed(self):
        self.response(Body=StreamingBody(io.BytesIO(DATA[:5]), len(DATA)))
        self.rejected('download-interrupted')

    def test_read_timeout_is_not_a_checksum_failure(self):
        from botocore.exceptions import ReadTimeoutError
        body = StreamingBody(io.BytesIO(DATA), len(DATA))
        self.response(Body=body)
        with patch.object(body, 'read', side_effect=ReadTimeoutError(endpoint_url='secret-value')):
            error = self.rejected('download-interrupted')
        self.assertNotIn('secret-value', str(error))

    def test_interrupt_cleans_partial_download(self):
        body = StreamingBody(io.BytesIO(DATA), len(DATA))
        self.response(Body=body)
        with patch.object(body, 'read', side_effect=[DATA[:4], KeyboardInterrupt()]):
            self.rejected('download-interrupted')

    def test_body_size_mismatch_is_not_committed(self):
        self.response(ContentLength=len(DATA) - 1)
        self.rejected('size-mismatch')

    def test_download_deadline_removes_partial_file(self):
        self.response()
        with patch('restoreproof.s3.retrieval.time.monotonic', side_effect=[0, 1, 61]):
            self.rejected('download-timeout')

    def test_stale_backup_fails_before_get_object(self):
        self.spec = self.spec.model_copy(update={'captured_at': NOW - timedelta(hours=2)})
        self.assertEqual(self.rejected('stale-backup').status, 'FAIL')

    def test_future_capture_is_invalid(self):
        self.spec = self.spec.model_copy(update={'captured_at': NOW + timedelta(seconds=1)})
        self.assertEqual(self.rejected('future-backup').status, 'INVALID')

    def test_upload_time_does_not_refresh_capture_time(self):
        self.response(LastModified=NOW + timedelta(days=1))
        receipt = retrieve(self.client, self.spec, self.path, now=NOW)
        self.assertEqual(receipt['age_seconds'], 0)

    def test_existing_destination_is_never_replaced(self):
        self.path.write_bytes(b'keep me')
        with self.assertRaises(RetrievalError):
            retrieve(self.client, self.spec, self.path, now=NOW)
        self.assertEqual(self.path.read_bytes(), b'keep me')

    def test_missing_version_and_access_denied_have_distinct_safe_codes(self):
        for upstream, expected in [('NoSuchVersion', 'missing-object'), ('NoSuchKey', 'missing-object'),
                                   ('AccessDenied', 'access-denied')]:
            with self.subTest(upstream=upstream):
                self.stub.add_client_error('get_object', service_error_code=upstream,
                                           service_message='private upstream detail', expected_params=self.request)
                error = self.rejected(expected)
                self.assertEqual(error.status, 'INCOMPLETE')
                self.assertNotIn('private upstream detail', str(error))


class S3BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(create_client, 'explicit local/cloud S3 configuration is not implemented')

    def test_no_unversioned_or_ambiguous_identity(self):
        for name, value in [('version_id', 'null'), ('version_id', ''), ('bucket', 's3://bucket'),
                            ('key', 'bad\nkey'), ('expected_bucket_owner', '123'),
                            ('captured_at', '2026-10-07T12:00:00'), ('max_age_seconds', True)]:
            payload = backup_payload()
            payload[name] = value
            with self.subTest(name=name), self.assertRaises(ValueError):
                S3Backup.model_validate(payload)

    def test_local_mode_refuses_non_loopback_or_ambiguous_endpoint(self):
        for endpoint in [None, 'https://s3.amazonaws.com', 'http://localhost:5000',
                         'http://127.0.0.1.evil:5000', 'http://user:pass@127.0.0.1:5000',
                         'http://127.0.0.1:5000/path', 'http://127.0.0.1:5000?q=x']:
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                create_client(mode='local', endpoint=endpoint, region='us-east-1')

    def test_local_mode_ignores_ambient_cloud_credentials_and_endpoint(self):
        with patch.dict(os.environ, {'AWS_ACCESS_KEY_ID': 'REAL-KEY', 'AWS_SECRET_ACCESS_KEY': 'REAL-SECRET',
                                     'AWS_ENDPOINT_URL_S3': 'https://example.com'}):
            client = create_client(mode='local', endpoint='http://127.0.0.1:5000', region='us-east-1')
        self.addCleanup(client.close)
        self.assertEqual(client.meta.endpoint_url, 'http://127.0.0.1:5000')
        self.assertEqual(client._request_signer._credentials.access_key, 'restoreproof-local')
        self.assertEqual(client.meta.config.proxies, {})
        self.assertEqual(client.meta.config.retries['total_max_attempts'], 1)

    def test_aws_requires_free_gate_and_temporary_explicit_credentials(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                create_client(mode='aws', region='us-east-1')
            os.environ['RESTOREPROOF_AWS_FREE_VERIFIED'] = 'true'
            with self.assertRaises(ValueError):
                create_client(mode='aws', region='us-east-1')
            os.environ.update(AWS_ACCESS_KEY_ID='temporary', AWS_SECRET_ACCESS_KEY='temporary', AWS_SESSION_TOKEN='temporary')
            client = create_client(mode='aws', region='us-east-1')
            self.addCleanup(client.close)
            self.assertEqual(client.meta.endpoint_url, 'https://s3.us-east-1.amazonaws.com')
            with self.assertRaises(ValueError):
                create_client(mode='aws', endpoint='http://127.0.0.1:5000', region='us-east-1')

    def test_sdk_redirect_cannot_escape_the_selected_endpoint(self):
        from botocore.awsrequest import AWSPreparedRequest
        client = create_client(mode='local', endpoint='http://127.0.0.1:5000', region='us-east-1')
        self.addCleanup(client.close)
        request = AWSPreparedRequest('GET', 'https://s3.us-east-1.amazonaws.com/bucket', {}, None, False)
        with self.assertRaises(ValueError):
            client.meta.events.emit('before-send.s3.GetObject', request=request)
