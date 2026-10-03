"""G2 fail-closed Codex subscription-path preflight; never starts model inference.

Uses installed Omnigent worker containment, not a shell/tool-enabled agent.
The operator chooses a NEW G2 attempt directory under the private runs root.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import importlib.metadata
import inspect
import json
import logging
from pathlib import Path
import shutil
import subprocess
import sys
import uuid


def allocate_attempt(requested: Path, private_runs: Path | None = None) -> Path:
    runs = private_runs or Path.home() / "recursive-scientist-local" / "runs"
    if not requested.is_absolute() or requested.parent != runs:
        raise ValueError("attempt must be an immediate child of the private runs root")
    if not requested.name.startswith("RS-20261003-G2-"):
        raise ValueError("G2 attempt name required; G1 evidence must remain unchanged")
    if any(p.is_symlink() for p in (requested, *requested.parents)):
        raise ValueError("symlinked attempt paths are forbidden")
    requested.mkdir(mode=0o700, exist_ok=False)
    return requested


def preflight(attempt: Path) -> dict:
    # No auth/config file reads; these imports load framework code only.
    from omnigent.inner.codex_worker import prepare_codex_worker
    from omnigent.inner.datamodel import OSEnvSandboxSpec, OSEnvSpec
    from omnigent.inner.codex_executor import _CodexAppServerSession

    logging.disable(logging.CRITICAL)
    workspace = attempt / "workspace"
    state = attempt / "codex-state"
    workspace.mkdir(mode=0o700)
    state.mkdir(mode=0o700)  # Empty: do not populate/bridge authentication here.
    record = {
        "task_id": "RS-20261003-G2", "revision": "r1",
        "timestamp": datetime.now().astimezone().isoformat(),
        "session_id": "g2-preflight-" + uuid.uuid4().hex,
        "omnigent_version": importlib.metadata.version("omnigent"),
        "requested_marker": "OMNIGENT_READY", "model_output": "",
        "model_requests": 0, "output_tokens": 0,
        "limits": {"model_requests": 6, "output_tokens": 6000},
        "credential_files_accessed": False,
        "tools_requested": [], "model_status": "not_started",
        "ready": False,
        "scope": "isolation preflight only; not a successful agent request",
    }
    code = inspect.getsource(_CodexAppServerSession.run_turn)
    record["installed_codex_run_turn_source_sha256"] = hashlib.sha256(code.encode()).hexdigest()
    record["tool_surface_status"] = "unverified_for_empty_tools; source audit required before any model call"
    binary = shutil.which("codex")
    if binary is None:
        record.update(status="blocked", failure_layer="missing_cli")
        return record
    spec = OSEnvSpec(type="caller_process", cwd=str(workspace), sandbox=OSEnvSandboxSpec(
        type="linux_bwrap", read_paths=[], write_paths=[], allow_network=False,
        cwd_allow_hidden=[], cwd_hidden_scan_overflow="error"))
    record["sandbox"] = {"type": "linux_bwrap", "allow_network": False,
                         "read_paths": [], "write_paths": [], "empty_private_state": True}
    launch = None
    try:
        launch = prepare_codex_worker(codex_path=binary, cwd=workspace,
            codex_home=state, os_env=spec, spawn_env_names=["PATH"])
        if not launch.sandboxed:
            raise RuntimeError("framework did not contain the worker; refusing launch")
        process = subprocess.run([launch.launch_path, "--version"], cwd=workspace,
            env={"PATH": "/usr/bin:/bin"}, capture_output=True, text=True, timeout=20)
        record.update(probe_command="<Omnigent-generated restricted launcher> --version",
                      exit_code=process.returncode, stdout=process.stdout, stderr=process.stderr)
        record.update(status="blocked", failure_layer=("sandbox_spawn" if process.returncode else "tool_surface_not_yet_verified"))
    except Exception as exc:
        # No credential sources are in this path; error logs are still reviewed before packaging.
        record.update(status="blocked", failure_layer="sandbox_preparation",
                      error_type=type(exc).__name__, error=str(exc))
    finally:
        if launch is not None:
            launch.close()  # Only the launcher owned by this preflight.
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt-dir", type=Path, required=True)
    args = parser.parse_args()
    attempt = allocate_attempt(args.attempt_dir)
    record = preflight(attempt)
    with (attempt / "preflight.json").open("x") as stream:
        json.dump(record, stream, indent=2)
        stream.write("\n")
    print(json.dumps(record, indent=2))
    return 2  # Preflight cannot establish OMNIGENT_READY, even if isolation succeeds.


if __name__ == "__main__":
    sys.exit(main())
