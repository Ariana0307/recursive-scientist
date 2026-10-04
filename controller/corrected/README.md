# Corrected controller and dispatcher source

These six files are configurable adaptations of the actual G14 protocol builder, controller, bounded Qwen runner, audit builder, remote job owner and independent objective scorer. The source implementation completed a separately approved 12-request experiment. This public adaptation has passed offline checks only; it has not been deployed or run against a model in a new environment.

`recorded-config.json`, `recorded-frozen-proposal.json` and `recorded-payloads/` are sanitized recorded fixtures. `recorded-pre-review.json` binds approval to the original implementation hashes, NOT to these edited public files. `recorded-execution-fidelity.json` records that all twelve original requests matched their frozen previews. Scientific acceptance and original-explanation review belong to the research report, not to these engineering tests.

The example `runtime.json` disables live execution. It configures existing model/SSH endpoints and Python rather than installing software, downloading weights or creating paid resources. Private SSH credentials are not distributed. Supply an existing environment matching `requirements-recorded.txt`; fresh dependency installation was not tested. Paths in `remote_root` must be absolute paths without shell metacharacters or whitespace, because the inherited controller sends remote shell commands.

Offline checks with the existing SDK:

```
PYTHONDONTWRITEBYTECODE=1 python test_payload_capture.py
PYTHONDONTWRITEBYTECODE=1 python test_gate_offline.py
```

The first constructs twelve requests through the actual SDK and intercepts them before HTTP. They must equal the original previews exactly. Every pair must be identical except for the intended system prompt, including audit content. The SDK logs a connection error for the deliberately interrupted capture; the final PASS and zero ledger reservations distinguish this from a live model request. The second executes the runner's actual hash/approval gate with temporary synthetic records, confirming refusal of unapproved or changed inputs. It does not fabricate scientific approvals or send requests.

For a future live deployment, use a fresh working copy and run root. The operator must provide a new authentic researcher protocol as `frozen-proposal.json`, run `prepare.py`, and obtain independent preflight and a real Codex review bound to the new exact `config.json`, `qwen_batch.py` and twelve payload hashes in `gate-candidate.json`. The original approval must not be copied into an active `pre-review.json`: adaptation changes hashes. `dispatch_control.py precheck` runs the independent remote objective precheck, and the execution mode requires matching authentic review/preflight/hash records before reservation. The controller transfers `runtime.json` and the configuration loader with the runner. Existing service metadata and the environment must already exist at the configured remote root, as in the recorded setup; this code is not a service installer.

This directory contains real dispatch code, not just an evidence-reader API. It still requires integration with the adjacent authentic Omnigent role adapter and the operator's existing deployment; it does not claim a one-command portable research service. All new-environment SSH, GPU execution, process ownership and forced-cancel behavior remain unverified. The historical directory elsewhere in this candidate remains disabled and documents the invalid earlier protocol. No license grant is made by this source candidate.
