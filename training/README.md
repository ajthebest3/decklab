# DeckLab training resources and observation boundary

Reviewed primary repository/docs/model-card sources on 31 October 2026. Metadata/pinned model revision is in `test-results/training-source-review.json`. This directory distinguishes code in use from evaluated future dependencies.

| Resource | Appropriate role | Status here |
| --- | --- | --- |
| [Stable-Baselines3](https://github.com/DLR-RM/stable-baselines3) (MIT) + [Gymnasium custom environments](https://stable-baselines3.readthedocs.io/en/master/guide/custom_env.html) | A later trainable policy with a custom market-only observation and point reward; CPU baselines before considering GPUs | Evaluated, not installed or represented as an already-trained policy |
| [HftBacktest](https://github.com/nkaz001/hftbacktest) (MIT) | Reference for feed/order latency, order-book replay, partial execution and queue limitations | Execution design reference; the running ledger is custom code, not an installed HftBacktest engine |
| [Financial-news DistilRoBERTa](https://huggingface.co/mrm8488/distilroberta-finetuned-financial-news-sentiment-analysis) | Optional headline-tone feature, not a price/return predictor; model card declares Apache-2.0 | Evaluated, not downloaded or active. Candidate revision: `ae0eab9ad336d7d548e0efe394b07c04bcaf6e91` |
| [FinRL](https://github.com/AI4Finance-Foundation/FinRL) (MIT) | Research/reference infrastructure | Not a drop-in: its [default stock environment](https://github.com/AI4Finance-Foundation/FinRL/blob/master/finrl/meta/env_stock_trading/env_stocktrading.py) includes cash/holdings and a dollar asset-change reward, which violates this experiment's observation/reward rules |
| [ProsusAI FinBERT](https://huggingface.co/ProsusAI/finbert) | Financial-text sentiment alternative | Its current weight license is CC BY-NC-SA 4.0, not assumed Apache/MIT; not selected or installed |

The Hugging Face classifier is smaller than a generative trading LLM, but it is still an optional model with dependency/memory costs. Its reported text-classification evaluation is not evidence of profitable trading. No model weights, tokenizer code, third-party remote code or heavyweight RL packages have been silently installed. A later installation should pin revisions, use standard architectures with remote code disabled, and assess data rights separately from declared code/model licenses.

## What is implemented now

`demo_learning.py` uses terminal action-value updates driven only by the evaluator's confirmed points:

`Q(context, buy) ← Q + 0.2 × (points − Q)`

Each fully closed position is a terminal episode. Points are +1 for a net-positive result after entry/exit fees, −5 for net-negative, and 0 for neutral. These are deliberately the user's scoring rules; they differ from maximizing dollar return and can favor staying in cash. Open entries, rejected orders and failed model calls do not receive invented outcomes. Context values influence future entry sizing and deferral; they do not retrain Codex/AGY model weights. No convergence, profitability or improvement guarantee applies to nonstationary market data.

The underlying terminal-update reference is [Watkins & Dayan, Q-learning](https://www.gatsby.ucl.ac.uk/~dayan/papers/cjch.pdf). No third-party implementation is copied into the code.

Live Codex and AGY decisions receive only current market facts, selected headlines, held symbols and point/Q feedback. They do not receive wallet balances, equity, dollar P&L, cost bases or execution-price histories. The separate evaluator and owner dashboard see accounting. Private CLI workers use fresh homes and private PID/proc views, hide the host home/project/prior histories with bubblewrap, strip inherited secrets, disable Codex shell/exec/apps/browser features, and hard-deny AGY tools with immutable `.agents/hooks.json`. Real CLI canary probes verified the boundary; ordinary chat keeps its separate research context. They are not general-purpose self-modifying trading agents.

## Execution evidence and limits

See [HftBacktest's fill assumptions](https://hft.readthedocs.io/en/latest/order_fill.html): replayed data cannot be altered by a simulated order and large liquidity-taking fills can be unrealistic. DeckLab therefore queues orders, requires a later observed snapshot, limits participation, tracks consumed/replenished visible depth across bots, and charges fees. It never fills unsupported stock orders at an indicative close. This remains a counterfactual shadow simulation; actual counterparties, market impact and true exchange queue priority are not observable without real execution. The [Kraken L2 endpoint](https://docs.kraken.com/api-reference/market-data/get-order-book) supplies the current executable-book evidence. No real private trading API is called.

## Export genuine point transitions

```bash
python3 training/export_points.py
```

This reads the real completed-episode ledger and writes private `data/training-points.jsonl`. It exports the observation recorded before the action, the action, terminal point reward and timestamps. It excludes dollar outcome/accounting fields and invents no samples while waiting for closes. Keep chronology when splitting training and evaluation, and never evaluate a policy on future observations it already trained on.

These are logged actions and observed outcomes, not counterfactual rewards for actions never taken. Do not feed this static file into on-policy PPO as if it were a fresh interactive environment. A later SB3/Gymnasium integration must connect to the actual execution/evaluator boundary or a clearly labelled historical replay environment and validate held-out performance against costs and simple baselines. Extra Delhi-server capacity is not needed for the current point learner; consider resources only after measuring a heavier workload.

## Continuous learning extension — 1.5

`demo_policy.py` is an active point-only policy, not a downloaded pretrained trading model. It selects recurring eligible batches from fresh public observations; the evaluator grants real terminal points on closure. Actual Codex/AGY reviews can repeatedly revise bounded exploration, market-filter, batch-size and horizon parameters from those points. Reviews and fast-policy decisions have distinct persisted provenance. None of this changes Codex/AGY model weights or executes their generated code.

The export marks recurring episodes as `point_policy_exploration`, preserving their actual entry observation/action/point reward without dollar outcomes. No synthetic future rewards or counterfactual labels are added. Actual orders/fills per second are limited by evidence and capacity even when the configured ceiling is 1,000.


The 1 November owner-authorized fee restatement recalculates rewards for fixed historical executions under the Binance 0.10% fee scenario. Point exports now include reward_basis and historical_fee_restatement. Preserve the original dated observations; do not present restated rewards as the fees/outcomes originally observed by the advisors, or as out-of-sample profitability. Original financial amounts, learning values and depth evidence are retained in the fee audit and private backups.
