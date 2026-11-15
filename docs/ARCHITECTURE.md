# Architecture

DeckLab’s central objective is an AI paper-trading and learning loop: agents research markets, test strategies in simulation, receive completed-outcome feedback and work toward better after-cost decisions under risk controls. See [Objective and learning loop](OBJECTIVE.md) for the full workflow and success criteria. The public observation path below is one supporting subsystem; it never activates that loop.

## Public observation path

~~~mermaid
flowchart LR
  A[Public Kraken spot API] --> W[Bounded feed workers]
  B[Public equity / NSE observations] --> W
  C[Publisher RSS feeds] --> W
  W --> D[(Separate observer SQLite)]
  D --> H[Read-only HTTP API]
  H --> U[Markets / watchlist / news / indicators]
  G[Original WebGL halo] --> U
  X[AI / orders / admin / personal accounts] -. not exposed .-> H
~~~

The observer is a separate entry point. It imports shared market helpers but never calls the full backend initializer, automation, AI loops, portfolio loops or private account endpoints. Its schema contains only instruments, quotes, sampled history, headlines and provider status. It does not create financial order, position or demo ledger tables.

## Core modules

| Module | Role |
| --- | --- |
| observer_server.py | Public feed-only lifecycle, observation schema, narrow HTTP allowlist |
| static/observer.html / observer.css / observer.js | Read-only public experience |
| static/vendor/new-era.js | Original decorative WebGL scene and fallback |
| server.py | Full private terminal, source adapters and original-account controls |
| foundation.py | Read-only versioned diagnostics and truthful capability/resource state |
| operations.py | Durable original-only stop identity/revision journal; disabled by default |
| coverage.py / news_sources.py / execution_markets.py | Discovery, headline parsing and market adapter boundaries |
| demo_engine.py / demo_learning.py / demo_policy.py | Independent archived paper execution and point-learning infrastructure |
| population_engine.py / population_controls.py / population_models.py | Managed paper population, controls and assignment infrastructure |
| terminal_engine.py / day_trader.py | Research workspace and bounded vendored analysis tools |
| chat_engine.py / private_advisor.py | Optional full-backend CLI/privacy infrastructure, never invoked by observer |
| admin_session.py / mobile_events.py | Private admin and notification mechanisms, not public endpoints |
| android/ | Native Java application, legacy specialist workspace and tests |
| training/ | Offline export/evaluation tooling; no dataset or weights shipped |
| tools/cli_advisor.py | Explicit manual developer CLI entry point |

## Data and concurrency

A bounded pool handles public-feed checks. Crypto observations are scheduled about every30seconds, equities/NSE about120seconds, and publisher checks about300seconds. Network delays and provider throttling can extend these intervals. No promise of exchange-stream latency is made.

SQLite uses WAL and busy timeouts through shared connection helpers. The browser reads every15seconds while visible, skips automatic reads while hidden and distinguishes view receipt from observation time.

Source IDs, currencies, observation timestamps and coverage gaps remain attached to data. Charts only use stored prices. Statistical descriptors use observed samples and do not feed an executor.

## Full backend boundaries

The original, managed and archived paper stores are distinct. Model discussion or review never authorizes execution or activation. Pending order evidence, journal identity, funding, fees and terminal rewards must not be fabricated or replaced during migration.

The original-stop extension binds origin, persistent server identity, principal, original account, monotonic settings revision and command ID. Duplicate payloads return durable results; conflicting/stale reviews fail; effect and acknowledgement are committed together. The extension remains disabled in the full server construction.

## Public distribution versus personal deployment

This is a fresh, portable public source snapshot, not an upload of a personal runtime or private Git history. Contacts, workspace paths, private project memory, accounts, backups and signing identities were excluded or generalized. Historical verification reports are identified as historical; current public-profile checks are recorded separately.
