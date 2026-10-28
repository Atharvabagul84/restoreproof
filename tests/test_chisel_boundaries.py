"""Behavioral checks at the app transport, source provenance and report boundaries."""
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from test_chisel import contract_payload
from restoreproof.chisel.client import AppClient, DependencyUnavailable
from restoreproof.chisel.images import verify_source
from restoreproof.chisel.journey import REQUIRED_CHECKS
from restoreproof.chisel.runner import verify_app


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.run = Mock(return_value=json.dumps({'status': 200, 'cookies': [], 'body': {'ok': True}}).encode())
        self.client = AppClient(SimpleNamespace(db=SimpleNamespace(_run=self.run), owned=lambda _: 'a'*64))
        self.client.ca = 'TEST CERTIFICATE'

    def test_cookies_are_sent_only_to_tls_application_and_only_via_stdin(self):
        self.client.cookies = {'session': 'sensitive-value'}
        self.client.request('GET', '/')
        args, kwargs = self.run.call_args
        self.assertNotIn('sensitive-value', ' '.join(args))
        payload = json.loads(kwargs['input_data'])
        self.assertEqual(payload['headers']['Cookie'], 'session=sensitive-value')
        self.assertEqual(payload['ca'], 'TEST CERTIFICATE')
        self.client.request('GET', '/api/v1/messages', target='mail')
        self.assertNotIn('Cookie', json.loads(self.run.call_args.kwargs['input_data'])['headers'])

    def test_unverified_tls_and_arbitrary_targets_are_rejected_without_exec(self):
        for target, path in [('external', '/'), ('app', '//remote'), ('app', '/\r\nhost: remote')]:
            with self.subTest(target=target, path=path), self.assertRaises(ValueError):
                self.client.request('GET', path, target=target)
        self.client.ca = None
        with self.assertRaises(RuntimeError):
            self.client.request('GET', '/')
        self.run.assert_not_called()

    def test_insecure_session_cookie_is_rejected(self):
        for cookie in ['session=value; Path=/', 'session=value; Path=/; Secure', 'session=value; HttpOnly; Path=/']:
            self.run.return_value = json.dumps({'status': 200, 'cookies': [cookie], 'body': {}}).encode()
            with self.subTest(cookie=cookie), self.assertRaises(RuntimeError):
                self.client.request('GET', '/')

    def test_signout_cookie_removes_session(self):
        self.client.cookies = {'session': 'secret'}
        self.run.return_value = json.dumps({'status': 200, 'cookies': ['session=; Max-Age=0; Path=/; Secure; HttpOnly'], 'body': {}}).encode()
        self.client.request('POST', '/api/auth/signout', {})
        self.assertEqual(self.client.cookies, {})

    def test_auth_dependency_failure_retains_only_safe_http_status(self):
        self.run.side_effect = [json.dumps({'status': 200, 'cookies': [], 'body': {'messages': []}}).encode(),
                               json.dumps({'status': 503, 'cookies': [], 'body': {'error': 'secret-upstream'}}).encode()]
        with self.assertRaises(DependencyUnavailable) as captured:
            self.client.login('owner@restoreproof.test')
        self.assertEqual(getattr(captured.exception, 'http_status', None), 503)
        self.assertNotIn('secret-upstream', str(captured.exception))


class SourceProvenanceTests(unittest.TestCase):
    def test_installed_source_exactly_matches_pinned_manifest(self):
        self.assertEqual(len(verify_source()['files']), 104)

    def test_changed_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'app').mkdir()
            (root / 'app/package.json').write_text('changed')
            (root / 'source-manifest.json').write_text(json.dumps({
                'commit': contract_payload()['source_commit'], 'files': {'package.json': 'a'*64}}))
            with patch('restoreproof.chisel.images.ASSETS', root), self.assertRaises(ValueError):
                verify_source()


class RecoveryVerdictTests(unittest.TestCase):
    def exercise(self, root, checks, *, cleanup='PASS', failure=None, prepare=False):
        archive = root / 'backup.dump'
        archive.write_bytes(b'PGDMPfixture')
        payload = contract_payload()
        payload['backup']['sha256'] = hashlib.sha256(archive.read_bytes()).hexdigest()
        contract = root / 'contract.json'
        contract.write_text(json.dumps(payload))
        stack = Mock()
        stack.db.name = 'owned-database'
        stack.snapshot.return_value = {'database_id': 'a'*64}
        stack.cleanup.return_value = {'status': cleanup, 'remaining': [] if cleanup == 'PASS' else ['a'*64]}
        def journey(client, contract, record):
            for check in checks:
                record(check)
            if failure:
                raise failure
        with patch('restoreproof.chisel.runner.ChiselStack', return_value=stack), \
                patch('restoreproof.chisel.runner.run_journey', journey):
            return verify_app(contract, root / 'out', images=None if prepare else {'database': 'postgres:17.11-bookworm'})

    def test_recovery_clock_includes_preflight_but_excludes_image_preparation(self):
        from restoreproof.chisel.contract import load_contract
        clock = [0.0]
        def load(path):
            clock[0] += 2
            return load_contract(path)
        def prepare():
            clock[0] += 100
            return {'database': 'postgres:17.11-bookworm'}
        with tempfile.TemporaryDirectory() as temp, patch('restoreproof.chisel.runner.time.monotonic', lambda: clock[0]), \
                patch('restoreproof.chisel.runner.load_contract', load), patch('restoreproof.chisel.runner.prepare_images', prepare):
            report = self.exercise(Path(temp), [{'name': name, 'status': 'PASS'} for name in REQUIRED_CHECKS], prepare=True)
        duration = next(item for item in report['checks'] if item['name'] == 'recovery-duration')
        self.assertEqual(duration['observed_seconds'], 2)

    def test_partial_green_check_set_cannot_become_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            report = self.exercise(Path(temp), [{'name': 'email-otp-login', 'status': 'PASS'}])
        self.assertEqual(report['status'], 'INCOMPLETE')

    def test_duplicate_acceptance_checks_cannot_become_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            checks = [{'name': name, 'status': 'PASS'} for name in REQUIRED_CHECKS]
            report = self.exercise(Path(temp), checks + [checks[0]])
        self.assertEqual(report['status'], 'INCOMPLETE')

    def test_unknown_acceptance_status_cannot_become_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            checks = [{'name': name, 'status': 'unknown'} for name in REQUIRED_CHECKS]
            report = self.exercise(Path(temp), checks)
        self.assertEqual(report['status'], 'INCOMPLETE')

    def test_cleanup_failure_overrides_all_successful_app_checks(self):
        with tempfile.TemporaryDirectory() as temp:
            checks = [{'name': name, 'status': 'PASS'} for name in REQUIRED_CHECKS]
            report = self.exercise(Path(temp), checks, cleanup='INCOMPLETE')
        self.assertEqual(report['status'], 'INCOMPLETE')
        self.assertEqual(report['exit_code'], 2)

    def test_completed_functional_failure_stays_fail(self):
        with tempfile.TemporaryDirectory() as temp:
            checks = [{'name': name, 'status': 'FAIL' if name == 'saved-brief-content' else 'PASS'} for name in REQUIRED_CHECKS]
            report = self.exercise(Path(temp), checks)
        self.assertEqual(report['status'], 'FAIL')
        self.assertEqual(report['cleanup']['status'], 'PASS')

    def test_dependency_exception_is_incomplete_and_omits_upstream_secret(self):
        with tempfile.TemporaryDirectory() as temp:
            report = self.exercise(Path(temp), [], failure=RuntimeError('upstream-secret'))
            persisted = Path(report['report_path']).read_text()
        self.assertEqual(report['status'], 'INCOMPLETE')
        self.assertNotIn('upstream-secret', persisted)

    def test_invalid_contract_does_not_prepare_images_or_allocate_resources(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'invalid.json'
            path.write_text('{"application":"production"}')
            with patch('restoreproof.chisel.runner.prepare_images') as prepare, patch('restoreproof.chisel.runner.ChiselStack') as stack:
                report = verify_app(path, Path(temp) / 'out')
            prepare.assert_not_called()
            stack.assert_not_called()
        self.assertEqual(report['status'], 'INVALID')
