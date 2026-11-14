# Current public deployment

- Repository: https://github.com/ajthebest3/decklab
- Live site: https://decklab-live-5xw6xv99qvvc7g9j-8790.app.github.dev
- Codespace editor: https://decklab-live-5xw6xv99qvvc7g9j.github.dev
- Profile: public, read-only observation; AI disabled; execution disabled.
- Machine:2 cores,8GB RAM,32GB storage; Central India.
- Idle timeout:4hours. Retention after stop:30days. Codespaces can stop or exhaust quota; this is not a24/7 production-hosting guarantee.
- Port8790 is explicitly public. GitHub may show a one-time Continue warning on the first visit.

The app refreshes observations while the Codespace is running. The lifecycle helper detaches the feed-only observer from the startup hook. Source, setup and documentation are versioned; runtime observations are not committed.

Codex CLI, Claude Code and AGY CLI binaries are installed. No provider login was copied, no model was invoked, and no API-gateway connection is enabled. Use each CLI's own login only if you deliberately want manual developer assistance.

The original private server and its financial/identity data were not activated or migrated. Public source is a sanitized independent snapshot. The first provisioning attempt is stopped; this is the active Codespace.

See the verification JSON files for actual measurements and screenshots. The previous failed Actions run exposed an environment-dependent test fixture; the test now mocks CLI availability instead of requiring real authenticated binaries.
