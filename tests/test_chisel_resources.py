import copy
import unittest
from unittest.mock import Mock

from restoreproof.chisel.stack import ChiselStack
from restoreproof.chisel.resources import COMPONENT_LABEL, RUN_LABEL
try:
    from restoreproof.chisel.resources import isolation_evidence
except ImportError:
    isolation_evidence = None

RUN, CID, DBID = 'a'*32, 'b'*64, 'c'*64


class IsolationTests(unittest.TestCase):
    def test_runtime_isolation_is_observed_and_unsafe_settings_rejected(self):
        self.assertIsNotNone(isolation_evidence, 'observed runtime isolation is missing')
        item = {'Mounts': [], 'HostConfig': {'NetworkMode': 'container:' + DBID, 'Memory': 268435456,
                'NanoCpus': 1000000000, 'PidsLimit': 128, 'ReadonlyRootfs': True,
                'CapDrop': ['ALL'], 'SecurityOpt': ['no-new-privileges'], 'Privileged': False,
                'PortBindings': {}, 'Binds': None, 'Tmpfs': {'/tmp': 'rw,nosuid,size=67108864'}}}
        evidence = isolation_evidence(item, 'auth', DBID)
        self.assertEqual(evidence['network_mode'], 'container:' + DBID)
        self.assertEqual(evidence['memory_bytes'], 268435456)
        for key, value in [('NetworkMode', 'host'), ('Privileged', True), ('Memory', 0),
                           ('NanoCpus', 0), ('PidsLimit', 0), ('ReadonlyRootfs', False),
                           ('CapDrop', []), ('SecurityOpt', []), ('PortBindings', {'80/tcp': []}),
                           ('Binds', ['/host:/container']), ('Tmpfs', {})]:
            changed = copy.deepcopy(item)
            changed['HostConfig'][key] = value
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                isolation_evidence(changed, 'auth', DBID)
        changed = copy.deepcopy(item)
        changed['Mounts'] = [{'Type': 'volume', 'Name': 'unintended-persistent-data'}]
        with self.assertRaises(RuntimeError):
            isolation_evidence(changed, 'auth', DBID)


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.stack = ChiselStack(RUN, {'database': 'postgres:17.11-bookworm'})
        self.stack.db.container_id = DBID
        self.stack.ids = {'app': CID}
        self.stack.attempted = {'app'}
        self.item = {'Id': CID, 'Name': '/restoreproof-' + RUN + '-app',
                     'Config': {'Labels': {RUN_LABEL: RUN, COMPONENT_LABEL: 'app'}},
                     'HostConfig': {'NetworkMode': 'container:' + DBID}}
        self.present = True
        self.deleted = []
        def find(selector):
            matches = selector in {'label=' + RUN_LABEL + '=' + RUN, 'id=' + CID,
                                   'name=^/restoreproof-' + RUN + '-app$'}
            return [CID] if self.present and matches else []
        def run(*args, **kwargs):
            if args[0] == 'rm':
                self.deleted.append(args[-1])
                self.present = False
        self.stack.db._find = find
        self.stack.db._run = run
        self.stack._inspect = lambda _: self.item
        self.stack.db.cleanup = Mock(return_value={'status': 'PASS', 'remaining': []})

    def test_exact_owned_sidecar_is_removed_before_database(self):
        self.assertEqual(self.stack.cleanup()['status'], 'PASS')
        self.assertEqual(self.deleted, [CID])
        self.stack.db.cleanup.assert_called_once()

    def test_foreign_label_stops_all_cleanup(self):
        self.item['Config']['Labels'][RUN_LABEL] = 'foreign'
        self.assertEqual(self.stack.cleanup()['status'], 'INCOMPLETE')
        self.assertEqual(self.deleted, [])
        self.stack.db.cleanup.assert_not_called()

    def test_renamed_sidecar_is_not_deleted(self):
        self.item['Name'] = '/renamed'
        self.assertEqual(self.stack.cleanup()['status'], 'INCOMPLETE')
        self.assertEqual(self.deleted, [])

    def test_timed_out_create_can_recover_only_attempted_component(self):
        self.stack.ids = {}
        self.assertEqual(self.stack.cleanup()['status'], 'PASS')
        self.assertEqual(self.deleted, [CID])

    def test_unattempted_preexisting_component_is_not_adopted(self):
        self.stack.ids = {}
        self.stack.attempted = set()
        self.assertEqual(self.stack.cleanup()['status'], 'INCOMPLETE')
        self.assertEqual(self.deleted, [])

    def test_daemon_unavailability_never_means_absence(self):
        self.stack.db._find = Mock(side_effect=RuntimeError('daemon unavailable'))
        self.assertEqual(self.stack.cleanup()['status'], 'INCOMPLETE')
        self.assertEqual(self.deleted, [])
