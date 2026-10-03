# Single G1 runner

This directory is the only training implementation. Worker 02 must use the exact
full runner commit, shared contract, and pinned dependencies, not a second runner.
No public command accepts an arbitrary executable, model, dataset or output path.
The operator supplies an approved request JSON file. All job/data locations are
fixed under `Path.home() / 'recursive-scientist-local'`; data is never committed.

Use a **separate Python 3.12 venv**, with system-site-packages disabled. Install
`requirements-test.txt` and `requirements-torch.txt` using their official indexes.
Do not install torchvision. Save the observed complete package freeze privately.
Always launch with `-I -B` to exclude inherited Python paths and user site packages.
The CLI adds only its own reviewed checkout to the isolated import path.

From this checkout, with `RS_PYTHON` set to your private venv interpreter:

```sh
"$RS_PYTHON" -I -B runner/cli.py preflight
"$RS_PYTHON" -I -B -c 'import sys,pytest; sys.path.insert(0,"."); raise SystemExit(pytest.main(["-q","-p","no:cacheprovider","schemas/tests","runner/tests"]))'
```

Preflight verifies the archive before deserialization, reads only the five named
training batches, checks the contract split and environment, and initializes no
CUDA context. The source archive must be the official `cifar-10-python.tar.gz`
with MD5 `c58f30108f718f92721af3b95e74349a`, under the private `data/` directory.
The runner records SHA256 and does not load `test_batch` or write model weights.

Only worker 01 is authorized for G1 GPU attempts. Before execution, commit all code,
ensure clean `git status`, copy `configs/baseline.json` to private storage, set a fresh
experiment_id, status `approved`, and code_version to the exact clean full runner
commit. Keep the resolved config unchanged (or recompute its RFC8785 config_hash
using the shared validator). Validate the final bytes with ExperimentConfig. No
committed template claims to be approved for a future commit.

```sh
# Operator-only diagnostic: 128 train / 64 validation, one epoch, no benchmark metrics.
"$RS_PYTHON" -I -B runner/cli.py run "$RS_SMOKE_REQUEST" --smoke
# Full pilot: all 45000 train / 5000 validation, one epoch per baseline.
"$RS_PYTHON" -I -B runner/cli.py run "$RS_PILOT_REQUEST"
```

The smoke intentionally emits a contract `cancelled` result with null accuracy/loss
(exit 2); completion evidence is `execution.json`, which must show 128/64 samples.
It consumes one of the two G1 GPU reservations. The full pilot must emit a validated
`succeeded` Result (exit 0), or its real failure/timeout (exit 2). No subset success
claim is permitted. Admission/config/environment errors exit 1, before GPU use.
A successful same-request cache hit or in-progress admission exits 0; inspect the
`admission` field, not just the process exit code.

Each invocation validates the complete request, approval, exact HEAD, clean tree
and independent environment before dispatch. Per-ID locks prevent concurrent
attempts. Results are matched back to requests on reuse. Full-envelope conflicts
are rejected. Terminal failures can be retried only in a new append-only attempt
subdirectory, consuming the same global two-attempt quota. Lost or ambiguous state
requires manual review. Never delete quota reservations to obtain more attempts.
Quota reservation occurs before child launch; crashes/spawn failures conservatively
consume a slot. A zero-attempt interrupted ID also requires review.

The parent enforces the configured <=300 s wall deadline over its own child process
group, including Python imports, data/model initialization and final validation.
It never targets pre-existing process groups. SIGINT/SIGTERM cancel that job and
produce a terminal record. An uncatchable parent crash leaves a review-required
attempt, never automatic rerun. Original child errors stay in private worker.log;
public Result messages contain no private paths or echoed untrusted content.

Training exactly follows docs/interfaces.md. Shuffle and augmentation share a
dedicated CPU torch.Generator(seed). For every epoch: randperm(train_count), then
for every selected image (basic only) randint(0,9,(2,)) top/left and rand(())<0.5
horizontal flip. Num_workers=0, no drop-last, validation sorted, no AMP/scheduler,
Adam, fixed small CNN. TF32 is also disabled. Deterministic failures remain failures.

02 acceptance: verify full commit and clean tree, official archive hashes,
requirements and preflight; run CPU tests and inspect the matching request/Result,
`provenance.json`, `data.json`, `execution.json`, and split indices. G1 does not
approve worker 02 training. The private G1 handoff contains actual pilot request,
commit and outcomes; no model weights or dataset need to be transferred.
