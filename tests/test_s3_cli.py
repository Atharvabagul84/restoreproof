import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from restoreproof.cli import main


class S3CliTests(unittest.TestCase):
    def test_missing_contract_retains_invalid_summary_without_cloud_access(self):
        with tempfile.TemporaryDirectory() as temp, contextlib.redirect_stdout(io.StringIO()) as stdout:
            root = Path(temp)
            try:
                code = main(['verify-s3', str(root/'missing.json'), '--endpoint', 'http://127.0.0.1:5000',
                             '--output', str(root/'runs'), '--summary', str(root/'current.json')])
            except SystemExit:
                self.fail('verify-s3 CLI command is missing')
            self.assertEqual(code, 3)
            summary = json.loads((root/'current.json').read_text())
            self.assertEqual(summary['status'], 'INVALID')
            self.assertTrue(Path(summary['report_path']).exists())
            self.assertEqual(json.loads(stdout.getvalue())['status'], 'INVALID')

    def test_aws_mode_cannot_run_without_cost_gate(self):
        import os
        with patch.dict(os.environ, {}, clear=True), contextlib.redirect_stdout(io.StringIO()):
            try:
                code = main(['verify-s3', 'missing.json', '--mode', 'aws'])
            except SystemExit:
                self.fail('verify-s3 CLI command is missing')
            self.assertEqual(code, 3)

    def test_empty_history_is_explicit(self):
        with tempfile.TemporaryDirectory() as temp, contextlib.redirect_stdout(io.StringIO()) as stdout:
            try:
                code = main(['s3-history', '--output', temp])
            except SystemExit:
                self.fail('s3-history CLI command is missing')
            self.assertEqual(code, 0)
            self.assertIsNone(json.loads(stdout.getvalue())['last_success'])
