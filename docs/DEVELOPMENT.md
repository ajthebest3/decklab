# Setup and operations

## GitHub Codespaces

The repository includes a Python3.13 development container and Node tooling for optional CLI installation. On creation, the bootstrap creates ignored private runtime directories and preserves the full-backend pause. On start, only the public observer is launched.

Port8790 serves the observer. Its expected external hostname is derived from the Codespace name and GitHub forwarding domain; arbitrary Host headers are rejected. All HTTP POSTs are denied.

The Codespace is a development host, not permanent production hosting. An idle stop, quota, deletion, lifecycle failure or source outage can interrupt the website. Data under data/observer persists with that Codespace but is not committed; deleting the Codespace deletes unbacked observations.

## Terminal status

~~~bash
curl http://127.0.0.1:8790/api/health
tail -n 30 data/observer.log
python tools/cli_advisor.py --status
~~~

No model is invoked by those checks.

## Isolated testing outside Codespaces

~~~bash
python3 test_observer.py
python3 test_foundation.py
python3 test_foundation_http.py
python3 test_foundation_operations.py
python3 test_risk.py
python3 test_http.py
~~~

Run files as separate processes; fixtures own separate temporary data stores. Do not set a test's data path to a personal deployment.

observer_server.py's live main entry point is restricted to Codespaces and its separate data/observer path. Local test modules can instantiate its handler against disposable fixtures without starting feed workers.

## Public endpoints

- GET /api/health: reachability and disabled AI/execution flags.
- GET /api/observer/state: paginated instrument observations, headlines, health and deterministic descriptors. Parameters: q, offset, limit<=100, optional JSON pins list<=100.
- GET /api/observer/history?symbol=BTC%2FUSD: at most96 recorded samples.
- A narrow static file allowlist serves the public interface.
- No account, settings, AI, broker, admin, private transport or financial-write endpoints.

## Optional full backend

The full source is included for study and private deployment. It is not launched by this Codespace. Do not remove a pause marker or start full backend workers as a side effect of setup.

A private installation must configure its own identities, CLI authentication and private storage. Owner transport is disabled unless DECKLAB_OWNER_SENDER is configured. Never publish private data, signing keys, sessions or backups. Existing personal installations are not migrated or resumed by this repository.

## Updating

Use branches/commits and review changes. Observe the narrow boundary between data observation and financial execution. Updating public quotes does not mean updating a private ledger. Do not automatically push runtime data into Git or ship a signed APK without its separate verification.
