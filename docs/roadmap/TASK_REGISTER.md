# Implementation task register

102 proposed work items. The CSV carries module owners, exact gate dependencies, affected stores/contracts, migration impact, test categories, feature defaults, release gates and rollback methods. Every implementation slice must refine its source/API fields and estimates before coding.

## Phase 1

| ID | Change | Acceptance |
|---|---|---|
| P1-01 | Inventory saved controls and service masks | Private baseline records effective settings; no historical default is reapplied |
| P1-02 | Capture protected-state and source manifests | All protected-file hashes and source diff inventory recorded without key text |
| P1-03 | Verify consistent backup and restore workflow | Disposable SQLite restore passes integrity and accounting reconciliation |
| P1-04 | Verify new Mirai key with bounded completion | Exact model response/status and credential fingerprint recorded; no portfolio action |
| P1-05 | Design deliberate credential promotion | Existing keys/routes preserved; scoped diff and owner intent captured |
| P1-06 | Create model capability verification states | Listed/completion/schema verification and expiry cannot be conflated |
| P1-07 | Add bounded model request budgets | Concurrency/timeouts/cancellation/usage or unknown cost visible |
| P1-08 | Protect model settings drafts | Catalog refresh preserves dirty non-secret fields; secrets clear after success |
| P1-09 | Rename original-account stop action | Label and confirmation identify original-account-only scope |
| P1-10 | Document each engine stop/exit semantics | Review screen states whether automatic exits stop and positions remain |
| P1-11 | Design aggregate stop coordinator | Durable ID and per-engine outcomes; partial failure never says all stopped |
| P1-12 | Reconcile uncertain mutation acknowledgements | Lost acknowledgement uses read/reconcile and same command ID without duplicate action |
| P1-13 | Expose versioned readiness/capabilities | Cheap liveness separate from build/schema/capability readiness |
| P1-14 | Expose per-source and per-resource timestamps | Exchange/source/receipt/attempt/success timestamps are distinct |
| P1-15 | Represent full owner pause explicitly | Paused service never claims market observations continue |
| P1-16 | Bind review to origin/account/settings revision | Changed origin or revision rejects stale confirmation |
| P1-17 | Audit Host/Origin and route allowlists | Forbidden origin/path and malformed payload rejected |
| P1-18 | Standardize request IDs and redacted errors | No keys/passkeys/private data in logs or error responses |
| P1-19 | Add market-specific calendar/FX health | US/NSE/crypto sessions and source failures remain separate |
| P1-20 | Freeze phase-one acceptance evidence | Scoped stop/privacy/compatibility/preservation tests pass on isolated data |
| P1-21 | Build exact changed-route manifest and classify complete route inventory | All route rows classified; admin-prefix operations explicitly enumerated; reviewed schemas and contract fixtures hash-linked |
| P1-22 | Inventory server/device store migrations and supported schema fixtures | Current/supported versions,transactions,disk/interruption tests,compatibility and forward-fix behavior recorded |

## Phase 2

| ID | Change | Acceptance |
|---|---|---|
| P2-01 | Approve visual hierarchy and token sheet | Dark/light typography/spacing/status tokens reviewed at phone and desktop sizes |
| P2-02 | Unify DeckLab naming and terminology | Account scopes, virtual execution and source labels consistent |
| P2-03 | Restructure navigation without broken links | All old deep links resolve and keyboard focus remains meaningful |
| P2-04 | Build persistent pause and status strip | Separate service/feed/model/engine statuses with timestamps |
| P2-05 | Design overview panel composition | Chart, instrument context, research and health have deliberate reading order |
| P2-06 | Add bounded saved desktop panel layouts | Resize/reset works; preferences origin-scoped and contain no secrets |
| P2-07 | Upgrade chart toolbar and source legend | Range/type/reset/source/asof accessible and preserve selection |
| P2-08 | Link market row and research context | Selection consistently drives chart/details/research without stale response repaint |
| P2-09 | Add truthful breadth/heatmap graphics | Coverage/window shown; missing data stays missing |
| P2-10 | Add traceable fill and event markers | Every marker opens exact persisted evidence; no invented fills |
| P2-11 | Add accessible chart data view | Keyboard/screen-reader users can inspect equivalent values |
| P2-12 | Replace route-wide rebuilds incrementally | Polls preserve viewport/selection/focus/scroll/drafts |
| P2-13 | Unify lifecycle-aware polling | Hidden tabs suspend routine reads; single-flight bounded requests |
| P2-14 | Add request generation and cancellation | Old symbol/origin/route responses cannot replace current view |
| P2-15 | Page and virtualize full scanner results | Visible/total count accurate; every result reachable |
| P2-16 | Build structured why-blocked drawer | Failed gate has source/time/explanation and exact related record |
| P2-17 | Build structured Day Trader cards | Waiting/expired/unaffordable/skipped/replay states readable without JSON |
| P2-18 | Improve evidence/Admin detail presentation | Structured summaries with raw Advanced view; no queue duplication |
| P2-19 | Polish error/empty/loading/retry interactions | Durable operation status, drafts and explicit recovery retained |
| P2-20 | Validate responsive visual/accessibility budget | 320/390/768/1440,200% text,keyboard,contrast,reduced motion and measured latency |

## Phase 3

| ID | Change | Acceptance |
|---|---|---|
| P3-01 | Extract native screen controllers | Navigation behavior preserved with testable state holders |
| P3-02 | Share theme tokens and density settings | Paper/Graphite consistent; system font scale honored |
| P3-03 | Replace tiny labels and narrow actions | Readable metadata and >=48dp primary action targets |
| P3-04 | Adapt dashboard columns by available width | 320dp and large text do not clip cards or controls |
| P3-05 | Expose individual pipeline accessibility nodes | TalkBack can focus/activate each stage and hear state |
| P3-06 | Add chart identity key | Origin/instrument/series/interval isolates cursor/zoom state |
| P3-07 | Improve chart inspection and evidence links | Long-press/pan/pinch/table work without scroll conflict |
| P3-08 | Retain state across rotation/process recreation | Draft/filter/scroll restored; admin tokens are not |
| P3-09 | Incrementally migrate model-roster tools | Native controls match API review semantics; legacy fallback labelled |
| P3-10 | Incrementally migrate Day Trader results | Structured stages preserve US-only planning boundaries |
| P3-11 | Add per-resource repository state | Partial failure is visible despite unrelated successful requests |
| P3-12 | Report queue saturation and prioritize actions | Rejected read yields visible busy state; no silent loss |
| P3-13 | Add bounded per-route backoff/cancellation | No hot retry loop or old-origin repaint |
| P3-14 | Build private connection diagnostics | Existing tunnel checked without starting backend or exposing listener |
| P3-15 | Replace list/stat rebuilds with keyed binds | Stable selection/scroll and measured reduction in redraw work |
| P3-16 | Implement nondestructive SQLite migrations | Version upgrade preserves notes/saves/drafts; no throw-only upgrade path |
| P3-17 | Bound cache by bytes and age | Eviction never removes durable user records; usage visible |
| P3-18 | Retain per-origin notification cursors | Endpoint switch/replay cannot duplicate or cross-origin deep-link events |
| P3-19 | Add private export and sync-state labels | Local-only/server-saved explicit; opt-in conflicts never overwrite silently |
| P3-20 | Validate native performance and real lifecycle | IME/TalkBack/offline/process death/rotation measured; handset results separate |

## Phase 4

| ID | Change | Acceptance |
|---|---|---|
| P4-01 | Write current-algorithm specification | EWMA alpha,point objective,context hash,sizing and actual controls documented |
| P4-02 | Explain point versus financial objective | +1/-5 expected-score threshold and monetary expectancy separated |
| P4-03 | Create immutable experiment manifest | Source/settings/prompt/model/strategy/policy/schema/source-time versions pinned |
| P4-04 | Inventory replayable historical evidence | Exact intervals with/without later L2 books and relevant sources listed |
| P4-05 | Capture opportunity and abstention records | Flag-off bounded nonblocking observer cannot change/delay gate decisions; drops/failures record visible coverage gaps and degradation |
| P4-06 | Declare features/templates and allowed actions | Small causal feature set; actions cannot weaken risk or change executor |
| P4-07 | Implement hierarchical shrinkage candidate offline | Strategy/venue/version separation and confidence-based abstention reproducible |
| P4-08 | Freeze legacy rewards and version variants | No rewriting historical points; new reward spec explicit and isolated |
| P4-09 | Pin episode attribution and exits | No reward duplicate on partials; all admitted episodes retain policy/exit provenance |
| P4-10 | Build chronological walk-forward splits | Train-only transforms and purge/embargo cover overlapping horizons |
| P4-11 | Lock final holdout and trial registry | Dataset hash and model trials frozen before final outcomes examined |
| P4-12 | Implement identical-opportunity baselines | Abstain,fixed strategies,current champion,candidate share data/execution assumptions |
| P4-13 | Replay later-book execution faithfully | No synthetic L2 from candles; gaps imply signal-only cohort |
| P4-14 | Estimate clustered uncertainty and sensitivity | Correlated bots not independent; stress fees/delay and trial scope reported |
| P4-15 | Account for unresolved exposure/pause effects | Closed-only survivor bias and management/fee cohorts visible |
| P4-16 | Build owner-only evaluator boundary | Dollars/performance never enter strategy prompts or public evidence exports |
| P4-17 | Build durable five-model review desk | Exact model/verdict/diff/hash/error/dissent retained; no order tools |
| P4-18 | Build learning and decision-trace inspector | Opportunity→gate→action→execution→close→reward traceable or explicitly unavailable |
| P4-19 | Define preregistered promotion/demotion gates | Coverage/power analysis defines thresholds; inconclusive result blocks promotion |
| P4-20 | Prepare shadow and paper-canary runbooks | Zero-authority shadow and separate owner Start for canary; champion rollback retained |

## Phase 5

| ID | Change | Acceptance |
|---|---|---|
| P5-01 | Create exact-artifact release manifest | Source/APK/assets/contracts/migrations/flags hashed and linked |
| P5-02 | Run relevant isolated backend regressions | Ledger/risk/HTTP/Mirai/Admin/DayTrader contracts verified without production actions |
| P5-03 | Run full web user journeys | Connect/search/chart/evidence/research/settings/stop/error journeys pass |
| P5-04 | Run native contract and lifecycle journeys | Native/offline/origin switching/cache migration paths pass |
| P5-05 | Run API old/new compatibility matrix | Old clients fail safely or function with advertised capabilities |
| P5-06 | Test uncertain commands and partial stops | No duplicate order/admin submission or false aggregate-stop success |
| P5-07 | Test feed/model/network failure matrix | Stale/partial/429/timeout/expired-key/tunnel failures remain explicit |
| P5-08 | Scan secrets and dependency artifacts | No credentials in APK/web/reports; licenses/pins/hash manifest complete |
| P5-09 | Reconcile protected immutable histories | All unchanged history/funding/fee/point/identity assertions pass |
| P5-10 | Run backup restoration drill offline | Restore into disposable directory; integrity and reconciliation succeed |
| P5-11 | Measure API/query/cache performance | Realistic archive load measured; external provider latency separated |
| P5-12 | Measure web interaction and accessibility | Keyboard/font/contrast/motion and defined response budgets measured |
| P5-13 | Measure native scroll/memory/battery | Agreed handset baseline with screenshots and actual lifecycle evidence |
| P5-14 | Add bounded observability and retention | Request IDs,source freshness,queue age,disk/DB errors visible without model chatter |
| P5-15 | Build signed compatible APK and checksums | Original package/key retained; no emulator beside Gradle |
| P5-16 | Record physical handset acceptance | Real device results explicit; remaining checks marked pending |
| P5-17 | Complete five-reviewer final dossier | All blocker dispositions and exact final hash/verdicts recorded honestly |
| P5-18 | Prepare feature rollback and policy demotion | Compatible artifacts restored without rolling financial history backward |
| P5-19 | Deliver operator guide and control scope table | Connection,pause,stops,uncertainty,cost and recovery understandable |
| P5-20 | Apply staged operational authorization gates | Deployment cannot silently unmask/resume research,trading or candidate policy |
