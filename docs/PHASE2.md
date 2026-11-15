# Phase 2 — website implementation delivery

Implemented 15 November 2026. Public observer changes are deployable on the existing Codespace; private terminal changes are source-only under the continuing owner pause. **Implementation is complete; manual assistive-technology acceptance remains unverified.** This is not a Phase 3 native release or Phase 5 operational sign-off.

## Delivered

- Shared New Era black semantic tokens, readable flat evidence surfaces, consistent Simulation Portfolio naming and scoped status. Black-only is the latest owner direction, superseding the older mandatory light theme.
- Workspace navigation and symbol search, unchanged old deep links, compatibility aliases in the full terminal, and shareable public symbol/chart URLs.
- Keyboard-adjustable desktop panel split (35–65%), compact rows, origin-local persistence and reset. A Phase 2 workspace toggle restores the classic composition; `?workspace=classic` provides a visit-only fallback. Preferences contain layout values only.
- Source-specific breadth across the full tracked public catalog, with advancing/declining/unchanged/missing counts, freshness exclusions, source windows and included timestamps. The private terminal has equivalent scoped counts. Providers with different baselines are not presented as one market return.
- Linked instrument/source/research context; public line/area/range/reset and saved-sample inspector/table; full terminal provider candles/line, accessible OHLC table and links to exact persisted fill evidence. Public ticker samples never become invented candles or fills.
- Complete private scanner paging/search over supported tracked instruments. The former per-group and first-80 truncations are removed; public catalog paging stays server-side.
- Keyed refreshes preserve input identity, focus, disclosures, drafts, scanner selection and chart canvas/viewport. Render bindings are replaced through one AbortController to prevent duplicated submissions.
- Completion-scheduled refreshes, bounded requests, lifecycle suspension and stale-response rejection. Mutating request timeouts explain uncertain delivery; existing request identities and drafts remain.
- Structured entry-check explanations with bot/instrument/source/snapshot provenance, explicit distinction from saved admission verdicts, exact fill detail, structured Day Trader waiting/skipped/unaffordable/replay evidence and stable Admin queue records. Advanced JSON remains available.

## Scope

The public observer exposes public observations, publisher headlines and deterministic descriptors. Accounts, bots, administrator commands, models, orders and fills remain private/unavailable, not simulated in the public page. Public breadth is an additive read-only response field. No financial schema migration is needed.

The private full-backend web source includes account/journal/risk/Admin/Day Trader presentation. Its tests use fresh disposable stores or intercepted synthetic HTTP records. No owner model or command session is contacted by browser verification. Private runtime activation remains separately authorized; this delivery never starts that service.

The native APK and signing identity are unchanged. Native token mapping, device lifecycle, assistive-technology handset acceptance and signed APK delivery belong to the remaining native/release work.

## Acceptance evidence

- [Public workspace browser report](verification/phase2-workspace-browser.json): layouts at 320/390/768/1440, 200% text, saved preferences/reset, command/deep-link journeys, focus preservation, request races, failure recovery, lifecycle suspension, reduced motion and accessibility-tree names. It includes a local cached-interaction p95 measurement and semantic token contrast ratios.
- [Full terminal browser report](verification/phase2-terminal-browser.json): complete scanner reachability, accessible candles, stable selection/drafts/chart canvas, old routes, responsive widths, single mutation submission after repeated renders, uncertain Admin delivery and structured Day Trader results. Synthetic fixture only.
- [Backend report](verification/phase2-backend.json): 111 isolated checks across 12 suites, including public isolation, full terminal, risk, HTTP, foundation, Admin and Day Trader boundaries.
- [Live deployment report](verification/phase2-live.json): actual public site controls and read-only metadata, captured after deployment. Its timestamp/revision identifies the deployed artifact.
- [Day Trader screenshot](images/phase2-day-trader-fixture.png) uses synthetic isolated browser records and is not market evidence.

Automated AX-tree checks and semantic-token contrast checks are not a claim of manual screen-reader certification, full-page WCAG conformance, physical handset acceptance or a universal latency guarantee. The cached interaction measurement applies to its documented browser/runner only. Manual assistive-technology acceptance is still open and is explicitly tracked under P2-20.

## Rollback

Use the Workspace layout toggle for the classic composition without changing data. For complete source rollback, restore the affected source files from pre-delivery commit `5f16ff3`, then restart only the public observer. The private installation has a private source-before archive. Never restore an old financial database as a UI rollback. The response extension is additive; old public clients continue to work.
