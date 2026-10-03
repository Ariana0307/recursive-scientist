# G4 local research role handoff

## Published worker history

The original worker commits were reviewed and published unchanged:

- `dev/campaign-5090-01`: `931049af15ddafa12a5163e924a3ea84bbfbbf3f`.
- `dev/eval-g3-5090-02`: `2cdd3a512aacaaff3a521d1e2c474d4466dfdcc5`.

The first implements the previously authorized three-start baseline campaign. Publishing it grants no new training starts. The second audits the older runner and proposes acceptance gates; its WAITING statements must not be mistaken for acceptance of the newer campaign. Main remains unchanged. No scripts from the handoff archives were executed on control.

`g4-baseline-evidence.json` is a sanitized evidence index. Its three original request/result pairs passed the frozen contract, including code version, RFC8785 config hash and split identity. Prediction counts and all 5000 ordered validation indices per seed were independently checked. The mean is 0.6637333333333333, sample standard deviation 0.007400900846068241 and exploratory 2*sigma 0.014801801692136482. This is neither a significance test nor evidence that a search variable helps. Old one-epoch pilots are excluded. Source records and private manifests remain local.

## Actual model execution

Ollama 0.35.1 served the official `qwen3:4b` Q4_K_M model, digest `359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7`, through its loopback-only OpenAI-compatible gateway. Cloud inference was disabled. Existing private environments were reused. Model metadata reported 3178149969 bytes of model VRAM and a 4096-token active context.

The runtime uses Omnigent 0.16.0's real `OpenAIAgentsSDKExecutor`, an injected gateway client, and `use_responses=False`. The model calls are made by Omnigent's SDK executor. This is trusted application sequencing of distinct research sessions, not the Omnigent CLI, an autonomous executable HandoffTool, or a full experiment feedback loop.

Five real generation requests occurred, confirmed by both the durable transport ledger and server access records:

1. READY: real response contained additional reasoning text and failed exact-output validation. The complete original response is retained; this is not counted as success.
2. READY with a closed JSON schema: actual `{"status":"OMNIGENT_READY"}` passed (11 completion tokens).
3. Evidence: baseline-only findings and exploratory limitations passed (51 tokens).
4. Hypothesis: two untested directions passed—higher learning rate and lower weight decay, each predicting that validation accuracy may improve (115 tokens).
5. Planner: selected H1, higher learning rate, proposal only (41 tokens).

The first request did not ask for streamed usage, so its exact completion token count is unknown. Every request transmitted `max_tokens=1000`; the Ollama adapter maps this to `num_predict`. All later requests reported usage and stopped normally. Six is the hard total limit, including diagnostics and internal retries; no hidden model retries were observed. The controller enforces a 120-second deadline around each role, request transport and response stream. No sixth request was sent.

The trusted sampler selected learning_rate=0.003 from the frozen space; weight_decay=0.0001 and augmentation=none remained at baseline. Epochs=3, batch_size=128, fixed model/dataset/split remain unchanged. This output is explicitly **proposed, not authorized**, and is not a dispatchable training request. There was no new training.

## Capability and evidence boundaries

Each actual SDK Agent has zero tools, zero MCP servers and zero executable handoffs. The transport checks these objects before sending, rather than trusting prompts. No shell, arbitrary file access, plugins or training functions are exposed. Omnigent SDK tracing is disabled and the gateway client ignores environment proxies. Application capability restrictions do not claim isolation from a malicious process with the trusted controller's OS identity.

The controller reads verified records, sends structured input, validates each raw JSON output through Pydantic, and includes its session identity, output hash and actual contents in the next role's input. Planner must preserve its referenced hypothesis's variable/direction. Numeric parameter choices are made only by trusted code within the frozen space. Raw requests/responses, the initial failure, validated role JSON and handoff references are private handoff artifacts, not fabricated examples.

To reproduce in a later authorized task, use the existing Omnigent environment and a local service configured with `OLLAMA_HOST=127.0.0.1:11434`, `OLLAMA_NO_CLOUD=1`, and a project-private `OLLAMA_MODELS`. Use a task-specific private output directory:

```sh
python -m orchestrator.local_research --output "$RS_TASK_RUN_DIR" --baseline docs/g4-baseline-evidence.json
```

Re-running against the same output directory retains the original request budget; changing directories is not authorization to evade a task budget. Runtime logs go to that directory through `OMNIGENT_DATA_DIR`; HOME is not reassigned. This G4 run has one unused request slot, but no further model request is required.

Offline validation includes rejected tools/commands/paths, missing or excessive token limits, destination and timeout checks, persisted six-request accounting, and hypothesis-to-planner binding. A separately labeled mocked transport check exercised the actual Omnigent SDK's serialization without a model call. These tests are not counted as real research evidence.

## Remaining work and rollback

The role chain is verified. An experiment feedback loop is not: the proposed setting has not been trained, evaluated or used to update another decision. The next step is to review and authorize a bounded new experiment, then verify how its real result affects the next decision. Do not claim AI superiority from this chain or the three-seed baseline.

Stop only a task-owned service after checking its PID and recorded process start identity. Preserve model blobs, Ollama identity, immutable handoffs and all request/result ledgers. Revert reviewed control commits to roll back code; do not reset, clean, force-push, recreate exhausted campaign ledgers or rewrite worker commits. No main integration was performed in G4.

References: [Omnigent gateway support](https://omnigent.ai/docs/build/models#gateway), [Ollama compatibility](https://docs.ollama.com/api/openai-compatibility), and [Ollama 0.35.1 adapter source](https://github.com/ollama/ollama/blob/v0.35.1/openai/openai.go).
