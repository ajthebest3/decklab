/* Shared Phase 2 presentation utilities. No requests, model or execution authority. */
(()=>{'use strict';
let enhanced=true;try{enhanced=localStorage.getItem('decklab-workspace-enhanced')!=='false';}catch{}
const mode=new URLSearchParams(location.search).get('workspace');if(['classic','v2'].includes(mode))enhanced=mode==='v2';
document.documentElement.dataset.workspace=enhanced?'v2':'classic';
const escape=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const key=n=>n.nodeType===1?(n.id||n.getAttribute('data-key')||[...n.attributes].filter(a=>a.name.startsWith('data-')&&!['data-portfolio'].includes(a.name)).map(a=>a.name+'='+a.value).join('|')):'';
function patch(old,fresh,preserveInputs=true){
 if(old.nodeType!==fresh.nodeType||old.nodeName!==fresh.nodeName){old.replaceWith(fresh.cloneNode(true));return;}
 if(old.nodeType===3){if(old.data!==fresh.data)old.data=fresh.data;return;}
 if(old.nodeType!==1)return;
 if(old.hasAttribute('data-workspace-owned'))return;
 const live=['INPUT','TEXTAREA','SELECT'].includes(old.tagName), focused=old===document.activeElement,keep=live&&(focused||preserveInputs);
 for(const a of [...old.attributes])if(!fresh.hasAttribute(a.name)&&!(old.tagName==='DETAILS'&&a.name==='open')&&!(keep&&['value','checked','selected'].includes(a.name)))old.removeAttribute(a.name);
 for(const a of [...fresh.attributes])if(!(old.tagName==='DETAILS'&&a.name==='open')&&!(keep&&['value','checked','selected'].includes(a.name))&&old.getAttribute(a.name)!==a.value)old.setAttribute(a.name,a.value);
 if(live&&!keep){old.value=fresh.value;if(old.tagName==='INPUT')old.checked=fresh.checked;}
 if(['CANVAS','TEXTAREA','INPUT'].includes(old.tagName)||focused&&live)return;
 const pool=[...old.childNodes],used=new Set();
 [...fresh.childNodes].forEach((f,i)=>{const k=key(f);let n=k?pool.find(n=>!used.has(n)&&key(n)===k&&n.nodeName===f.nodeName):pool.find(n=>!used.has(n)&&!key(n)&&n.nodeName===f.nodeName);
 if(n){used.add(n);patch(n,f,preserveInputs);}else n=f.cloneNode(true);
 if(old.childNodes[i]!==n)old.insertBefore(n,old.childNodes[i]||null);
 });for(const n of pool)if(!used.has(n)&&n.parentNode===old&&!n.hasAttribute?.('data-workspace-owned'))old.removeChild(n);
}
function update(root,html,options={}){if(!root)return;if(!enhanced){root.innerHTML=html;return;}const t=document.createElement('template');t.innerHTML=root.tagName==='TBODY'?'<table><tbody>'+html+'</tbody></table>':html;const f=root.cloneNode(false);f.append(...(root.tagName==='TBODY'?t.content.querySelector('tbody'):t.content).childNodes);patch(root,f,options.preserveInputs!==false);}
function read(){try{const p=JSON.parse(localStorage.getItem('decklab-layout-v2')||'{}');return {width:Math.max(35,Math.min(65,Number(p.width)||58)),dense:p.dense===true};}catch{return {width:58,dense:false};}}
function layout(){const p=read();document.documentElement.style.setProperty('--workspace-split',p.width+'%');document.documentElement.dataset.density=p.dense?'compact':'comfortable';return p;}
function save(p){try{localStorage.setItem('decklab-layout-v2',JSON.stringify(p));return true;}catch{return false;}}
function controls(){if(document.querySelector('#workspace-preferences'))return;const host=document.querySelector('.observer-content')||document.querySelector('#main-content')||document.querySelector('main');if(!host)return;
 const p=layout(),box=document.createElement('details');box.id='workspace-preferences';box.setAttribute('data-workspace-owned','');box.innerHTML='<summary>Workspace layout</summary><div class="workspace-options"><label>Desktop panel width <input id="workspace-width" type="range" min="35" max="65" value="'+p.width+'"> <output id="workspace-width-value">'+p.width+'%</output></label><label><input id="workspace-enhanced" type="checkbox" '+(enhanced?'checked':'')+'> Phase 2 workspace</label><label><input id="workspace-density" type="checkbox" '+(p.dense?'checked':'')+'> Compact rows</label><button id="workspace-reset">Reset layout</button><span id="workspace-save" role="status">Saved in this browser only</span></div>';
 host.prepend(box);function change(){enhanced=document.querySelector('#workspace-enhanced').checked;document.documentElement.dataset.workspace=enhanced?'v2':'classic';try{localStorage.setItem('decklab-workspace-enhanced',String(enhanced));}catch{}const v={width:Number(document.querySelector('#workspace-width').value),dense:document.querySelector('#workspace-density').checked};document.documentElement.style.setProperty('--workspace-split',v.width+'%');document.documentElement.dataset.density=v.dense?'compact':'comfortable';document.querySelector('#workspace-width-value').textContent=v.width+'%';document.querySelector('#workspace-save').textContent=save(v)?'Layout saved in this browser':'Storage unavailable; layout applies for this visit';}
 box.addEventListener('input',change);box.querySelector('button').onclick=()=>{document.querySelector('#workspace-width').value=58;document.querySelector('#workspace-density').checked=false;change();};}
function fields(value,depth=0){if(value===null||typeof value!=='object')return '<p>'+escape(value??'Unavailable')+'</p>';const entries=Array.isArray(value)?value.slice(0,10).map((v,i)=>[String(i+1),v]):Object.entries(value).slice(0,30);return '<dl class="workspace-facts">'+entries.map(([k,v])=>'<div><dt>'+escape(k.replaceAll('_',' '))+'</dt><dd>'+(v!==null&&typeof v==='object'?(depth<2?fields(v,depth+1):'<span>Nested evidence in Advanced</span>'):escape(v??'Unavailable'))+'</dd></div>').join('')+'</dl>';}
function record(value){return fields(value)+'<details><summary>Advanced: exact saved JSON</summary><pre>'+escape(JSON.stringify(value,null,2))+'</pre></details>';}

window.DeckWorkspace={update,escape,record,layout};layout();document.addEventListener('DOMContentLoaded',controls);
})();
