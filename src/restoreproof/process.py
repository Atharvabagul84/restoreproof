"""Shell-free subprocesses with bounded input, output and elapsed time."""
import math
import os
import subprocess
import threading


class ProcessError(RuntimeError):
    """Sanitized failure: intentionally excludes arguments and captured output."""
    def __init__(self, message, *, returncode=None):
        super().__init__(message)
        self.returncode = returncode


def run_command(args, *, input_data=None, timeout=60, max_output=1024 * 1024, env=None):
    if not isinstance(args, (list, tuple)) or not args or not all(isinstance(value, str) and value for value in args):
        raise ValueError("Command must be a nonempty argument array.")
    if not math.isfinite(timeout) or timeout <= 0 or not isinstance(max_output, int) or max_output <= 0:
        raise ValueError("Process limits must be positive and finite.")
    if input_data is not None and (not isinstance(input_data, bytes) or len(input_data) > 1024 * 1024):
        raise ValueError("Process input must be bytes no larger than 1 MiB.")
    try:
        process = subprocess.Popen(
            args, shell=False, stdin=subprocess.PIPE if input_data is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env={**os.environ, **(env or {})},
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError:
        raise ProcessError("Command could not be started.") from None
    overflow = threading.Event()
    buffers = [bytearray(), bytearray()]

    def collect(stream, buffer):
        try:
            while chunk := stream.read(65536):
                if len(buffer) + len(chunk) > max_output:
                    overflow.set()
                    process.kill()
                    return
                buffer.extend(chunk)
        finally:
            stream.close()

    def supply():
        try:
            process.stdin.write(input_data)
            process.stdin.flush()
        except (BrokenPipeError, OSError):
            pass
        finally:
            process.stdin.close()

    threads = [threading.Thread(target=collect, args=(stream, buffer), daemon=True)
               for stream, buffer in zip((process.stdout, process.stderr), buffers)]
    if input_data is not None:
        threads.append(threading.Thread(target=supply, daemon=True))
    for thread in threads:
        thread.start()
    timed_out = False
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
        process.wait(timeout=5)
    except KeyboardInterrupt:
        # Stop this client before callers begin container cleanup. Never stop
        # the daemon or unrelated processes, and preserve the interruption.
        try:
            process.kill()
        except ProcessLookupError:
            pass
        process.wait(timeout=5)
        raise
    finally:
        for thread in threads:
            thread.join(timeout=1)
    if overflow.is_set():
        raise ProcessError("Command exceeded the output limit.", returncode=process.returncode)
    if timed_out:
        raise ProcessError("Command timed out.", returncode=process.returncode)
    if any(thread.is_alive() for thread in threads):
        raise ProcessError("Command output did not close within the deadline.")
    if process.returncode:
        raise ProcessError(f"Command failed (exit {process.returncode}).", returncode=process.returncode)
    return bytes(buffers[0])
