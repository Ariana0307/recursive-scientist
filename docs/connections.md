# Private worker connection plan

Connectivity is unknown until verified. Prefer existing private-network SSH with user-confirmed worker aliases. Keep addresses in private local configuration; never publish them.

Development: each worker clones the public repository and uses its own branch. Confirm each SSH host fingerprint independently before trusting it; use an existing local key without copying private keys and with ForwardAgent=no. A bounded read-only probe can run hostname and nvidia-smi once aliases are provided. Do not install network services or change firewalls.

Future runtime dispatch is separate: dedicated unprivileged account/key, forced command or restricted runner, allowlisted operations, isolated run directories, immutable experiment IDs, resource/time limits and structured results. Do not grant an agent unrestricted development SSH credentials. No dispatcher or new SSH/public endpoint is created in Gate 0.
