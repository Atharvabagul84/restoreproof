import sys
import subprocess
import unittest
from unittest.mock import patch

try:
    from restoreproof.process import ProcessError, run_command
except ImportError:
    ProcessError, run_command = RuntimeError, None


class ProcessTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(run_command, "bounded process runner is missing")

    def test_arguments_remain_literal_and_stdin_round_trips(self):
        literal = "$(touch unsafe); & echo SECRET"
        output = run_command(
            [sys.executable, "-c", "import sys; print(sys.argv[1]); print(sys.stdin.read())", literal],
            input_data=b"input payload", timeout=5,
        )
        self.assertEqual(output.decode().splitlines(), [literal, "input payload"])

    def test_failure_never_discloses_stderr_or_command_arguments(self):
        with self.assertRaises(ProcessError) as caught:
            run_command([sys.executable, "-c", "import sys; sys.stderr.write('password-secret'); sys.exit(7)"], timeout=5)
        self.assertNotIn("password-secret", str(caught.exception))
        self.assertEqual(caught.exception.returncode, 7)

    def test_timeout_terminates_process(self):
        with self.assertRaisesRegex(ProcessError, "timed out"):
            run_command([sys.executable, "-c", "import time; time.sleep(5)"], timeout=0.1)

    def test_stdout_is_bounded(self):
        with self.assertRaisesRegex(ProcessError, "output limit"):
            run_command([sys.executable, "-c", "import sys; sys.stdout.write('x'*200000)"], timeout=5, max_output=1024)

    def test_stderr_is_bounded_and_redacted(self):
        with self.assertRaisesRegex(ProcessError, "output limit") as caught:
            run_command([sys.executable, "-c", "import sys; sys.stderr.write('secret'*50000)"], timeout=5, max_output=1024)
        self.assertNotIn("secret", str(caught.exception))

    def test_invalid_limits_are_rejected(self):
        for timeout in [0, -1, float("nan"), float("inf")]:
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                run_command([sys.executable, "-c", "pass"], timeout=timeout)

    def test_oversized_stdin_is_rejected_before_execution(self):
        with self.assertRaises(ValueError):
            run_command([sys.executable, "-c", "pass"], input_data=b"x" * (1024 * 1024 + 1))

    def test_string_commands_are_rejected(self):
        with self.assertRaises(Exception) as caught:
            run_command("not-a-command-array")
        self.assertIsInstance(caught.exception, ValueError)

    def test_keyboard_interrupt_reaps_only_its_child_before_reraising(self):
        original_popen = subprocess.Popen
        children = []

        def interrupt_once(*args, **kwargs):
            child = original_popen(*args, **kwargs)
            children.append(child)
            original_wait = child.wait
            interrupted = False

            def wait(*args, **kwargs):
                nonlocal interrupted
                if not interrupted:
                    interrupted = True
                    raise KeyboardInterrupt
                return original_wait(*args, **kwargs)

            child.wait = wait
            return child

        try:
            with patch("restoreproof.process.subprocess.Popen", interrupt_once):
                with self.assertRaises(KeyboardInterrupt):
                    run_command([sys.executable, "-c", "import time; time.sleep(30)"], timeout=5)
            self.assertIsNotNone(children[0].poll(), "interrupted runner left its child alive")
        finally:
            for child in children:
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
