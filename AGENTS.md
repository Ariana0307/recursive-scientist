# Project rules

- Roles are logical assignments; record actual hostname and GPU, never infer hardware from a role name.
- 5060 control: branch `dev/control-5060`; sole repository initializer, schema owner and integration authority for main.
- G1 5090-01: branch `dev/runner-5090-01`; owns runner/ and configs/. After gate1-contract-v1 is published, may perform at most TWO small GPU validation attempts, each with a hard wall-clock limit of 300 seconds (retries count). No broader training campaign.
- G1 5090-02: branch `dev/eval-5090-02`; owns analysis/ and its tests. This round may download data and check environment; no formal training.
- Workers propose interface changes in writing; only control changes shared schemas/contracts and integrates them.
- Use small reviewable commits. Never reset --hard, clean -fd, force push, or overwrite an unknown project. Recover through separate worktrees or reviewed revert commits.
- Original references are immutable, read-only and hash recorded. Never commit private references.
- Create a fresh runs/<experiment_id> directory for every new experiment; retries use append-only attempt subdirectories under the existing ID, following docs/interfaces.md; never overwrite previous run evidence. Failed runs are explicit failures, never fabricated accuracy.
- Review evidence for credentials, private addresses, internal details and personal information before any publication.
- Keep credentials, data, weights, environments and raw logs outside Git. Never print secrets, copy private SSH keys or enable SSH agent forwarding.
- Do not change other repositories, robotics programs, system CUDA/drivers/global Python, firewall, tunnels or public listeners. G1 permits only the bounded 01 validation above; control does not download CIFAR, train, or establish SSH dispatch. Credentials remain on control.
