"""Offline report boundaries: evidence integrity, scope, privacy and safe HTML."""
import contextlib
from copy import deepcopy
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import tempfile
import unittest

from restoreproof.cli import main

EVIDENCE = Path(__file__).resolve().parents[1] / 'evidence/aws-live'


class Document(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.tags, self.attributes, self.text = [], [], []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attributes.extend(attrs)

    def handle_data(self, data):
        self.text.append(data)


class HtmlReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root/'export.html'
        self.healthy = json.loads((EVIDENCE/'healthy/report.json').read_text())
        self.failed = json.loads((EVIDENCE/'download-interrupted/report.json').read_text())

    def put(self, name, report):
        path = self.root/name/'report.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report), encoding='utf-8')
        return path

    def export(self, inputs=None):
        try:
            from restoreproof.reporting.export import write_html
        except ImportError:
            self.fail('Offline evidence export is not implemented')
        return write_html(inputs or [self.root], self.output)

    def test_latest_failure_does_not_replace_last_success(self):
        self.put('a', self.healthy)
        self.put('b', self.failed)
        summary = self.export()
        scope = summary['scopes'][0]
        self.assertEqual(scope['latest_attempt']['run_id'], self.failed['run_id'])
        self.assertEqual(scope['latest_attempt']['status'], 'INCOMPLETE')
        self.assertEqual(scope['last_success']['run_id'], self.healthy['run_id'])
        self.assertEqual(summary['export_status'], 'PASS')
        text = self.output.read_text()
        self.assertIn('Latest attempt', text)
        self.assertIn('Last successful recovery', text)
        self.assertIn(self.healthy['backup']['version_id'], text)
        self.assertIn(self.healthy['backup']['sha256'], text)
        self.assertIn('Age at verification', text)

    def test_aws_and_emulator_histories_remain_separate(self):
        self.put('aws', self.healthy)
        local = deepcopy(self.failed)
        local['storage_endpoint'] = 'http://127.0.0.1:54321'
        self.put('local', local)
        scopes = {item['scope']: item for item in self.export()['scopes']}
        self.assertEqual(set(scopes), {'aws', 'local'})
        self.assertIsNone(scopes['local']['last_success'])
        text = self.output.read_text()
        self.assertIn('AWS S3', text)
        self.assertIn('Local S3 emulator', text)
        self.assertIn('No successful recovery in these inputs', text)

    def test_html_escapes_object_identity_and_omits_unselected_secrets(self):
        report = deepcopy(self.healthy)
        report['backup']['key'] = '<img src="https://bad.invalid/leak" onerror="alert(1)">'
        report['retrieval']['key'] = report['backup']['key']
        report['errors'] = ['PRIVATE_ERROR_TOKEN']
        report['credentials'] = {'SessionToken': 'PRIVATE_SESSION_TOKEN'}
        report['report_path'] = 'C:/private/PRIVATE_HOME/report.json'
        report['checks'][1]['cookie'] = 'PRIVATE_COOKIE'
        self.put('hostile', report)
        self.export()
        text = self.output.read_text()
        document = Document(text)
        self.assertNotIn('img', document.tags)
        self.assertNotIn('script', document.tags)
        self.assertFalse(any(name.startswith('on') for name, _ in document.attributes))
        self.assertIn('&lt;img', text)
        for marker in ['PRIVATE_ERROR_TOKEN', 'PRIVATE_SESSION_TOKEN', 'PRIVATE_HOME', 'PRIVATE_COOKIE']:
            self.assertNotIn(marker, text)

    def test_self_contained_output_has_no_external_asset_or_navigation_dependency(self):
        self.put('healthy', self.healthy)
        self.export()
        document = Document(self.output.read_text())
        self.assertNotIn('script', document.tags)
        self.assertNotIn('link', document.tags)
        self.assertNotIn('iframe', document.tags)
        self.assertFalse(any(name == 'src' or (name == 'href' and not value.startswith('#'))
                             for name, value in document.attributes))
        self.assertIn(('http-equiv', 'Content-Security-Policy'), document.attributes)
        self.assertIn('details', document.tags)

    def test_missing_required_check_cannot_be_presented_as_success(self):
        report = deepcopy(self.healthy)
        report['checks'] = [c for c in report['checks'] if c['name'] != 'tenant-isolation']
        self.put('inconsistent', report)
        with self.assertRaises(ValueError): self.export()
        self.assertFalse(self.output.exists())

    def test_success_with_failed_cleanup_is_rejected(self):
        report = deepcopy(self.healthy)
        report['cleanup']['status'] = 'INCOMPLETE'
        self.put('inconsistent', report)
        with self.assertRaises(ValueError): self.export()

    def test_success_with_remaining_container_is_rejected(self):
        report = deepcopy(self.healthy)
        report['cleanup']['remaining'] = ['owned-container']
        self.put('contradictory-cleanup', report)
        with self.assertRaises(ValueError): self.export()

    def test_success_with_retained_download_is_rejected(self):
        report = deepcopy(self.healthy)
        report['download_cleanup']['archive_retained'] = True
        self.put('retained-download', report)
        with self.assertRaises(ValueError): self.export()

    def test_retrieved_version_must_match_the_presented_backup(self):
        report = deepcopy(self.healthy)
        report['retrieval']['version_id'] = 'unexpected-version'
        self.put('wrong-version', report)
        with self.assertRaises(ValueError): self.export()

    def test_retrieved_hash_must_match_the_presented_backup(self):
        report = deepcopy(self.healthy)
        report['retrieval']['sha256'] = '0' * 64
        self.put('wrong-hash', report)
        with self.assertRaises(ValueError): self.export()

    def test_unknown_storage_is_not_labeled_as_aws(self):
        report = deepcopy(self.failed)
        report['storage_endpoint'] = 'https://s3.ap-southeast-2.amazonaws.com.evil.invalid'
        self.put('unknown', report)
        self.assertEqual(self.export()['scopes'][0]['scope'], 'unknown')
        self.assertIn('Unclassified storage', self.output.read_text())

    def test_unfinished_journal_is_retained_without_inventing_backup_or_cleanup(self):
        report = deepcopy(self.failed)
        report.pop('backup')
        report.pop('download_cleanup')
        report.pop('completed_at')
        report['checks'] = []
        report['cleanup'] = {'status': 'NOT_REQUIRED'}
        self.put('unfinished', report)
        summary = self.export()
        self.assertIsNone(summary['scopes'][0]['last_success'])
        self.assertIn('Backup identity unavailable', self.output.read_text())
        self.assertIn('Not confirmed', self.output.read_text())

    def test_duplicate_identical_run_is_counted_once(self):
        self.put('a', self.healthy)
        self.put('b', self.healthy)
        self.assertEqual(self.export()['run_count'], 1)

    def test_conflicting_same_run_id_is_rejected(self):
        self.put('a', self.healthy)
        changed = deepcopy(self.healthy)
        changed['timings']['total_seconds'] += 1
        self.put('b', changed)
        with self.assertRaises(ValueError): self.export()

    def test_duplicate_json_keys_are_rejected_and_existing_export_survives(self):
        self.output.write_text('existing export')
        path = self.put('bad', self.healthy)
        path.write_text(path.read_text().replace('"status": "PASS"', '"status": "PASS", "status": "FAIL"', 1))
        with self.assertRaises(ValueError): self.export()
        self.assertEqual(self.output.read_text(), 'existing export')

    def test_oversized_report_is_rejected(self):
        path = self.put('large', self.healthy)
        path.write_bytes(b' ' * (256 * 1024 + 1))
        with self.assertRaises(ValueError): self.export()

    def test_report_count_is_bounded_before_deduplication(self):
        for index in range(201): self.put(str(index), self.healthy)
        with self.assertRaises(ValueError): self.export()

    def test_embedded_file_paths_are_not_followed(self):
        report = deepcopy(self.failed)
        report['application_recovery'] = {'report_path': 'does-not-exist/secret.json'}
        self.put('failed', report)
        self.assertEqual(self.export()['run_count'], 1)

    def test_nested_application_and_source_reports_are_not_double_counted(self):
        self.put('healthy', self.healthy)
        self.put('healthy/application', json.loads((EVIDENCE/'healthy/application/report.json').read_text()))
        self.put('source', json.loads((EVIDENCE/'source/report.json').read_text()))
        self.assertEqual(self.export()['run_count'], 1)

    def test_output_cannot_overwrite_a_json_journal(self):
        path = self.put('healthy', self.healthy)
        before = path.read_bytes()
        self.output = path
        with self.assertRaises(ValueError): self.export()
        self.assertEqual(path.read_bytes(), before)

    def test_empty_input_has_no_green_export(self):
        with self.assertRaises(ValueError): self.export()
        self.assertFalse(self.output.exists())

    def test_cli_renders_historical_evidence_without_credentials_or_containers(self):
        with contextlib.redirect_stdout(io.StringIO()) as stdout, contextlib.redirect_stderr(io.StringIO()):
            try:
                code = main(['report-html', '--input', str(EVIDENCE), '--output', str(self.output)])
            except SystemExit:
                self.fail('report-html CLI command is missing')
        self.assertEqual(code, 0)
        summary = json.loads(stdout.getvalue())
        self.assertEqual(summary['run_count'], 6)
        self.assertEqual(summary['scopes'][0]['latest_attempt']['status'], 'INCOMPLETE')
        self.assertTrue(self.output.exists())
