"""Hard deadlines affect only a newly created process group."""
import os
import signal
import subprocess
import time


def stop_group(proc):
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        proc.wait(timeout=0.5)
    except subprocess.TimeoutExpired:
        pass
    # Also clean descendants if the leader exited in response to TERM.
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    proc.wait()


def supervise(command, timeout, log, env, pass_fds=()):
    start = time.monotonic()
    proc = subprocess.Popen(command, start_new_session=True, stdout=log,
                            stderr=subprocess.STDOUT, env=env, pass_fds=pass_fds)
    try:
        try:
            proc.wait(timeout=max(0, timeout - (time.monotonic() - start)))
        except subprocess.TimeoutExpired:
            stop_group(proc)
            return 'timed_out', time.monotonic() - start, proc.returncode
        if time.monotonic() - start >= timeout:
            stop_group(proc)
            return 'timed_out', time.monotonic() - start, proc.returncode
        # A job must not leave its own descendants running after normal exit either.
        stop_group(proc)
        return 'finished', time.monotonic() - start, proc.returncode
    except BaseException:
        stop_group(proc)
        raise
