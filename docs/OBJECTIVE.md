# DeckLab’s objective

Build AI trading agents that can paper-trade, learn from their outcomes and improve their trading decisions over time. Success means better after-cost results and controlled risk supported by repeatable evidence on new market data.

The market dashboard, research workspace, website and Android app support this objective. They let the owner understand what each agent decided, what happened in the simulation, what feedback it received and whether its next strategy is actually better.

## The trading and learning loop

~~~mermaid
flowchart TD
    M[Dated public market data and news] --> A[AI advisor: propose or revise a strategy]
    A --> P[Bounded policy and owner risk checks]
    P --> E[Paper execution from later observed market evidence]
    E --> L[Persistent fills, fees and closed outcomes]
    L --> V[Isolated evaluator]
    V --> F[Point feedback: +1 / -5 / 0]
    F --> Q[Update contextual policy values and strategy feedback]
    Q --> A
    V --> O[Owner-only monetary evaluation and audit]
~~~

This diagram describes the wider project’s intended workflow and existing infrastructure. It is not the execution path of the public website or evidence that the paused private service is running.

### What “trade” means

Trades are simulated. Supported fills require subsequent observed bid/ask evidence, processing delay, available quantities and current risk checks. Costs and partial fills are recorded. Unsupported or stale market evidence cannot be replaced with invented fills. No real-money broker is implemented.

### What “learn” means

A fully closed episode receives **+1 for a net-profitable result after modeled fees, −5 for a net loss, or 0 for break-even**. An entry or an unrealized gain is not a completed learning outcome.

The existing contextual learner persists point-based action-value updates. Bounded policies can use those values for eligibility, sizing or exploration, and advisor/review infrastructure can propose strategy revisions. Trading prompts use permitted public-market context, symbol-only holdings/pending context and point feedback; balances, dollar P&L, entry costs and execution-price histories stay outside those prompts.

This is policy adaptation and strategy feedback. It is not a claim that DeckLab trains the underlying Codex, Claude, AGY or other provider’s LLM weights.

### What “improve” must mean

A strategy needs enough completed, evidence-backed outcomes to evaluate. Review should account for net results after fees, drawdowns and loss limits, sample size, market coverage and performance on later data that was not used to select it. A few winning trades, a higher point total or an attractive chart are insufficient to establish reliable trading quality.

The point score and the owner’s financial evaluation are separate. A positive point total alone cannot demonstrate monetary profitability. Preserve every legitimate loss, fee and failed experiment when comparing strategies.

Chronological experiments, held-out evaluation, uncertainty/abstention and stronger candidate-promotion gates are part of [Phase 4](ROADMAP.md). Source infrastructure and past test evidence do not establish that these broader evaluation gates are complete or that a profitable strategy exists.

## Current scope and operating state

| Area | Status |
| --- | --- |
| Main product objective | AI agents paper-trade, learn and improve through measurable outcomes |
| Wider source | Paper engines, managed agents, point-learning policies, strategy reviews, journals, risk controls and owner web/Android interfaces |
| Public website | Read-only observations, publisher headlines, watchlists and deterministic indicators; AI and execution disabled |
| Private research/trading service | Paused; this documentation does not authorize activation |
| Autonomous provider connection in this public distribution | Not configured; optional developer CLIs are separate from the website |
| Reliable profitability | Not established |
| Real-money execution | Not implemented |

See [Architecture](ARCHITECTURE.md) for source boundaries, [Features](FEATURES.md) for the public experience and [Roadmap](ROADMAP.md) for implementation versus remaining evaluation work.
