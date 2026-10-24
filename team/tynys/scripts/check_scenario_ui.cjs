// Configured 3D events with real model and local Ditto transport fixture.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||undefined,
    args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
  try{
    const page=await browser.newPage({viewport:{width:1440,height:1050}});
    const errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.goto((process.argv[2]||'http://127.0.0.1:18098')+'/3d.html');
    await page.waitForFunction(()=>window.__tynys?.source==='live');
    await page.locator('#skip').click();
    await page.locator('#scenario-line').selectOption('1');
    await page.locator('#scenario-duration').fill('6');
    await page.locator('[data-scenario="line_trip"]').click();
    await page.waitForFunction(()=>window.__tynys.data['line-1'].available===false);
    const ev=await page.evaluate(()=>window.__tynys.events.find(e=>e.kind==='line_trip'&&e.line===1));
    assert.equal(ev.dur,6);
    assert.match(await page.locator('#scenario-list').innerText(),/Авария линии 1/);
    const overlaps=await page.evaluate(()=>{
      const a=document.querySelector('#scenario-launch').getBoundingClientRect();
      const b=document.querySelector('#scenario-banner').getBoundingClientRect();
      return a.left<b.right&&a.right>b.left&&a.top<b.bottom&&a.bottom>b.top;
    });
    assert.equal(overlaps,false);
    assert.equal(await page.locator('#l-plan').isVisible(),false,'inactive plan label must remain hidden after rendering');
    await page.locator('.scenario-cancel[data-id="'+ev.id+'"]').click();
    await page.waitForFunction(()=>!window.__tynys.events.some(e=>e.kind==='line_trip'&&e.line===1));
    await page.locator('#scenario-tariff-pct').fill('0');
    await page.locator('[data-scenario="tariff_change"]').click();
    await page.waitForFunction(()=>window.__tynys.events.some(e=>e.kind==='tariff_change'));
    const tariff=await page.evaluate(()=>window.__tynys.events.find(e=>e.kind==='tariff_change'));
    assert.equal(tariff.change_pct,0,'zero must not fall back to a nonzero tariff change');
    await page.locator('.scenario-cancel[data-id="'+tariff.id+'"]').click();
    await page.waitForFunction(()=>!window.__tynys.events.some(e=>e.kind==='tariff_change'));
    assert.deepEqual(errors,[]);
    if(process.argv[3])await page.screenshot({path:process.argv[3]});
    console.log(JSON.stringify({configuredLine:1,duration:6,zeroTariff:'PASS',panels:'no overlap',pageErrors:errors}));
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
