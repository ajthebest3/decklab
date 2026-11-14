#!/usr/bin/env python3
"""Render the owner-only frozen-data analysis; requires matplotlib and Markdown."""
import argparse
import base64
import html
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

import markdown
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter


def money(value):
    return ('−$' if value < 0 else '$') + f'{abs(value):,.2f}'


def table(headers, rows):
    return '\n'.join(['| '+' | '.join(headers)+' |', '| '+' | '.join('---' for _ in headers)+' |']+
                     ['| '+' | '.join(str(v) for v in r)+' |' for r in rows])+'\n'


def render(folder):
    d=json.loads((folder/'analysis.json').read_text())
    episodes=json.loads((folder/'episodes.json').read_text())
    definitions=json.loads((folder/'strategy-definitions.json').read_text())
    pop=d['population']; total=d['overall']; diag=d['diagnostics']['population']; rev=d['revision_diagnostics']
    t=d['tables']; archive=Path(d['archive'])
    closed=[e for e in episodes if e['ledger']=='population' and e['closed']]
    positive=[r for r in t['by-entry-strategy'] if r['closed_net_usd']>1e-6 and r['episodes']]
    pure=[e for e in closed if not e['crossed_pause'] and not e['mixed_buy_strategy'] and not e['strategy_revisions_during_episode']]
    fee_percent=100*pop['paid_fees_closed_usd']/-pop['closed_net_usd']
    profitable_original=sum(r['original_fee_path_closed_net_usd']>1e-6 for r in positive)
    overview=f'''**DeckLab: which strategies made money?**

Analysis of the frozen collection completed on 2 November 2026 at 07:27:40 UTC / 12:57:40 IST. The original ledger snapshot finished at 07:26:47 UTC and the managed ledger at 07:26:55 UTC. Trading evidence spans 31 October–2 November. All amounts below are simulated USD, computed from recorded fills; no trading settings or live ledger records were changed.

**The answer: some entry configurations earned a small profit, but none of the four broad strategy families, none of the recorded model cohorts, and none of the individual bots was profitable overall.** The managed portfolio has {money(pop['closed_net_usd'])} across 1,046 fully closed positions and {money(pop['all_exposure_net_usd'])} including its still-open exposure at the frozen marks. It has not demonstrated a repeatable profitable strategy.

The most useful positive evidence is a three-trade momentum signal cohort that earned $4.95 after the effective fees, and several mean-reversion entry cohorts earning $8–$23. Those are specific observed results. The small sample sizes, exploration entries, later strategy changes, and pauses prevent treating them as validated fixed trading rules.

**What the four names mean in this engine.** All executed entries are long-only buys in Kraken USD spot pairs; the ledger contains no equity/broker fills or short-selling strategies. Broader stock/index headlines and quotes are research context, not proof of diversified multi-asset execution.

- Momentum buys when the observed return over the configured lookback reaches the positive threshold.
- Trend adds a second condition: the current price must also be at or above the lookback mean.
- Mean reversion buys when the current price is below the lookback mean by at least the threshold.
- Breakout buys when the current quote exceeds the prior sampled high by at least the threshold.

The engine requires enough sampled history for a normal signal, then separately permits exploratory entries when the signal is absent. Selling is managed by timed/risk exits, with both entry-policy and later bot-policy effects. These are bounded rule families whose parameters are revised by models, not unrestricted model-generated trading programs. Shared exposure and a weak market regime can affect many bots at once.

**Start with the accounting, because closed trades and portfolio value answer different questions.**

'''
    body=overview+table(['Measure','Original portfolio','Managed population'],[
        ['Closed positions','19','1,046'],
        ['Wins / losses','0 / 19','184 / 862'],
        ['Closed net after fees',money(sum(e['net_usd'] for e in episodes if e['ledger']=='market' and e['closed'])),money(pop['closed_net_usd'])],
        ['Open-position rows','2 tiny residuals','239'],
        ['Open-episode net, including partial exits',money(sum(e['economic_net_usd'] for e in episodes if e['ledger']=='market' and not e['closed'])),money(pop['open_net_including_partial_exits_usd'])],
        ['Total marked net',money(d['diagnostics']['market']['marked_net_usd']),money(pop['all_exposure_net_usd'])],
        ['Paid fees, all fills',money(d['diagnostics']['market']['paid_fees_usd']),money(diag['paid_fees_usd'])],
    ])+f'''
The managed portfolio's total marked equity is **{money(1000000+pop['all_exposure_net_usd'])}**. Its $920,000 reserve is uninvested; $80,000 was allocated to 16 bots. The marked loss is 0.1300% of the whole $1M portfolio, but **1.6254% of the allocated $80,000**. The two separate $1M portfolios must not be confused with each other or the preserved original $100k paper account.

The managed open-episode contribution of {money(pop['open_net_including_partial_exits_usd'])} contains {money(diag['realized_parts_still_open_usd'])} from partial sales and {money(diag['remaining_unrealized_usd'])} on the remaining holdings. It is not all unrealized P&L. Their remaining acquisition cost is {money(pop['open_cost_usd'])}. Marks include estimated exit fees; no sale was fabricated. At the ledger snapshot, {diag['stale_open_marks']} of 239 held marks exceeded the engine's 20-second freshness window (maximum age {diag['max_open_mark_age_seconds']:.1f}s). These marked values are estimates, separate from completed outcomes.

**All four strategy families lost money.** These are entry-style cohorts: subsequent management can differ. Every figure uses complete positions, not individual fills.

'''
    body+=table(['Entry family','Closed','Win rate','Gross before fees','Closed net','Profit factor','Net incl. open'],[
        [r['entry_style'],r['episodes'],f"{r['win_rate_pct']:.1f}%",money(r['gross_before_paid_fees_usd']),money(r['closed_net_usd']),f"{r['profit_factor']:.2f}",money(r['all_exposure_net_usd'])] for r in t['by-entry-style']])
    body+='''
Momentum produced the largest dollar loss and the weakest profit factor. Breakout lost the least in dollars, but it also had far fewer trades and lower deployed turnover; that does not make it a profitable winner. All four families also lost before fees. Profit factor is total winning dollars divided by the absolute total losing dollars; values below 1 mean losses exceeded wins.

The conclusions survive a narrower check. Restricting to positions whose buys all used the same exact entry configuration still leaves every family negative. Restricting to unchanged entry style across buys and the last recorded exit style also leaves every family negative. That second filter does not prove every intermediate exit parameter stayed fixed.

**The individual configurations that actually ended positive are useful hypotheses, with important qualifications.**

'''
    body+=table(['Entry ID','Family','Closed / wins','Net','Net without largest win','Recorded-fee path net'],[
        [r['strategy_id'],r['entry_style'],f"{r['episodes']} / {r['wins']}",money(r['closed_net_usd']),money(r['net_without_largest_winner_usd']),money(r['original_fee_path_closed_net_usd'])] for r in positive[:6]])
    body+=f'''
There are {len(positive)} positive exact entry configurations out of {rev['exact_strategies_with_closed_samples']} with at least one closed outcome. Only one positive configuration has 10 or more closed outcomes; none of these is an independent validation sample. Of those {len(positive)} positives, {profitable_original} remain positive using each fill's originally recorded fee rather than the retrospective fee scenario. This is fixed-fill sensitivity, not a rerun of historical decisions or funding.

An exact entry configuration groups the recorded strategy parameter fields. The same fields can recur across models or regimes; `by-entry-revision.csv` retains the separate bot/advisor-seed groups. No parameter hash implies identical market conditions or unchanged exit management.

- **Gemini mean-reversion cohort, ID 620c591ba12be5: +$22.83, 4 wins / 5 positions.** Entry settings: 30-minute lookback, 1.75% deviation threshold, 8% exploration, one-order batches, 40-minute planned hold, 3.5% stop, 4.8% target, 12% allocation, no additions. Saved advisor seed 151, bot AGY-06-g0001. All five entries were explicitly exploration, so they did not establish that the mean-reversion condition selected winners. All five crossed a 13-hour pause and had later strategy revisions; every final exit style differed from its entry style. AVAX contributed +$12.86, AAVE +$6.51, ETH +$3.10, LINK +$1.24 and SUI −$0.89. The cohort loses $5.15 under the original recorded fee path. Its profit is real within the current simulation scenario; attributing it to an unchanged 40-minute rule would be unsupported.
- **Claude Opus 4.6 mean-reversion cohort, ID 494cf70aa9e8be: +$10.25, 3 wins / 10 positions.** 15-minute lookback, 0.30% threshold, 8% exploration, one-order batches, 30-minute planned hold, 3% stop, 4% target, 8% allocation, no additions; bot Mirai-10-g0001, advisor seed 625. Six entries were signals and four exploration. LIGHTER produced +$10.06 and ZRO +$6.38; other losses consumed most of those gains. Removing LIGHTER leaves +$0.20; removing both LIGHTER and ZRO leaves −$6.19. The cohort crossed an approximately 4-hour-36-minute pause, and its original recorded-fee path is −$8.60. This is the largest positive cohort by sample count, not a validated mean-reversion edge.
- **Claude Fable 5 mean-reversion cohort, ID 77f07941a6af5e: +$12.21, 1 win / 4 positions.** 15-minute lookback, 0.80% threshold, 8% exploration, 30-minute planned hold, 8% allocation, no additions. One LIGHTER signal made +$13.62; the three exploration entries collectively lost $1.42. Remove LIGHTER and the cohort is negative. All four spanned the same long pause. Its fixed-fill original-fee net remains +$3.75, but the four-position sample cannot establish repeatability.
- **The cleaner uninterrupted signal candidate is Gemini momentum, ID fec624bfdc2fe1: +$4.95, 3 wins / 3 positions.** 10-minute lookback, +0.20% return threshold, 10% exploration setting, two-order batches, 20-minute planned hold, 3% stop and 4.5% target. HYPE, ENA and INJ were all actual signals, not exploration. Each closed after roughly 20 minutes without a pause. However, six accepted strategy revisions occurred during each position and the final exit style changed; under the original recorded 0.80% fees the cohort loses $5.51. The older schema did not record allocation_pct/add_to_positions, so those values are unknown, not reconstructed from today's defaults.
- **Uninterrupted breakout cohort, ID 80cd327af60420: +$3.09, 2 wins / 3 positions.** Same 10-minute lookback and 0.20% threshold, 20-minute planned hold, one-order batches, 2.5% stop and 4.5% target. Two signals (HYPE and INJ) won; one PAXG exploration lost. It also had six intervening revisions and a changed final exit style. Its originally recorded fee path loses $7.36. Again, a candidate to retest, not a reliable production strategy.

The +$10.35 momentum entry configuration in the table depends on one +$10.50 AVAX position; remove that winner and it loses $0.16. A high-ranked configuration can therefore be one fortunate exposure rather than a robust rule.

**Signal entries and exploration must be evaluated separately.**

'''
    body+=table(['Entry family','Entry type','Closed','Wins','Net'],[[r['entry_style'],r['entry_kind'],r['episodes'],r['wins'],money(r['closed_net_usd'])] for r in t['by-entry-style-and-kind']])
    body+=f'''
**859 / 1,046 closed positions (82.1%) began as exploration.** Their closed loss is $738.66; the 187 signal-origin positions lost $234.41. The loss per invested dollar was about 0.453% for exploration versus 0.497% for signals, so the larger exploration dollar loss also reflects its larger activity. Eliminating exploration cannot be assumed to make the remaining strategy profitable: the observed signal cohort is already negative.

The only positive family/type cell is breakout signals: +$0.77 across just three positions. It has no statistical weight as a deployment decision. Positions with later additions are attributed to their first entry here; the raw export identifies every later buy's classification, and the separate pure-all-buys table removes mixed classification episodes.

Exploration is applied per eligible symbol per new quote, not as a small percentage of total executed trades. The engine permits exploration even when the strategy signal is absent or features are not ready. With many symbols and sparse qualifying signals, a 5–10% configured exploration probability can dominate actual activity. This follows from the saved code and the observed entry labels; it is not a claim about a randomized no-exploration counterfactual.

**The losing configurations show recurring patterns, but comparisons are observational.**

'''
    worst=t['by-entry-strategy'][-4:]
    body+=table(['Entry configuration','Closed / wins','Closed net','Key settings'],[
        [r['strategy_id'],f"{r['episodes']} / {r['wins']}",money(r['closed_net_usd']),
         f"{definitions[r['strategy_id']]['style']}; threshold {definitions[r['strategy_id']].get('threshold_pct')}%; hold {definitions[r['strategy_id']].get('hold_seconds',0)//60}m; allocation {definitions[r['strategy_id']].get('allocation_pct','unknown')}%; additions {definitions[r['strategy_id']].get('add_to_positions','unknown')}"] for r in reversed(worst)])
    body+='''
Actual additions were particularly weak: 68 closed positions with multiple buy orders lost $254.89, versus $718.18 across 978 without additions. The turnover-normalized loss was 0.681% with additions versus 0.416% without. Additions also mix multiple strategy revisions in 40 closed positions, making causal attribution harder. This supports testing additions separately; it does not establish that disabling them alone creates an edge.

All large planned-hold cohorts were negative. The 15-minute planned-hold cohort had 408 closes and lost $535.66. A 90-minute group earned $2.47 from only nine closes. Actual wall-clock holds often include pauses and later rule changes, so this is not evidence to choose 90 minutes as an optimal horizon. Similarly, reducing allocation often reduces dollars at risk; that is risk reduction, not demonstrated signal improvement.

The worst symbol cohorts were ZRO (−$124.97), LIGHTER (−$94.03), NEAR (−$88.49), AAVE (−$72.02) and PEPE (−$60.70) on closed outcomes. LIGHTER appears in several standout winning configurations, but lost overall across 40 completed positions: cherry-picking its winning episode would reverse the conclusion. ZEC's closed cohort made +$4.31, but including its frozen open exposure gives −$2.88. No symbol cohort is positive after including frozen open exposure.

**Fees matter, but the strategy also lost before fees.**

'''
    body+=table(['Managed closed-position accounting','USD'],[
        ['Price/execution result before paid fees',money(pop['gross_before_paid_fees_usd'])],
        ['Paid buy and sell fees on those closed positions',money(-pop['paid_fees_closed_usd'])],
        ['Net',money(pop['closed_net_usd'])]])
    body+=f'''
Paid fees explain {fee_percent:.1f}% of the managed closed loss; unfavorable execution-to-execution price movement explains the remaining {100-fee_percent:.1f}%. **Even zero paid fees on the same fills would leave a $553.69 loss.** The gross result already contains crossing the observed bid/ask book and any fixed observed execution-price effects; a pure prediction loss cannot be separated from spread/price effects without additional counterfactual evidence.

The effective fee is 0.10% on buys and sells. The price-rise hurdle before spread is `(1.001 / 0.999 − 1) × 100 = 0.2002%`. Binance's official standard spot schedule lists 0.100% maker/taker for regular users; these records use that modeled scenario on **Kraken** observed books, not historical Binance fills. The owner-authorized restatement reduced fees on earlier fixed fills; it did not rerun model choices, sizes or market prices. See the [official Binance fee schedule](https://www.binance.com/en/fee/trading).

In the managed closed data, 355 positions had a positive gross result, but 171 of them became net losses after fees. Losing entries and excessive turnover both matter. Total managed paid fees across closed and open episodes are $456.14; adding the estimated exit fees on remaining holdings gives a different quantity and must not be counted again in closed net.

**The experiment was heavily interrupted, and that changes what a winning strategy means.**

Eight recorded enabled windows total **{diag['total_active_seconds']/60:.2f} minutes**, spread over about 40 hours. This is enabled engine time, not proof of uninterrupted CLI or feed availability. Pausing holds positions and cancels pending orders; it does not liquidate. Market prices can change while both entry and exit execution are stopped.

786 closed positions crossed at least one pause and lost $830.30. The 260 closed without a pause lost $142.77. The median full episode lasts 112 minutes in wall time, but that must not be interpreted as 112 minutes of continuous strategy management. Some paused winners held roughly 13 hours despite advertised holds of 20–40 minutes.

One profitable entry window was 1 November 07:17–07:21 UTC: its 63 eventual closes earned +$36.27. Those positions were then held through a long pause. Later entry windows were negative, including −$289.17 from the 11:58 window and −$371.77 from the 12:11 window. The latest window still has 239 open positions, so it is not a mature performance sample. This is evidence that timing/regime and operational controls mattered; it does not measure what continuous execution would have earned.

**The many strategy changes have not demonstrated improvement.**

There are 528 accepted revisions and 472 parameter-changing revisions across both ledgers. Of these, the original portfolio has 211 accepted revisions and the managed portfolio 317. In the managed portfolio, only 170 recorded entry revision/configuration groups have closed samples; 24 are positive. Many accepted revisions have no completed exposure to evaluate.

205 of the original portfolio's 211 accepted revisions occurred after its last recorded fill. Those responses therefore cannot be treated as 205 newly executed strategy experiments. They may still be legitimate research or control-aware holds, but revision count is not tested-performance count.

775 managed closed positions had at least one accepted revision while open; 464 had a different final recorded exit style from their entry style; 40 received buys from multiple exact configurations and 17 from multiple styles. Returns must therefore be attributed to recorded entry cohorts with mixed-management flags, not claimed as clean end-to-end performance for a fixed strategy. A stricter subset with no pause, no later accepted revision and no mixed buy configuration contains only {len(pure)} closed positions and collectively loses {money(sum(e['net_usd'] for e in pure))}.

'''
    body+=table(['Chronological third by entry time','Closed','Win rate','Net','Turnover return'],[
        [r['entry_third'],r['episodes'],f"{r['win_rate_pct']:.1f}%",money(r['closed_net_usd']),f"{r['turnover_return_pct']:.3f}%"]
        for r in sorted(t['by-entry-third'],key=lambda r:['early','middle','late'].index(r['entry_third']))])
    body+='''
The splits contain equal numbers of completed positions, not equal time or risk. All four styles lose within every chronological third. The later loss per invested dollar is worse than the earlier result. This does not prove the revisions caused deterioration—market conditions, position size, pauses and incomplete recent positions confound the comparison—but there is no observed evidence here that more revisions produced reliable improvement.

Selecting the best small cohort from 147 configurations is a multiple-comparison problem. These configurations were found after observing the same history, not tested on an untouched holdout. Trade outcomes also share symbols and market moves. Counting them as independent trials or annualizing a Sharpe ratio from this short, interrupted experiment would overstate the evidence. The [original probability-of-backtest-overfitting paper](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf) explains why selecting historical winners can fail out of sample. No formal probability-of-overfitting or significance level has been estimated for DeckLab here.

**The learning machinery has limits that are visible in the code and the outcomes.**

- **The reward measures win frequency, not dollars.** +1 per win and −5 per loss needs a win probability above 83.33% for a positive expected point reward when outcomes are win/loss. Dollar break-even depends on win/loss size: the observed average +$1.57 win and −$1.46 loss imply approximately 48.3% wins at that payoff ratio. These are different objectives. The +$22.83 five-position mean-reversion cohort receives −1 point; the +$10.25 ten-position cohort receives −32. This follows the owner's chosen scoring rule, but it can penalize profitable asymmetric strategies. No reward change was made.
- **Most learned contexts have almost no repeated evidence.** 803 of 913 managed context cells (88.0%) have one update, 89 have two, 19 have three and two have four. 148 Q cells are positive, but none with at least three visits is positive. A positive single outcome is not demonstrated learning of a durable edge. Contexts include style, symbol and regime but not all threshold/holding/allocation parameters; this can mix distinct configurations in the same learned value.
- **Managed learning mode keeps failed contexts eligible.** The population overrides the base entry-safety rules, and authorized learning entries call the gate with exploration allowed. Negative Q is therefore not a hard stop for managed learning. The original portfolio's three-loss brake cannot be assumed to apply to the newer population.
- **The population budget function replaces the earlier Q-scaled budget.** It recomputes each order as available unreserved cash × allocation_pct, capped by owner settings. Q can affect candidate ranking and model feedback, but the final managed allocation does not retain the base engine's Q size multiplier. Claims that negative Q directly shrinks managed order sizing are unsupported by the current implementation. This is a source-audit finding, not a live change.
- **Candidate scoring receives only the 20 most recently updated context Q rows per bot.** Other contexts fall back to zero in that scoring view, although the underlying gate queries persisted history. With sparse symbol/style contexts, this deserves a separate test before relying on Q-based ranking.
- **Frequent LLM revisions are parameter tuning.** The persisted Q updates are actual learning records, but the logs provide no evidence of model-weight retraining. There are zero published shared successful-strategy lessons. A reviewer score or fluent explanation is not a realized return.

Source locations in the frozen archive: `sources/current/demo_learning.py` (feedback/gate), `sources/current/population_engine.py` (entry_safety, fit_entry_budget, fast_policy and exits), and `sources/current/demo_engine.py` (base gate, budget and delayed executor). These conclusions concern the implementation that generated the records, with older schema differences explicitly retained.

**No recorded model cohort was profitable overall.** Entry models are taken from the executed decision or its same-bot advisor_seed, never from the bot's current display name. All 96 older managed attributions missing from the fast decision were recovered from explicitly linked saved advisor outputs. The table therefore has 17 historical model IDs, including the earlier Gemini and the 16 current roster identities.

'''
    body+=table(['Recorded entry model','Closed','Win rate','Closed net','Net incl. open'],[
        [r['model'],r['episodes'],f"{r['win_rate_pct']:.1f}%",money(r['closed_net_usd']),money(r['all_exposure_net_usd'])] for r in t['by-entry-model']])
    body+='''
These are provider-reported model IDs in the saved records. The table does not independently identify provider model weights. Exposure, time windows, styles and numbers of trades differ, so ranking dollar losses is not a controlled comparison of model skill. The Gemini cohort was earlier, smaller and materially affected by the retrospective fee scenario; it is not proof that Gemini is a superior future trading model. The separate bot-lifetime CSV includes older and newer model assignments under each persistent bot ID; do not label that whole lifetime as its current model's result.

The original $1M experiment also should not be used to claim that its advisors recommended all losing buys. Its 21 entry orders were initial or continuous bounded exploration. The original 19 completed positions all lost after the effective fees, but advisor hold recommendations and engine exploration are distinct records.

**What I would retain for a controlled retest, and what I would not promote as profitable yet.**

1. Retain the 10-minute / 0.20% / 20-minute momentum signal configuration as a narrowly defined candidate: three actual signal wins and no pause are useful evidence, but the exits changed and the sample is only three. Specify the missing old allocation fields explicitly in any future test; do not silently reuse a current default.
2. Retain 15-minute / 0.30% / 30-minute mean reversion, 8% allocation and no additions as a second candidate. Its 10 completed positions are the largest positive exact-configuration cohort, but the large winner and pause make it provisional. Evaluate signal and exploration arms separately.
3. Keep the high-profit mean-reversion and breakout snapshots in the research archive. The +$22.83 cohort was entirely exploration; the +$12.21 cohort was one LIGHTER win; the +$3.09 breakout cohort mixed signals and exploration. None should be labelled a proven strategy.
4. Test one fixed parameter set at a time on new chronological data with the same disclosed fee/execution assumptions, stable entry/exit rules, explicit pause behavior and a separately recorded exploration arm. Record eligibility and deferred signals as well as fills. Use time/symbol clusters when judging repeatability. The target is positive net expectancy and controlled loss, not an arbitrary trade count or reviewer grade.
5. Treat the Q-sizing overwrite, context sparsity, mandatory exploration range and win-frequency reward objective as separate implementation/design questions. Resolve their intended behavior before interpreting future losses as proof that a model has learned. This analysis does not authorize changing the owner's reward rule, enabling trading, changing fees, or restarting services.

**Verification and access to the evidence.**

Every fill was replayed chronologically with additions, partial exits and dust writeoffs. All 1,065 closed outcomes match the recorded rewards to within $0.000001. All 241 remaining positions match their recorded quantities, costs and partial realization. Summed closed plus open episode economics reconcile to each portfolio's cash-and-marked-holdings net within $0.000001. The input files were hash-checked against the frozen collection manifest. Historical backup versions were not added as extra trades, and retrospective fee credits were not counted as market-earned profit.

Use `episodes.csv` for every reconstructed position and its attribution, `episode-fills.csv` for its execution records, `entry-orders.csv` for saved entry choices, `strategy-definitions.json` for all exact parameter sets, and the `by-*.csv` files for every table and subgroup. `analysis.json` contains the complete numerical results and reconciliation checks. The original collection retains full observations, decision text, review explanations, depth evidence and original-fee audits. This owner analysis contains evaluator dollars and must not be passed to the P&L-blind trading bots as their training input.

The data establish which recorded cohorts made or lost simulated dollars under the effective scenario. They do not establish a strategy that will reliably profit on new market data.
'''
    # A single standalone figure provides exported charts without a plotting dependency for readers.
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,axs=plt.subplots(2,2,figsize=(13,9),layout='constrained')
    styles=t['by-entry-style']
    ax=axs[0,0];names=[r['entry_style'].replace('_',' ') for r in styles];ys=list(range(len(styles)))
    ax.barh([y-.18 for y in ys],[r['closed_net_usd'] for r in styles],.34,label='Closed net',color='#416c99')
    ax.barh([y+.18 for y in ys],[r['all_exposure_net_usd'] for r in styles],.34,label='Including frozen open marks',color='#b54c4c')
    ax.set_yticks(ys,names);ax.invert_yaxis();ax.set_title('Every broad family lost');ax.set_xlabel('USD');ax.legend(fontsize=8)
    ax=axs[0,1];ax.bar(['Price result\nbefore paid fees','Paid fees\non closed episodes','Closed net'],[pop['gross_before_paid_fees_usd'],-pop['paid_fees_closed_usd'],pop['closed_net_usd']],color=['#5b748b','#c18b3b','#b54c4c'])
    ax.set_title('Fees worsened an already negative result');ax.set_ylabel('USD');ax.axhline(0,color='#444',lw=.6)
    ax=axs[1,0]
    for r in t['by-entry-strategy']:
        if r['episodes']:
            ax.scatter(r['episodes'],r['closed_net_usd'],s=24,color='#38794f' if r['closed_net_usd']>0 else '#b54c4c',alpha=.7)
    for sid,label in [('620c591ba12be5','5 positions, +$22.83'),('494cf70aa9e8be','10 positions, +$10.25')]:
        r=next(r for r in t['by-entry-strategy'] if r['strategy_id']==sid)
        ax.annotate(label,(r['episodes'],r['closed_net_usd']),xytext=(10,8),textcoords='offset points',fontsize=8)
    ax.axhline(0,color='#444',lw=.6);ax.set_xlabel('Closed positions per exact entry configuration');ax.set_ylabel('Closed net USD');ax.set_title('Positive configurations mostly have tiny samples')
    ax=axs[1,1];groups=sorted(t['by-entry-run'],key=lambda r:r['entry_run'])
    ax.bar([str(r['entry_run']) for r in groups],[r['all_exposure_net_usd'] for r in groups],color=['#38794f' if r['all_exposure_net_usd']>0 else '#b54c4c' for r in groups])
    ax.set_title('Entry window matters; latest includes open marks');ax.set_xlabel('Recorded enabled window (no entries in window 5)');ax.set_ylabel('USD');ax.axhline(0,color='#444',lw=.6)
    fig.suptitle('DeckLab managed portfolio · frozen 2 November 2026 · effective 0.10% fee per side',fontsize=13)
    fig.savefig(folder/'strategy-results.svg');fig.savefig(folder/'strategy-results.png',dpi=170);fig.savefig(folder/'strategy-results.pdf');plt.close(fig)
    body=body.replace('**All four strategy families lost money.**','![Strategy results](strategy-results.svg)\n\n**All four strategy families lost money.**',1)
    (folder/'REPORT.md').write_text(body)
    svg=(folder/'strategy-results.svg').read_text();svg=svg[svg.index('<svg'):]
    rendered=markdown.markdown(body,extensions=['tables','fenced_code'])
    rendered=rendered.replace('<p><img alt="Strategy results" src="strategy-results.svg" /></p>',svg)
    data=json.dumps(episodes,ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    explorer='''<section class="explorer"><p><strong>Inspect every reconstructed position.</strong> Filters show recorded entry attribution. Open net is marked, not a completed outcome.</p>
<div class="filters"><label>Portfolio <select id="ledger"><option value="population">Managed population</option><option value="market">Original</option><option value="">Both</option></select></label><label>Status <select id="closed"><option value="true">Closed</option><option value="false">Open</option><option value="">Both</option></select></label><label>Style <select id="style"><option value="">All styles</option></select></label><label>Type <select id="kind"><option value="">Both types</option><option>signal</option><option>exploration</option></select></label><label>Model <select id="model"><option value="">All recorded models</option></select></label><label>Search <input id="search" placeholder="Symbol, bot, configuration ID"></label><label>Sort <select id="sort"><option value="best">Highest net first</option><option value="worst">Lowest net first</option><option value="newest">Latest entry first</option></select></label></div><p id="count"></p><div class="scroll"><table><thead><tr><th>Episode / bot</th><th>Symbol / entry</th><th>Entry model</th><th>Net USD</th><th>Evidence</th></tr></thead><tbody id="rows"></tbody></table></div><button id="prev">Previous 50</button> <button id="next">Next 50</button></section>
<script id="dataset" type="application/json">DATA</script><script>
const D=JSON.parse(document.getElementById('dataset').textContent),$=id=>document.getElementById(id),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));let page=0;
for(const [id,key] of [['style','entry_style'],['model','model']])for(const v of [...new Set(D.map(e=>e[key]))].sort()){const o=document.createElement('option');o.value=v;o.textContent=v;$(id).append(o)}
function draw(){const q=$('search').value.toLowerCase();let a=D.filter(e=>(!$('ledger').value||e.ledger===$('ledger').value)&&(!$('closed').value||String(e.closed)===$('closed').value)&&(!$('style').value||e.entry_style===$('style').value)&&(!$('kind').value||e.entry_kind===$('kind').value)&&(!$('model').value||e.model===$('model').value)&&(!q||JSON.stringify(e).toLowerCase().includes(q)));a.sort((x,y)=>$('sort').value==='newest'?y.entry_ts-x.entry_ts:$('sort').value==='worst'?x.economic_net_usd-y.economic_net_usd:y.economic_net_usd-x.economic_net_usd);page=Math.max(0,Math.min(page,Math.ceil(a.length/50)-1));$('count').textContent=a.length+' positions · '+a.reduce((s,e)=>s+e.economic_net_usd,0).toLocaleString('en-US',{style:'currency',currency:'USD'})+' net · page '+(page+1);$('rows').innerHTML=a.slice(page*50,page*50+50).map(e=>'<tr><td>'+esc(e.ledger+'/'+e.episode+' · '+e.bot)+'</td><td>'+esc(e.symbol)+'<br>'+esc(e.entry_style+' · '+e.entry_kind)+'</td><td>'+esc(e.model)+'</td><td class="'+(e.economic_net_usd<0?'loss':'gain')+'">'+e.economic_net_usd.toFixed(4)+(e.closed?'':' (marked)')+'</td><td><details><summary>Position details</summary><pre>'+esc(JSON.stringify(e,null,2))+'</pre></details></td></tr>').join('');$('prev').disabled=page===0;$('next').disabled=(page+1)*50>=a.length}
for(const id of ['ledger','closed','style','kind','model','search','sort'])$(id).addEventListener(id==='search'?'input':'change',()=>{page=0;draw()});$('prev').onclick=()=>{page--;draw()};$('next').onclick=()=>{page++;draw()};draw();</script>'''.replace('DATA',data)
    css='''body{font:16px/1.65 system-ui,sans-serif;margin:0;color:#172733;background:#f6f4ee}main{max-width:1100px;margin:auto;padding:36px 24px}p{margin:1.3em 0}strong{color:#173f4f}table{border-collapse:collapse;width:100%;font-size:13px;margin:20px 0;display:block;overflow-x:auto}th,td{padding:9px 12px;text-align:left;border-bottom:1px solid #ccd4d7;vertical-align:top}th{background:#dfe8e8;white-space:nowrap}td{min-width:70px}a{color:#1b567f}li{margin:12px 0}svg{width:100%;height:auto;background:white}.filters{display:flex;flex-wrap:wrap;gap:12px}label{display:flex;flex-direction:column;font-size:13px}input,select,button{font:inherit;padding:9px;border:1px solid #aebbbf;border-radius:5px;max-width:100%}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:11px;max-width:600px}td details{min-width:110px}.loss{color:#a02f35}.gain{color:#1c7047}.explorer{margin-top:42px;border-top:3px solid #285c64;padding-top:20px}.scroll{overflow-x:auto}.downloads{background:#e4ece9;padding:16px}@media(max-width:600px){main{padding:20px 12px}body{font-size:15px}td,th{padding:7px;font-size:12px}.filters label{width:100%}}@media print{body{background:white;font-size:10px;line-height:1.5}main{padding:0;max-width:none}table{font-size:8px;display:table}td,th{padding:5px;min-width:0;white-space:normal}p,li{orphans:3;widows:3}tr{break-inside:avoid}svg{break-inside:avoid}.explorer,.downloads{display:none}a{color:inherit}body{-webkit-print-color-adjust:exact;print-color-adjust:exact}}'''
    page='<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>DeckLab strategy analysis · 2 November 2026</title><style>'+css+'</style><main><div class="downloads">Private owner report · <a href="REPORT.md">Markdown report</a> · <a href="REPORT.pdf">PDF</a> · <a href="episodes.csv">All positions CSV</a> · <a href="analysis.json">Complete results JSON</a></div>'+rendered+explorer+'</main></html>'
    (folder/'report.html').write_text(page)
    print(json.dumps({'report':str(folder/'report.html'),'words':len(body.split()),'positive_configurations':len(positive),'original_fee_positive_configs':profitable_original,'episodes':len(episodes)},indent=2))


if __name__=='__main__':
    import os
    os.umask(0o077)
    parser=argparse.ArgumentParser();parser.add_argument('folder',type=Path);args=parser.parse_args();render(args.folder.resolve())
