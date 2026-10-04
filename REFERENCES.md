# Methods and references

## Components used

- [Omnigent](https://github.com/omnigent-ai/omnigent): orchestration dependency. The recorded integration uses its public `CodexExecutor` to coordinate genuine Codex researcher/reviewer turns and retain their results. The installed version recorded for the replication is 0.16.0.
- [OpenAI Codex](https://github.com/openai/codex): the coding-agent harness used for the researcher and reviewer roles. Qwen is the evaluated subject, not the scientific decision maker.
- [Qwen3-4B-Instruct-2507 model card](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507): reference for the evaluated model family. The experiment used an existing local `qwen3:4b-instruct` service. Local service metadata/digests, rather than this citation alone, identify what was actually executed. Model weights are not distributed here.

## Related work

- [The AI Scientist-v2: Workshop-Level Automated Scientific Discovery via Agentic Tree Search](https://github.com/SakanaAI/AI-Scientist-v2), Sakana AI: related work in automated scientific discovery. This citation is not a dependency, a claim of reused code or an experimental baseline reproduced here.

## This project's evidence

The website's Evidence section links the original recorded methods/results and the corrected replication. The historical 24-request run and corrected 12-request cohort remain separate. `controller/corrected/` contains the adapted implementation, frozen example protocol, actual recorded request previews, original approval hashes and recorded execution-fidelity summary. The public adaptation is only offline-tested; original approval does not transfer to changed source or a fresh deployment.

Official references checked 4 October 2026. No priority, competitor-performance or productivity-savings claims are made.
