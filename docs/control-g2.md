# G2 control integration and subscription-path status

G2 preserves main at gate1-contract-v1. Worker 01's original runner commit
`4fcfadfb02e2c50e0dffde7b12ec6f2336fd1bd8` is published unchanged on
`dev/runner-5090-01`. No GPU work is dispatched in G2. Private handoff packages,
identities and historical pilot outcomes remain outside Git.

## Codex subscription route

Omnigent documents ChatGPT subscriptions through the official Codex CLI:
https://omnigent.ai/docs/build/models#subscription . No API purchase or token
export is required for that documented route. `omnigent setup` detects CLI login;
setup is not a repair for kernel sandbox or tool-surface failures. Do not log out,
read/copy authentication files, or repackage a subscription token as an API key.

Installed 0.16.0 distinguishes `omnigent codex` (native terminal path) from
`harness: codex` (official Codex app-server executor). Source audit found:

- codex_harness._resolve_os_env defaults an omitted OS environment to sandbox none.
  Therefore omitting os_env here does NOT make the Codex harness a no-tool agent.
- _CodexAppServerSession.run_turn only sets features.shell_tool=false and
  features.unified_exec=false inside `if tools:`. tools=[] skips that branch,
  even with HARNESS_CODEX_DISABLE_NATIVE_TOOLS=true.
- CodexExecutor has no observed per-turn max_output_tokens forwarding in this
  installed path. A prompt requesting short output is not a hard token budget.
- The wrapper can bridge user config/MCP/plugin state; a safe model-only route
  must explicitly exclude those capabilities as well as native shell and files.

The G2 preflight uses the original prepare_codex_worker function with explicit
linux_bwrap, network denied, empty private workspace and credential-free state.
It only runs `codex --version` behind the generated launcher. On this host it
fails at sandbox spawn before any model request. This does not prove subscription
authentication fails; authentication and actual model access remain untested.

`orchestrator/codex_preflight.py` takes a new --attempt-dir under private runs,
refuses G1/reused/symlinked paths, and assigns a new session identity. It has no
model inference code, so its output cannot be mistaken for readiness. Example:

```sh
~/recursive-scientist-local/omnigent-venv/bin/python orchestrator/codex_preflight.py \
  --attempt-dir ~/recursive-scientist-local/runs/RS-20261003-G2-r1-codex-preflight-NEW
```

A later safe implementation must independently demonstrate: (1) actual sandbox
containment; (2) an empty model tool surface, including inherited plugins/MCP;
(3) official CLI-owned existing subscription authentication; (4) supported model
discovery; (5) at most six model requests and a cumulative 6000-output-token cap,
including retries. Do not retry model inference until these gates hold. Native
full-access mode and sandbox:none are not alternatives.

A candidate is a reviewed Codex adapter that applies supported disable switches
unconditionally, retains read-only/native containment, and never imports user
tools. It still needs testing in an already authorized isolated environment in
which its sandbox works. This is a proposal, not a verified fallback on this host.
No system-policy changes, new paid service or worker credentials are authorized.

Evidence→Hypothesis is conditional on real readiness. Omnigent exposes AgentTool,
HandoffTool and session-send mechanisms, but no successful role invocation or
handoff is claimed in G2 while startup is blocked. A single historical pilot is
not a causal comparison; its accuracy cannot establish which variable helps.

Official Codex references (version differences must be checked locally):
https://learn.chatgpt.com/docs/app-server
https://learn.chatgpt.com/docs/config-file/config-reference
https://learn.chatgpt.com/docs/security
