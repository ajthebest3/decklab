# DeckLab public development instructions

This is the portable public source distribution. Read README.md and docs/ARCHITECTURE.md first.

- Public Codespace runs observer_server.py only: public market observations, headlines and deterministic descriptors. No AI, broker, original/managed/archive accounts, orders, admin or private transport endpoints.
- Never copy credentials, data/, financial ledgers, signing keys, private deployment memory or backups into Git. Public deployment must remain independent of personal installations.
- .devcontainer/post-create.sh preserves the full-backend owner pause. postStartCommand launches only the explicitly authorized read-only observer in Codespaces.
- Never turn an indicator into an order or invent missing quote/return/history data. Provider errors, stale timestamps and coverage gaps remain explicit.
- Runtime backend is Python standard library; frontend is buildless HTML/CSS/ES modules. Vendor licenses/notices stay intact.
- Run each backend test file in a separate process; tests use temporary stores. See docs/TESTING.md. Never point tests at a person's real data.
- Existing source includes an optional full paper-research backend and native Android app; neither is deployed by the observer. Full-backend startup, provider authentication and signed releases need separately configured private environments.
- The detailed roadmap is docs/roadmap/PLAN.md; older Graphite/Paper/CSS mockup constraints are superseded by the current black New Era/WebGL direction.
- Model names returned by third-party gateways are provider reports, not independently verified upstream identity. Do not claim trained LLM weights or profitability.
