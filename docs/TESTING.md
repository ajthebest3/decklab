# Testing and verification

## Supported public checks

Run each file as a separate Python process. The public observer suite verifies no financial/AI tables, denied writes, absent private/model routes, exact Host restriction, explicit disabled-mode metadata, receipt-time semantics, global parameterized watchlists and no model/order invocation on reads.

The selected full-foundation/risk/HTTP suites cover readiness, owner pause, scope, revisions, duplicate/uncertain acknowledgements, transactional migration retries and original-account risk controls. The public distribution disables its historical API adapter; API-provider-specific tests are not shipped as supported public tests.

Optional CLI command construction is tested without invoking any model or using credentials.

A manually triggered GitHub Actions workflow runs isolated supported backend checks with read-only repository permissions. It needs no project secrets and does not start the observer or a trading engine.

## Historical foundation evidence

Selected reports under docs/verification describe the original foundation work:107 backend checks,32 JVM/Robolectric tests and30 browser checks at that recorded source revision. They are historical evidence, not a claim all unchanged counts apply to this sanitized CLI-only export.

Current public-profile results and screenshot checks are written separately. A browser emulation screenshot is not a physical handset test. A JVM/Robolectric pass is not a signed Android release or FPS/battery certification.

## Runtime verification

Inspect /api/health for live-observation mode with ai_enabled=false and execution_enabled=false. Inspect source timestamps/provider results to determine freshness; HTTP200 alone does not prove every provider is current.

Live source verification must never place an order, submit a model prompt or copy a personal ledger.
