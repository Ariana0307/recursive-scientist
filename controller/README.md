# Controller source candidate

This is a sanitized source candidate, not a claim that the corrected experiment has run. It contains real historical controller/dispatcher source as well as configurable components adapted from that implementation. It includes the corrected dispatcher in `corrected/`, adapted from the actual approved G14 implementation. The original implementation completed 12 real requests; the public configuration adaptation has only been tested offline and has not been independently reproduced in a new environment.

## Contents and status

- `corrected/`: actual final G14 controller, protocol builder, bounded dispatcher, shared audit, remote owner and independent scorer, with configurable deployment and execution disabled by default. Its actual SDK payload construction and hash gate passed offline checks. See its README and STATUS.json for original-versus-adapted validation boundaries.
- `historical/`: complete recorded controller, protocol constructor, Qwen dispatcher, remote job owner, Omnigent role adapter, independent scorer and state primitives. The controller/dispatcher/scorer entry points deliberately fail immediately: the historical second batch gave only the selected arm a computed audit, so rerunning it would reproduce a known invalid comparison. These files document what actually ran; they are not a corrected runnable pipeline.
- `audit_contract.py`: the existing offline correction, which constructs one computed audit and identical paired user payloads. It is not proof that a live dispatcher used it.
- `omnigent_team.py`: configurable adaptation of the real public `omnigent.CodexExecutor` researcher/reviewer integration. Qwen is not assigned a research role. This adaptation has not made live calls in a new environment. It retains version-sensitive private session/event integration inherited from the source.
- `ssh_adapter.py`, `remote_job.py`, `lifecycle.py`: configured SSH RPC, owned remote job and durable state components. No new-environment SSH execution, cancellation or process-ownership validation is claimed. The top-level components remain general adaptations; the corrected dispatcher and its matching remote owner are in `corrected/`.
- `evidence_tools.py`: a bounded run-root evidence reader for the actual role adapter. Private runtime directories are excluded.
- `config.example.json`, `runtime_config.py`: deployment inputs with execution disabled. Credentials, SSH identity contents, addresses, weights and environments are absent. Runtime metadata/results can contain private paths and should remain private until reviewed.

## Offline verification

Run `PYTHONDONTWRITEBYTECODE=1 python3 test_offline.py` from this directory. This checks Python syntax, positive/negative/zero numeric audits, missing-test/p=alpha/p<alpha evidence audits, shared payload equality, durable reservation, persistent stop-pending state, SSH argv and the disabled default. It makes zero model or network requests. These checks do not validate the actual SDK-generated HTTP payload or a live corrected dispatcher.

For future integration, copy the example config outside the source directory and set `RS_CONFIG` to its location. Existing Python 3.11+ / Omnigent / OpenAI SDK / httpx installations and authenticated Codex must be supplied by the operator; no dependencies are installed here. Use a fresh run root and existing model service. A fresh authentic Codex protocol/review and deployment-specific hashes must be supplied before enabling execution. Recorded approval is not transferable to edited source or a new deployment. No automatic installation, model download, retry or paid resource creation is included.

The project owner has not supplied an open-source license. See `LICENSE_STATUS.md`. This candidate grants no new software license. The recorded website and earlier recorded 24-request run remain independent of this engineering candidate.
