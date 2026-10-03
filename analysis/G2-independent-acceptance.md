# G2 independent acceptance — worker 02

Two real sequential full GPU pilots passed. The task explicitly supersedes the G1 worker-02 no-training restriction, authorizing at most two attempts, each at most 300 seconds. Both slots are consumed; no further GPU attempt is authorized by this task. No runner/schema change was made.

Runner: `4fcfadfb02e2c50e0dffde7b12ec6f2336fd1bd8`. Contract: `4d32d28a290c2c14baf6de497968a4584f20f4da`; the published `gate1-contract-v1` peels to this commit and is an ancestor of the runner. Execution used a separate clean detached worktree; this analysis commit is not the executed code version.

## Environment and inputs

A new Python 3.12.3 venv, without system site packages, used torch 2.8.0+cu128, NumPy 2.2.6, Pydantic 2.11.7 and RFC8785 0.1.4. Invocations used `-I -B`. Full observed freeze is private; direct pins are not represented as a hash-locked transitive environment. The old environment was retained. Hardware recorded by both runs: RTX 5090, driver 580.173.02, capability 12.0.

Existing official CIFAR archive was reused, not downloaded: SHA256 `6d958be074577803d12ecdefd02955f39262c83c16fe9348329d7fe0b5c001ce`; specified MD5 matched. Actual split indices were hashed independently with RFC8785 and matched `48a8983fa5fdf95d137855c818b7bc716c476396dbe5b274eec41982b27e815e`. Each run used all 45000 training and 5000 validation examples, one epoch, batch 128, learning rate 0.001, weight decay 0.0001, augmentation none. No test-batch scoring, smoke mode, model transfer or search.

## Real GPU results

| Run | Status | Accuracy (fraction) | Mean loss | Runner elapsed (s) | Training + validation loop (s) |
| --- | --- | ---: | ---: | ---: | ---: |
| Worker 02 seed42 | succeeded | 0.5646 | 1.2003214321136475 | 6.282014088001233 | 0.6477046320014779 |
| Worker 02 seed43 | succeeded | 0.5686 | 1.1968097543716432 | 6.23312706499928 | 0.6270552330006467 |
| Worker 01 seed42, user-supplied reference | reported succeeded | 0.5646 | 1.2003214321 | unknown | unknown |

Seed42 config hash: `ad62ac0451c300dd62242aa099bc5bf82d8100e55857a8901d8811ed608e324a`.
Seed43 config hash: `3b76a325fdd9fb5274fae31069a3730952492ec3be9ade20a963ee3c70d5139f`.

Against the supplied 01 reference, seed42 accuracy difference is 0.0000; loss difference is +0.0000000000136475. Loss agrees when rounded to the supplied ten decimal places; no arbitrary tolerance was introduced. Original 01 raw result/provenance was not independently obtained, so full-precision/driver equivalence remains unknown.

Seed43 minus local seed42 is +0.0040 accuracy (+0.40 percentage points) and -0.0035116777420043 loss. This is a two-seed observation, not statistical significance or evidence of a superior strategy. Loop-only timing excludes initialization; runner elapsed includes supervised initialization and completion. No relative-speed conclusion follows from these single-host observations.

## Checks and limits

| Check | Outcome | Evidence class |
| --- | --- | --- |
| Preflight, data dimensions/hash, split | passed | CPU with real official training batches; CUDA not initialized |
| schemas/tests + runner/tests | 56 passed in 1.91 s | CPU; runner result/timeout/cache fixtures are mocked |
| Config, unknown keys, bounds, seed/hash mismatch | passed within existing CPU suite | Contract fixture validation |
| Same-ID reuse/conflict, append-only retry/quota | passed within existing CPU suite | Synthetic jobs in temporary directories |
| Failure/timeout/null metrics and unrelated-process preservation | passed within existing CPU suite | Mock outcomes plus actual CPU child supervision; no real GPU fault injection |
| Both real request/Result bindings, execution counts, split/data hashes | passed | Raw GPU run evidence independently revalidated |
| Quota | passed | Fixed original ledger: two new reservations, sequential, no reset or relocation |
| Cross-driver bitwise equivalence / speed / significance | unknown | No sufficient comparison design or evidence |

The unchanged runner calls its ledger `.g1-quota` and labels reservations `RS-20261003-G1`. It was absent before G2, with an empty runs directory. The user explicitly authorized using this fixed ledger for G2; slots 1 and 2 carry the fresh G2 IDs. Never delete/reset/move it to regain quota. Raw requests/results, progress, execution, provenance, split indices, device and timing evidence are retained privately; public files contain only reviewed conclusions.

Next: control reviews the handoff and documentation commit, then decides any later experiment authorization. This task grants no third attempt.
