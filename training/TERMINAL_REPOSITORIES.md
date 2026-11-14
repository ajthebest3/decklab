# DeckLab terminal: reference and repository review

Reviewed 5 November 2026. Reference: https://x.com/EaStEnRaY1/status/2117838083362324871 . The 20.131-second video was retrieved as a private reference; sampled frames and a detailed frame were inspected. Its workflow, scanner, rule checks, analyst display, chart, statistics and event log informed the new interface. No media from the video is bundled in the app.

The interface shows actual stored observations, strategies, reviewer scores, simulated executions and outcomes. Stopped states and missing data remain visible. The six displayed stages describe the existing engine workflow; they are not six newly created LLM agents.

| Repository | License reviewed | Decision |
|---|---|---|
| [bmoscon/cryptofeed](https://github.com/bmoscon/cryptofeed) | AGPL-3.0-or-later with attribution terms | Reviewed · future streaming adapter; current source cadence stays explicit |
| [ccxt/ccxt](https://github.com/ccxt/ccxt) | MIT | Reviewed · future multi-exchange adapters; current execution uses existing public books |
| [freqtrade/freqtrade](https://github.com/freqtrade/freqtrade) | GPL-3.0 | Reviewed · standalone strategy/backtest engine; no second executor installed |
| [polakowo/vectorbt](https://github.com/polakowo/vectorbt) | Apache-2.0 plus Commons Clause; see upstream license | Reviewed · future isolated chronological research; current outcomes remain actual ledger results |
| [TA-Lib/ta-lib-python](https://github.com/TA-Lib/ta-lib-python) | BSD-2-Clause | Reviewed · optional indicators; no uncomputed indicator scores displayed |
| [skfolio/skfolio](https://github.com/skfolio/skfolio) | BSD-3-Clause | Reviewed · future constrained optimization; owner allocation controls stay in force |
| [ranaroussi/quantstats](https://github.com/ranaroussi/quantstats) | Apache-2.0 | Reviewed · reporting concepts; current closed metrics calculated directly from ledger, package not installed |
| [duckdb/duckdb](https://github.com/duckdb/duckdb) | MIT | Reviewed · future archive analytics; SQLite ledger retained |
| [agronholm/apscheduler](https://github.com/agronholm/apscheduler) | MIT | Reviewed · scheduling concepts; existing bounded worker retained |
| [tradingview/lightweight-charts](https://github.com/tradingview/lightweight-charts) | Apache-2.0 | Integrated · pinned 5.0.9 chart bundle, candlesticks/area, crosshair, touch pan/zoom and recorded-fill markers |

The integrated chart dependency is **Lightweight Charts 5.0.9**. Its npm tarball SHA-512 integrity was verified before extracting the standalone production bundle. Bundle, LICENSE, matching-tag NOTICE and SHA-256 manifest live in `static/vendor/` and are copied into Android. Visible chart attribution links to TradingView. It supplies actual interactive candlestick/area rendering, crosshair, touch pan/zoom and markers from persisted fills.

The other nine libraries are reviewed candidates, not installed runtime dependencies. The application retains its existing SQLite ledger, source adapters, worker scheduler and single simulation executor. Closed-episode win rate, profit factor and expectancy are computed directly from recorded outcomes; no backtests, optimization, model training or synthetic strategy performance are claimed.

Mirai terminal research uses the private server-side client and saved primary credential. Jobs run on explicit request, one at a time, with a 30-second admission cooldown, request-id deduplication and persisted success/error states. Its allowlisted prompt contains only `asof`, `focus`, public price history and headlines; the owner accounting payload is excluded. A real disposable probe and a real saved RELIANCE.NS launch note succeeded with gpt-6.1-sol. No model output has an order-execution path.

Terminal views refresh every two seconds while visible, with single-flight requests and a Freeze view control. Market feeds and candles retain their own timestamps and cadence. Candle requests are bounded to the selected instrument/range, cached by the existing provider handler, and automatically refreshed at most once per minute while viewed. Every fill marker links to an actual stored execution; unavailable prices/candles and connection errors are shown explicitly.

Validation: 307 isolated backend/protocol/privacy checks, disposable desktop/Android bridge interaction checks at 320/390/768/1440px and shortened keyboard height, a real Mirai probe, 46 live preservation/status checks, read-only live chart/Mirai/controls checks at 390/1440px, signed Android 1.14.0/code 17 build/lint and 33 artifact/privacy checks. Native device behavior remains a handset check. Both portfolios and entries remain stopped. See `test-results/terminal-*.json` and `SESSION_MEMORY.md`.
