# G3 control review and bounded local-model plan

## Reviewed handoffs

The two G2 input packages passed archive SHA256, relative-path, CRC, manifest identity, and per-payload size/SHA256 checks. Private reports remain outside version control.

Worker 02 documentation commit `676492d7bc8797994eb699fcba79c28b37d7266e` has runner commit `4fcfadfb02e2c50e0dffde7b12ec6f2336fd1bd8` as its parent. Its three changed files are `analysis/G2-independent-acceptance.json`, `analysis/G2-independent-acceptance.md`, and `docs/worker-02.md`. The unchanged commit is published as `dev/eval-5090-02`. No merge into main was made.

The original worker 01 proposal contains 18 candidates and a 27-run budget. The G3 proposal in `docs/campaign-g3-proposal.json` retains that candidate space but replaces the budget with 24 total training attempts. The old proposal remains immutable. All 31 proposed configuration templates passed the frozen contract validator; that does not authorize execution.

Two historical one-epoch results passed ExperimentConfig/Result validation and match_result, including code revision, seed, RFC8785 config hash, and fixed split identity. They are evidence of runner behavior, not part of a future three-epoch comparison. Two seeds at one hyperparameter setting cannot establish which search variable helps. Source records and exact metrics are retained only in the private handoff.

## Local gateway audit

Installed Omnigent version: 0.16.0. The official [gateway documentation](https://omnigent.ai/docs/build/models#gateway) explicitly supports Ollama with the OpenAI-agents harness and a local OpenAI-compatible endpoint. Source inspection confirms that OpenAIAgentsSDKExecutor supports an injected AsyncOpenAI client and use_responses=False. Its Agent tools are built from the supplied ToolSpec list; an empty list in this SDK path exposes no native shell. No Codex harness was launched.

The intended boundary is a trusted Python controller supplying explicitly validated historical records to separate named role sessions. The agent receives no shell, arbitrary file operations, MCP, plugins, training tools, or dispatch authority. This is an application-level capability boundary, not an OS sandbox claim.

Before a future request, a transport guard must verify the exact loopback destination, requested model, max_tokens <= 1000, empty tools, and timeout <= 120 seconds; increment a durable six-request ledger before dispatch, including diagnostics and retries. SDK retries must be disabled and Omnigent's internal empty-turn retry must also remain subject to that transport ledger. ExecutorConfig.extra max_tokens must be checked on the serialized request, not assumed from the top-level field. Tracing must be disabled. No request was sent in G3, so transport propagation is NOT runtime-verified.

Planned sequence: local diagnostic, Omnigent OMNIGENT_READY, then Evidence -> Hypothesis -> Planner. Each role output must pass a closed Pydantic model before being passed onward with source/session/output-hash identity. Hypothesis and Planner select only variable/direction enums; trusted code samples exact values within the shared catalog. No role JSON or READY result exists yet; these are requirements, not a completed implementation or handoff.

Official Ollama 0.35.1 was unpacked privately. Startup was withheld because its [RunServer/initializeKeypair implementation](https://github.com/ollama/ollama/blob/v0.35.1/cmd/cmd.go#L1968-L2026) creates identity state in the default user home before binding a listener. The reviewed CLI/envconfig has a model-directory option but no separate identity-directory option. The current project-only path boundary does not allow creating that default state, and HOME was not reassigned. This is a startup preflight blocker, not a runtime failure or proof that Omnigent cannot work. Model download was not started. No new service, listener, training, or model request was created.

## Campaign authorization and rollback

This round prepares only. The proposed 24 attempts require a later explicit authorization. The old G1 worker limits are historical; no G3 GPU training is authorized. Control remains the sole integrator and shared-contract owner; worker ownership/branches remain unchanged.

Keep the private install, extracted references, and historical records for investigation. No new service requires stopping. Future rollback must stop only task-owned processes after checking their identity, preserve model/data directories, and revert reviewed code commits; never reset --hard, clean, force-push, or rewrite worker commits.
