/* Dashboard UI fixture: reads repository trace, never contacts live Ditto. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const { chromium } = require('playwright');

const ui = path.resolve(__dirname, '../ui');
const out = path.resolve(process.env.TYNYS_DASHBOARD_ARTIFACT_DIR || '.dashboard-test-output');
const original = JSON.parse(fs.readFileSync(path.join(ui, 'trace.json'), 'utf8'))[0];
const fullStats = {season:'весь год (4 × 14 сут)',mw_mean:136,mw_median:143.1,mw_p10:69.8,mw_p90:185.6,
  h_mean:4.5,h_median:1,h_p10:.6,h_p90:1.9};
let stats = [structuredClone(fullStats)], offline = false;
const twins = structuredClone(original), writes = [], errors = [], checks = [];
Object.assign(twins.site, {sim_hour:12,elapsed_hours:3,sim_time:'2026-10-21 12:00',co2_t:200,co2_adj_t:180,co2_per_t_cu:1.8});
Object.assign(twins['shadow-v0'], {co2_t:100,co2_adj_t:110,co2_per_t_cu:1.1});
Object.assign(twins['shadow-v1'], {co2_t:100,co2_adj_t:90,co2_per_t_cu:.9});
const sizing = [{wind_mw:0,pv_mwp:0,variant:'V0',co2_kt:300,co2_adj_kt:310},
  ...['V0','V2fixed','V2','V2green'].map((variant,i)=>({wind_mw:300,pv_mwp:250,variant,co2_kt:200-20*i,co2_adj_kt:190-20*i}))]
  .map(row=>({...row,cu_adj_t:100000,renew_share_pct:40,curtail_mwh:1000}));
Object.assign(twins.scenario, {goal:'copper',events:'[]',rev:4});
Object.assign(twins.coordinator, {goal:'copper'});
Object.assign(twins.plant, {decision_source:'coordinator'});
const things = () => Object.entries(twins).map(([id, values]) => ({thingId:'kz.tynys:'+id,
  features:Object.fromEntries(Object.entries(values).map(([key,value]) => [key,{properties:{value}}]))}));

async function main() {
  fs.mkdirSync(out,{recursive:true});
  const server = http.createServer((req,res) => {
    const file = path.resolve(ui, '.' + new URL(req.url,'http://localhost').pathname);
    if (!file.startsWith(ui+path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
      res.writeHead(404); res.end(); return;
    }
    const type = {'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json'}[path.extname(file)];
    res.writeHead(200,{'Content-Type':(type||'application/octet-stream')+'; charset=utf-8'});
    fs.createReadStream(file).pipe(res);
  });
  await new Promise(resolve => server.listen(0,'127.0.0.1',resolve));
  let browser;
  try {
    browser = await chromium.launch({headless:true,
      ...(process.env.CHROME_PATH ? {executablePath:process.env.CHROME_PATH} : {})});
    const page = await browser.newPage({viewport:{width:1440,height:1000}});
    page.on('pageerror',error => errors.push(String(error)));
    await page.route('**/ditto/api/2/**',async route => {
      if (offline) return route.fulfill({status:503,body:'fixture offline'});
      const request = route.request(), url = new URL(request.url());
      if (request.method()==='PUT') {
        assert.ok(url.pathname.endsWith('/kz.tynys:scenario/features'));
        const body = request.postDataJSON(); writes.push(body);
        for (const [key,value] of Object.entries(body)) twins.scenario[key]=value.properties.value;
        return route.fulfill({status:204,body:''});
      }
      const body = url.pathname.endsWith('/flex_stats') ? stats : url.pathname.endsWith('/sizing') ? sizing
        : url.pathname.endsWith('kz.tynys:energy/attributes') ? {sizing}
        : url.pathname.endsWith('kz.tynys:substation/attributes') ? {flex_stats:stats} : things();
      return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(body)});
    });
    await page.goto(`http://127.0.0.1:${server.address().port}/dashboard.html`);
    await page.waitForFunction(() => document.getElementById('comparison-emissions').dataset.direction==='higher');
    assert.match(await page.locator('#comparison-period').innerText(), /3 завершённых модельных ч/);
    assert.match(await page.locator('#comparison-goal').innerText(), /Больше меди/);
    assert.equal(await page.locator('#g-copper').getAttribute('aria-pressed'),'true');
    assert.deepEqual(await page.locator('#kt tr').filter({hasText:/^CO₂ из сети, т/}).locator('td').allTextContents(),
      ['CO₂ из сети, т','100','100','200']);
    assert.deepEqual(await page.locator('#kt tr').filter({hasText:/^CO₂ с учётом запасов, т/}).locator('td').allTextContents(),
      ['CO₂ с учётом запасов, т','110','90','180']);
    assert.deepEqual(await page.locator('#kt tr').filter({hasText:/^CO₂ на т меди/}).locator('td').allTextContents(),
      ['CO₂ на т меди (с учётом запасов)','1,10','0,90','1,80']);
    assert.match(await page.locator('#comparison-emissions').innerText(),/CO₂ из сети/);
    assert.equal(writes.length,0);
    checks.push('Actual CO2, period and backend objective remain visible; page load performs no writes');

    await page.waitForFunction(()=>document.querySelectorAll('#sizing tr').length>1);
    assert.deepEqual((await page.locator('#sizing tr').filter({hasText:/^CO₂ из сети/}).locator('td').allTextContents()).slice(1),
      ['300','200','180','160','140']);
    assert.deepEqual((await page.locator('#sizing tr').filter({hasText:/^CO₂ с учётом запасов/}).locator('td').allTextContents()).slice(1),
      ['310','190','170','150','130']);
    delete sizing[3].co2_adj_kt;
    await page.evaluate(()=>loadSizing());
    assert.equal((await page.locator('#sizing tr').filter({hasText:/^CO₂ с учётом запасов/}).locator('td').allTextContents())[4],'—');
    assert.equal((await page.locator('#sizing tr').filter({hasText:/^CO₂ на т меди/}).locator('td').allTextContents())[4],'—');
    assert.equal((await page.locator('#sizing tr').filter({hasText:/^CO₂ из сети/}).locator('td').allTextContents())[4],'160');
    sizing[3].co2_adj_kt=150; await page.evaluate(()=>loadSizing());
    checks.push('Inventory-adjusted CO2 remains separate from gross emissions; absent adjusted sizing is never replaced with gross');

    let text = await page.locator('#flexstat').innerText();
    assert.match(text,/Мощность: медиана 143,1 МВт/);
    assert.match(text,/Длительность: медиана 1,0 ч/);
    assert.match(text,/среднее длительности: 4,5 ч/);
    assert.match(text,/рассчитаны отдельно/);
    checks.push('Separate marginal medians and labelled means, without a paired reserve guarantee');

    stats=[{...fullStats}]; delete stats[0].h_median; delete stats[0].mw_median;
    await page.evaluate(() => loadFlex()); text=await page.locator('#flexstat').innerText();
    assert.match(text,/Мощность: медиана не передана/);
    assert.match(text,/Длительность: медиана не передана/);
    assert.match(text,/среднее длительности: 4,5 ч/);
    assert.doesNotMatch(text,/медиана (4,5|136,0)/);
    checks.push('Old Ditto statistics never relabel means as medians');

    stats=[{...fullStats,mw_median:'',h_median:null,mw_mean:true,h_mean:'Infinity',h_p10:-1}];
    await page.evaluate(() => loadFlex()); text=await page.locator('#flexstat').innerText();
    assert.match(text,/медиана не передана/); assert.match(text,/не передан или некорректен/);
    assert.doesNotMatch(text,/NaN|Infinity|медиана 0,0/);
    stats=[{...fullStats,mw_median:0,h_median:0}];
    await page.evaluate(() => loadFlex()); text=await page.locator('#flexstat').innerText();
    assert.match(text,/Мощность: медиана 0,0 МВт/); assert.match(text,/Длительность: медиана 0,0 ч/);
    stats=[]; await page.evaluate(() => loadFlex());
    assert.match(await page.locator('#flexstat').innerText(),/Статистика резерва не передана/);
    checks.push('Missing/invalid values stay explicit, while actual numeric zero remains valid');

    twins.scenario.goal='green'; twins.coordinator.goal='green';
    await page.evaluate(() => poll());
    assert.equal(await page.locator('#g-green').getAttribute('aria-pressed'),'true');
    assert.match(await page.locator('#g-note').innerText(),/не гарантировано/);
    await page.locator('#btns button').first().click();
    await page.waitForFunction(() => document.querySelectorAll('#events button').length===1);
    assert.equal(writes.length,1); assert.equal(writes[0].goal.properties.value,'green');
    assert.equal(writes[0].rev.properties.value,5);
    checks.push('Scenario action preserves the backend green objective');

    delete twins.scenario.goal; delete twins.coordinator.goal;
    await page.evaluate(() => poll());
    assert.equal(await page.locator('#g-green').getAttribute('aria-pressed'),'false');
    assert.equal(await page.locator('#g-copper').getAttribute('aria-pressed'),'false');
    await page.locator('#btns button').first().click();
    await page.waitForTimeout(150); assert.equal(writes.length,1);
    checks.push('Missing backend objective is not silently replaced with copper');

    twins.scenario.goal='copper'; twins.coordinator.goal='copper'; twins.plant.decision_source='fallback_v1';
    delete twins.site.co2_t; delete twins.site.co2_adj_t;
    await page.evaluate(() => poll());
    assert.match(await page.locator('#comparison-goal').innerText(),/резервному правилу V1/);
    assert.match(await page.locator('#comparison-emissions').innerText(),/ожидает данных/);
    assert.equal((await page.locator('#kt tr').filter({hasText:/^CO₂ из сети, т/}).locator('td').allTextContents())[3],'—');
    assert.equal((await page.locator('#kt tr').filter({hasText:/^CO₂ на т меди/}).locator('td').allTextContents())[3],'—');
    offline=true; await page.evaluate(async () => { await poll(); await loadFlex(); });
    assert.equal(await page.locator('#connection').getAttribute('data-state'),'offline');
    assert.match(await page.locator('#flexstat').innerText(),/Статистика резерва недоступна/);
    checks.push('Fallback, absent CO2 and offline statistics are clearly distinguished');

    offline=false; stats=[structuredClone(fullStats)]; twins.site.co2_t=200; twins.site.co2_adj_t=180; twins.plant.decision_source='coordinator';
    await page.evaluate(async () => { await poll(); await loadFlex(); });
    assert.equal(await page.locator('nav a[aria-current=page]').getAttribute('href'),'./dashboard.html');
    assert.equal(await page.locator('nav a[href="./"]').count(),1);
    await page.screenshot({path:path.join(out,'dashboard-desktop.png'),fullPage:true});
    await page.setViewportSize({width:390,height:844});
    await page.waitForTimeout(150);
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth+1),'Dashboard overflows mobile viewport');
    await page.screenshot({path:path.join(out,'dashboard-mobile.png'),fullPage:true});
    assert.deepEqual(errors,[]);
    checks.push('Dashboard route, Unity navigation and mobile layout work without JS errors');
    fs.writeFileSync(path.join(out,'report.json'),JSON.stringify({status:'PASS',transport:'local HTTP + intercepted Ditto fixture; no live writes',checks,errors},null,2));
    console.log('Dashboard fixture PASS:',checks.length,'checks');
  } finally {
    if (browser) await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
}
main().catch(error => {console.error(error);process.exitCode=1;});
