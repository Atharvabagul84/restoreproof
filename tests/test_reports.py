import json
from pathlib import Path
import tempfile
import unittest
from xml.etree import ElementTree
from unittest.mock import patch

try:
    from restoreproof.reports import write_report
except ImportError:
    write_report = None


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(write_report, 'report writer is not implemented')

    def test_failure_and_incomplete_are_visible_in_junit(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            report = {'run_id': 'test', 'status': 'INCOMPLETE', 'checks': [
                {'name': 'wrong <snapshot>', 'status': 'FAIL', 'expected': True, 'actual': False},
                {'name': 'watermark', 'status': 'INCOMPLETE', 'reason': 'no evidence'},
            ], 'cleanup': {'status': 'INCOMPLETE', 'remaining': ['target']}}
            write_report(folder, report)
            self.assertEqual(json.loads((folder / 'report.json').read_text())['status'], 'INCOMPLETE')
            suite = ElementTree.parse(folder / 'junit.xml').getroot()
            self.assertGreaterEqual(int(suite.get('failures')), 1)
            self.assertGreaterEqual(int(suite.get('errors')), 1)
            self.assertIn('cleanup', [case.get('name') for case in suite.findall('testcase')])

    def test_invalid_without_checks_cannot_produce_green_junit(self):
        with tempfile.TemporaryDirectory() as temp:
            write_report(Path(temp), {'status': 'INVALID', 'checks': [], 'errors': ['bad contract'],
                                     'cleanup': {'status': 'NOT_REQUIRED', 'remaining': []}})
            suite = ElementTree.parse(Path(temp) / 'junit.xml').getroot()
            self.assertGreater(int(suite.get('errors')), 0)

    def test_junit_write_failure_does_not_publish_successful_json(self):
        import restoreproof.reports as reports
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            write_report(folder, {'status': 'INCOMPLETE', 'checks': [],
                                 'cleanup': {'status': 'NOT_REQUIRED'}})
            original = reports._atomic_write
            def fail_junit(path, text):
                if path.name == 'junit.xml':
                    raise OSError('simulated disk write failure')
                original(path, text)
            with patch.object(reports, '_atomic_write', side_effect=fail_junit):
                with self.assertRaises(OSError):
                    write_report(folder, {'status': 'PASS', 'checks': [{'name': 'data', 'status': 'PASS'}],
                                         'cleanup': {'status': 'PASS'}})
            self.assertEqual(json.loads((folder / 'report.json').read_text())['status'], 'INCOMPLETE')


if __name__ == '__main__':
    unittest.main()
