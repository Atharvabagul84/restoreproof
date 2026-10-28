"""Recovery contract and ownership tests for the real Chisel adapter."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_docker_postgres import DockerFixture, RUN, IMAGE, DIGEST
try:
    from restoreproof.chisel.contract import AppContract, load_contract, SOURCE_COMMIT
    from restoreproof.chisel.database import ChiselPostgres
    from restoreproof.chisel.resources import validate_owned
except ImportError:
    AppContract = ChiselPostgres = validate_owned = None
    SOURCE_COMMIT = 'fdb206cb24b3319328315eadaaee01eb03fda432'


def contract_payload():
    return {'version': 1, 'application': 'chisel', 'source_commit': SOURCE_COMMIT,
            'backup': {'path': 'backup.dump', 'sha256': 'a' * 64},
            'owner_id': 'a' * 8 + '-aaaa-4aaa-8aaa-' + 'a' * 12,
            'workspace_id': 'b' * 8 + '-bbbb-4bbb-8bbb-' + 'b' * 12,
            'outsider_workspace_id': 'c' * 8 + '-cccc-4ccc-8ccc-' + 'c' * 12,
            'brief_id': 'd' * 8 + '-dddd-4ddd-8ddd-' + 'd' * 12,
            'brief_sha256': 'e' * 64}


class AppContractTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(AppContract, 'strict application recovery contract is missing')

    def test_contract_is_fixed_to_reviewed_app_and_has_no_secret_or_endpoint_inputs(self):
        self.assertEqual(AppContract.model_validate(contract_payload()).application, 'chisel')
        for key, value in [('application', 'other'), ('source_commit', 'f'*40),
                           ('owner_id', "';DROP TABLE auth.users;--"),
                           ('url', 'https://production.example'), ('password', 'secret'),
                           ('version', True), ('max_recovery_seconds', float('inf'))]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                AppContract.model_validate({**contract_payload(), key: value})

    def test_duplicate_keys_and_nonfinite_numbers_are_invalid(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'contract.json'
            for data in ['{"version":1,"version":1}', '{"version":NaN}', 'x' * 131073]:
                path.write_text(data)
                with self.subTest(data=data[:30]), self.assertRaises(ValueError):
                    load_contract(path)


class AppRestoreTests(unittest.TestCase):
    def test_application_restore_preserves_owners_and_grants_after_copy_hash_check(self):
        self.assertIsNotNone(ChiselPostgres, 'role-aware application restore is missing')
        fixture = DockerFixture()
        with patch('restoreproof.docker_postgres.run_command', fixture):
            backend = ChiselPostgres(IMAGE, RUN)
            backend.create()
            with tempfile.TemporaryDirectory() as temp:
                archive = Path(temp) / 'backup.dump'
                archive.write_bytes(b'PGDMPfixture')
                backend.restore(archive, DIGEST)
        commands = [args for args, _ in fixture.calls]
        restore = next(args for args in commands if 'pg_restore' in args)
        self.assertNotIn('--no-owner', restore)
        self.assertNotIn('--no-privileges', restore)
        self.assertIn('--single-transaction', restore)
        self.assertLess(next(i for i, args in enumerate(commands) if 'sha256sum' in args), commands.index(restore))


class AppOwnershipTests(unittest.TestCase):
    def test_foreign_identity_name_label_component_and_network_are_rejected(self):
        self.assertIsNotNone(validate_owned, 'application sidecar ownership validation is missing')
        cid, db = 'b'*64, 'c'*64
        item = {'Id': cid, 'Name': '/restoreproof-' + RUN + '-app',
                'Config': {'Labels': {'io.restoreproof.app_run_id': RUN, 'io.restoreproof.app_component': 'app'}},
                'HostConfig': {'NetworkMode': 'container:' + db}}
        self.assertEqual(validate_owned(item, RUN, 'app', cid, db), cid)
        for altered in [dict(item, Id='d'*64), dict(item, Name='/other'),
                        dict(item, Config={'Labels': {}}),
                        dict(item, HostConfig={'NetworkMode': 'host'})]:
            with self.subTest(item=altered), self.assertRaises(RuntimeError):
                validate_owned(altered, RUN, 'app', cid, db)
        with self.assertRaises(ValueError):
            validate_owned(item, RUN, 'unknown', cid, db)
