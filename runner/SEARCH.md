# Controlled search preparation: G4 has zero GPU authorization

G4 adds an independent search mechanism; it does not alter or extend G3. G3's
three slots remain exhausted. The committed worker plans are **draft examples**,
not executable authorizations. No real search authority/budget is created in G4.
The search CLI deliberately has no `authorize` action.

## Trust and closed plans

`search_plan.py` defines strict/frozen Pydantic models, rejects extra fields, and
validates cross-field invariants. The generated `plans/search-plan.schema.json`
is descriptive; use `SearchPlan.model_validate_json` for authoritative validation.
Plans lock campaign/task/worker/role, every slot's seed and arm, the exact 18-member
parameter grid, 3 epochs, batch 128, fixed model/dataset/split, 300 seconds, and at
most six starts with at most three random and three AI slots per worker.

Both examples have three slots per arm, so their combined prospective budget is
six random and six AI starts. No inter-machine service is introduced. The trusted
controller must approve one bound plan per worker, not issue duplicate allocations.
Example seeds 42/43/44 and random draws are proposals, not approved future inputs.
Worker-02 role is UNASSIGNED pending the controller. Its example cannot be approved
until that identity is resolved. Random candidate draws are frozen in the plans:
NumPy2.2.6 PCG64 seeds20261004/20261005, permutation of the 18 lexicographically
ordered (lr,wd,augmentation) combinations, first3. AI choices remain unknown.

The scientific model's entire request is JSON with learning_rate, weight_decay,
augmentation. It cannot pass a seed/role/arm/campaign/path/command/budget or approval.
The trusted sequence selects the next plan slot; random slots must exactly match
the precommitted draw. Parent and child independently reconstruct and validate the
full approved ExperimentConfig from these parameters and trusted plan identity.
Extra fields, altered seeds, wrong roles, invalid ranges, plan/commit/hash tampering,
exhausted quotas and mismatched child requests are rejected.

Only a future explicitly authorized operator may commit an approved worker plan
and call the internal `SearchAuthority.authorize()` API, from clean committed code.
It requires the exact versioned allowlisted worker-plan file. That creates an
owner-only signing key and mirrored signed authorization in **new search-only**
private directories. G4 does not call it outside isolated synthetic CPU fixtures.

The local launcher defaults to worker-01/01_train. A future controller can install
an operator-private `search-worker-binding.json` under the fixed project-private
root with closed worker_id/role fields for the other worker. No environment or
model JSON selects it. Both parent and child read the same protected binding.
No binding file is created in G4. The Python implementation is reusable on both
workers; identities/roles require trusted binding, not a code fork.

The implementation reuses G3's storage lock, exclusive atomic writes, timeout
supervisor, canonical signing representation and clean-commit check. It follows
the same primary+mirror reservation and sealed memfd one-use child claim protocol
in a separate authority object. G3 files and ledger formats remain byte-identical.
Reservations persist across restarts, failures/timeout/cancellation consume slots,
and an unknown/missing mirror or unfinished attempt fails closed. Only one active
attempt is permitted. No counter refund or blind retry is available.

As in G3, the operator is trusted and scientific models have **no host shell or
filesystem tools**. A same-UID unrestricted process could read the operator's key
or edit files; chmod is not claimed as a sandbox against it. Such a model must not
be connected here without a separate identity/broker. No accounts/security policy,
SSH, firewall, ports or services are changed in G4.

## Model artifact transaction

Only the new search child sets save_state_dict. Legacy G1/G3 entry points retain
their prior behavior and are not rerun/backfilled. After the unchanged complete
training and validation, the child stages CPU-cloned tensor state_dict entries in
its fixed private run's `.model-pending` directory with atomic file writes. It
saves neither the entire model object nor optimizer/RNG objects. torch.save's
container stores tensor-only state_dict; loading uses `weights_only=True` and
`map_location='cpu'` with a matching successful Result and SHA256 check.

The parent first validates the child outcome, checks artifact identity/hash, then
atomically renames the complete directory to model-artifact. The final atomic
successful result.json is the **commit marker**: artifact.json explicitly requires
that matching successful Result. A crash/timeout/cancellation may retain diagnostic
staged or uncommitted bytes, but `load_success` rejects them. Existence of a .pt file
alone never means success. There is no externally supplied weights path; only a
trusted resolved run identity reaches the internal artifact functions.

Metadata records seed, full config/config_hash, training commit, evaluation hash,
experiment ID, bytes and SHA256. Weights are private and excluded from Git/ZIP.
Saving occurs after all random/training/scoring work. CPU tests check exact loaded
predictions and unchanged Python/NumPy/torch/dedicated-generator RNG states. The
only engine diff is this post-score opt-in; model/split/preprocessing/evaluation
remain unchanged. No GPU save/load validation was authorized or claimed in G4.

## Future final-test interface (specification only, not implemented)

A trusted controller must first freeze the winning training-run identity, its
successful Result, artifact SHA256, config/seed/training commit and evaluation
hash. A separately authorized final-test operation should accept **only that
registered artifact identity**, not filesystem paths, model code, commands or
new hyperparameters. The trusted resolver locates the private run, checks the
matching success marker, hashes, tensor shapes and `load_state_dict(strict=True)`.
It must never accept an arbitrary pickle model or weights file from an agent.

Final test requires a new signed task/role/dataset/operation authorization and
its own usage policy, not search/G3 slots. No model selection/adaptation may use its
results. The immutable evaluator hash below must be checked; the existing
training-only loader remains unchanged, and a separately reviewed test-only loader
would be required. Neither a test loader nor final-test dispatch is implemented
here. **No official test examples are read or scored in G4.**

Frozen evaluate.py SHA256:
68d34bb53116e8d1debc77b65b08320c52836a5b31414a7a32239b33b5d79bc7

## Checks, next inputs and rollback

CPU checks: shared old contracts/runner/G3 tests; plan bounds and exact request
binding; role/seed mismatch; authorization tampering; concurrent last slot;
persistent failures; child one-use; artifact numerics/RNG, corruption, failed and
timeout gating; frozen evaluator/old G3 source and post-score-only engine diff.
Fixtures use temporary paths and synthetic outcomes, never production authority
or data/GPU. Do not treat their synthetic accuracy as experiment evidence.

Safe current action: `python -I -B runner/search_cli.py validate-plan`.
`run` is deliberately rejected by the draft plan. Future operator must supply the
actual next task/campaign IDs, worker-02 role, per-slot seeds and random/AI schedule,
commit the approved plans and receive explicit training authorization first.
This G4 preparation confers zero starts. Model inputs cannot perform that upgrade.

Rollback: stop exposing search dispatch, retain all evidence, use the unchanged
G3 worktree for reference, or make reviewed revert commits on a new branch. Never
delete/reset/rename old authority to reclaim quota. G3 still has zero remaining
slots. Existing completed G3 runs cannot yield model weights retroactively.
