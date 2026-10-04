"""Deployment inputs for the sanitized source candidate; never stores credentials."""
import json
import os
from pathlib import Path


def load_config():
    path = Path(os.environ.get("RS_CONFIG", Path(__file__).with_name("runtime.json")))
    config = json.loads(path.read_text())
    if config["request_limit"] > 12 or config["retry_limit"] != 0:
        raise ValueError("This candidate allows at most 12 attempts, without retries")
    return config


CONFIG = load_config()


def require_execution():
    if CONFIG.get("enable_execution") is not True:
        raise RuntimeError("Live execution is disabled in this source candidate configuration")


def ssh_args(copy=False):
    args = ["scp", "-q"] if copy else ["ssh"]
    identity = CONFIG.get("ssh_identity_file")
    if identity:
        args += ["-i", str(Path(identity).expanduser()), "-o", "IdentitiesOnly=yes"]
    args += ["-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "-o", "ConnectionAttempts=1",
             "-o", "StrictHostKeyChecking=yes", "-o", "ForwardAgent=no"]
    return args
