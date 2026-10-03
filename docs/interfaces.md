# Executable G1 contract v1 (schema_version 1.0.0)

Control owns `schemas/contracts.py`. This supersedes the G0 draft while retaining its identity, config, validation, runtime and decision meanings. Import ExperimentConfig, Result, Decision; validate untrusted bytes with `Model.model_validate_json(payload)`. Models are strict, frozen and forbid unknown fields recursively. Never use model_construct or unvalidated model_copy for incoming data. Model JSON schemas are descriptive only: cross-field checks and RFC8785 hashes require the Python validators.

## Config and baseline

See `configs/baseline.json` (a real valid proposed request, not a measured result). All config fields are required: seed uint32, learning_rate [0.00001,0.1], weight_decay [0,0.01], augmentation none/basic, epochs 1..3, batch_size one of 16/32/64/128/256, split_seed 20261003, model small-cnn-v1, dataset cifar10-python-v1, timeout_seconds 1..300. Timeout is duplicated in runtime and must match. The outer seed must equal config.seed. All numeric values must be finite, strings are not coerced into numbers, and boolean seeds are rejected.

No code, command, import target, arbitrary model/dataset, tool, input path or output path can be supplied. Runner chooses all local paths. experiment_id is an ASCII alphanumeric initial character followed by at most 63 alphanumerics/underscores/hyphens; no traversal. Rationale and error messages are inert bounded descriptive text, never evaluated as code or used as paths/commands.

The baseline is `proposed`; before local execution, 01 verifies clean checkout and sets status to `approved`, updates code_version to the actual full clean runner commit, and validates again. This does not change config_hash. A tag cannot self-reference its own commit in a committed sample: baseline code_version records the real prior source commit, not a fabricated runner version. Do not execute this scaffold commit as though a runner exists.

## Fixed model and training semantics

small-cnn-v1: NCHW float32 input; Conv2d(3,32,3,padding=1,bias=True), ReLU, MaxPool2d(2); Conv2d(32,64,3,padding=1,bias=True), ReLU, MaxPool2d(2); Flatten; Linear(64*8*8,128,bias=True), ReLU; Linear(128,10,bias=True). No dropout, batch norm, pretrained weights or architecture search. Use PyTorch default parameter initialization after seeding Python random, NumPy and torch (including CUDA).

Convert uint8 pixels to float32 /255, then normalize each channel with mean=(0.5,0.5,0.5), std=(0.5,0.5,0.5). basic training augmentation: zero-pad raw pixels by 4 on every spatial edge, random 32x32 crop (top,left independently uniform integers 0..8), horizontal flip with probability 0.5, then conversion/normalization. none skips padding/crop/flip. Validation is always conversion/normalization only. Use a dedicated seeded CPU torch generator for training shuffle/augmentation, num_workers=0, shuffle train each epoch, drop_last=False; validation in ascending index order. Record precise RNG implementation in runner provenance. Optimizer Adam (not AdamW), lr/weight_decay from config, betas=(0.9,0.999), eps=1e-8; no scheduler, no AMP; mean CrossEntropyLoss. Enable deterministic algorithms, disable cudnn.benchmark, set CUBLAS_WORKSPACE_CONFIG=:4096:8 before CUDA initialization. Unsupported deterministic operations produce a failure, not a silent fallback. Train on all 45000 indices, validate on all 5000 after the final epoch; if the hard time budget is reached first return timed_out. No subset success claims.

## Immutable split

Only official 50000 training images participate. Number data_batch_1 rows 0..9999, then data_batch_2, through data_batch_5 (index 49999). NumPy 2.2.6 Generator(PCG64(20261003)).permutation(50000): first 5000 are validation, remaining 45000 train; sort each selected index list ascending. See `schemas/split.py` and `schemas/split_manifest.json`; no dataset is needed to reproduce indices.

split_indices_hash = SHA256(RFC8785({"train": [45000 sorted indices], "validation": [5000 sorted indices]})). The committed manifest saves the golden hash; all requests/results must match it. Worker stores the actual indices in local run evidence. Official 10000 test images are neither read nor used for selection or scoring in G1.

## Identity, results and decisions

All objects require schema_version, experiment_id, seed, config, config_hash, code_version. config_hash is lowercase SHA256 of RFC8785 UTF-8 canonical bytes of the entire resolved config object, implemented by pinned `rfc8785.dumps` (not json.dumps). No omitted defaults. Commit is full 40-hex Git identity; runner must check HEAD equals request.code_version and tree is clean before starting. Runtime limits and seed are hashed inside config. Validation split metadata is independently checked against the fixed split.

ExperimentConfig.status is proposed/approved; runtime has timeout_seconds and device_class=cuda; validation fixes metric=accuracy, objective=maximize and split identity/hash. A proposal does not authorize execution.

Result.status is succeeded/failed/cancelled/timed_out. Validation.metrics has accuracy in [0,1] (never percent), and nonnegative mean loss. Both are required and measured on all validation images on success; both MUST be null otherwise. No partial metrics in v1. Non-success has bounded sanitized error.kind/message. Timeout and cancellation have their own kinds. runtime records elapsed_seconds (monotonic wall duration), timezone-aware started_at/finished_at, and actual_device (cuda/cpu/null); success requires all four. All time quantities are seconds. Null records unavailable facts, never invent values. Consumers must call match_result(request,result), not only validate a standalone result.

The runner enforces the hard timeout on its own newly spawned job process group, including model/data initialization and validation, using monotonic time; do not kill unrelated processes. Pre-download/verify data separately. On deadline terminate that job, then emit timed_out with null metrics; elapsed may exceed budget by teardown overhead, never claim successful completion after deadline.

Decision.experiment_id and evidence_result_id identify the source experiment; in v1 these IDs are equal. config/seed/hash describe the proposed next config (or retained config for stop/review), code_version is decision implementation. observed validation metrics describe the source result, never the next proposed config. Copy them from a validated matching Result; they are null for failures. status=propose_next requires a distinct next_experiment_id; stop/needs_review require null. runtime.elapsed_seconds measures decision time; rationale is inert text; strategy_version is a bounded identifier. No decision execution loop is implemented yet.

## IDs, retries and G1 quota

A new ID creates runs/<experiment_id> exclusively. Runner validates before allocating, then holds a per-ID lock. Same ID with any changed config hash is a conflict; same hash but different code_version, timeout, approval or other envelope fields is also a conflict. The complete approved request is immutable. `retry_action` returns in_progress for a running attempt, reuse for a succeeded result, and retry for terminal non-success. Retry creates a NEW append-only attempt-N directory, preserving all earlier attempts. Never run concurrent attempts under an ID; lost/unknown state requires manual review, not blind rerun. Revalidate returned cached results with match_result. A new proposal/config/code version uses a new ID.

G1 allows worker 01 at most TWO total GPU attempts, each <=300 seconds; retries consume that same global quota. Runner must persist and lock this quota locally across IDs/restarts. Passing validation does not implement timeout, quota or filesystem locking: these remain runner responsibilities. Worker 02 only downloads data/checks environment this round. No control-host training or CIFAR download.

## Verification

`python -m pytest -q schemas/tests` tests acceptance/rejection, identity/hash, immutable split, result consistency and retry admission. See docs/environment.md for pinned independent Python 3.12 setup. Public tests contain synthetic contract fixtures only, not experiment outcomes.
