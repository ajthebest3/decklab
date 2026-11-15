import asyncio,json,os,sys,tempfile,threading,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));TMP=tempfile.TemporaryDirectory(prefix='decklab-phase2-full-');os.environ['MARKET_DECK_DATA']=TMP.name
import server as s
s.init();now=time.time()
with s.db() as c:
 for i in range(185):
  sym=f'QA{i:03}/USD';c.execute('INSERT OR REPLACE INTO assets VALUES(?,?,?,?,?,?,?,1)',(sym,sym,'crypto','Global','USD','Kraken',sym));s.store(c,sym,100+i,(-1)**i,1000000,now,'Isolated fixture')
 c.execute("INSERT OR REPLACE INTO providers VALUES('Fixture','ok','No network',?)",(now,))
# Isolated managed fixture, no live data and no model calls.
s.ARENA.start_population();s.ARENA.sync_market()
with s.ARENA.db() as c:
 bot=c.execute('SELECT bot FROM demo_wallets LIMIT 1').fetchone()[0]
 c.execute('INSERT INTO demo_fills(id,order_id,bot,symbol,side,ts,qty,native_price,currency,fx_usd,usd_total,fee,realized,book_ts,book_hash,evidence) VALUES(77,700,?,?,?,?,1,100,?,1,100,0,0,?,?,?)',(bot,'QA184/USD','buy',now-350,'USD',now-350,'synthetic-fixture',json.dumps({'source':'Synthetic isolated fill evidence; never live'})))
class Handler(s.Handler):
 def do_GET(self):
  if self.path.startswith('/api/candles'):
   return self.send([dict(ts=now-(20-i)*300,open=100+i,high=102+i,low=99+i,close=101+i,volume=100) for i in range(20)])
  return super().do_GET()
http=s.ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=http.serve_forever,daemon=True).start()
from playwright.async_api import async_playwright
async def main():
 checks=[];errors=[]
 def check(name,ok):
  checks.append({'name':name,'pass':bool(ok)});print(name,ok,flush=True)
  if not ok:raise AssertionError(name)
 async with async_playwright() as p:
  browser=await p.chromium.launch(headless=True,args=['--no-sandbox','--use-angle=swiftshader','--enable-unsafe-swiftshader'])
  page=await browser.new_page(viewport=dict(width=1440,height=1000),reduced_motion='reduce');page.on('pageerror',lambda e:(errors.append(str(e)),print('JS ERROR',e,flush=True)))
  await page.goto(f'http://127.0.0.1:{http.server_port}',wait_until='networkidle');print('Page loaded',flush=True);await page.wait_for_selector('#deck-terminal')
  await page.wait_for_selector('[data-dt-scanner] .dt-market');await page.wait_for_selector('[data-dt-candle-values] tr',state='attached')
  check('Terminal renders complete scanner', '185' in await page.locator('[data-dt-count]').inner_text())
  await page.locator('[data-dt=scanner-next]').click();await page.locator('[data-dt=scanner-next]').click()
  check('Last scanner result reachable', 'QA184' in await page.locator('[data-dt-scanner]').inner_text())
  await page.locator('[data-dt=scanner-previous]').click()
  await page.locator('#dt-search').fill('QA184');check('Full scanner search',await page.locator('[data-dt-scanner] .dt-market').count()==1)
  await page.locator('[data-dt-scanner] .dt-market').click();await page.wait_for_function("document.querySelector('[data-dt-symbol]').textContent==='QA184/USD'")
  check('Accessible candle data',await page.locator('[data-dt-candle-values] tr').count()==20)
  await page.locator('[data-dt-chart-events]').locator('xpath=..').locator('summary').click()
  await page.locator('[data-dt-chart-events] [data-dt-fill="77"]').click();await page.wait_for_selector('#dt-dialog[open]')
  check('Recorded marker resolves exact persisted evidence','Synthetic isolated fill evidence' in await page.locator('#dt-dialog').inner_text() and '77' in await page.locator('#dt-dialog').inner_text())
  await page.locator('[data-dt=close-dialog]').click()
  await page.locator('#dt-question').fill('Keep this unsent private draft')
  await page.locator('[data-dt-rule=entries] summary').click()
  await page.evaluate("window.ruleBefore=document.querySelector('[data-dt-rule=entries]');window.questionBefore=document.querySelector('#dt-question');window.scannerBefore=document.querySelector('[data-dt-scanner] .dt-market');window.chartBefore=document.querySelector('#dt-chart canvas')")
  await page.locator('[data-dt=refresh]').click();await page.wait_for_timeout(2600)
  check('Terminal input identity preserved',await page.evaluate("questionBefore===document.querySelector('#dt-question')"))
  check('Open gate preserved',await page.locator('[data-dt-rule=entries]').get_attribute('open') is not None)
  check('Research draft preserved',await page.locator('#dt-question').input_value()=='Keep this unsent private draft')
  check('Scanner selection node preserved',await page.evaluate("scannerBefore===document.querySelector('[data-dt-scanner] .dt-market')"))
  check('Chart canvas preserved',await page.evaluate("chartBefore===document.querySelector('#dt-chart canvas')"))
  check('Gate provenance visible','Snapshot time' in await page.locator('[data-dt-rule=entries]').text_content())
  # State route reconciliation reuses view and field identities.
  await page.evaluate("window.rootBefore=document.querySelector('#view');window.refresh()")
  await page.wait_for_timeout(800)
  check('State refresh retains terminal',await page.locator('#deck-terminal').count()==1)
  for route in ['markets','portfolio','news','signals','research','bots','journal','controls','guide','overview']:
   await page.evaluate('(r)=>location.hash=r',route);await page.wait_for_timeout(300)
   check('Route '+route, await page.locator('#view').inner_text()!='')
  for width in [320,390,768,1440]:
   await page.set_viewport_size(dict(width=width,height=1000));await page.wait_for_timeout(150)
   over=await page.evaluate('document.documentElement.scrollWidth>innerWidth+1')
   if over:print('OVERFLOW',await page.evaluate("[...document.querySelectorAll('body *')].filter(e=>e.getBoundingClientRect().right>innerWidth+1).map(e=>[e.tagName,e.id,e.className,Math.round(e.getBoundingClientRect().right)]).slice(0,20)"))
   check('Private layout width '+str(width),not over)
  await page.set_viewport_size(dict(width=390,height=1000))
  await page.evaluate("window.savedTextSizes=[...document.querySelectorAll('body *')].map(e=>[e,e.style.fontSize,parseFloat(getComputedStyle(e).fontSize)]);for(const [e,old,size] of savedTextSizes)e.style.fontSize=(size*2)+'px'")
  check('Private terminal at 200% text',await page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
  await page.evaluate("for(const [e,old] of savedTextSizes)e.style.fontSize=old")
  await page.set_viewport_size(dict(width=1440,height=1000))
  await page.evaluate("location.hash='controls'");await page.wait_for_timeout(200)
  await page.evaluate("render();render();render();window.confirm=()=>true")
  submissions=[]
  async def settings_fixture(r):
   submissions.append(r.request.post_data);await r.fulfill(json={'ok':True})
  await page.route('**/api/settings',settings_fixture)
  await page.locator('#limits-form button[type=submit]').click();await page.wait_for_timeout(300)
  check('Stable rendering submits one settings request',len(submissions)==1)
  # Auth and analysis UI use mocked HTTP records; nothing reaches an owner session.
  async def admin_fixture(r):
   path=r.request.url.split('/api/admin/')[1]
   if path=='unlock':result={'session':'fixture-only-token'}
   elif path=='status':result={'connected':True,'session':{'status':'idle','updated':now,'messages':[{'role':'assistant','text':'Synthetic saved reply'}]},'commands':[{'id':71,'body':'Synthetic uncertain request','state':'uncertain','error':'Synthetic timeout'}]}
   else:result={'ok':True}
   await r.fulfill(json=result)
  await page.route('**/api/admin/**',admin_fixture)
  await page.locator('[data-decklab-admin]').click();await page.locator('#admin-unlock input').fill('fixture-passkey-123456')
  await page.locator('#admin-unlock button').click();await page.wait_for_selector('[data-admin-id="71"]',state='attached')
  check('Admin uncertain delivery remains explicit','previous delivery may have succeeded' in (await page.locator('#admin-queue').text_content()).lower())
  await page.locator('#admin-command-text').fill('Unsent command fixture')
  await page.locator('#admin-queue').locator('xpath=..').locator('summary').click()
  await page.locator('[data-admin-id="71"]').first.focus()
  await page.evaluate("window.commandBefore=document.querySelector('#admin-command-text');window.queueBefore=document.querySelector('[data-admin-id=\"71\"]')")
  await page.wait_for_timeout(2300)
  check('Admin queue focus and draft survive refresh',await page.evaluate("commandBefore===document.querySelector('#admin-command-text')&&queueBefore===document.querySelector('[data-admin-id=\"71\"]')") and await page.locator('#admin-command-text').input_value()=='Unsent command fixture')
  await page.locator('[data-admin-close]').click()
  # A complete returned analysis is readable without opening raw JSON.
  async def analysis_fixture(r):
   result={'id':1,'tool':'analyze','state':'completed','symbols':['QA'],'created':now,'finished':now,'result':{'steps':{'entry':{'state':'completed','data':{'status':'waiting','reason':'No completed breakout'}},'budget':{'state':'skipped','reason':'Entry is waiting; no affordable plan','data':{'status':'unaffordable','shares':0}},'replay':{'state':'skipped','reason':'No triggered entry'}}}}
   await r.fulfill(json=result if '?id=' in r.request.url else {'notice':'Isolated browser fixture','commit':'fixture','jobs':[result]})
  await page.route('**/api/day-trader*',analysis_fixture)
  await page.goto(f'http://127.0.0.1:{http.server_port}/day-trader',wait_until='networkidle');await page.wait_for_selector('#results details')
  check('Day Trader waiting and skipped cards', 'completed' in await page.locator('#results').inner_text() and 'Entry is waiting' in await page.locator('#results').text_content())
  await page.locator('#results>details').nth(1).locator('summary').first.click()
  check('Day Trader unaffordable plan readable','unaffordable' in await page.locator('#results').inner_text())
  await page.locator('#symbols').fill('Unsent ticker draft');await page.evaluate("window.resultBefore=document.querySelector('#results>details')")
  # GET refresh on demand using visibility event avoids a 15s wait.
  await page.evaluate("document.dispatchEvent(new Event('visibilitychange'))");await page.wait_for_timeout(300)
  check('Day Trader result identity and form draft retained',await page.evaluate("resultBefore===document.querySelector('#results>details')") and await page.locator('#symbols').input_value()=='Unsent ticker draft')
  for width in [320,390,768,1440]:
   await page.set_viewport_size(dict(width=width,height=1000));check('Day Trader width '+str(width),await page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
  check('No JS errors',not errors)
  await page.screenshot(path=str(ROOT/'docs/images/phase2-day-trader-fixture.png'),full_page=False)
  await browser.close()
 (ROOT/'docs/verification/phase2-terminal-browser.json').write_text(json.dumps(dict(scope='Synthetic disposable full terminal fixture; no model or live store access',checks=checks,errors=errors),indent=2))
try:asyncio.run(main())
finally:http.shutdown();TMP.cleanup()
