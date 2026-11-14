# DeckLab 2.1 native Android

The launcher is a Java Android Activity. Home, markets, instrument details, Canvas charts, bots, journal, Mirai research, device settings, portfolio controls, alerts, news, company discovery, original-account views and the admin command screen use Android Views. They do not load HTML or JavaScript. The previous WebView workspace is a separate, non-exported LegacyActivity, available explicitly from More for specialist tools such as the full model-roster editor.

## Code and data

- `MainActivity.java`: native navigation, theme selection, forms, cached-first screen binding, confirmation dialogs and lifecycle handling.
- `NativeChart.java`: local Canvas rendering of observed equity and provider candles, cursor inspection, pinch zoom and keyboard access.
- `LocalStore.java`: private `decklab-device.db` SQLite database. Snapshots, normalized instruments, device saves, notes and research drafts are scoped to the configured server origin. Cache eviction cannot delete device notes or saved instruments. Initial server watchlist/notes are imported without overwriting later device edits.
- `DeviceRepository.java`: two bounded background workers, duplicate-request suppression, bounded cache, foreground refresh and cached reads. Cache freshness avoids redundant network calls. Returning responses from a previous endpoint cannot replace the current endpoint's view.
- `Connection.java`: the existing private server API allowlist and endpoint validation, also used by the native repository. Credentials are not bundled in the APK.
- `LegacyActivity.java`: the preserved optional specialist workspace and existing native bridge.

The app opens cached portfolio/market data immediately. Market filters and text search query the device database; notes and saved instruments work offline. Downloaded charts, viewed journal pages and recent research remain readable after disconnect or restart. Empty/unavailable data stays empty, with cached/source timestamps visible. Downloading a snapshot does not create a new market observation.

Device watchlist/note edits are local to the phone and explicitly labelled that way. The existing server copies remain intact. This release does not silently upload edits or queue financial mutations. It does not move the server's financial ledger or 24/7 strategy worker onto a phone that may sleep or close.

## Interaction and safety

Paper and Graphite themes use native typography and sizing, 48dp action targets and a separate bottom navigation bar. Source timestamp, saved timestamp and current connection state are separate. Views do not rebuild on every quote update while the user is editing. New Android system-bar/IME insets are handled natively; Android 15 startup is covered by an API 35 runtime test. Small-screen/large-font layouts were rendered and inspected.

Start, Stop, risk-control changes, original-account order previews and final order execution require the relevant native user actions and confirmations. Financial actions are blocked offline. Confirmations are bound to the server origin they were reviewed against. Requests and order IDs retain the existing server idempotency/atomic gates. Mirai output is plain text and cannot execute actions. Research retries retain their request ID while a submission's result is uncertain. Admin access is held only in memory, is locked when the app leaves the foreground, and is never cached in SQLite.

Live prices, new Mirai answers, new server alert events and 24/7 bot execution require the existing server connection. Termius/localhost:8790, package identity, private signing key and all existing server account data are preserved. Trading remains stopped following the existing owner instruction.

## Verification and resource limits

`NativeAppTest.java` uses Robolectric 4.17 with native Android graphics on API 28 and API 35. It validates SQLite persistence, endpoint isolation, server-note import, local search/filtering, cache clearing without losing saves/notes, invalid-snapshot rejection, native view trees, native charts, Paper/Graphite rendering, larger-font/small-screen layout, research drafts/errors, Start confirmation/offline blocking, cross-server confirmation rejection and the locked admin screen. These are Android framework/runtime tests, not browser mocks and not a physical-handset claim.

Native screenshots are generated under `android/app/build/native-screens/`. Test results are saved in `test-results/native-unit.json` and the Android unit-test XML. Existing isolated mobile/HTTP backend checks are also run. The final release uses the existing private signing identity and is checked for version/package, source classes, download hash, credentials not being in the APK, and unchanged financial tables.

The attempted software emulator was stopped because it competed with the build for this 8GB server's memory. Do not run the API 35 software emulator and Gradle simultaneously on this host. Build settings are capped at a 1GB Gradle heap and one worker. The emulator is not required to build or use the app. Test-only Robolectric dependencies are not packaged into the release APK.


## Completion follow-up

Chart inspection and zoom now survive recurring snapshots. A zoomed chart supports horizontal dragging through earlier observations and keyboard inspection scrolls the visible range. Returning research submissions tolerate navigation away from the research view.

The original terminal snapshot predates the owner's recorded 09:21–09:23 UTC simulation run. Its 37 position exits produced 39 observed sell fills and 37 rewards before native app development began. `test-results/native-history-audit.json` verifies old immutable records, cash-versus-ledger changes, unchanged funding/reserve and closed-position rewards. `native-completion-preservation.json` separately checks the current financial state against the completion session's own baseline. No financial history was rolled back to make an old checksum match.


## 2.1 reference terminal redesign — 5 November 2026

The owner rejected the sparse portfolio layout and reiterated the exact reference at https://x.com/EaStEnRaY1/status/2117838083362324871. The matching locally preserved video and frames were inspected. `TerminalDashboard.java` implements the new native home: navy panels, cyan/pink/violet/gold stage colors, Canvas orb and connected workflow, market-group selection and tracked quote tiles, selected-instrument history and portfolio chart toggle, expandable eight execution checks, model selection with saved reviewer gauge, actual ledger statistics and persisted event/fill evidence links. Source times, stale/indicative FX, stopped states and unavailable data remain visible. No reference profits, scores, trades or activity are synthesized.

MainActivity binds the same private server APIs and on-device cache. The terminal does not load HTML/JavaScript. Header duplication is removed on Home, controls and Mirai remain accessible, and buttons resize at larger system font settings. Saved chart zoom/cursor survive ordinary refreshes. Package identity and signing key are preserved; version 2.1.0/code 19 is an in-place update.

24 Android framework/native-graphics tests passed, including API 28/35, reference panels, expandable checks, tablet rendering, 320dp/large-font rendering, SQLite/offline preservation and chart interactions. Phone and tablet screenshots use explicit test fixtures, stored in `android/app/build/native-screens/`. Actual emulator results are recorded separately in `test-results/native-emulator.json`; these fixture screenshots are not claims of production performance.


Final 2.1 validation passed: 19 actual API 28 emulator checks, 58 artifact/publication/privacy checks, 33 strict financial preservation checks, historical reconciliation, and final installed-versus-served APK checksum/launch. See `test-results/native-completion.json`. System UI ANR and accessibility timing on the unaccelerated emulator are recorded in the underlying reports. Handset behavior is not claimed tested.
