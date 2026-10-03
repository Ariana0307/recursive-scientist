# G5 integration and unapproved search preparation

## Integrated history

The original search commit `b15b9817b49889d5eb4bea4b93836d3e0a828b65`, rule commit `f19e4f18d17433c9d7398f15b516c9d716158564`, and control commit `f67efa65438bf13cf3abcab044a77ff50bce7cf4` are ancestors of `dev/integration-g5-r1`. Both worker commits were published unchanged to `dev/search-5090-01` and `dev/eval-g4-5090-02`; the existing control ref was verified. Two ordinary merge commits preserve original history. There were no merge conflicts or manual conflict resolutions. Main is unchanged.

The G4 success criteria and final-test protocol remain the frozen scientific rules. Historical WAITING statements describe their original review scope; integration and CPU tests do not upgrade them to real search, final-test or scientific success. The evaluator remains SHA256 `68d34bb53116e8d1debc77b65b08320c52836a5b31414a7a32239b33b5d79bc7`. Imported tests verify that G3 method/authority sources are unchanged and the engine change only adds post-score artifact saving. Adam, model, split and scoring are preserved.

## Frozen G5 inputs

`runner/plans/search-worker-01.json` and `search-worker-02.json` now contain the actual G5 **draft** allocation. Worker 01 is `01_train`; worker 02 is `02_deploy`. Both have six slots, seeds 42..47, epochs=3, batch_size=128, fixed small-cnn-v1/data/split/evaluator and 300-second timeout. Worker 01 arms alternate random/ai/random/ai/random/ai; worker 02 uses the inverse. Each strategy has three slots per worker and six globally. This confers zero execution authorization.

`configs/g5/random-global.json` records the timestamp, complete sorted catalog, full permutation, six draws and list hash. NumPy 2.2.6 `Generator(PCG64(20261004)).permutation(18)` selects the first six without replacement. The tuples sort by numeric learning_rate, numeric weight_decay, then ascending augmentation strings: **basic before none**. This explicit ascending string order is distinct from the domain's presentation order `[none,basic]`. One global draw is assigned to the Random worker in each round; there are no independent per-worker draws.

The complete freeze record is `configs/g5/freeze-manifest.json`; it contains RFC8785/SHA256 worker-plan hashes, global-list hashes and the initial AI proposal hash. `python -m orchestrator.validate_g5` performs a read-only revalidation, including regeneration in memory. It never authorizes a campaign. `freeze_g5` is trusted draft-authoring code, not a research tool; do not rerun it to change frozen inputs without a reviewed new version.

`configs/g5/ai-initial-proposal.json` binds the genuine G4 Planner direction and trusted numeric sampler record to AI trial 1, round 1, seed 42, worker-02/02_deploy: learning_rate=.003, weight_decay=.0001, augmentation=none. It retains source hashes/session provenance, not an invented new model response. AI rounds 2..6 have no prechosen parameter values. Failure and retries continue to consume future authorized budgets; this preparation creates no quota or authority.

## Two registered research capabilities

`read_ai_history` accepts only `{ "view": "ai_visible_history" }`. Trusted ingestion validates full ExperimentConfig/Result identity, config/split hashes, source-byte hashes and the bound AI plan slot. Random and test records are rejected. A snapshot includes exactly the common three-seed baseline and every prior completed AI-strategy result, including failure/null metrics, across the two execution workers. Missing, duplicate or future AI rounds fail closed. The SDK receives neither worker plans nor random catalog/score data.

`submit_experiment_proposal` accepts only the three strict finite allowlisted hyperparameters: learning_rate, weight_decay, augmentation. Paths, commands, seed, role, budget, authorization, epochs and batch size are rejected. Trusted current round binds worker/role/seed. Round 1 must equal the preserved G4 proposal. Later rounds remain undecided until their actual future call. The only effect is an append-only unapproved proposal in a controller-selected directory; a matching duplicate reuses its receipt, a conflicting proposal is refused. No authority or training entry point is exposed.

The tool callback uses Omnigent 0.16.0's actual `_tool_executor` hook and `ToolSpec` list. Its `_build_tools` constructs actual SDK FunctionTools, whose callbacks invoke the strict dispatcher. This is a version-pinned internal integration, not a promise of compatibility with a future Omnigent release. Schemas prohibit extra fields; validation is enforced in callbacks even though this Omnigent implementation sets SDK `strict_json_schema=False`. Required read arguments also prevent malformed JSON being silently treated as a valid empty read request.

`orchestrator.research_feedback.run_feedback` is the real SDK execution entry for Evaluator → Hypothesis → Planner with an explicitly injected transport. The current CLI **only permits in-memory MockTransport**. Future real model execution requires separate authorization and a trusted caller; none occurred in G5. Evaluator must call the history tool; its classification is checked against the visible verified metrics. Hypothesis emits exploratory directions; trusted code samples concrete candidates. Planner submits a candidate through the registered proposal tool, and its receipt is bound to the chosen hypothesis. Each validated output, hash and session identity becomes the next role's input. No HandoffTool is called or claimed.

The gateway transport permits only the explicit tool-name allowlist and rejects native/MCP/handoff capabilities. The old G4 default still allows zero tools. Model seed/budget/authorization are never controlled by tool arguments. This is an application capability boundary under a trusted operator, not isolation from a same-UID hostile process.

## Environments and validation limits

No environment was rebuilt or upgraded. The existing Python 3.12 contract environment handles NumPy 2.2.6, RFC8785 and complete result validation. It emits a SHA256-pinned, closed AI-visible snapshot. The existing Omnigent environment serves that snapshot using Pydantic and the SDK; it has no NumPy/torch dependency added. A trusted supplied snapshot digest binds the handoff between these existing environments. Models cannot choose the snapshot path or expected hash.

Current results: 60 contract/plan/history/tool CPU tests; 14 selected imported CPU tests; 7 SDK/mock and prior transport tests passed. Twenty-one imported tests were deselected: authorization-related fixtures would call the prohibited SearchAuthority.authorize API, and tensor/GPU dependencies are absent locally. No such call was made, including a draft-rejection call. This is not a full rerun of the worker's historical suite.

The final demo exercises the actual SDK with five **simulated transport requests**, including both real local tool callbacks and predecessor references. Model text is synthesized by MockTransport and explicitly labeled `cpu_mock`; these are not real generation responses. Real generations=0, training starts=0, production authorizations=0. No model/data downloads, services, network listeners or firewall/SSH changes were made. Existing ledgers and G4 real-generation evidence remain untouched.

## Remaining gate and rollback

The integration branch and bundle prepare inputs and interfaces only. Real scientific feedback, production dispatch, cross-machine reservation reconciliation and final testing are not validated by this task. Workers should fetch into new worktrees, validate the plan hashes, and report readiness without running authorize/run. A later explicit review and authorization is needed before real model generation or search.

Retain old references and ledgers. Isolate this worktree or revert reviewed commits. To revert a merge, inspect its parents and select the appropriate mainline explicitly; never reset --hard, clean, delete ledgers or force-push. Preserved worker branches remain usable independently.
