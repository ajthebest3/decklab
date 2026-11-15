# Features in detail

DeckLab’s core goal is AI paper trading, outcome-based learning and measurable strategy improvement. [The objective and learning loop](OBJECTIVE.md) explain that wider project. Sections 1–7 describe the currently deployed public observer, where AI and execution remain disabled.

## 1. Market radar

The public observer maintains a tracked instrument directory from two sources: a seed list of international instruments and the available Kraken spot USD pairs. It searches names and symbols, pages through results and shows price, native currency, source change and observation status.

The change column is the provider's day/session basis, not a personal account return. Crypto REST ticker timestamps are receipt times because that response does not provide an exchange timestamp. Equity/provider timestamps are retained when available. A browser refresh does not imply a new market observation.

Not every tracked row has a quote. Provider access, session closure, throttling, unavailable symbols and incomplete coverage stay visible. Tokenized securities are not included in this observer's spot-only crypto import.

## 2. Personal browser watchlist

Star symbols to pin them. The watchlist is stored in the visitor's local browser, not on the server, and can be filtered across all results. It is separate from any personal deployment's server-side watchlist. Clearing browser storage removes these pins; no private account data is synchronized.

## 3. Observed price history

Charts use recorded observations in the observer's own SQLite database. They do not synthesize candles or bridge missing prices. A chart needs at least two actual samples. Historical provider observations can arrive in a batch; sampling frequency and source coverage remain source-dependent.

The public endpoint returns at most96 recorded prices per selected instrument. Chart timestamps are explicit. A flat market produces a flat line, not invented movement.

## 4. News and research wire

Selected business, world, Asia and financial RSS/Atom/RDF sources are polled periodically. Each story retains its publisher, original URL and available publication time. Readers follow the publisher for the full article.

The tool does not reproduce full/paywalled articles, generate news summaries, assert why a price moved, or claim exhaustive global coverage. Invalid links are not rendered as active navigation.

## 5. Deterministic research

When enough samples exist, the observer presents a14-delta sampled RSI, a recent sampled mean and sampled momentum. These are reproducible arithmetic descriptors, not AI analysis, calibrated forecasts, recommended trades or evidence of profitability.

An instrument requires at least15 price observations. A new crypto history may need over an hour of sampling; a provider can supply historical observations earlier. The interface shows insufficient evidence instead of fabricating statistics.

## 6. Source health

Provider results and last checks remain visible. A source can fail while other sources continue. A successful page load is not proof all markets are fresh. Crypto observations older than120seconds and other quotes older than300seconds are labelled stale by the public view; receipt-age checks also apply.

US, NSE and crypto retain distinct semantics in the full foundation. The public observer does not claim a verified holiday calendar or current executable depth.

## 7. Spatial interface

Original WebGL halo, orbit and galaxy geometries provide a decorative introduction. The site supports pointer drag, keyboard rotation, scene reset and explicit motion control. Rendering stops while hidden/offscreen; a static design remains if WebGL is unavailable or its context is lost. This artwork is not market evidence.

## 8. Full backend source, outside the public deployment

The wider source tree contains separate original-account, managed-population and archived-demo paper systems; execution-depth evidence; fees and point feedback; watchlists and research notes; alerts; private admin/session boundaries; Day Trader analysis integration; native Android source; versioned readiness and an explicitly disabled durable original-stop extension.

Those accounts and endpoints are not served by observer_server.py. Real broker execution is absent. Existing personal deployments and their ledgers are independent of this public distribution.

## 9. Optional developer assistants

Codex, Claude and AGY CLI launchers are available for deliberate terminal use. Installation is separate from authentication. No credentials are copied from another machine, and merely opening the site does not invoke a model. There is no configured external AI API gateway.

## 10. Planned work

The five-phase roadmap covers foundation, website, native Android, research/learning evaluation and delivery. Experimental algorithms, broader native improvements and final releases are not represented as live capabilities merely because they are planned.

## Phase 2 workspace improvements

Select a market row or research symbol to inspect its chart and source evidence together. Line/area views and time windows use saved samples only. Open **Accessible price data** for the equivalent values, or use the sample slider with arrow keys. The evidence panel includes timestamps, freshness, source and Advanced public JSON. Background refresh preserves selection, chart controls, focus and open disclosures. [Phase 2 delivery and acceptance limits](PHASE2.md).
