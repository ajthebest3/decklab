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
        for i in range(20):c.execute('INSERT OR REPLACE INTO history VALUES(?,?,?)',(symbol,now-1200+i*60,base+i))
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
        for width in [320,390,768,1440]:
            await page.set_viewport_size({'width':width,'height':1000});await page.wait_for_timeout(100)
            check('No page overflow '+str(width),await page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
        await page.set_viewport_size({'width':390,'height':1000})
        await page.evaluate('''() => { const sizes=[...document.querySelectorAll('body *')].map(e=>[e,parseFloat(getComputedStyle(e).fontSize)]); for(const [e,size] of sizes) e.style.fontSize=(size*2)+'px'; }''')
        check('200% computed text at 390 does not overflow page',await page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
        check('Reduced motion scene remains off',await page.locator('#motion').get_attribute('aria-pressed')=='false')
        check('No browser JavaScript errors',not errors)
        await browser.close()
    report={'scope':'Phase 2 public observer first slice; isolated synthetic test fixture, not market evidence','checks':checks,'errors':errors,'device':'Headless Chromium / Linux software WebGL; viewport emulation, not physical handset','limits':'No full screen-reader or manual contrast audit; no interaction latency budget claim.'}
    if len(sys.argv)>1:Path(sys.argv[1]).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
try:asyncio.run(main())
finally:http.shutdown();http.server_close();TMP.cleanup()
