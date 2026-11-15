"use strict";
const $ = (s) => document.querySelector(s),
  $$ = (s) => [...document.querySelectorAll(s)];
const esc = (v) =>
  String(v ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const money = (n, c = "USD") => {
  if (!Number.isFinite(n)) return "—";
  if (c === "GBp") return n.toLocaleString("en-GB", {maximumFractionDigits: 2}) + " GBp";
  if (!/^[A-Z]{3}$/.test(c)) return n.toLocaleString("en-US") + " (currency unavailable)";
  return new Intl.NumberFormat("en-US", {style: "currency", currency: c, maximumFractionDigits: Math.abs(n) < 1 ? 6 : 2}).format(n);
};
const num = (n, d = 2) =>
  Number.isFinite(n)
    ? n.toLocaleString("en-US", { maximumFractionDigits: d })
    : "—";
const pct = (n) =>
  Number.isFinite(n) ? `${n >= 0 ? "+" : ""}${n.toFixed(2)}%` : "—";
const cls = (n) => (n >= 0 ? "positive" : "negative");
const age = (t) => {
  if (!t) return "unavailable";
  let s = Math.max(0, Date.now() / 1000 - t);
  return s < 60
    ? `${Math.floor(s)}s ago`
    : s < 3600
      ? `${Math.floor(s / 60)}m ago`
      : s < 86400
        ? `${Math.floor(s / 3600)}h ago`
        : `${Math.floor(s / 86400)}d ago`;
};
const date = (t) => (t ? new Date(t * 1000).toLocaleString() : "—");
let readinessState = null;
let S = null,
  route = "overview",
  selected = localStorage.getItem("deck-symbol") || "BTC/USD",
  span = localStorage.getItem("deck-span") || "1D",
  chartType = localStorage.getItem("deck-chart") || "candles",
  bars = [],
  chartSymbol = "",
  cross = null,
  page = 0,
  marketFilter = "all",
  query = "",
  region = "all",
  chartGeneration = 0,
  fetching = null;
const navs = [
  ["demo", "◉", "Simulation Portfolio", "Simulation Portfolio", "$1M virtual wallet · USD / INR · observed execution and point-only learning"],
  [
    "overview",
    "◈",
    "Overview",
    "Market overview",
    "The bigger picture. The details that matter.",
  ],
  [
    "markets",
    "▤",
    "All markets",
    "Global markets",
    "Search the catalog. Track exact equity symbols from exchanges worldwide.",
  ],
  [
    "portfolio",
    "◴",
    "Portfolio",
    "Your paper portfolio",
    "Follow positions, costs and every simulated execution.",
  ],
  [
    "news",
    "≋",
    "News wire",
    "The market wire",
    "Archived headlines from selected financial and business RSS feeds.",
  ],
  [
    "signals",
    "⌁",
    "Research & signals",
    "Find your next idea",
    "Transparent technical screens, with the evidence behind each signal.",
  ],
  [
    "research",
    "✦",
    "AI research",
    "Your research desk",
    "Global context. Conditional ideas. A fresh brief every ten minutes.",
  ],
  [
    "bots",
    "⌘",
    "AI workspace",
    "Your research crew",
    "Local Codex and AGY advisors, Hermes commands and paper automation.",
  ],
  [
    "journal",
    "▥",
    "Activity journal",
    "Every move, recorded",
    "Persistent orders, alerts, advisor runs and system events.",
  ],
  [
    "controls",
    "⚙",
    "Controls",
    "Engine & risk controls",
    "Know your data. Set limits. Stay in control.",
  ],
  [
    "guide",
    "◇",
    "Field guide",
    "Your terminal, explained",
    "Coverage, methods, integrations and the path to broker connectivity.",
  ],
];
$("#navigation").innerHTML = navs
  .map(
    ([id, icon, label]) =>
      `<a href="#${id}" data-nav="${id}" title="${label}"><span class="nav-icon">${icon}</span><span class="nav-label">${label}</span></a>`,
  )
  .join("");
const viewReads = new Set();
async function api(path, body) {
  const controller = new AbortController();
  if (!body) viewReads.add(controller);
  const deadline = setTimeout(() => controller.abort(), 15000);
  try {
  let r = await fetch("/api/" + path, {
    method: body ? "POST" : "GET",
    signal: controller.signal,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  let d = await r.json();
  if (!r.ok) throw new Error(d.error || "Request failed");
  return d;
  } catch (error) {
    if (controller.signal.aborted && body) throw new Error("Response not confirmed. Check saved records before retrying the same request. Your draft is retained.");
    throw error;
  } finally { clearTimeout(deadline); viewReads.delete(controller); }
}
let toastTimer;
function toast(t, error = false) {
  let el = $("#toast");
  el.textContent = t;
  el.style.display = "block";
  el.style.background = error ? "#38202a" : "#1c322c";
  el.style.color = error ? "#ff9bad" : "#4be2ae";
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (el.style.display = "none"), 6500);
}
function asset(s = selected) {
  return S?.assets.find((a) => a.symbol === s);
}
function choose(s) {
  if (!asset(s)) {
    toast("Track this instrument first.", true);
    return;
  }
  selected = s;
  localStorage.setItem("deck-symbol", s);
  bars = [];
  chartSymbol = "";
  cross = null;
  if (route !== "overview") location.hash = "overview";
  else render();
}
function stat(label, value, foot, extra = "") {
  return `<div class="stat"><div class="stat-label">${label}<span class="stat-mark">↗</span></div><div class="stat-value ${extra}">${value}</div><div class="stat-foot">${foot}</div></div>`;
}
function stats() {
  let p = S.portfolio,
    q = S.assets.filter((a) => a.price),
    fresh = q.filter(isFresh);
  return `<div class="stats">${stat("PAPER ACCOUNT EQUITY", money(p.equity), `<b class="${cls(p.pnl)}">${money(p.pnl)}</b> <span>all-time P&L</span>`)}${stat("AVAILABLE TO INVEST", money(p.cash), `${p.positions.length} open positions <span class="stat-divider">/</span> USD paper funds`)}${stat("YOUR MARKET UNIVERSE", num(q.length, 0), `${num(S.catalog_count, 0)} catalog instruments <span class="positive">↗</span>`)}${stat("FRESH QUOTES", num(fresh.length, 0), `<span class="tiny-dot"></span> ${q.length - fresh.length} delayed or closed`, "positive")}</div>`;
}
function chartPanel() {
  let a = asset() || {
    symbol: selected,
    name: "Loading instrument",
    currency: "USD",
  };
  return `<section class="panel chart-panel"><div class="panel-head"><div class="panel-title"><span class="section-index">01</span><h2>Market workspace</h2></div><span class="tag">${esc(a.provider || "MARKET DATA")}</span></div><div class="chart-top"><div class="symbol-identity"><span class="coin-icon" style="${assetColor(a)}">${assetGlyph(a)}</span><div class="symbol-name"><select class="chart-selection" id="chart-symbol" aria-label="Chart instrument">${S.assets.map((x) => `<option value="${esc(x.symbol)}" ${x.symbol === selected ? "selected" : ""}>${esc(x.symbol + " · " + x.name)}</option>`).join("")}</select><small>${esc(a.name)} <span> / </span> ${esc(a.currency || "USD")}</small></div></div><div class="chart-actions"><button class="star ${isSaved(a.symbol) ? "saved" : ""}" data-save="${esc(a.symbol)}" aria-label="${isSaved(a.symbol) ? "Remove from" : "Add to"} watchlist" aria-pressed="${isSaved(a.symbol)}">${isSaved(a.symbol) ? "★" : "☆"}</button><button class="small-button" data-trade="${esc(a.symbol)}">Paper trade ↗</button></div></div><div class="chart-price">${money(a.price, a.currency)} <small class="change-badge ${cls(a.change)}">${pct(a.change)}</small><span class="muted">${a.kind === "crypto" ? "UTC day" : "prior close"}</span></div><div class="chart-toolbar"><div class="chart-tools">${["1D", "1W", "1M"].map((x) => `<button data-span="${x}" class="${span === x ? "active" : ""}">${x}</button>`).join("")}</div><div class="chart-tools">${["candles", "line"].map((x) => `<button data-chart="${x}" class="${chartType === x ? "active" : ""}">${x === "line" ? "Line" : "Candles"}</button>`).join("")}<button id="chart-sma" class="${showSma ? "active" : ""}" aria-pressed="${showSma}">SMA 20</button><button id="chart-export" title="Download visible candle data" aria-label="Export candle data">↓</button></div></div><div class="chart-details" id="ohlc-label">OHLC + real reported volume · hover to inspect</div><div class="chart-wrap"><canvas id="price-chart" aria-label="Price and volume chart" role="img"></canvas><div class="chart-empty" id="chart-empty">Loading provider candles…</div></div><div id="chart-metrics" class="chart-metrics"></div><div class="chart-footer"><span id="chart-source">${esc(a.source || "No quote")} · ${age(a.asof)}</span><span><button class="text-button" id="chart-retry">↻ Reload</button> <span class="chart-footer-help">· volume in base units</span></span></div></section>`;
}
function marketRows(items) {
  return items
    .map(
      (a) =>
        `<tr data-symbol="${esc(a.symbol)}" tabindex="0" aria-label="Open ${esc(a.symbol)} chart"><td><div class="instrument"><button class="star ${isSaved(a.symbol) ? "saved" : ""}" data-save="${esc(a.symbol)}" aria-label="${isSaved(a.symbol) ? "Remove " + esc(a.symbol) + " from" : "Add " + esc(a.symbol) + " to"} watchlist" aria-pressed="${isSaved(a.symbol)}">${isSaved(a.symbol) ? "★" : "☆"}</button><span class="asset-icon" style="${assetColor(a)}">${assetGlyph(a)}</span><div><b>${esc(a.symbol)}</b><small>${esc(a.name)}</small></div></div></td><td>${money(a.price, a.currency)}</td><td class="${cls(a.change)}">${pct(a.change)}</td><td><span class="tag">${esc(a.region)}</span></td><td class="${isFresh(a) ? "positive" : "muted"}">${age(a.asof)}</td><td><button class="text-button" data-trade="${esc(a.symbol)}">Trade ↗</button></td></tr>`,
    )
    .join("");
}
function marketTable(items, sortable = false) {
  let headers = [
    ["symbol", "INSTRUMENT"],
    ["price", "LAST PRICE"],
    ["change", "CHANGE*"],
    ["region", "REGION"],
    ["asof", "QUOTE AGE"],
    ["", "ACTION"],
  ];
  return `<div class="table-wrap"><table><thead><tr>${headers.map(([key, label]) => `<th ${sortable && key ? `aria-sort="${sortKey === key ? (sortDir === 1 ? "ascending" : "descending") : "none"}"` : ""}>${sortable && key ? `<button data-sort="${key}" class="sort-button">${label} <span>${sortKey === key ? (sortDir === 1 ? "↑" : "↓") : "↕"}</span></button>` : label}</th>`).join("")}</tr></thead><tbody>${marketRows(items)}</tbody></table></div>${!items.length ? '<div class="empty">No instruments match.<br>Try another filter or add instruments to your watchlist.</div>' : ""}`;
}
function portfolioPanel() {
  let p = S.portfolio;
  let total = p.equity || 1,
    colors = ["#4be2ae", "#8cb7ff", "#ba9bf3", "#e9c588"];
  return `<section class="panel"><div class="panel-head"><h2>Portfolio snapshot</h2><span class="tag">USD · PAPER</span></div><div class="panel-body"><div class="subheading">TOTAL EQUITY</div><div class="balance">${money(p.equity)}</div><span class="${cls(p.pnl)}" style="font:10px 'IBM Plex Mono',monospace">${money(p.pnl)} <span class="muted">total return</span></span><div class="allocation"><span style="width:${Math.max(0, (p.cash / total) * 100)}%;background:#4be2ae"></span>${p.positions.map((x, i) => `<span style="width:${((x.qty * (x.price || x.average)) / total) * 100}%;background:${colors[(i + 1) % colors.length]}"></span>`).join("")}</div><div class="row"><span class="muted">● Available cash</span><span class="mono">${money(p.cash)}</span></div><div class="row"><span class="muted">● Market value</span><span class="mono">${money(p.market_value)}</span></div><div class="row"><span class="muted">Open positions</span><span class="mono">${p.positions.length}</span></div><button class="wide" data-route="portfolio">View portfolio <span>↗</span></button></div></section>`;
}
function newsItem(n) {
  return `<a class="news-item" href="${esc(n.url)}" target="_blank" rel="noopener noreferrer"><div class="news-meta"><span class="news-source">${esc(n.source)}</span><span>·</span><span>${age(n.published_ts || n.seen)}</span></div><h3>${esc(n.title)}</h3><span class="news-read">Read source ↗</span></a>`;
}
function overview() {
  return (
    sessionStrip() +
    stats() +
    briefBanner() +
    `<div class="workspace-grid"><div class="left-col">${chartPanel()}<div class="insight-grid">${moversPanel()}<section class="panel"><div class="panel-head"><div class="panel-title"><span class="section-index">03</span><h2>Global pulse</h2></div><span class="muted">Prior close</span></div><div class="panel-body heatmap">${heatmap()}</div><div class="panel-caption">Latest index quotes · may be delayed or closed</div></section></div><section class="panel liquidity-panel"><details id="liquidity-details" ${liquidityOpen ? "open" : ""}><summary><span class="panel-title"><span class="section-index">04</span><span>Order book & time sales</span></span><span class="muted">Kraken snapshot <span class="details-chevron">⌄</span></span></summary><div id="microstructure" class="micro-grid"><div class="empty">Loading order book…</div></div></details></section>${notebookPanel()}</div><div class="right-col">${watchlistPanel()}${portfolioPanel()}<section class="panel"><div class="panel-head"><h2>World news wire</h2><button class="text-button" data-route="news">Explore ↗</button></div>${balancedNews().slice(0, 4).map(newsItem).join("") || '<div class="empty">Waiting for news feeds…</div>'}<div class="panel-caption">Source headlines · refreshed every 5 minutes</div></section></div></div>`
  );
}
function heatmap() {
  return S.assets
    .filter((a) => a.kind === "index" && a.price && a.symbol !== "^VIX")
    .slice(0, 12)
    .map((a) => {
      let v = a.change || 0;
      return `<button class="heat" data-symbol="${esc(a.symbol)}" style="background:${v >= 0 ? "rgba(140,187,88," : "rgba(201,88,101,"}${Math.min(0.32, 0.07 + Math.abs(v) * 0.06)})"><b>${esc(a.name)}</b><span class="${cls(v)}">${pct(v)}</span><small>${esc(a.region)} · ${age(a.asof)}</small></button>`;
    })
    .join("");
}
function marketItems() {
  return S.assets
    .filter(
      (a) =>
        (marketFilter === "all" || a.kind === marketFilter) &&
        (region === "all" || a.region === region) &&
        (!savedOnly || isSaved(a.symbol)) &&
        (!freshOnly || isFresh(a)) &&
        (!query ||
          (a.symbol + " " + a.name)
            .toLowerCase()
            .includes(query.toLowerCase())),
    )
    .sort((a, b) => {
      let x = a[sortKey],
        y = b[sortKey];
      if (x == null) return y == null ? 0 : 1;
      if (y == null) return -1;
      return (typeof x === "string" ? x.localeCompare(y) : x - y) * sortDir;
    });
}
function markets() {
  let items = marketItems(),
    pages = Math.max(1, Math.ceil(items.length / 30));
  page = Math.min(page, pages - 1);
  return `<div class="market-header"><div class="filters"><input id="market-query" placeholder="Filter symbols or names…" value="${esc(query)}" aria-label="Filter market symbols"><select id="kind-filter" aria-label="Asset class">${["all", "crypto", "equity", "tokenized_equity", "index", "etf", "tokenized_etf", "forex", "commodity_token", "commodity", "rates"].map((k) => `<option value="${k}" ${marketFilter === k ? "selected" : ""}>${k === "all" ? "All asset classes" : k[0].toUpperCase() + k.slice(1)}</option>`).join("")}</select><select id="region-filter" aria-label="Region"><option value="all">All regions</option>${[
    ...new Set(S.assets.map((a) => a.region)),
  ]
    .sort()
    .map((r) => `<option ${r === region ? "selected" : ""}>${esc(r)}</option>`)
    .join(
      "",
    )}</select></div><button data-add>＋ Track symbol</button></div><div class="market-toggles"><button id="saved-filter" class="filter-chip ${savedOnly ? "active" : ""}" aria-pressed="${savedOnly}">★ My watchlist <span>${S.watchlist.length}</span></button><button id="fresh-filter" class="filter-chip ${freshOnly ? "active" : ""}" aria-pressed="${freshOnly}">● Fresh quotes only</button><span class="muted">Click a column to sort · click an instrument to inspect</span></div><section class="panel">${marketTable(items.slice(page * 30, (page + 1) * 30), true)}<div class="table-bottom"><span>${num(items.length, 0)} results · ${num(S.catalog_count, 0)} catalog instruments</span><div class="pagination"><button data-page="-1" aria-label="Previous page" ${page === 0 ? "disabled" : ""}>←</button>${page + 1} / ${pages}<button data-page="1" aria-label="Next page" ${page >= pages - 1 ? "disabled" : ""}>→</button></div></div></section><div class="notice">*Crypto change is measured from the UTC day open. Other instruments use the provider's prior close. Sources, currencies and quote ages vary. Use Track symbol to explore the full catalog.</div>`;
}
function ordersTable() {
  return `<div class="table-wrap"><table><thead><tr><th>TIME / ACTOR</th><th>INSTRUMENT</th><th>SIDE</th><th>QUANTITY</th><th>FILL PRICE</th><th>FEE</th><th>REALIZED P&L</th></tr></thead><tbody>${S.orders.map((o) => `<tr><td>${esc(date(o.ts))}<small class="muted" style="display:block;margin-top:5px">${esc(o.actor)}</small></td><td>${esc(o.symbol)}</td><td class="${o.side === "buy" ? "positive" : "negative"}">${o.side.toUpperCase()}</td><td>${num(o.qty, 8)}</td><td>${money(o.price)}</td><td>${money(o.fee)}</td><td class="${cls(o.realized)}">${money(o.realized)}</td></tr>`).join("")}</tbody></table></div>${!S.orders.length ? '<div class="empty">Your order ledger starts with your first paper trade.<br>Funds are simulated. Every fill is saved.</div>' : ""}`;
}
function portfolioView() {
  let p = S.portfolio;
  return (
    stats() +
    `<section class="panel"><div class="panel-head"><h2>Open positions</h2><span class="muted">Unrealized P&L includes allocated entry fees</span></div><div class="table-wrap"><table><thead><tr><th>INSTRUMENT</th><th>QUANTITY</th><th>AVG COST</th><th>LAST</th><th>VALUE</th><th>UNREALIZED</th><th>ACTION</th></tr></thead><tbody>${p.positions.map((x) => `<tr data-symbol="${esc(x.symbol)}"><td>${esc(x.symbol)}</td><td>${num(x.qty, 8)}</td><td>${money(x.average)}</td><td>${money(x.price)}</td><td>${money(x.qty * x.price)}</td><td class="${cls(x.price - x.average)}">${money((x.price - x.average) * x.qty)}</td><td><button class="text-button" data-trade="${esc(x.symbol)}">Trade ↗</button></td></tr>`).join("")}</tbody></table></div>${!p.positions.length ? '<div class="empty">No open positions. Use the paper order ticket to get started.</div>' : ""}</section><section class="panel section-space"><div class="panel-head"><h2>Execution ledger</h2><a class="text-button" href="/api/export?table=orders" download="market-deck-orders.csv">↓ Export CSV</a></div>${ordersTable()}</section><div class="notice">Cash ${money(p.cash)} · Realized P&L ${money(p.realized)} · Fees paid ${money(p.fees)}. Marks use latest saved prices and can be stale. USD stocks, ETFs and crypto only; no leverage or short selling.</div>`
  );
}
function news() {
  return `<div class="news-topline"><div><span class="eyebrow">WORLDWIDE PERSPECTIVE</span><h2>${S.news.length} archived headlines</h2><p class="note">Markets, geopolitics, business and crypto.</p></div><span class="tag">${new Set(S.news.map((n) => n.source)).size} SOURCES · 5-MIN POLLING</span></div><div class="news-tabs">${["all", "markets", "world", "asia", "crypto"].map((x) => `<button data-news-topic="${x}" class="${newsTopic === x ? "active" : ""}">${x === "all" ? "All headlines" : x === "asia" ? "India & Asia" : x[0].toUpperCase() + x.slice(1)}</button>`).join("")}</div><div class="filters"><input id="news-query" value="${esc(newsQuery)}" placeholder="Search headlines…" aria-label="Search news"><select id="news-source" aria-label="News source"><option value="">All sources</option>${[
    ...new Set(S.news.map((n) => n.source)),
  ]
    .sort()
    .map(
      (x) => `<option ${x === newsSource ? "selected" : ""}>${esc(x)}</option>`,
    )
    .join(
      "",
    )}</select><a class="text-button" href="/api/export?table=news" download="market-news.csv">↓ Archive CSV</a></div><div class="news-grid" id="news-cards">${newsCards(filteredNews())}</div><div class="notice">Publisher headlines and original source links. This desk does not reproduce full articles. Source timestamps and feed failures are shown; worldwide coverage is selected, not exhaustive.</div>`;
}
function newsCards(items) {
  return (
    items
      .map(
        (n, i) =>
          `<a class="news-card" href="${esc(n.url)}" target="_blank" rel="noopener noreferrer"><div class="news-meta"><span class="news-source">${esc(n.source)}</span><span>${age(n.published_ts || n.seen)}</span></div><span class="news-category">${newsCategory(n)}</span><h3>${esc(n.title)}</h3><div class="news-card-footer"><span>${n.published_ts ? esc(new Date(n.published_ts * 1000).toLocaleString()) : "Publisher time unavailable"}</span><span>Read story ↗</span></div></a>`,
      )
      .join("") ||
    '<div class="empty">No headlines match. Try a different topic or source.</div>'
  );
}
function signalsView() {
  return `<div class="notice">Research screens use up to 30 stored prices per instrument, with a 14-sample RSI and up to 20-sample moving average. Stored samples are spaced at least five minutes apart; historical provider bars may also be present. These are conditional technical observations, not personalized investment advice or predictions. Freshness and sample count matter.</div><section class="panel"><div class="panel-head"><h2>Technical research screen</h2><span class="tag">RULE-BASED · NOT AN AI FORECAST</span></div><div class="table-wrap"><table><thead><tr><th>INSTRUMENT</th><th>LAST</th><th>RSI (14)</th><th>SMA ≤20</th><th>MOMENTUM</th><th>SAMPLES</th><th>OBSERVATION</th></tr></thead><tbody>${S.signals.map((s) => `<tr data-symbol="${esc(s.symbol)}"><td><b>${esc(s.symbol)}</b><small class="muted" style="display:block;margin-top:4px">${age(s.asof)}</small></td><td>${money(s.price, s.currency)}</td><td class="${s.rsi < 30 ? "positive" : s.rsi > 70 ? "negative" : ""}">${s.rsi}</td><td>${money(s.mean, s.currency)}</td><td class="${cls(s.momentum)}">${pct(s.momentum)}</td><td>${s.samples}</td><td><span class="tag">${esc(s.action.toUpperCase())}</span></td></tr>`).join("")}</tbody></table></div>${!S.signals.length ? '<div class="empty">Collecting samples. Signals appear after at least 15 observed prices.</div>' : ""}</section><div class="full-grid section-space">${S.signals
    .filter((s) => s.action !== "watch")
    .slice(0, 6)
    .map(
      (s) =>
        `<section class="panel panel-body"><div class="eyebrow">${esc(s.action.toUpperCase())}</div><h2>${esc(s.symbol)}</h2><p class="note" style="margin-top:13px">${esc(s.reason)}</p><div class="row"><span class="muted">RSI ${s.rsi}</span><span class="muted">${s.samples} samples · ${age(s.asof)}</span></div><button class="wide" data-symbol="${esc(s.symbol)}">Inspect chart ↗</button></section>`,
    )
    .join("")}</div>`;
}
function bots() {
  return `<div class="full-grid">${S.integrations.map((b, i) => `<section class="panel bot-card"><div class="bot-summary"><span class="bot-icon">${["⌘", "✳", "↗"][i]}</span><div><h2>${esc(b.name)}</h2><small class="${b.installed ? "positive" : "muted"}">${b.installed ? "● CLI installed" : "CLI unavailable"}</small></div></div><p class="note">${b.name === "Hermes" ? "Authenticated localhost commands for your allowed WhatsApp sender. Paper orders, portfolio status and emergency stop." : "Run an on-demand research brief using the current portfolio and technical snapshot through your local CLI session."}</p><div class="row"><span class="muted">Execution</span><span class="tag">${b.name === "Hermes" ? "PAPER ONLY" : "ADVISORY"}</span></div>${b.name === "Hermes" ? '<div class="notice">Allowed personal sender: configured owner. Local skill installed separately. WhatsApp pairing and delivery are managed by Hermes.</div>' : `<button class="wide" data-ai="${b.name}" ${!b.installed || S.jobs.some((j) => j.state === "running") ? "disabled" : ""}>${S.jobs.some((j) => j.state === "running" && j.bot === b.name) ? "Research in progress…" : "Run " + b.name + " research ↗"}</button>`}</section>`).join("")}</div><section class="panel section-space"><div class="panel-head"><div><h2>Paper strategy engine</h2><small>Deterministic signals · separate from AI advisors</small></div><button class="${S.settings.autopilot ? "auto-button" : ""}" id="toggle-auto">${S.settings.autopilot ? "Pause paper strategy" : "Enable paper strategy"}</button></div><div class="panel-body"><p class="note">Every five minutes, evaluate fresh USD crypto quotes. Review-buy signals may open a $100 paper position; review-trim signals may close up to $100. One order per cycle, at most one order per instrument per hour, subject to all risk controls. It starts paused and never sends real orders.</p><div class="row"><span class="muted">Strategy status</span><span class="${S.settings.autopilot ? "positive" : "muted"}">${S.settings.autopilot ? "ENABLED" : "PAUSED"} ${S.settings.kill_switch ? "· EMERGENCY STOP" : ""}</span></div></div></section><section class="panel section-space"><div class="panel-head"><h2>Advisor results</h2><span class="muted">Saved in your database</span></div>${S.jobs.map((j) => `<div class="panel-head"><h3>${esc(j.bot)} <span class="tag">${esc(j.state)}</span></h3><small>${date(j.created)}</small></div><div class="bot-result">${esc(j.result || "Waiting for local advisor…")}</div>`).join("") || '<div class="empty">Run a research brief to start your advisor history.</div>'}</section>`;
}
function journal() {
  return `<section class="panel"><div class="panel-head"><h2>Workspace activity</h2><a class="text-button" href="/api/export?table=events" download="market-events.csv">↓ Export journal</a></div>${S.events.map((e) => `<div class="log-row"><time>${date(e.ts)}</time><span><span class="tag">${esc(e.kind)}</span></span><span>${esc(e.message)}</span></div>`).join("") || '<div class="empty">No events yet.</div>'}</section>`;
}
function controls() {
  return `<div class="setting-grid"><section class="panel"><div class="panel-head"><h2>Paper risk limits</h2><span class="tag">USD ACCOUNT</span></div><div class="panel-body"><form id="limits-form"><label>Maximum order notional ($)<input name="max_order" type="number" min="1" max="10000" required value="${S.settings.max_order}"></label><label>Maximum position (% of equity)<input name="max_position_pct" type="number" min="1" max="50" required value="${S.settings.max_position_pct}"></label><label>Daily equity loss limit ($)<input name="daily_loss_limit" type="number" min="1" max="10000" required value="${S.settings.daily_loss_limit}"></label><p class="help-text">Loss limit compares current marked equity to the first order's equity baseline each UTC day. A breach blocks new buys. Selling remains subject to order size and freshness checks.</p><button type="submit" class="primary wide">Save limits</button></form><button id="resume" class="wide ${S.settings.kill_switch ? "auto-button" : "danger"}">${S.settings.kill_switch ? "Resume original-account execution" : "Stop original paper account"}</button></div></section><section class="panel"><div class="panel-head"><h2>Price alerts</h2><span class="tag">LOCAL JOURNAL</span></div><div class="panel-body"><form id="alert-form"><label>Instrument<select name="symbol">${S.assets
    .filter((a) => a.price)
    .map((a) => `<option value="${esc(a.symbol)}">${esc(a.symbol)}</option>`)
    .join(
      "",
    )}</select></label><label>Trigger<select name="op"><option value="above">Crosses above</option><option value="below">Crosses below</option></select></label><label>Target price (instrument currency)<input name="price" type="number" min="0.00000001" step="any" required></label><button class="primary wide">Create price alert</button></form><div class="alert-list">${S.alerts.map((a) => `<div class="alert-line"><div>${esc(a.symbol)} ${a.op} ${num(a.price, 8)}<small class="${a.active ? "muted" : "positive"}" style="display:block;margin-top:6px">${a.active ? "Monitoring" : "Triggered " + date(a.triggered)}</small></div><button data-delete-alert="${a.id}" aria-label="Delete alert">×</button></div>`).join("")}</div></div></section></div><section class="panel section-space"><div class="panel-head"><h2>Provider health & coverage</h2><span class="muted">No fabricated fallback prices</span></div><div class="table-wrap"><table><thead><tr><th>PROVIDER</th><th>STATE</th><th>CHECKED</th><th>DETAIL</th></tr></thead><tbody>${S.providers.map((p) => `<tr><td>${esc(p.name)}</td><td class="${p.state === "ok" ? "positive" : "negative"}">${esc(p.state.toUpperCase())}</td><td>${age(p.checked)}</td><td class="feed-message">${esc(p.message)}</td></tr>`).join("")}</tbody></table></div></section>`;
}
function guide() {
  let cards = [
    [
      "Scheduled market research",
      "The AI research desk generates a saved brief every ten minutes, even with your browser closed. It combines a dated quote snapshot, sampled technical screens, your paper portfolio and recent headlines. Mirai API keys stay in a private server file; automatic mode falls back to your authenticated Codex CLI if Mirai fails. Configure the key, model, provider and schedule in Controls. Research suggests conditional setups and never places orders.",
    ],
    [
      "Your personal workspace",
      "Star instruments to save a server-backed watchlist. Add a private research note to each instrument, inspect real provider candles and export their OHLC data. Ctrl K or Cmd K opens market and page search. All markets supports sorting, region and asset filters, saved-only view and fresh-quote filtering. Unsaved notes and control edits survive background refreshes.",
    ],
    [
      "World news desk",
      "The news wire collects selected publisher headlines and original links every five minutes: BBC World, Asia and Business, Guardian World and Business, Al Jazeera, CNBC Markets, CoinDesk and Economic Times. Filter by topic, source or headline text. News titles are not verified full-article analysis; feed failures are shown in Controls.",
    ],
    [
      "What is live here?",
      "Kraken USD spot pairs are polled every 30 seconds. The dashboard refreshes every 10 seconds. Exchange REST snapshots show collection time; they are not tick-by-tick streams. Stocks and indices refresh every 120 seconds through indicative Yahoo Finance data. Currency, source and quote age accompany each instrument.",
    ],
    [
      "Worldwide coverage",
      "The crypto catalog includes Kraken spot pairs, with USD pairs tracked automatically. Default equities, indices, FX and commodities span major regions. Add Yahoo Finance symbols such as INFY.NS, 7203.T or SAP.DE. This does not include every exchange or private asset. Licensed consolidated market data needs provider accounts and entitlements.",
    ],
    [
      "Charts and technicals",
      "Candles use provider OHLC and real reported volume. Choose 1D, 1W or 1M and inspect candles with the crosshair. The gold line is the 20-bar simple moving average. Research screens use stored price samples; their timeframe differs from chart bars. The chart never invents missing candles.",
    ],
    [
      "Paper fills and risk",
      "The account begins with $100,000 simulated cash. Buy fills add 0.05% slippage and sells subtract 0.05%, plus a 0.1% fee. Orders require recent USD quotes, respect cash and position limits, and forbid shorts. There is no exchange matching, partial-fill model, margin or guaranteed liquidity.",
    ],
    [
      "Your AI workspace",
      "Codex and AGY research jobs are launched using the installed CLIs and their existing authentication. Results are stored. Research-only prompts do not authorize money movement. The separate deterministic paper strategy can be enabled explicitly in AI workspace. CLI installation is checked; authentication is verified when a job runs.",
    ],
    [
      "Hermes and WhatsApp",
      "The local Market Deck Hermes skill uses a private token and the allowlisted sender CONFIGURED_OWNER. Hermes may request paper status, paper orders and emergency stop through the local API. WhatsApp must be paired in Hermes. Sender identity must come from the actual gateway session; never accept a phone number claimed inside a message.",
    ],
    [
      "Persistence and availability",
      "SQLite saves quotes, candles, headline links, orders, alerts, jobs and audit events in data/market.db. Prices are sampled for storage at five-minute spacing. Sampled history is retained 90 days; news and orders are kept. Daily database snapshots retain seven days. The systemd user service restarts on failure and starts after reboot with lingering enabled. The server still depends on this machine and network being available.",
    ],
    [
      "Connecting a real broker",
      "Real-money execution is not implemented or enabled. To add it, first choose a broker or exchange and supply credentials, account permissions and explicit limits. India, global equities and crypto require different eligible venues. A future adapter needs order reconciliation, cancellation, kill controls and broker-side risk tests before live use.",
    ],
  ];
  return `<div class="guide-grid">${cards.map(([h, p]) => `<section class="panel panel-body"><h3>${h}</h3><p>${p}</p></section>`).join("")}</div><section class="panel panel-body section-space"><h3>Access from your laptop</h3><p class="note" style="margin-top:10px">This terminal runs on the GCP server's loopback interface. Forward the port through your existing SSH connection, then open localhost on your laptop.</p><code class="command">ssh -L 8790:127.0.0.1:8790 YOUR_EXISTING_SSH_HOST</code></section>`;
}
let viewBindings = new AbortController();
function listen(node, event, handler) { if (node) node.addEventListener(event, handler, {signal:viewBindings.signal}); }
function render() {
  if (!S) return;
  let n = navs.find((x) => x[0] === route) || navs[0];
  $("#page-name").textContent = n[2];
  $("#heading").innerHTML = esc(n[3]) + '<span class="dot">.</span>';
  $("#subtitle").textContent = n[4];
  $("#heading-eyebrow").textContent =
    route === "overview"
      ? "YOUR DAILY PERSPECTIVE"
      : route === "research"
        ? "RESEARCH, ON A RHYTHM"
        : "YOUR MARKET WORKSPACE";
  $$("[data-nav]").forEach((x) => {
    x.classList.toggle("active", x.dataset.nav === route);
    if (x.dataset.nav === route) x.setAttribute("aria-current", "page");
    else x.removeAttribute("aria-current");
  });
  let html = (
    {
      overview: () => (window.simulationHome ? window.simulationHome() : "") + overview(),
      demo: () => window.demoView ? window.demoView() : "Loading demo…",
      markets,
      portfolio: portfolioView,
      news,
      signals: signalsView,
      research: researchView,
      bots,
      journal,
      controls,
      guide,
    }[route] || overview
  )();
  const nextView = readinessBanner() +
    (S.settings.kill_switch
      ? '<div class="banner">■ Original paper account stopped: manual and automatic buys/sells are blocked. Holdings remain. Simulation and research have separate controls.</div>'
      : "") + html;
  const host = $("#view");
  if (host.dataset.workspaceRoute === route && window.DeckWorkspace) window.DeckWorkspace.update(host, nextView, {preserveInputs:viewDirty()});
  else { host.innerHTML = nextView; host.dataset.workspaceRoute = route; }
  viewBindings.abort();
  viewBindings = new AbortController();
  bindView();
  bindUpgrades();
  if (route === "overview") {
    if (chartSymbol === selected) requestAnimationFrame(drawChart);
    else loadChart();
    if (liquidityOpen) loadBook();
  }
}
function readinessBanner() {
  if (!readinessState) return '<div class="notice" role="status">Resource health and owner pause are unknown. Legacy connection; quote timestamps remain authoritative.</div>';
  const r = readinessState;
  const paused = r.owner_pause?.active === true;
  return '<div class="notice workspace-status" role="status">' + (paused ? 'Owner pause is active. Research/service activation is separate. ' : 'Owner pause state: ' + esc(r.owner_pause?.state || 'unknown') + '. ') +
    'Quotes: ' + esc(r.resources?.quotes?.state || 'unknown') + ' · FX: ' + esc(r.resources?.fx?.state || 'unknown') +
    ' · Executable books: ' + esc(r.resources?.executable_books?.state || 'unknown') + ' · Model identity: upstream unverified.</div>';
}
function bindView() {
  $$("[data-symbol]").forEach(
    (el) => (el.onclick = () => choose(el.dataset.symbol)),
  );
  $$("[data-trade]").forEach(
    (el) =>
      (el.onclick = (e) => {
        e.stopPropagation();
        openTrade(el.dataset.trade);
      }),
  );
  $$("[data-route]").forEach(
    (el) => (el.onclick = () => (location.hash = el.dataset.route)),
  );
  $$("[data-add]").forEach((el) => (el.onclick = openAdd));
  $$("[data-span]").forEach(
    (el) =>
      (el.onclick = () => {
        span = el.dataset.span;
        localStorage.setItem("deck-span", span);
        bars = [];
        chartSymbol = "";
        render();
      }),
  );
  $$("[data-chart]").forEach(
    (el) =>
      (el.onclick = () => {
        chartType = el.dataset.chart;
        localStorage.setItem("deck-chart", chartType);
        render();
      }),
  );
  listen($("#chart-symbol"), "change", (e) => choose(e.target.value));
  $$("[data-page]").forEach(
    (el) =>
      (el.onclick = () => {
        page += Number(el.dataset.page);
        render();
      }),
  );
  listen($("#market-query"), "input", (e) => {
    query = e.target.value;
    page = 0;
    let p = e.target.selectionStart;
    render();
    let x = $("#market-query");
    x.focus();
    x.setSelectionRange(p, p);
  });
  listen($("#kind-filter"), "change", (e) => {
    marketFilter = e.target.value;
    page = 0;
    render();
  });
  listen($("#region-filter"), "change", (e) => {
    region = e.target.value;
    page = 0;
    render();
  });
  for (let sel of ["#news-query", "#news-source"])
    listen($(sel), "input", () => {
      newsQuery = $("#news-query").value;
      newsSource = $("#news-source").value;
      if (window.loadNewsArchive) window.loadNewsArchive();
      else $("#news-cards").innerHTML = newsCards(filteredNews());
    });
  $$("[data-ai]").forEach(
    (el) =>
      (el.onclick = async () => {
        el.disabled = true;
        try {
          await api("ai", { bot: el.dataset.ai });
          toast("Advisor started. Results will appear here.");
          await refresh();
        } catch (e) {
          toast(e.message, true);
          el.disabled = false;
        }
      }),
  );
  listen($("#toggle-auto"), "click", () =>
    mutate(
      "settings",
      { autopilot: !S.settings.autopilot },
      "Paper strategy " + (S.settings.autopilot ? "paused" : "enabled"),
    ),
  );
  listen($("#resume"), "click", () => {
    const stopping = !S.settings.kill_switch;
    if (!confirm((stopping ? "Stop" : "Resume") + " original paper account at " + location.origin + "? Manual and automatic buys/sells are affected. Holdings remain. Independent simulation/research and the full-service owner pause are unaffected.")) return;
    mutate("settings", { kill_switch: stopping }, "Original-account execution control updated");
  });
  listen($("#limits-form"), "submit", (e) => {
    e.preventDefault();
    mutate(
      "settings",
      Object.fromEntries(
        [...new FormData(e.target)].map(([k, v]) => [k, Number(v)]),
      ),
      "Risk limits saved",
    );
  });
  listen($("#alert-form"), "submit", (e) => {
    e.preventDefault();
    mutate(
      "alerts",
      Object.fromEntries(new FormData(e.target)),
      "Price alert created",
    );
  });
  $$("[data-delete-alert]").forEach(
    (el) =>
      (el.onclick = () =>
        mutate(
          "alert-delete",
          { id: Number(el.dataset.deleteAlert) },
          "Alert removed",
        )),
  );
  let canvas = $("#price-chart");
  if (canvas) {
    canvas.addEventListener("pointermove", (e) => {
      let rect = canvas.getBoundingClientRect();
      cross = { x: e.clientX - rect.left, y: e.clientY - rect.top };
      drawChart();
    });
    canvas.addEventListener("pointerleave", () => {
      cross = null;
      drawChart();
    });
  }
}
async function mutate(path, body, message) {
  try {
    await api(path, body);
    let form =
      path === "settings" && Object.hasOwn(body, "max_order")
        ? "limits-form"
        : path === "alerts"
          ? "alert-form"
          : null;
    if (form) {
      dirtyForms.delete(form);
      formDrafts.delete(form);
    }
    toast(message);
    await refresh();
  } catch (e) {
    toast(e.message, true);
  }
}
async function refresh() {
  if (document.hidden) return;
  if (fetching) return fetching;
  fetching = (async () => {
    try {
      const [stateResult, readinessResult] = await Promise.allSettled([api("state"), api("v2/readiness")]);
      if (stateResult.status !== "fulfilled") throw stateResult.reason;
      S = stateResult.value;
      readinessState = readinessResult.status === "fulfilled" && readinessResult.value.contract_version === "2.0" ? readinessResult.value : null;
      if (!asset()) selected = S.assets[0]?.symbol || "BTC/USD";
      $("#live-badge").textContent = "● SERVER REACHABLE";
      $("#live-badge").classList.remove("offline");
      $("#engine-label").textContent =
        "Persistent · " + Math.floor((S.now - S.started) / 60) + "m uptime";
      $("#updated").textContent =
        "UI received " +
        new Date().toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
        });
      $("#stop").textContent = S.settings.kill_switch
        ? "◼ Original account stopped"
        : "◼ Stop original account";
      let syms = [
        "BTC/USD",
        "ETH/USD",
        "^GSPC",
        "^NSEI",
        "^N225",
        "EURUSD=X",
        "GC=F",
      ];
      $("#ticker").innerHTML = syms
        .map((s) => asset(s))
        .filter(Boolean)
        .map(
          (a) =>
            `<button class="tick" data-tick="${esc(a.symbol)}"><span class="tick-label">${esc(a.kind === "index" ? a.name : a.symbol)}</span><b>${money(a.price, a.currency)}</b><span class="${cls(a.change)}">${pct(a.change)}</span></button>`,
        )
        .join("");
      $$("[data-tick]").forEach(
        (el) => (el.onclick = () => choose(el.dataset.tick)),
      );
      let editing =
        $("#view input:focus, #view select:focus, #view textarea:focus") ||
        viewDirty();
      if (!editing) render();
      if ($("#trade-dialog").open) updateOrderEstimate();
      updateCountdowns();
    } catch (e) {
      $("#live-badge").textContent = "● DISCONNECTED";
      $("#live-badge").classList.add("offline");
      $("#engine-label").textContent = "Server disconnected · saved observations may be stale";
      if (!S)
        $("#view").innerHTML =
          '<div class="empty">Waiting for the local engine. Retrying automatically…</div>';
    } finally {
      fetching = null;
    }
  })();
  return fetching;
}
let bookCache = null,
  bookSymbol = "";
async function loadBook() {
  let s = selected;
  try {
    let result;
    if (
      bookSymbol === s &&
      bookCache &&
      Date.now() / 1000 - bookCache.fetched < 15
    )
      result = bookCache;
    else result = await api("microstructure?symbol=" + encodeURIComponent(s));
    if (s !== selected || !$("#microstructure")) return;
    bookCache = result;
    bookSymbol = s;
    if (!result.available) {
      $("#microstructure").innerHTML =
        '<div class="empty">' + esc(result.message) + "</div>";
      return;
    }
    let max = Math.max(
      ...result.asks.map((x) => x[1]),
      ...result.bids.map((x) => x[1]),
    );
    let level = (b, side) =>
      `<div class="depth-row" style="--depth:${(b[1] / max) * 100}%;--depth-color:${side === "buy" ? "#4be2ae15" : "#fa738315"}"><span class="${side === "buy" ? "positive" : "negative"}">${num(b[0], 4)}</span><span>${num(b[1], 6)}</span></div>`;
    $("#microstructure").innerHTML =
      `<div class="book"><div class="book-label"><span>PRICE</span><span>SIZE</span></div>${result.asks
        .slice(0, 6)
        .reverse()
        .map((b) => level(b, "sell"))
        .join(
          "",
        )}<div class="spread">Spread ${money(result.spread, asset()?.currency)} <span class="muted">${age(result.fetched)}</span></div>${result.bids
        .slice(0, 6)
        .map((b) => level(b, "buy"))
        .join(
          "",
        )}</div><div class="tape"><div class="book-label"><span>TIME & SALES</span><span>QUANTITY</span></div>${result.trades
        .slice(0, 12)
        .map(
          (t) =>
            `<div class="depth-row"><span class="${t.side === "buy" ? "positive" : "negative"}">${num(t.price, 4)}</span><span>${num(t.qty, 6)} <small class="muted">${new Date(t.ts * 1000).toLocaleTimeString()}</small></span></div>`,
        )
        .join(
          "",
        )}<div class="help-text" style="padding:10px 14px">Kraken spot only · REST snapshots · ${age(result.fetched)}</div></div>`;
  } catch (e) {
    if ($("#microstructure"))
      $("#microstructure").innerHTML =
        '<div class="empty">Exchange liquidity snapshot unavailable.</div>';
  }
}
async function loadChart() {
  let gen = ++chartGeneration,
    s = selected,
    range = span;
  try {
    let result = await api(
      "candles?symbol=" + encodeURIComponent(s) + "&span=" + range,
    );
    if (gen !== chartGeneration || s !== selected || range !== span) return;
    bars = result;
    chartSymbol = s;
    if ($("#chart-empty"))
      $("#chart-empty").textContent = bars.length
        ? ""
        : "No provider candles for this range.";
    drawChart();
  } catch (e) {
    if (gen !== chartGeneration) return;
    bars = [];
    chartSymbol = s;
    if ($("#chart-empty")) {
      $("#chart-empty").style.display = "grid";
      $("#chart-empty").textContent =
        "Provider candles unavailable. Use Reload to try again.";
    }
  }
}
function drawChart() {
  let canvas = $("#price-chart");
  if (!canvas) return;
  let rect = canvas.getBoundingClientRect(),
    w = rect.width,
    h = rect.height;
  if (w < 10) return;
  let ratio = window.devicePixelRatio || 1;
  canvas.width = Math.round(w * ratio);
  canvas.height = Math.round(h * ratio);
  let ctx = canvas.getContext("2d");
  ctx.scale(ratio, ratio);
  ctx.clearRect(0, 0, w, h);
  let empty = $("#chart-empty");
  if (!bars.length) {
    empty.style.display = "grid";
    return;
  }
  empty.style.display = "none";
  let display = bars.slice(-720);
  let left = 12,
    right = w < 500 ? 62 : 76,
    top = 20,
    bottom = h - 72,
    pw = w - left - right,
    ph = bottom - top;
  let min = Math.min(...display.map((b) => b.low)),
    max = Math.max(...display.map((b) => b.high));
  let pad = (max - min) * 0.12 || max * 0.01;
  min -= pad;
  max += pad;
  let y = (p) => top + ((max - p) / (max - min)) * ph,
    step = pw / display.length,
    x = (i) => left + (i + 0.5) * step;
  ctx.font = '9px "IBM Plex Mono", monospace';
  ctx.textAlign = "left";
  for (let i = 0; i < 5; i++) {
    let gy = top + (i * ph) / 4;
    ctx.strokeStyle = "#202a37";
    ctx.lineWidth = 0.5;
    ctx.beginPath();
    ctx.moveTo(left, gy);
    ctx.lineTo(w - right + 4, gy);
    ctx.stroke();
    ctx.fillStyle = "#65778e";
    ctx.fillText(
      num(max - ((max - min) * i) / 4, max < 1 ? 6 : 2),
      w - right + 12,
      gy + 3,
    );
  }
  let vmax = Math.max(...display.map((b) => b.volume)) || 1;
  display.forEach((b, i) => {
    let up = b.close >= b.open;
    ctx.fillStyle = up ? "#4be2ae38" : "#fa738338";
    let vh = (b.volume / vmax) * 38;
    ctx.fillRect(
      x(i) - Math.max(1, step * 0.32),
      h - 27 - vh,
      Math.max(2, step * 0.64),
      vh,
    );
    if (chartType === "candles") {
      ctx.strokeStyle = up ? "#4be2ae" : "#fa7383";
      ctx.fillStyle = ctx.strokeStyle;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x(i), y(b.high));
      ctx.lineTo(x(i), y(b.low));
      ctx.stroke();
      let a = y(Math.max(b.open, b.close)),
        bh = Math.max(1, Math.abs(y(b.open) - y(b.close)));
      ctx.fillRect(
        x(i) - Math.max(1, step * 0.3),
        a,
        Math.max(2, step * 0.6),
        bh,
      );
    }
  });
  if (chartType === "line") {
    let grad = ctx.createLinearGradient(0, top, 0, bottom);
    grad.addColorStop(0, "#4be2ae30");
    grad.addColorStop(1, "#4be2ae00");
    ctx.beginPath();
    display.forEach((b, i) =>
      i ? ctx.lineTo(x(i), y(b.close)) : ctx.moveTo(x(i), y(b.close)),
    );
    ctx.lineTo(x(display.length - 1), bottom);
    ctx.lineTo(x(0), bottom);
    ctx.closePath();
    ctx.fillStyle = grad;
    ctx.fill();
    ctx.beginPath();
    display.forEach((b, i) =>
      i ? ctx.lineTo(x(i), y(b.close)) : ctx.moveTo(x(i), y(b.close)),
    );
    ctx.strokeStyle = "#4be2ae";
    ctx.lineWidth = 1.7;
    ctx.stroke();
  }
  ctx.beginPath();
  let started = false,
    offset = bars.length - display.length;
  display.forEach((b, i) => {
    let end = offset + i;
    if (end < 19) return;
    let avg =
      bars.slice(end - 19, end + 1).reduce((s, b) => s + b.close, 0) / 20;
    if (started) ctx.lineTo(x(i), y(avg));
    else {
      ctx.moveTo(x(i), y(avg));
      started = true;
    }
  });
  ctx.strokeStyle = "#e9c588";
  ctx.lineWidth = 1.1;
  if (showSma) ctx.stroke();
  ctx.textAlign = "center";
  ctx.fillStyle = "#65778e";
  for (let i = 0; i < 5; i++) {
    let j = Math.floor((i * (display.length - 1)) / 4),
      d = new Date(display[j].ts * 1000);
    let label =
      span === "1D"
        ? d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
        : d.toLocaleDateString([], { month: "short", day: "numeric" });
    ctx.fillText(label, x(j), h - 9);
  }
  let last = display.at(-1);
  ctx.setLineDash([3, 4]);
  ctx.strokeStyle = "#4be2ae66";
  ctx.beginPath();
  ctx.moveTo(left, y(last.close));
  ctx.lineTo(w - right, y(last.close));
  ctx.stroke();
  ctx.setLineDash([]);
  let bar = last;
  if (cross && cross.x >= left && cross.x < w - right) {
    let i = Math.min(
      display.length - 1,
      Math.max(0, Math.floor((cross.x - left) / step)),
    );
    bar = display[i];
    ctx.setLineDash([3, 3]);
    ctx.strokeStyle = "#8091aa";
    ctx.beginPath();
    ctx.moveTo(x(i), top);
    ctx.lineTo(x(i), h - 28);
    ctx.moveTo(left, cross.y);
    ctx.lineTo(w - right, cross.y);
    ctx.stroke();
    ctx.setLineDash([]);
  }
  chartMetrics();
  $("#ohlc-label").textContent =
    `O ${num(bar.open, 4)}  H ${num(bar.high, 4)}  L ${num(bar.low, 4)}  C ${num(bar.close, 4)}  V ${num(bar.volume, 2)}`;
}
function openTrade(s = selected) {
  if (!S) return;
  let available = S.assets.filter(
    (a) =>
      a.currency === "USD" &&
      ["crypto", "equity", "etf"].includes(a.kind) &&
      a.price,
  );
  if (!available.length) {
    toast("Waiting for tradable USD quotes.", true);
    return;
  }
  let requested = asset(s);
  if (requested && !available.some((a) => a.symbol === s)) {
    toast(
      "This instrument is research-only. Paper execution supports USD stocks, ETFs and crypto.",
      true,
    );
    return;
  }
  $("#order-symbol").innerHTML = available
    .map(
      (a) =>
        `<option value="${esc(a.symbol)}" ${a.symbol === s ? "selected" : ""}>${esc(a.symbol + " · " + a.name)}</option>`,
    )
    .join("");
  $("#order-form").reset();
  $("#order-symbol").value = available.some((a) => a.symbol === s)
    ? s
    : available[0].symbol;
  orderRequestId = crypto.randomUUID();
  updateOrderEstimate();
  $("#trade-dialog").showModal();
}
function updateOrderEstimate() {
  let a = asset($("#order-symbol").value);
  if (!a) return;
  $("#order-quote").innerHTML =
    money(a.price) + ' <small class="muted">' + age(a.asof) + " · USD</small>";
  let qty = Number($("#order-form [name=qty]").value),
    side = $("#order-form [name=side]:checked").value;
  let p = a.price * (side === "buy" ? 1.0005 : 0.9995);
  $("#order-estimate").textContent =
    qty > 0
      ? `Estimated ${side === "buy" ? "debit" : "credit"}: ${money(p * qty * (side === "buy" ? 1.001 : 0.999))} · fee ${money(p * qty * 0.001)}`
      : "Enter quantity to estimate the order.";
  $("#order-form [type=submit]").disabled = true;
  $("#order-preflight").innerHTML = "";
  $("#order-preflight").classList.toggle("has-quantity", qty > 0);
  clearTimeout(preflightTimer);
  let generation = ++preflightGeneration;
  if (qty > 0 && Number.isFinite(qty)) {
    let body = { symbol: a.symbol, side, qty };
    $("#order-preflight").innerHTML =
      '<div class="preflight-wait">Checking quote, funds & risk limits…</div>';
    preflightTimer = setTimeout(async () => {
      try {
        let p = await api("order-preview", body);
        if (generation !== preflightGeneration) return;
        $("#order-preflight").innerHTML =
          `<div class="preflight"><div class="preflight-state"><span class="tiny-dot"></span> Preflight passed <span>Estimate</span></div><div class="row"><span>Modeled fill</span><b>${money(p.price)}</b></div><div class="row"><span>Paper cash after</span><b>${money(p.cash_after)}</b></div><div class="row"><span>Position after</span><b>${num(p.qty_after, 8)}</b></div><div class="row"><span>Portfolio weight</span><b>${num(p.position_pct)}%</b></div></div>`;
        $("#order-form [type=submit]").disabled = false;
      } catch (e) {
        if (generation !== preflightGeneration) return;
        $("#order-preflight").innerHTML =
          '<div class="preflight-error">' + esc(e.message) + "</div>";
      }
    }, 300);
  }
}
let sortKey = "symbol",
  sortDir = 1,
  savedOnly = false,
  freshOnly = false,
  newsQuery = "",
  newsSource = "",
  newsTopic = "all",
  moverSide = "gainers",
  liquidityOpen = false;
let showSma = localStorage.getItem("deck-sma") !== "false",
  preflightTimer,
  preflightGeneration = 0,
  orderRequestId = "",
  paletteIndex = 0;
const noteDrafts = new Map(),
  dirtyForms = new Set(),
  formDrafts = new Map();
let selectedBriefId = null;
if (!["1D", "1W", "1M"].includes(span)) span = "1D";
if (!["candles", "line"].includes(chartType)) chartType = "candles";
const isFresh = (a) =>
  Boolean(
    a?.price &&
      a.asof &&
      Date.now() / 1000 - a.asof < (a.kind === "crypto" ? 120 : 300) &&
      Date.now() / 1000 - a.fetched < 120,
  );
const isSaved = (s) => S?.watchlist?.includes(s);
function assetColor(a) {
  let colors =
    a.kind === "crypto"
      ? ["#e8b66a", "#32291c"]
      : a.region === "India"
        ? ["#bfabe9", "#272137"]
        : a.kind === "index"
          ? ["#aecf8c", "#252f20"]
          : ["#9bbfdb", "#1e2b34"];
  return `color:${colors[0]};background:${colors[1]}`;
}
function assetGlyph(a) {
  return esc(
    a.symbol?.startsWith("BTC")
      ? "₿"
      : a.symbol?.startsWith("ETH")
        ? "Ξ"
        : a.symbol?.replace(/[^A-Z]/g, "").slice(0, 2) || "↗",
  );
}
function sessionStrip() {
  return `<div class="session-strip"><div><span class="tiny-dot"></span><span>YOUR WORLD AT A GLANCE</span></div><div class="world-clocks">${[
    ["New York", "America/New_York"],
    ["London", "Europe/London"],
    ["Mumbai", "Asia/Kolkata"],
    ["Tokyo", "Asia/Tokyo"],
  ]
    .map(
      ([name, tz]) =>
        `<span>${name}<b>${new Intl.DateTimeFormat("en-GB", { timeZone: tz, hour: "2-digit", minute: "2-digit" }).format(new Date())}</b></span>`,
    )
    .join("")}</div></div>`;
}
function watchlistPanel() {
  let items = (S.watchlist || []).map((s) => asset(s)).filter(Boolean);
  return `<section class="panel watchlist-panel"><div class="panel-head"><div class="panel-title"><h2>Your watchlist</h2><span class="badge-count">${items.length}</span></div><button class="text-button" data-add aria-label="Add an instrument">＋ Add</button></div><div class="watchlist-label"><span>INSTRUMENT</span><span>LAST / CHANGE</span></div>${
    items
      .slice(0, 8)
      .map(
        (a) =>
          `<div class="watch-row ${a.symbol === selected ? "selected" : ""}"><button class="watch-asset" data-symbol="${esc(a.symbol)}"><span class="asset-icon" style="${assetColor(a)}">${assetGlyph(a)}</span><span><b>${esc(a.symbol)}</b><small>${esc(a.name)}</small></span><span class="watch-price"><b>${money(a.price, a.currency)}</b><small class="${cls(a.change)}">${pct(a.change)} <span class="quote-age">· ${age(a.asof)}</span></small></span></button><button class="star saved" data-save="${esc(a.symbol)}" aria-label="Remove ${esc(a.symbol)} from watchlist">★</button></div>`,
      )
      .join("") ||
    '<div class="empty">Make this space yours.<br>Star instruments in All markets to save them here.</div>'
  }<div class="table-bottom"><span>${items.length > 8 ? `Showing 8 of ${items.length}` : "Saved to your workspace"}</span><button class="text-button" id="view-watchlist">Manage →</button></div></section>`;
}
function moversPanel() {
  let items = S.assets
    .filter(
      (a) =>
        a.kind === "crypto" &&
        isFresh(a) &&
        Number.isFinite(a.change) &&
        ((moverSide === "gainers" && a.change > 0) ||
          (moverSide === "losers" && a.change < 0)),
    )
    .sort((a, b) =>
      moverSide === "gainers" ? b.change - a.change : a.change - b.change,
    )
    .slice(0, 5);
  let fresh = S.assets.filter((a) => a.kind === "crypto" && isFresh(a)),
    up = fresh.filter((a) => a.change > 0).length,
    down = fresh.filter((a) => a.change < 0).length;
  return `<section class="panel"><div class="panel-head"><div class="panel-title"><span class="section-index">02</span><h2>Market movers</h2></div><span class="tag">CRYPTO</span></div><div class="mover-tabs">${["gainers", "losers"].map((x) => `<button data-movers="${x}" class="${moverSide === x ? "active" : ""}">${x === "gainers" ? "↗ Gainers" : "↘ Losers"}</button>`).join("")}<span>UTC day</span></div><div class="mover-list">${items.map((a, i) => `<button class="mover" data-symbol="${esc(a.symbol)}"><span class="mover-rank">0${i + 1}</span><span><b>${esc(a.symbol)}</b><small>${money(a.price, a.currency)}</small></span><span class="${cls(a.change)}">${pct(a.change)}</span></button>`).join("") || '<div class="empty">No fresh quotes in this group.</div>'}</div><div class="breadth"><div><span><b class="positive">${up}</b> advancing</span><span><b class="negative">${down}</b> declining</span></div><div class="breadth-bar"><span style="width:${(up / (up + down || 1)) * 100}%"></span></div><small>Fresh tracked crypto only · price change, not a buy signal</small></div></section>`;
}
function chartMetrics() {
  let el = $("#chart-metrics");
  if (!el || !bars.length) return;
  let a = asset(),
    high = Math.max(...bars.map((b) => b.high)),
    low = Math.min(...bars.map((b) => b.low)),
    volume = bars.reduce((n, b) => n + b.volume, 0);
  el.innerHTML = `<div><span>RANGE HIGH</span><b>${money(high, a?.currency)}</b></div><div><span>RANGE LOW</span><b>${money(low, a?.currency)}</b></div><div><span>REPORTED VOLUME</span><b>${num(volume)} <small>base units</small></b></div><div><span>CANDLES</span><b>${bars.length} <small>${span === "1D" ? "5m" : span === "1W" ? "1h" : "1d"} bars</small></b></div>`;
}
function notebookPanel() {
  let saved = S.notes?.find((n) => n.symbol === selected),
    body = noteDrafts.has(selected)
      ? noteDrafts.get(selected)
      : saved?.body || "";
  return `<section class="panel notebook"><div class="panel-head"><h2>Your research notes <span class="tag">${esc(selected)}</span></h2><small>${noteDrafts.has(selected) ? "Unsaved draft" : saved ? "Saved " + age(saved.updated) : "A place for your thesis"}</small></div><form id="note-form" class="panel-body"><label for="research-note" class="sr-only">Research notes for ${esc(selected)}</label><textarea id="research-note" maxlength="4000" rows="3" placeholder="What are you watching? Write your thesis, the condition you need to see, and what would change your mind…">${esc(body)}</textarea><div class="notebook-footer"><span class="muted">Private to this workspace · up to 4,000 characters</span><button class="small-button" type="submit">Save note ↗</button></div></form></section>`;
}
function viewDirty() {
  return (
    (route === "controls" && dirtyForms.size > 0) ||
    (route === "overview" && noteDrafts.has(selected))
  );
}
function newsCategory(n) {
  return /BBC Asia|Economic Times/.test(n.source)
    ? "India & Asia"
    : /World|Al Jazeera/.test(n.source)
      ? "World"
      : /CoinDesk/.test(n.source)
        ? "Crypto"
        : "Markets";
}
function balancedNews() {
  let groups = {};
  for (let n of S.news) {
    groups[n.source] ??= [];
    groups[n.source].push(n);
  }
  let out = [];
  for (let i = 0; i < 40; i++)
    for (let rows of Object.values(groups)) if (rows[i]) out.push(rows[i]);
  return out;
}
function filteredNews() {
  return S.news.filter(
    (n) =>
      n.title.toLowerCase().includes(newsQuery.toLowerCase()) &&
      (!newsSource || n.source === newsSource) &&
      (newsTopic === "all" ||
        newsCategory(n) ===
          {
            markets: "Markets",
            world: "World",
            asia: "India & Asia",
            crypto: "Crypto",
          }[newsTopic]),
  );
}
function briefResult(b) {
  try {
    return JSON.parse(b?.result || "null");
  } catch {
    return null;
  }
}
function briefBanner() {
  let r = S.research;
  if (!r) return "";
  let running = r.briefs.find((b) => b.state === "running"),
    latest = r.briefs.find((b) => b.state === "completed"),
    data = briefResult(latest),
    last = r.briefs[0];
  return `<button class="research-banner" data-route="research"><span class="research-emblem">✦</span><span><b>Intelligence, on a rhythm.</b><span>${running ? "Your next brief is being researched…" : data ? esc(data.summary.slice(0, 160)) + (data.summary.length > 160 ? "…" : "") : last?.state === "failed" ? "The last research attempt failed. Open the desk for details." : "Global context and conditional trading ideas, every 10 minutes."}</span></span><span class="research-banner-right"><span class="tag">${r.enabled ? "10-MIN BRIEFS" : "SCHEDULE PAUSED"}</span><span>Open research desk ↗</span></span></button>`;
}
function researchSettings() {
  let r = S.research;
  if (!r) return "";
  return `<section class="panel research-settings"><div class="panel-head"><div><h2>Scheduled AI research</h2><small>A global market brief every 10 minutes · suggestions only</small></div><span class="tag">${r.enabled ? "ENABLED" : "PAUSED"}</span></div><form id="research-settings-form" class="panel-body"><div class="research-form-grid"><label>Research provider<select name="provider">${[
    ["auto", "Mirai API → Codex fallback"],
    ["mirai", "Mirai API only"],
    ["codex", "Local Codex subscription"],
  ]
    .map(
      ([value, name]) =>
        `<option value="${value}" ${r.provider === value ? "selected" : ""}>${name}</option>`,
    )
    .join(
      "",
    )}</select></label><label>Mirai model<input name="model" value="${esc(r.model)}" maxlength="100" required placeholder="Your API model name"></label><label>Replace Mirai API key<input name="api_key" type="password" autocomplete="new-password" placeholder="${r.key_configured ? "Key stored privately · leave blank to keep" : "Enter API key"}" maxlength="500"></label></div><label class="schedule-checkbox"><input name="enabled" type="checkbox" ${r.enabled ? "checked" : ""}> Generate a research brief every 10 minutes</label><div class="settings-bottom"><p class="help-text">API keys stay in a private server file and are never returned to the browser. Automatic mode tries Mirai first, then your local Codex session. Research consumes API or subscription usage. No orders are placed by this scheduler.</p><button class="primary" type="submit">Save research settings</button></div></form></section>`;
}
function researchView() {
  let r = S.research;
  if (!r) return '<div class="empty">Research engine unavailable.</div>';
  let latest =
      r.briefs.find(
        (b) => b.id === selectedBriefId && b.state === "completed",
      ) || r.briefs.find((b) => b.state === "completed"),
    current = r.briefs[0],
    data = briefResult(latest),
    running = r.briefs.some((b) => b.state === "running");
  return `<div class="research-status"><div class="research-status-main"><span class="research-emblem">✦</span><div><span class="eyebrow">YOUR SCHEDULED ANALYST</span><h2>Read the world. Find your setup.</h2><p>Prices, sampled technicals and source headlines — brought together.</p></div></div><div class="research-schedule"><div><span>${running ? "CURRENT STATUS" : r.enabled ? "NEXT SCHEDULED BRIEF" : "SCHEDULE"}</span><b data-research-countdown>${running ? "Researching…" : r.enabled ? "Calculating…" : "Paused"}</b></div><button id="run-research" class="primary" ${running ? "disabled" : ""}>${running ? "Researching…" : "Generate brief ↗"}</button></div></div>${current?.state === "failed" ? `<div class="banner">Last attempt failed: ${esc(current.error)}. ${latest ? "The last completed brief remains below." : "No suggestions were generated."}</div>` : ""}${data ? `<section class="panel brief-summary"><div class="brief-top"><span class="tag">${esc(data.regime)}</span><span class="muted">${esc(latest.provider)} · ${date(latest.finished)}</span></div><h2>The market, in context.</h2><p>${esc(data.summary)}</p><div class="brief-evidence"><span>${data.instrument_count} instruments</span><span>${data.headline_count} headlines</span><span>Snapshot ${date(data.snapshot_ts)}</span></div>${data.fallback_reason ? `<div class="fallback-note">${esc(data.fallback_reason)} This brief used ${esc(latest.provider)}.</div>` : ""}</section><div class="research-section-label"><h2>Conditional research ideas</h2><span class="muted">Every setup needs confirmation. These are research suggestions.</span></div><div class="idea-grid">${data.ideas.map((idea, i) => `<article class="panel idea-card"><div class="idea-top"><span class="idea-number">0${i + 1}</span><span class="tag ${idea.bias === "research long" ? "positive" : idea.bias === "research trim" ? "negative" : ""}">${esc(idea.bias.toUpperCase())}</span></div><button class="idea-symbol" data-symbol="${esc(idea.symbol)}">${esc(idea.symbol)} ↗</button><div class="idea-quote">${money(idea.price, idea.currency)} <span class="${idea.stale ? "negative" : "muted"}">Snapshot quote · ${age(idea.quote_asof)}${idea.stale ? " · delayed" : ""}${idea.liquidity_screen_passed === false ? " · liquidity screen below threshold" : ""}</span></div><p>${esc(idea.thesis)}</p><dl><dt>WAIT FOR</dt><dd>${esc(idea.entry_condition)}</dd><dt>INVALIDATION</dt><dd>${esc(idea.invalidation)}</dd><dt>HORIZON</dt><dd>${esc(idea.horizon)}</dd></dl>${idea.sources.length ? `<div class="idea-sources"><span>HEADLINE EVIDENCE</span>${idea.sources.map((n) => `<a href="${esc(n.url)}" target="_blank" rel="noopener noreferrer">${esc(n.source)} · ${esc(n.title)} ↗</a>`).join("")}</div>` : '<div class="idea-sources muted">Based on supplied market data; no headline cited.</div>'}<button class="wide" data-symbol="${esc(idea.symbol)}">Inspect live workspace ↗</button></article>`).join("") || '<div class="empty panel">No supported setup in this snapshot. Waiting is a valid research outcome.</div>'}</div><section class="panel research-risks"><div class="panel-head"><h2>What could change the picture</h2><span class="tag">RISK NOTES</span></div><div class="panel-body">${data.risks.map((risk) => `<p>↳ ${esc(risk)}</p>`).join("")}</div></section>` : `<section class="panel research-wait"><span class="research-emblem">✦</span><h2>${running ? "Connecting the dots…" : "Your first brief starts here."}</h2><p>${running ? "The advisor is reading your market snapshot and recent headlines. You can keep exploring while it works." : "Generate a brief now, or leave the schedule enabled. Completed research is saved here."}</p></section>`}<section class="panel section-space"><div class="panel-head"><h2>Recent research history</h2><button class="text-button" data-route="controls">Provider & schedule settings ↗</button></div><div class="brief-history">${
    r.briefs
      .slice(0, 20)
      .map(
        (b) =>
          `<div class="${b.id === latest?.id ? "viewing" : ""}"><span>${date(b.created)}</span><span class="tag ${b.state === "failed" ? "negative" : b.state === "completed" ? "positive" : ""}">${esc(b.state)}</span><span>${esc(b.provider || "Selecting provider…")}</span><span class="muted">${b.state === "completed" ? `<button class="text-button" data-brief-view="${b.id}" aria-pressed="${b.id === latest?.id}">${b.id === latest?.id ? "Viewing" : "View"} · ${briefResult(b)?.ideas?.length || 0} conditional ideas ↗</button>` : esc(b.error || "Reading market snapshot")}</span></div>`,
      )
      .join("") || '<div class="empty">No briefs yet.</div>'
  }</div></section><div class="notice">AI research uses the market data and selected news headlines available at the recorded snapshot. It cannot verify full articles or predict prices. Older briefs retain their original quote timestamps. Crypto below $1M estimated 24h USD turnover is restricted to watch-only ideas; turnover is not executable liquidity. The research scheduler does not submit paper or real orders.</div>`;
}
const originalControls = controls;
controls = function () {
  return researchSettings() + originalControls();
};
function updateCountdowns() {
  let r = S?.research;
  if (!r) return;
  let running = r.briefs.some((b) => b.state === "running");
  $$("[data-research-countdown]").forEach((el) => {
    let seconds = Math.max(0, Math.ceil(r.next_run - Date.now() / 1000));
    el.textContent = running
      ? "Researching…"
      : !r.enabled
        ? "Paused"
        : seconds
          ? `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`
          : "Starting shortly…";
  });
}
function bindUpgrades() {
  $$("[data-save]").forEach(
    (el) =>
      (el.onclick = async (e) => {
        e.stopPropagation();
        el.disabled = true;
        let symbol = el.dataset.save,
          saved = !isSaved(symbol);
        try {
          await api("watchlist", { symbol, saved });
          S.watchlist = saved
            ? [...S.watchlist, symbol]
            : S.watchlist.filter((s) => s !== symbol);
          render();
          toast(
            saved ? "Added to your watchlist." : "Removed from your watchlist.",
          );
        } catch (e) {
          toast(e.message, true);
          el.disabled = false;
        }
      }),
  );
  $$("tr[data-symbol]").forEach(
    (el) =>
      (el.onkeydown = (e) => {
        if (e.target === el && (e.key === "Enter" || e.key === " ")) {
          e.preventDefault();
          choose(el.dataset.symbol);
        }
      }),
  );
  $$("[data-sort]").forEach(
    (el) =>
      (el.onclick = () => {
        let key = el.dataset.sort;
        sortDir =
          sortKey === key
            ? -sortDir
            : key === "symbol" || key === "region"
              ? 1
              : -1;
        sortKey = key;
        page = 0;
        render();
      }),
  );
  listen($("#saved-filter"), "click", () => {
    savedOnly = !savedOnly;
    page = 0;
    render();
  });
  listen($("#fresh-filter"), "click", () => {
    freshOnly = !freshOnly;
    page = 0;
    render();
  });
  listen($("#view-watchlist"), "click", () => {
    savedOnly = true;
    marketFilter = region = "all";
    query = "";
    freshOnly = false;
    page = 0;
    location.hash = "markets";
  });
  $$("[data-movers]").forEach(
    (el) =>
      (el.onclick = () => {
        moverSide = el.dataset.movers;
        render();
      }),
  );
  $$("[data-news-topic]").forEach(
    (el) =>
      (el.onclick = () => {
        newsTopic = el.dataset.newsTopic;
        render();
      }),
  );
  listen($("#chart-sma"), "click", () => {
    showSma = !showSma;
    localStorage.setItem("deck-sma", showSma);
    render();
  });
  listen($("#chart-retry"), "click", loadChart);
  listen($("#chart-export"), "click", () => {
    if (!bars.length) {
      toast("No candles to export.", true);
      return;
    }
    let csv =
      "time,open,high,low,close,volume\n" +
      bars
        .map((b) =>
          [
            new Date(b.ts * 1000).toISOString(),
            b.open,
            b.high,
            b.low,
            b.close,
            b.volume,
          ].join(","),
        )
        .join("\n");
    download(
      csv,
      selected.replaceAll("/", "-") + "-" + span + "-candles.csv",
      "text/csv",
    );
  });
  listen($("#liquidity-details"), "toggle", (e) => {
    liquidityOpen = e.target.open;
    if (liquidityOpen) loadBook();
  });
  listen($("#research-note"), "input", (e) =>
    noteDrafts.set(selected, e.target.value),
  );
  listen($("#note-form"), "submit", async (e) => {
    e.preventDefault();
    let symbol = selected,
      body = $("#research-note").value,
      btn = e.target.querySelector("button");
    btn.disabled = true;
    try {
      await api("note", { symbol, body });
      if (noteDrafts.get(symbol) === body) noteDrafts.delete(symbol);
      toast("Research note saved.");
      await refresh();
    } catch (e) {
      toast(e.message, true);
    } finally {
      btn.disabled = false;
    }
  });
  for (let id of ["limits-form", "alert-form", "research-settings-form"]) {
    let form = $("#" + id);
    if (!form) continue;
    let draft = formDrafts.get(id);
    if (draft)
      for (let el of form.elements) {
        if (!el.name || !Object.hasOwn(draft, el.name)) continue;
        if (el.type === "checkbox") el.checked = draft[el.name];
        else el.value = draft[el.name];
      }
    listen(form, "input", () => {
      dirtyForms.add(id);
      let values = {};
      for (let el of form.elements)
        if (el.name)
          values[el.name] = el.type === "checkbox" ? el.checked : el.value;
      formDrafts.set(id, values);
    });
  }

  listen($("#research-settings-form"), "submit", async (e) => {
    e.preventDefault();
    let f = new FormData(e.target),
      body = {
        provider: f.get("provider"),
        model: f.get("model"),
        api_key: f.get("api_key"),
        enabled: f.has("enabled"),
      },
      btn = e.target.querySelector("button");
    btn.disabled = true;
    try {
      await api("research-settings", body);
      dirtyForms.delete("research-settings-form");
      formDrafts.delete("research-settings-form");
      e.target.elements.api_key.value = "";
      toast("Research settings saved.");
      await refresh();
      render();
    } catch (e) {
      toast(e.message, true);
    } finally {
      btn.disabled = false;
    }
  });
  listen($("#run-research"), "click", async (e) => {
    e.target.disabled = true;
    try {
      await api("research-run", {});
      toast("Research started. Your brief will appear here.");
      await refresh();
    } catch (err) {
      toast(err.message, true);
      e.target.disabled = false;
    }
  });
  $$("[data-brief-view]").forEach(
    (el) =>
      (el.onclick = () => {
        selectedBriefId = Number(el.dataset.briefView);
        render();
        $("#heading").scrollIntoView({ block: "start", behavior: "smooth" });
      }),
  );
  updateCountdowns();
}
function download(text, name, type) {
  let url = URL.createObjectURL(new Blob([text], { type })),
    a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function paletteResults() {
  let q = $("#global-query").value.trim().toLowerCase(),
    pages = navs
      .filter((n) => !q || n.slice(2).join(" ").toLowerCase().includes(q))
      .slice(0, q ? 4 : 5),
    items =
      S?.assets
        .filter((a) =>
          q
            ? (a.symbol + " " + a.name).toLowerCase().includes(q)
            : isSaved(a.symbol),
        )
        .slice(0, q ? 9 : 5) || [];
  $("#global-results").innerHTML =
    `${pages.length ? '<div class="palette-section">WORKSPACE</div>' : ""}${pages.map((n) => `<button class="palette-result" data-palette-route="${n[0]}"><span class="palette-icon">${n[1]}</span><span><b>${n[2]}</b><small>${n[4]}</small></span><span>↗</span></button>`).join("")}${items.length ? '<div class="palette-section">' + (q ? "INSTRUMENTS" : "YOUR WATCHLIST") + "</div>" : ""}${items.map((a) => `<button class="palette-result" data-palette-symbol="${esc(a.symbol)}"><span class="asset-icon" style="${assetColor(a)}">${assetGlyph(a)}</span><span><b>${esc(a.symbol)}</b><small>${esc(a.name)}</small></span><span>${money(a.price, a.currency)}<small class="${cls(a.change)}">${pct(a.change)}</small></span></button>`).join("")}<button class="palette-result palette-add" id="palette-add"><span>＋</span><span><b>Explore the full catalog</b><small>Track another stock or crypto pair</small></span><span>↗</span></button>`;
  $$("[data-palette-route]").forEach(
    (el) =>
      (el.onclick = () => {
        $("#search-dialog").close();
        location.hash = el.dataset.paletteRoute;
      }),
  );
  $$("[data-palette-symbol]").forEach(
    (el) =>
      (el.onclick = () => {
        $("#search-dialog").close();
        choose(el.dataset.paletteSymbol);
      }),
  );
  $("#palette-add").onclick = () => {
    $("#search-dialog").close();
    openAdd();
  };
  paletteIndex = 0;
  highlightPalette();
}
function highlightPalette() {
  let results = $$(".palette-result");
  results.forEach((el, i) => el.classList.toggle("active", i === paletteIndex));
  results[paletteIndex]?.scrollIntoView({ block: "nearest" });
}
function openSearch() {
  if (!S) return;
  $("#global-query").value = "";
  $("#search-dialog").showModal();
  paletteResults();
  $("#global-query").focus();
}
$("#open-search").onclick = openSearch;
$("#global-query").addEventListener("input", paletteResults);
$("#global-query").addEventListener("keydown", (e) => {
  if (["ArrowDown", "ArrowUp"].includes(e.key)) {
    e.preventDefault();
    let length = $$(".palette-result").length;
    paletteIndex =
      (paletteIndex + (e.key === "ArrowDown" ? 1 : -1) + length) % length;
    highlightPalette();
  } else if (e.key === "Enter") {
    e.preventDefault();
    $$(".palette-result")[paletteIndex]?.click();
  }
});
document.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
    e.preventDefault();
    if ($("#search-dialog").open) $("#search-dialog").close();
    else if (!$$("dialog[open]").length) openSearch();
  }
});
$$("[data-nav]").forEach((el) =>
  el.addEventListener("click", () => {
    document.body.classList.remove("nav-open");
    $("#menu-toggle").setAttribute("aria-expanded", "false");
  }),
);
$("#menu-toggle").onclick = () => {
  let open = document.body.classList.toggle("nav-open");
  $("#menu-toggle").setAttribute("aria-expanded", open);
};
$("#nav-backdrop").onclick = () => {
  document.body.classList.remove("nav-open");
  $("#menu-toggle").setAttribute("aria-expanded", "false");
};
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    document.body.classList.remove("nav-open");
    $("#menu-toggle").setAttribute("aria-expanded", "false");
  }
});
$$("[data-budget]").forEach(
  (el) =>
    (el.onclick = () => {
      let a = asset($("#order-symbol").value);
      if (!a?.price) return;
      let side = $("#order-form [name=side]:checked").value;
      $("#order-form [name=qty]").value = (
        Number(el.dataset.budget) /
        (a.price * (side === "buy" ? 1.0005 : 0.9995))
      ).toFixed(8);
      orderRequestId = crypto.randomUUID();
      updateOrderEstimate();
    }),
);
$("#close-position").onclick = () => {
  let symbol = $("#order-symbol").value,
    p = S.portfolio.positions.find((p) => p.symbol === symbol);
  $("#order-form [name=side][value=sell]").checked = true;
  $("#order-form [name=qty]").value = p?.qty || "";
  orderRequestId = crypto.randomUUID();
  updateOrderEstimate();
  if (!p) toast("You have no position in this instrument.", true);
};

$("#order-form").addEventListener("input", () => {
  orderRequestId = crypto.randomUUID();
  updateOrderEstimate();
});
$("#order-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  let btn = e.target.querySelector("[type=submit]");
  btn.disabled = true;
  try {
    let body = Object.fromEntries(new FormData(e.target));
    body.request_id = orderRequestId;
    await api("orders", body);
    $("#trade-dialog").close();
    toast("Paper order filled and saved to your ledger.");
    await refresh();
  } catch (e) {
    toast(e.message, true);
  } finally {
    if ($("#trade-dialog").open) updateOrderEstimate();
  }
});
function openAdd() {
  $("#catalog-query").value = "";
  $("#catalog-results").innerHTML = "";
  $("#add-dialog").showModal();
  $("#catalog-query").focus();
}
let searchTimer;
$("#catalog-query").addEventListener("input", () => {
  clearTimeout(searchTimer);
  let q = $("#catalog-query").value;
  searchTimer = setTimeout(async () => {
    try {
      let result = await api("search?q=" + encodeURIComponent(q));
      if (q !== $("#catalog-query").value) return;
      $("#catalog-results").innerHTML = result
        .map(
          (a) =>
            `<button type="button" data-catalog="${esc(a.symbol)}"><span>${esc(a.symbol)} <small class="muted">${esc(a.name)}</small></span><span class="positive">＋</span></button>`,
        )
        .join("");
      $$("[data-catalog]").forEach(
        (b) => (b.onclick = () => track(b.dataset.catalog)),
      );
    } catch (e) {
      toast(e.message, true);
    }
  }, 250);
});
async function track(s) {
  try {
    toast("Resolving instrument…");
    await api("track", { symbol: s });
    $("#add-dialog").close();
    await refresh();
    choose(s);
    toast("Instrument is now tracked.");
  } catch (e) {
    toast(e.message, true);
  }
}
$("#add-form").addEventListener("submit", (e) => {
  e.preventDefault();
  track($("#catalog-query").value.trim());
});
$$(".close-dialog").forEach(
  (b) => (b.onclick = () => b.closest("dialog").close()),
);
$("#open-ticket").onclick = () => openTrade();
$("#refresh").onclick = () => refresh();
$("#stop").onclick = () => {
  if (!confirm("Stop the original paper account at " + location.origin + "? This blocks its manual and automatic buys/sells. Holdings remain. Independent simulation and research are unaffected.")) return;
  mutate("settings", { kill_switch: true }, "Original paper account stopped. Holdings retained.");
};
window.addEventListener("resize", drawChart);
window.addEventListener("hashchange", () => {
  route = ({learning:'bots',alerts:'journal',connections:'controls',admin:'controls'})[location.hash.slice(1)] || location.hash.slice(1) || "overview";
  document.body.classList.remove("nav-open");
  $("#menu-toggle").setAttribute("aria-expanded", "false");
  render();
  $("#heading").setAttribute("tabindex","-1");
  $("#heading").focus({preventScroll:true});
  window.scrollTo(0, 0);
});
setInterval(() => {
  $("#clock").textContent =
    new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) +
    " LOCAL";
  updateCountdowns();
}, 1000);
let statePoll;
async function pollState(){clearTimeout(statePoll);await refresh();if(!document.hidden)statePoll=setTimeout(pollState,10000);}
document.addEventListener('visibilitychange',()=>{clearTimeout(statePoll);if(document.hidden){++chartGeneration;for(const c of viewReads)c.abort();}else pollState();});
setInterval(() => {
  if (!document.hidden && route === "overview") loadChart();
}, 60000);
route = ({learning:'bots',alerts:'journal',connections:'controls',admin:'controls'})[location.hash.slice(1)] || location.hash.slice(1) || "overview";
$("#view").innerHTML =
  '<div class="loading">Connecting to your local market engine…</div>';
pollState();
