import {initNewEra} from '/vendor/new-era.js';
initNewEra();
const q=s=>document.querySelector(s),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const stamp=t=>t?new Date(t*1000).toLocaleString():'No observation',num=(n,d=2)=>Number.isFinite(n)?n.toLocaleString(undefined,{maximumFractionDigits:d}):'—';
const price=a=>!Number.isFinite(a.price)?'—':a.currency==='GBp'?num(a.price)+' GBp':/^[A-Z]{3}$/.test(a.currency)?num(a.price,a.price<1?6:2)+' '+a.currency:'Currency unknown';
let offset=0,query='',generation=0,pinsOnly=false,symbol='BTC/USD',last=null;
let stateRequest,historyRequest,historyGeneration=0,pollTimer,searchTimer,searchPending=false;
let history=[],visibleHistory=[],historySymbol='',historyStatus='loading',cursorTime=null;
const knownAssets=new Map();
let pins;try{const v=JSON.parse(localStorage.getItem('decklab-observer-watchlist')||'[]');pins=new Set(Array.isArray(v)?v.filter(s=>typeof s==='string'&&s.length<=40).slice(0,100):[]);}catch{pins=new Set();}
// Patch existing nodes instead of rebuilding polling surfaces. Focus, scroll and
// open evidence disclosures belong to the reader and survive background updates.
function morph(old,fresh){
 if(old.nodeType!==fresh.nodeType||old.nodeName!==fresh.nodeName){old.replaceWith(fresh.cloneNode(true));return;}
 if(old.nodeType===Node.TEXT_NODE){if(old.data!==fresh.data)old.data=fresh.data;return;}
 if(old.nodeType!==Node.ELEMENT_NODE)return;
 for(const a of [...old.attributes])if(!fresh.hasAttribute(a.name)&&!(old.tagName==='DETAILS'&&a.name==='open'))old.removeAttribute(a.name);
 for(const a of [...fresh.attributes])if(old.getAttribute(a.name)!==a.value)old.setAttribute(a.name,a.value);
 const children=[...fresh.childNodes];children.forEach((n,i)=>{if(old.childNodes[i])morph(old.childNodes[i],n);else old.append(n.cloneNode(true));});
 while(old.childNodes.length>children.length)old.lastChild.remove();
}
function sync(selector,html){
 const root=q(selector),t=document.createElement('template');
 // A tbody needs table parsing context for valid row elements.
 if(root.tagName==='TBODY'){t.innerHTML='<table><tbody>'+html+'</tbody></table>';}else t.innerHTML=html;
 const source=root.tagName==='TBODY'?t.content.querySelector('tbody'):t.content;
 const old=new Map([...root.children].map(n=>[n.dataset.key,n]));
 [...source.children].forEach((fresh,i)=>{let node=old.get(fresh.dataset.key);if(node){old.delete(fresh.dataset.key);morph(node,fresh);}else node=fresh.cloneNode(true);if(root.children[i]!==node)root.insertBefore(node,root.children[i]||null);});
 for(const node of old.values())node.remove();
}
async function get(path,controller){const timeout=setTimeout(()=>controller.abort(),15000);try{const r=await fetch(path,{signal:controller.signal});if(!r.ok)throw Error('Observation source unavailable');return await r.json();}finally{clearTimeout(timeout);}}
function schedule(){clearTimeout(pollTimer);if(!document.hidden&&!searchPending)pollTimer=setTimeout(refresh,15000);}
function evidence(){
 const a=knownAssets.get(symbol),s=last?.research.find(r=>r.symbol===symbol);
 q('#chart-symbol').textContent=symbol;
 q('#instrument-context').textContent=a?`${a.name} · ${a.kind} · ${price(a)}`:'Instrument details are outside this results page. Search this symbol to load its source.';
 const facts=a?[['Provider',a.source||'Unavailable'],['Observation',stamp(a.asof)],['Timestamp basis',a.timestamp_basis||'Unavailable'],['Currency',a.currency||'Unknown'],['Freshness',a.fresh?'Observed recently':'Stale / unavailable']]:[['Source','Not yet loaded']];
 sync('#source-facts',facts.map(([k,v])=>`<div data-key="${esc(k)}"><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join(''));
 q('#selected-research').textContent=s?`Sampled RSI ${num(s.rsi,1)} · mean ${num(s.mean,6)} · momentum ${num(s.momentum)}% · ${s.samples} samples · ${stamp(s.asof)} · ${s.fresh?'recent observation':'stale observation'}. Descriptive only.`:'No indicator returned for this symbol in the current research snapshot. At least 15 recorded samples are required; coverage is limited.';
 q('#evidence-json').textContent=JSON.stringify({symbol,observation:a||null,indicator:s||null,history_status:historyStatus,history_symbol:historySymbol||null,saved_samples:historySymbol===symbol?history.length:0,ai_enabled:false,execution_enabled:false},null,2);
 for(const b of document.querySelectorAll('[data-symbol]'))b.setAttribute('aria-pressed',String(b.dataset.symbol===symbol));
}
function sample(){
 const i=Number(q('#sample-cursor').value),r=visibleHistory[i];
 q('#sample-value').textContent=r?`${stamp(r.ts)} · ${num(r.price,8)} ${knownAssets.get(symbol)?.currency||''}`:'No recorded sample selected.';
 if(r){cursorTime=r.ts;const duration=visibleHistory.at(-1).ts-visibleHistory[0].ts;const x=12+(duration?(r.ts-visibleHistory[0].ts)/duration*496:0);const line=q('#chart-cursor');if(line){line.setAttribute('x1',x);line.setAttribute('x2',x);}}
}
function draw(){
 const windowSeconds=Number(q('#chart-range').value),cutoff=Date.now()/1000-windowSeconds;
 visibleHistory=historySymbol===symbol?history.filter(r=>!windowSeconds||r.ts>=cutoff):[];
 const rows=visibleHistory,values=rows.map(r=>r.price),lo=Math.min(...values),hi=Math.max(...values),span=hi-lo||1;
 if(rows.length>=2){const path=rows.map((r,i)=>(i?'L':'M')+(12+(r.ts-rows[0].ts)/(rows.at(-1).ts-rows[0].ts)*496).toFixed(2)+','+(200-(r.price-lo)/span*180).toFixed(2)).join(' ');
 q('#chart').innerHTML=(q('#chart-type').value==='area'?`<path d="${path} L508,200 L12,200 Z" fill="#bea3ff" fill-opacity=".15"/>`:'')+`<path d="${path}" fill="none" stroke="#bea3ff" stroke-width="2"/><line id="chart-cursor" y1="20" y2="200" stroke="#f5d7a5" stroke-dasharray="3 4"/><text x="12" y="218" fill="#b1adbf" font-size="12">${esc(num(lo,6))}</text><text x="12" y="12" fill="#b1adbf" font-size="12">${esc(num(hi,6))}</text>`;
 }else q('#chart').innerHTML='';
 q('#chart-note').textContent=historyStatus==='error'?'History refresh failed. Previous samples retained; they may be stale.':historyStatus==='loading'?'Loading saved observations…':rows.length<2?'Fewer than two recorded samples in this window. No missing prices are invented.':`${rows.length} recorded samples · ${stamp(rows[0].ts)} → ${stamp(rows.at(-1).ts)}`;
 q('#chart').setAttribute('aria-label',`${symbol}: ${rows.length} saved price samples. Equivalent values in Accessible price data.`);
 q('#price-caption').textContent=`${symbol} · ${rows.length} samples · ${knownAssets.get(symbol)?.currency||'currency not loaded'}`;
 sync('#history-rows',rows.map(r=>`<tr data-key="${esc(r.ts)}"><td>${esc(stamp(r.ts))}</td><td>${esc(num(r.price,8))}</td></tr>`).join('')||'<tr data-key="empty"><td colspan="2">No saved samples in this window.</td></tr>');
 const slider=q('#sample-cursor');slider.disabled=!rows.length;slider.max=Math.max(0,rows.length-1);
 const preserved=rows.findIndex(r=>r.ts===cursorTime);slider.value=preserved>=0?preserved:Math.max(0,rows.length-1);sample();evidence();
}
async function chart(){
 const selected=symbol,current=++historyGeneration;historyRequest?.abort();const controller=historyRequest=new AbortController();
 if(historySymbol!==symbol){history=[];historySymbol=symbol;cursorTime=null;historyStatus='loading';draw();}
 try{const rows=await get('/api/observer/history?symbol='+encodeURIComponent(selected),controller);if(current!==historyGeneration||selected!==symbol)return;
 history=rows.filter(r=>Number.isFinite(r.ts)&&Number.isFinite(r.price));historySymbol=selected;historyStatus='ready';draw();
 }catch{if(current!==historyGeneration||selected!==symbol||controller.signal.aborted&&document.hidden)return;historyStatus='error';draw();}
 finally{if(historyRequest===controller)historyRequest=null;}
}
function render(data){
 last=data;for(const a of data.assets)knownAssets.set(a.symbol,a);
 sync('#quotes',data.assets.map(a=>`<tr data-key="${esc(a.symbol)}"><td><button data-pin="${esc(a.symbol)}" aria-label="Track ${esc(a.symbol)}" aria-pressed="${pins.has(a.symbol)}">${pins.has(a.symbol)?'★':'☆'}</button></td><td><button class="instrument" data-symbol="${esc(a.symbol)}" aria-pressed="${a.symbol===symbol}">${esc(a.symbol)}</button><small>${esc(a.name)}</small></td><td>${esc(price(a))}</td><td class="${a.change>=0?'positive':'negative'}">${esc(num(a.change))}${Number.isFinite(a.change)?'%':''}</td><td><span class="${a.fresh?'positive':'stale'}">${a.fresh?'Observed recently':'Stale / unavailable'}</span><small>${esc(stamp(a.asof))}</small><small>${esc(a.timestamp_basis)}</small></td></tr>`).join('')||`<tr data-key="empty"><td colspan="5" class="empty-state">${pinsOnly?'No pinned instruments match this search.':'No matching observations yet.'}</td></tr>`);
 q('#page-info').textContent=Math.min(data.offset+1,data.total)+'–'+Math.min(data.offset+data.limit,data.total)+' / '+data.total;q('#previous').disabled=offset===0;q('#next').disabled=offset+data.limit>=data.total;
 sync('#headlines',data.news.map(n=>{let url;try{url=new URL(n.url);if(!['https:','http:'].includes(url.protocol))return '';}catch{return '';}
 return `<article data-key="${esc(url.href)}" class="news-card"><small>${esc(n.source)} · ${esc(stamp(n.published_ts))}</small><h3><a target="_blank" rel="noopener noreferrer" href="${esc(url.href)}">${esc(n.title)} ↗</a></h3></article>`;}).join('')||'<p data-key="empty" class="empty-state">The first publisher checks are in progress. Feed failures stay visible below.</p>');
 sync('#indicators',data.research.slice(0,12).map(s=>`<article data-key="${esc(s.symbol)}" class="research-card"><h3><button class="instrument" data-symbol="${esc(s.symbol)}" aria-pressed="${s.symbol===symbol}">${esc(s.symbol)}</button></h3><dl><dt>Sampled RSI</dt><dd>${esc(num(s.rsi,1))}</dd><dt>Sampled mean</dt><dd>${esc(num(s.mean,6))}</dd><dt>Momentum</dt><dd>${esc(num(s.momentum))}%</dd><dt>Samples</dt><dd>${esc(s.samples)}</dd></dl><small>${esc(stamp(s.asof))} · ${s.fresh?'recent observation':'stale observation'}</small></article>`).join('')||'<p data-key="empty" class="empty-state">Collecting evidence. Indicators need at least 15 recorded observations; no generated forecasts or synthetic results.</p>');
 sync('#providers',data.providers.map(p=>`<div data-key="${esc(p.name)}" class="provider-row"><strong>${esc(p.name)}</strong><span class="${p.state==='ok'?'positive':'stale'}">${esc(p.state)}</span><small>${esc(p.message)} · last attempt ${esc(stamp(p.checked))}</small></div>`).join('')||'<p data-key="empty">Feed checks are starting…</p>');
 const good=data.providers.filter(p=>p.state==='ok').length;
 q('#notice').textContent=data.notice;q('#connection').textContent=`${data.observed} instruments observed · feeds ${good}/${data.providers.length} OK · AI off · execution off`;
 q('#updated').textContent='View received '+new Date().toLocaleTimeString();evidence();
}
async function refresh(){
 clearTimeout(pollTimer);if(document.hidden||searchPending)return;
 const current=++generation;stateRequest?.abort();const controller=stateRequest=new AbortController();q('#refresh').setAttribute('aria-busy','true');
 try{const data=await get('/api/observer/state?limit=80&offset='+offset+'&q='+encodeURIComponent(query)+(pinsOnly?'&pins='+encodeURIComponent(JSON.stringify([...pins])):''),controller);if(current===generation){render(data);await chart();}}
 catch{if(current===generation&&!controller.signal.aborted)q('#connection').textContent='Disconnected / partial update. Existing observations may be stale. Use Refresh view to retry.';else if(current===generation&&!document.hidden)q('#connection').textContent='Refresh timed out. Existing observations retained. Use Refresh view to retry.';}
 finally{if(current===generation){stateRequest=null;q('#refresh').setAttribute('aria-busy','false');schedule();}}
}
q('#refresh').onclick=refresh;q('#previous').onclick=()=>{offset=Math.max(0,offset-80);refresh();};q('#next').onclick=()=>{offset+=80;refresh();};
q('#pins-only').onclick=()=>{pinsOnly=!pinsOnly;q('#pins-only').setAttribute('aria-pressed',String(pinsOnly));offset=0;refresh();};
q('#search').oninput=e=>{clearTimeout(searchTimer);clearTimeout(pollTimer);searchPending=true;++generation;stateRequest?.abort();query=e.target.value;offset=0;searchTimer=setTimeout(()=>{searchPending=false;refresh();},250);};
document.addEventListener('click',e=>{const pin=e.target.closest('[data-pin]'),asset=e.target.closest('[data-symbol]');if(pin){if(!pins.has(pin.dataset.pin)&&pins.size>=100){q('#connection').textContent='Watchlist limit: 100 instruments. Remove one before adding another.';return;}pins.has(pin.dataset.pin)?pins.delete(pin.dataset.pin):pins.add(pin.dataset.pin);try{localStorage.setItem('decklab-observer-watchlist',JSON.stringify([...pins]));}catch{q('#connection').textContent='Browser storage unavailable. Watchlist kept for this visit only.';}if(pinsOnly)refresh();else if(last)render(last);}if(asset){symbol=asset.dataset.symbol;evidence();chart();}});
q('#chart-range').onchange=draw;q('#chart-type').onchange=draw;q('#sample-cursor').oninput=sample;
q('#chart-reset').onclick=()=>{q('#chart-range').value='0';q('#chart-type').value='line';cursorTime=null;draw();};
q('#help').onclick=()=>q('#keyboard-help').showModal();q('#close-help').onclick=()=>q('#keyboard-help').close();
document.addEventListener('visibilitychange',()=>{clearTimeout(pollTimer);if(document.hidden){++generation;++historyGeneration;stateRequest?.abort();historyRequest?.abort();q('#refresh').setAttribute('aria-busy','false');}else refresh();});
refresh();
