# Project rules

- Roles are logical assignments; record actual hostname and GPU, never infer hardware from a role name.
- 5060 control: branch `dev/control-5060`; sole repository initializer, schema owner and integration authority for main.
- 5090-01 worker: branch `dev/worker-5090-01`; this round environment and connection preparation only.
- 5090-02 worker: branch `dev/worker-5090-02`; this round environment and connection preparation only.
- Workers propose interface changes in writing; only control changes shared schemas/contracts and integrates them.
- Use small reviewable commits. Never reset --hard, clean -fd, force push, or overwrite an unknown project. Recover through separate worktrees or reviewed revert commits.
- Original references are immutable, read-only and hash recorded. Never commit private references.
- Create a fresh runs/<experiment_id> directory for every run; never overwrite previous run evidence. Failed runs are explicit failures, never fabricated accuracy.
- Review evidence for credentials, private addresses, internal details and personal information before any publication.
- Keep credentials, data, weights, environments and raw logs outside Git. Never print secrets, copy private SSH keys or enable SSH agent forwarding.
- Do not change other repositories, robotics programs, system CUDA/drivers/global Python, firewall, tunnels or public listeners. No formal training in Gate 0.
