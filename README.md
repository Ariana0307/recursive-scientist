# Recursive Scientist

Your coding agents. Your GPUs. One research lab.

Recursive Scientist connects Codex researchers, real GPU experiments and persistent research memory. This release candidate presents a working bounded prototype and its recorded evidence. It does not claim unattended research across arbitrary subjects or measured productivity savings.

## Included

- `website/`: standalone Node website, recorded run explorer, interactive historical case study and evidence downloads. `npm ci && npm run build`, then `npm start` inside this directory. Requires Node 22.12 or newer. Hosting needs no private machine, SSH service or model server.
- `controller/`: real controller and dispatcher source with configurable deployment examples. `controller/corrected/` adapts the approved implementation used for the corrected 12-request replication. The public adaptation has passed offline SDK-payload and gate checks; it has not been live-tested in a new environment. Execution is disabled by default.
- `third-party/`, `REFERENCES.md`, `NOTICE`, `LICENSE_STATUS.md`: attribution, preserved third-party notices and project license status.
- `render.yaml`, `DEPLOYMENT.md`: prepared configuration for a Free Node web service; no service has been created.

The original recorded run contains 24 requests. Its apparent second-batch gain cannot be attributed to the prompt change because audit inputs differed. The separate corrected replication contains 12 requests: baseline objective 5/6, candidate objective 6/6, both explanation reviews 2/6. Neither was accepted; `best_accepted` remains null. These different cohorts are not a continuous improvement curve. The recorded-run route remains stable for narration; the replication is separately labeled.

Product and Technical videos use the current user-supplied narration and the original 24-request story. Historical 107/108-word scripts are not the current narration and are not part of this release. Final media and measured timings are delivered separately in the submission package.

No public deployment or software-license grant is implied by this candidate. The original project's license remains unresolved. See [license status](LICENSE_STATUS.md) and [references](REFERENCES.md).
