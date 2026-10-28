"""Actual loopback HTTP transport; emulator results are not AWS IAM evidence."""
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import os
from pathlib import Path
import tempfile
import threading
import unittest


@unittest.skipUnless(os.environ.get('RESTOREPROOF_S3_INTEGRATION') == '1', 'requires local Moto HTTP server')
class S3HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from moto.server import ThreadedMotoServer
        from restoreproof.s3.client import create_client
        logging.getLogger('werkzeug').setLevel(logging.ERROR)
        cls.server = ThreadedMotoServer(ip_address='127.0.0.1', port=0, verbose=False)
        cls.server.start()
        cls.client = create_client(endpoint='http://127.0.0.1:' + str(cls.server.get_host_and_port()[1]))
        cls.bucket = 'restoreproof-http-test'
        cls.client.create_bucket(Bucket=cls.bucket)
        cls.client.put_bucket_versioning(Bucket=cls.bucket, VersioningConfiguration={'Status': 'Enabled'})

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        cls.server.stop()

    def setUp(self):
        from restoreproof.s3.contract import S3Backup
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.destination = Path(self.temp.name) / 'download.dump'
        self.key = 'backups/' + self._testMethodName
        self.data = b'PGDMPoriginal-object-version'
        self.version = self.client.put_object(Bucket=self.bucket, Key=self.key, Body=self.data)['VersionId']
        self.spec = S3Backup.model_validate(dict(bucket=self.bucket, key=self.key, version_id=self.version,
            sha256=hashlib.sha256(self.data).hexdigest(), expected_bucket_owner='123456789012',
            captured_at=datetime.now(timezone.utc).isoformat(), max_age_seconds=3600))

    def test_retrieves_original_version_after_newer_upload_and_delete_marker(self):
        from restoreproof.s3.retrieval import retrieve
        self.client.put_object(Bucket=self.bucket, Key=self.key, Body=b'PGDMPnewer-unwanted')
        self.client.delete_object(Bucket=self.bucket, Key=self.key)
        receipt = retrieve(self.client, self.spec, self.destination)
        self.assertEqual(self.destination.read_bytes(), self.data)
        self.assertEqual(receipt['version_id'], self.version)

    def test_missing_object_is_not_replaced_with_latest(self):
        from restoreproof.s3.retrieval import retrieve, RetrievalError
        missing = self.spec.model_copy(update={'version_id': 'missing-version'})
        with self.assertRaises(RetrievalError) as caught:
            retrieve(self.client, missing, self.destination)
        self.assertEqual(caught.exception.code, 'missing-object')
        self.assertFalse(self.destination.exists())

    def test_explicit_deny_returns_distinct_access_failure(self):
        from restoreproof.s3.retrieval import retrieve, RetrievalError
        policy = {'Version': '2012-10-17', 'Statement': [{'Effect': 'Deny', 'Principal': '*',
            # Moto's preliminary bucket-policy check uses GetObject even for a versioned GET.
            # This broad local deny tests transport handling, not the real IAM policy.
            'Action': 's3:GetObject*', 'Resource': f'arn:aws:s3:::{self.bucket}/{self.key}'}]}
        self.client.put_bucket_policy(Bucket=self.bucket, Policy=json.dumps(policy))
        try:
            with self.assertRaises(RetrievalError) as caught:
                retrieve(self.client, self.spec, self.destination)
            self.assertEqual(caught.exception.code, 'access-denied')
        finally:
            self.client.delete_bucket_policy(Bucket=self.bucket)

    def test_transport_disconnect_removes_partial_file(self):
        from restoreproof.s3.client import create_client
        from restoreproof.s3.retrieval import retrieve, RetrievalError
        version = self.version

        class InterruptedObject(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header('Content-Length', '100')
                self.send_header('x-amz-version-id', version)
                self.end_headers()
                self.wfile.write(b'PGDMPcut')
                self.wfile.flush()
                self.close_connection = True

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), InterruptedObject)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        client = create_client(endpoint=f'http://127.0.0.1:{server.server_port}')
        try:
            with self.assertRaises(RetrievalError) as caught:
                retrieve(client, self.spec, self.destination)
            self.assertEqual(caught.exception.code, 'download-interrupted')
            self.assertEqual(list(self.destination.parent.iterdir()), [])
        finally:
            client.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
