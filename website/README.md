# Recursive Scientist website

Standalone Node 22 website: `npm ci`, `npm run build`, then `npm start`. The server respects PORT and serves the recorded API and all page assets without private SSH, GPU access, or a personal computer service. The interactive case study changes browser state only.

- `/`: product overview, research lifecycle and one interactive historical case.
- `/recorded-run`: original 24-request recorded loop, stable for the current narration.
- `/replication-g14/index.html`: latest completed corrected replication, 12 separate requests.
- `/evidence`: expandable original evidence and official references.
- `/how-it-works`: research history, with separate completed follow-up.

The cohorts are separate, and no accepted improvement is claimed. Current best_accepted is null. The historical second-batch 6/6 objective result remains next to its unequal-evidence limitation and failed acceptance.

Build, TypeScript, desktop browser navigation, Technical trace expansion, the interactive case and mobile layout were checked locally. Docker execution and deployment on a new host are not verified. This candidate is a Node server, not a static-only GitHub Pages export. See the release root for controller configuration, references and publication/license status.
