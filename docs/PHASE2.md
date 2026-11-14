# Phase 2 — public workspace refinement

Started 14 November 2026 at the owner's request. This first delivery refines the existing public observer. Phase 2 as a whole remains **in progress**; native, private account, execution and admin interfaces are outside this public release.

## First delivery

- Link market rows and research cards to the selected instrument chart, source facts and deterministic research context.
- Add line/area views, all-samples/last-hour/last-day windows, reset and a keyboard-operated recorded-sample inspector. Range controls filter saved timestamps; they do not fetch unavailable history. Exchange candles cannot be reconstructed from ticker samples, so no candle view is offered.
- Provide equivalent saved values in an accessible price table, plus structured source evidence and an Advanced JSON disclosure.
- Patch keyed quote, headline, indicator and provider nodes to preserve focus and open disclosures during refresh. Search, selection, chart settings and sample timestamp survive polling.
- Replace interval polling with one completion-scheduled refresh chain. Abort superseded requests; reject late search and symbol responses. Suspend routine reads when the tab is hidden, with a 15-second request timeout and refresh interval.
- Retain observations after an unsuccessful refresh and show a retry explanation. Add keyboard help and a skip link; improve metadata readability on narrow screens.

## Scope and data contract

Existing HTTP contracts are unchanged. Only these existing read endpoints are used:

| Endpoint | Fields consumed |
| --- | --- |
| `/api/observer/state` | assets: symbol, name, kind, currency, price, change, source, asof, timestamp_basis, fresh; news: URL/title/source/publication time; research: symbol/RSI/mean/momentum/samples/asof/fresh; providers: name/state/message/checked; total/offset/limit/observed/notice |
| `/api/observer/history?symbol=…` | Up to 96 saved `ts,price` pairs in ascending timestamp order |

Selection is browser-local and does not modify server state. Only the existing symbol watchlist persists in localStorage (maximum 100). Layout, chart windows and selection currently last for the page session. Source facts may be cached from a previously viewed results page; their observation timestamp remains visible. Indicators absent from the returned snapshot are described as unavailable, rather than asserting that no research exists.

The API exposes no account records, fills, gates, bots or administrator evidence; these are not fabricated in the public interface. No AI connection, CLI invocation, financial migration or private backend activation is introduced. The black New Era design and existing decorative scene remain the visual baseline.

## Delivery status against the full roadmap

| Tasks | Status in this first delivery |
| --- | --- |
| P2-07 chart controls, P2-08 linked context | Public observer implementation delivered; broader terminal remains open |
| P2-11 accessible chart values | Public observer price table and keyboard sample inspector delivered |
| P2-12 stable updates, P2-13 polling, P2-14 cancellation | Public observer implementation and focused browser journeys delivered |
| P2-18 structured evidence, P2-19 recovery | Public source evidence/retry slice delivered; private admin and mutation flows remain open |
| P2-04 status, P2-15 paging | Existing observer status/paging retained; broader phase acceptance remains open |
| P2-20 responsive/accessibility | Automated viewport, text scaling, reduced motion and keyboard checks; manual assistive-technology, contrast and device latency review remain open |
| Other Phase 2 tasks | Pending: complete token/theme system, workspace navigation, saved resizable layouts, meaningful breadth, persisted event markers and full terminal-specific views |

## Verification and rollback

Run `python3 test_observer.py` for the eight read-only isolation checks. With Playwright and Chromium installed, run `python tools/check_phase2_browser.py docs/verification/phase2-browser.json`. This uses a temporary SQLite fixture, starts no feed worker and makes no model calls. Fixture prices are never published as live-market evidence.

Automated browser coverage is documented in [the report](verification/phase2-browser.json). These checks do not establish screen-reader conformance, complete WCAG contrast conformance or a measured p95 interaction budget. Complete Phase 2 acceptance requires those remaining reviews and broader task delivery.

Rollback this slice by restoring the prior observer HTML/CSS/JS from commit `b72d967`. No store/schema migration or private-runtime restart is required. Deploy by pulling the reviewed source into the existing Codespace; public static assets are read on each request.
