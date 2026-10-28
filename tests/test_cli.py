import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from test_engine import contract_file


class CliTests(unittest.TestCase):
    def invoke(self, *args):
        return subprocess.run([sys.executable, '-m', 'restoreproof', *map(str, args)],
                              capture_output=True, text=True, timeout=15)

    def test_help_describes_commands_without_docker(self):
        result = self.invoke('--help')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('verify', result.stdout)
        self.assertIn('demo', result.stdout)
        self.assertIn('cleanup', result.stdout)

    def test_invalid_archive_returns_three_with_inspectable_report(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            contract = contract_file(root)
            (root / 'backup.dump').write_bytes(b'altered')
            result = self.invoke('verify', contract, '--output', root / 'reports')
            self.assertEqual(result.returncode, 3, result.stderr)
            summary = json.loads(result.stdout)
            self.assertEqual(summary['status'], 'INVALID')
            self.assertTrue(Path(summary['report_path']).is_file())

    def test_cleanup_rejects_arbitrary_container_name(self):
        result = self.invoke('cleanup', 'some-production-database')
        self.assertEqual(result.returncode, 3)
        self.assertNotIn('Traceback', result.stderr)


if __name__ == '__main__':
    unittest.main()
