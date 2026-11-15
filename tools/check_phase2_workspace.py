"""Optional Playwright journeys. Temporary observations only; no network feed workers.
Run with an interpreter containing playwright; report path is optional.
"""
import asyncio,json,os,sys,tempfile,threading,time
from pathlib import Path
from urllib.parse import parse_qs,urlsplit
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
TMP=tempfile.TemporaryDirectory(prefix='decklab-phase2-')
os.environ['MARKET_DECK_DATA']=TMP.name
import observer_server as m
m.init()
now=time.time()
with m.core.db() as c:
    for symbol,base in [('BTC/USD',100),('ETH/USD',50)]:
        c.execute('INSERT OR IGNORE INTO assets VALUES(?,?,?,?,?,?,?,1)',(symbol,symbol,'crypto','Global','USD','Fixture',symbol))
        m.core.store(c,symbol,base,1,1000,now,'Isolated browser fixture')
        for i in range(20):
            if i!=10:c.execute('INSERT OR REPLACE INTO history VALUES(?,?,?)',(symbol,now-1200+i*60,base+i))
http=m.core.ThreadingHTTPServer(('127.0.0.1',0),m.Handler)
threading.Thread(target=http.serve_forever,daemon=True).start()
async def main():
    checks=[];errors=[]
    def check(name,passed):
        checks.append({'name':name,'pass':bool(passed)})
        if not passed:raise AssertionError(name)
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True,args=['--no-sandbox','--use-angle=swiftshader','--enable-unsafe-swiftshader'])
        page=await browser.new_page(viewport={'width':1440,'height':1000},reduced_motion='reduce')
        page.on('pageerror',lambda e:errors.append(str(e)))
        await page.goto('http://127.0.0.1:'+str(http.server_port),wait_until='networkidle')
        await page.wait_for_function('document.querySelector("#history-rows").textContent.includes("100")')
        check('Real saved samples exposed as table',await page.locator('#history-rows tr').count()>=20)
        check('Read-only statuses visible','AI off · execution off' in await page.locator('#connection').inner_text())
        await page.locator('#chart-type').select_option('area')
        check('Area chart uses saved samples',await page.locator('#chart path').count()==2)
        check('Chart x axis reflects elapsed time across sample gaps',await page.evaluate('''() => { const d=document.querySelector('#chart path[fill="none"]').getAttribute('d');const xs=d.match(/[ML][0-9.]+/g).map(s=>Number(s.slice(1))); return Math.abs((xs[10]-xs[9])-2*(xs[1]-xs[0]))<.1; }'''))
        await page.locator('#sample-cursor').focus();await page.keyboard.press('Home')
        first=await page.locator('#sample-value').inner_text();await page.keyboard.press('ArrowRight')
        check('Keyboard sample inspector',first!=await page.locator('#sample-value').inner_text() and '101' in await page.locator('#sample-value').inner_text())
        await page.locator('#price-table summary').click()
        await page.locator('[data-pin="BTC/USD"]').focus()
        await page.evaluate('window.focusedBefore=document.activeElement; window.rowBefore=[...document.querySelectorAll("#quotes tr")].find(r=>r.dataset.key==="BTC/USD")')
        await page.evaluate('document.querySelector("#refresh").click()')
        await page.wait_for_function('document.querySelector("#refresh").getAttribute("aria-busy")==="false"')
        check('Refresh preserves exact focused button',await page.evaluate('document.activeElement===window.focusedBefore'))
        check('Refresh reuses keyed row',await page.evaluate('[...document.querySelectorAll("#quotes tr")].find(r=>r.dataset.key==="BTC/USD")===window.rowBefore'))
        check('Refresh preserves chart type and evidence disclosure',await page.locator('#chart-type').input_value()=='area' and await page.locator('#price-table').get_attribute('open') is not None)
        # Slow old symbol response must not overwrite newer selection.
        async def slow_history(route):
            if 'BTC' in route.request.url:await asyncio.sleep(.6)
            try:await route.continue_()
            except Exception:pass
        await page.route('**/api/observer/history?*',slow_history)
        await page.locator('#quotes [data-symbol="BTC/USD"]').click();await page.locator('#quotes [data-symbol="ETH/USD"]').click()
        await page.wait_for_timeout(800)
        check('Late symbol response cannot repaint selected evidence',await page.locator('#chart-symbol').inner_text()=='ETH/USD' and 'ETH/USD' in await page.locator('#price-caption').inner_text() and '50' in await page.locator('#history-rows').inner_text())
        await page.unroute('**/api/observer/history?*',slow_history)
        # Input invalidates old requests before debounce; newest search wins.
        async def slow_state(route):
            params=parse_qs(urlsplit(route.request.url).query)
            if params.get('q')==['AAPL']:await asyncio.sleep(.7)
            try:await route.continue_()
            except Exception:pass
        await page.route('**/api/observer/state?*',slow_state)
        await page.locator('#search').fill('AAPL');await page.wait_for_timeout(300);await page.locator('#search').fill('MSFT');await page.wait_for_timeout(1100)
        check('Late search response rejected',await page.locator('#quotes tr').count()==1 and 'MSFT' in await page.locator('#quotes').inner_text())
        await page.unroute('**/api/observer/state?*',slow_state)
        await page.locator('[data-pin="MSFT"]').click();await page.locator('#pins-only').click();await page.wait_for_timeout(300)
        check('Watchlist survives keyed rendering','MSFT' in await page.locator('#quotes').inner_text() and await page.locator('[data-pin="MSFT"]').get_attribute('aria-pressed')=='true')
        await page.locator('#search').fill('NO-MATCH-XYZ');await page.wait_for_timeout(500)
        check('Empty results explicit','No pinned instruments match' in await page.locator('#quotes').inner_text())
        await page.locator('#search').fill('');await page.locator('#pins-only').click();await page.wait_for_timeout(500)
        # Failed refresh retains previous data and exposes recovery.
        await page.route('**/api/observer/state?*',lambda route:route.fulfill(status=503,body='{}'))
        count=await page.locator('#quotes tr').count();await page.locator('#refresh').click();await page.wait_for_timeout(300)
        check('Failed refresh keeps observations and offers retry',count==await page.locator('#quotes tr').count() and 'retry' in await page.locator('#connection').inner_text())
        await page.unroute('**/api/observer/state?*');await page.locator('#refresh').click();await page.wait_for_timeout(300)
        await page.locator('#help').click();check('Keyboard help dialog opens',await page.locator('#keyboard-help').is_visible());await page.keyboard.press('Escape')
        check('Dialog closes with keyboard',not await page.locator('#keyboard-help').is_visible())
        # Complete workspace preferences, deep links and semantic accessibility.
        await page.locator('#search').fill('');await page.wait_for_timeout(600)
        await page.locator('#workspace-preferences summary').click()
        await page.locator('#workspace-width').focus();await page.keyboard.press('End')
        check('Layout keyboard resize bounded',await page.locator('#workspace-width').input_value()=='65')
        await page.locator('#workspace-enhanced').uncheck();check('Classic composition rollback available',not await page.locator('#breadth').is_visible())
        await page.locator('#workspace-enhanced').check();check('Phase 2 composition restores',await page.locator('#breadth').is_visible())
        await page.locator('#workspace-density').check()
        await page.reload(wait_until='networkidle')
        check('Layout persists across reload',await page.locator('#workspace-width').input_value()=='65' and await page.locator('#workspace-density').is_checked())
        await page.locator('#workspace-preferences summary').click();await page.locator('#workspace-reset').click()
        check('Layout reset works',await page.locator('#workspace-width').input_value()=='58' and not await page.locator('#workspace-density').is_checked())
        await page.locator('#command-open').click();await page.locator('#command-query').fill('BTC/USD');await page.locator('#command-form button').first.click();await page.wait_for_timeout(600)
        check('Command search updates full catalog',await page.locator('#quotes .instrument').count()==1 and 'BTC/USD' in await page.locator('#quotes').inner_text())
        await page.locator('#quotes .instrument').click();await page.locator('#chart-type').select_option('area');await page.locator('#chart-range').select_option('3600')
        await page.reload(wait_until='networkidle')
        check('Shared URL restores symbol and chart settings','symbol=BTC%2FUSD' in page.url and await page.locator('#chart-type').input_value()=='area' and await page.locator('#chart-range').input_value()=='3600')
        check('Breadth reports full coverage and windows',await page.locator('#breadth-cells .breadth-cell').count()>0 and 'missing / stale' in await page.locator('#breadth-cells').inner_text())
        await page.locator('.workspace-nav a[href="#breadth"]').first.click()
        check('Workspace navigation current state',await page.locator('.workspace-nav a[href="#breadth"]').first.get_attribute('aria-current')=='location')
        session=await page.context.new_cdp_session(page);tree=await session.send('Accessibility.getFullAXTree')
        names={n.get('name',{}).get('value','') for n in tree['nodes'] if not n.get('ignored')}
        check('Accessibility tree exposes navigation and chart controls','Workspace' in names and 'Inspect a recorded sample' in names and 'Accessible price data' in names)
        # Measured end-to-next-frame local interaction; fixture, this runner only.
        timings=await page.evaluate('''async()=>{const times=[];for(let i=0;i<30;i++){const t=performance.now();const el=document.querySelector('#chart-type');el.value=i%2?'line':'area';el.dispatchEvent(new Event('change'));await new Promise(requestAnimationFrame);times.push(performance.now()-t);}return times.sort((a,b)=>a-b)}''')
        p95=timings[28];check('Cached chart p95 below 100ms on this runner',p95<100)
        colors=await page.evaluate('''()=>{const s=getComputedStyle(document.documentElement);return Object.fromEntries(['bg','panel','text','muted','good','bad','attention','focus'].map(k=>[k,s.getPropertyValue('--workspace-'+k).trim()]));}''')
        def luminance(h):
            v=[int(h[i:i+2],16)/255 for i in (1,3,5)];v=[x/12.92 if x<=.04045 else ((x+.055)/1.055)**2.4 for x in v];return sum(a*b for a,b in zip(v,[.2126,.7152,.0722]))
        contrast={}
        for fg in ['text','muted','good','bad','attention','focus']:
            for bg in ['bg','panel']:
                a,b=sorted([luminance(colors[fg]),luminance(colors[bg])]);contrast[fg+'/'+bg]=(b+.05)/(a+.05)
        check('Semantic token text contrast at least 4.5:1',min(contrast.values())>=4.5)
        check('Observation evidence remains separate from private capabilities','private, unavailable here' in await page.locator('.workspace-health').inner_text())
        before=await page.locator('#quotes').text_content()
        await page.evaluate("Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange'))")
        calls=[];page.on('request',lambda r:calls.append(r.url) if '/api/observer/' in r.url else None)
        await page.evaluate("document.querySelector('#refresh').click()");await page.wait_for_timeout(200)
        check('Hidden tab suspends routine reads',not calls and before==await page.locator('#quotes').text_content())
        await page.evaluate("Object.defineProperty(document,'hidden',{configurable:true,value:false});document.dispatchEvent(new Event('visibilitychange'))")
        await page.wait_for_timeout(400);check('Visible tab resumes reads',bool(calls))
        for width in [320,390,768,1440]:
            await page.set_viewport_size({'width':width,'height':1000});await page.wait_for_timeout(100)
            check('No page overflow '+str(width),await page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
        await page.set_viewport_size({'width':390,'height':1000})
        await page.evaluate('''() => { const sizes=[...document.querySelectorAll('body *')].map(e=>[e,parseFloat(getComputedStyle(e).fontSize)]); for(const [e,size] of sizes) e.style.fontSize=(size*2)+'px'; }''')
        check('200% computed text at 390 does not overflow page',await page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
        check('Reduced motion scene remains off',await page.locator('#motion').get_attribute('aria-pressed')=='false')
        check('No browser JavaScript errors',not errors)
        await browser.close()
    report={'scope':'Phase 2 complete public workspace; isolated synthetic fixture, not market evidence','checks':checks,'errors':errors,'device':'Headless Chromium / Linux software WebGL; viewport emulation, not physical handset','performance':{'p95_ms':p95,'samples_ms':timings,'runner':'Headless Chromium, Linux software rendering, 1440x1000, reduced motion; local fixture'},'contrast':contrast,'limits':'Automated AX tree and semantic token contrast; manual assistive technology and physical handset acceptance are not claimed.'}
    if len(sys.argv)>1:Path(sys.argv[1]).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
try:asyncio.run(main())
finally:http.shutdown();http.server_close();TMP.cleanup()
