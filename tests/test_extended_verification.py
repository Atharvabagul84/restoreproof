import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from restoreproof.contract import ContractError, load_contract
from restoreproof.engine import verify
from test_engine import MemoryTarget, contract_file


class ExtendedVerificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = contract_file(self.root)
        self.document = json.loads(self.path.read_text())

    def save(self):
        self.path.write_text(json.dumps(self.document), encoding='utf-8')

    def ledger(self):
        rows = [{'write_id': f'write-{i}', 'sequence': i, 'payload_sha256': str(i) * 64,
                 'acknowledged_at': f'2026-01-01T00:00:0{i}Z'} for i in (1, 2, 3)]
        path = self.root / 'acknowledged.json'
        path.write_text(json.dumps({'version': 1, 'writes': rows}), encoding='utf-8')
        self.document['ledger'] = {'path': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                                   'sql': 'SELECT recovered_writes'}
        self.save()
        return rows

    def test_contract_accepts_opt_in_journey_and_ledger(self):
        self.ledger()
        self.document['application_journey'] = True
        self.save()
        try:
            contract = load_contract(self.path)
        except ContractError:
            self.fail('Contract must support explicit application journey and external ledger')
        self.assertTrue(contract.application_journey)
        self.assertEqual(contract.ledger.path, 'acknowledged.json')

    def test_journey_opt_in_is_strict_and_new_check_names_are_reserved(self):
        self.document['application_journey'] = 'true'
        self.save()
        with self.assertRaises(ContractError):
            load_contract(self.path)
        del self.document['application_journey']
        for name in ('committed-write-ledger', 'application-read', ' Application-Read '):
            self.document['checks'][0]['name'] = name
            self.save()
            with self.subTest(name=name), self.assertRaises(ContractError):
                load_contract(self.path)

    def test_ledger_bad_hash_rejected_before_target_allocation(self):
        self.ledger()
        (self.root / 'acknowledged.json').write_text('{}')
        def forbidden(**kwargs):
            self.fail('An invalid external ledger must not allocate a target')
        report = verify(self.path, self.root / 'runs', backend_factory=forbidden)
        self.assertEqual(report['status'], 'INVALID')

    def test_ledger_detects_missing_interior_write_despite_fresh_checkpoint(self):
        rows = self.ledger()
        target = MemoryTarget()
        original = target.query
        target.query = lambda sql: [rows[0], rows[2]] if sql == 'SELECT recovered_writes' else original(sql)
        report = verify(self.path, self.root / 'runs', backend_factory=lambda **kwargs: target)
        self.assertEqual(report['status'], 'FAIL')
        self.assertEqual(next(c for c in report['checks'] if c['name'] == 'freshness')['status'], 'PASS')
        self.assertEqual(next(c for c in report['checks'] if c['name'] == 'committed-write-ledger')['status'], 'FAIL')
        self.assertTrue(target.cleaned)

    def test_ledger_invalid_recovered_evidence_is_incomplete(self):
        self.ledger()
        report = verify(self.path, self.root / 'runs', backend_factory=lambda **kwargs: MemoryTarget())
        self.assertEqual(report['status'], 'INCOMPLETE')

    def test_application_failure_overrides_successful_sql_checks(self):
        self.document['application_journey'] = True
        self.save()
        target = MemoryTarget()
        try:
            report = verify(self.path, self.root / 'runs', backend_factory=lambda **kwargs: target,
                            application_runner=lambda current: [{'name': 'application-read', 'status': 'FAIL'}])
        except TypeError:
            self.fail('Engine must support and invoke the application journey boundary')
        self.assertEqual(report['status'], 'FAIL')
        self.assertEqual(report['checks'][0]['status'], 'PASS')
        self.assertTrue(target.cleaned)

    def test_selected_journey_cannot_pass_without_evidence(self):
        self.document['application_journey'] = True
        self.save()
        try:
            report = verify(self.path, self.root / 'runs', backend_factory=lambda **kwargs: MemoryTarget(),
                            application_runner=lambda current: [])
        except TypeError:
            self.fail('Engine must validate mandatory journey evidence')
        self.assertEqual(report['status'], 'INCOMPLETE')

    def test_partial_success_is_not_complete_application_evidence(self):
        self.document['application_journey'] = True
        self.save()
        report = verify(self.path, self.root / 'runs', backend_factory=lambda **kwargs: MemoryTarget(),
                        application_runner=lambda current: [{'name': 'application-placeholder', 'status': 'PASS'}])
        self.assertEqual(report['status'], 'INCOMPLETE')

    def test_duplicate_json_keys_cannot_silently_disable_checks(self):
        self.ledger()
        base = json.dumps(self.document)
        for ambiguous in (base[:-1] + ', "application_journey": true, "application_journey": false}',
                          base[:-1] + ', "ledger": null}'):
            with self.subTest(ambiguous=ambiguous[-80:]):
                self.path.write_text(ambiguous, encoding='utf-8')
                with self.assertRaises(ContractError):
                    load_contract(self.path)

    def test_unselected_journey_does_not_execute(self):
        def forbidden(target):
            self.fail('Application checks must be explicitly selected')
        try:
            report = verify(self.path, self.root / 'runs', backend_factory=lambda **kwargs: MemoryTarget(),
                            application_runner=forbidden)
        except TypeError:
            self.fail('Engine must expose the application runner boundary')
        self.assertEqual(report['status'], 'PASS')
