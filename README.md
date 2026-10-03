# Recursive Scientist

Omnigent will coordinate scientific agents proposing ML experiments; independent GPU workers will execute them and return real results for subsequent decisions.

G1 publishes executable, tested experiment contracts for a fixed small CNN on CIFAR-10. The runner, web application and multi-agent loop are not implemented here. Only worker 01 is authorized for up to two bounded GPU validation attempts after contract release; see AGENTS.md and docs/interfaces.md.

Code lives in this repository. Private references, datasets, runs, credentials and handoffs live outside it in `~/recursive-scientist-local/`. Original references are read-only; every run gets a new experiment_id directory.

## Recovery

`gate0-repo` identifies the initial baseline. Inspect with `git show gate0-repo`; create a separate recovery checkout with `git worktree add --detach ../recursive-scientist-gate0 gate0-repo` if that destination is absent. Integrate corrections with small commits or `git revert` after review. Never use destructive reset, clean, or force push.

See [interfaces](docs/interfaces.md) and [team rules](AGENTS.md).
