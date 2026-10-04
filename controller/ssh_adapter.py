"""Configured SSH RPC equivalent to the recorded controller's remote job calls.

Does not install dependencies, transfer weights, or launch an inference service.
"""
import json
import shlex
import subprocess
from runtime_config import CONFIG, require_execution, ssh_args

def rpc_argv(action, batch):
    if action not in {'start', 'status', 'stop'} or batch not in {'batch-1', 'batch-2'}:
        raise ValueError('unknown bounded action or batch')
    command = [CONFIG['remote_python'], CONFIG['remote_root'] + '/remote_job.py', action, batch]
    return ssh_args() + [CONFIG['ssh_host'], shlex.join(command)]

def rpc(action, batch):
    require_execution()
    process = subprocess.run(rpc_argv(action, batch), capture_output=True, text=True, timeout=30, check=True)
    return json.loads(process.stdout)
