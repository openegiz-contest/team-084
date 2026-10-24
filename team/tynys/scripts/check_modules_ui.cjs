// Integration against serve_mine_fixture: actual physics/futures, mocked transport.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const url=process.argv[2]||'http://127.0.0.1:18099';
const output=process.argv[3];
(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||undefined,
    args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
  try{
    const page=await browser.newPage({viewport:{width:1440,height:1050}});
    const errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.goto(url+'/dashboard.html');
    await page.waitForFunction(()=>/эквивалент \d+ МВт ВЭС/.test(document.querySelector('#page-title').textContent));
    const headline = await page.locator('#page-title').innerText();
    if (/архив/.test(headline)) throw new Error('Headline must come from the current sizing, not the archive: '+headline);
    if (!/Медь [−+-]?\d/.test(await page.locator('#equivalent-note').innerText())) throw new Error('Copper change must be shown next to the wind equivalent');
    await page.waitForFunction(()=>document.querySelector('#geo-active').textContent.includes('GM-'));
    const foreign=await page.evaluate(async()=>{
      const r=await fetch('ditto/api/2/things/kz.tynys:scenario/features');
      return JSON.parse((await r.json()).events.properties.value);
    });
    await page.locator('#demo-start').click();
    await page.waitForFunction(()=>document.querySelector('#demo-message')?.textContent.includes('Штиль действует'));
    if(output)await page.screenshot({path:output+'-dashboard.png',fullPage:true});
    // Follow the default single-click journey, including its real timers.
    await page.waitForURL('**/3d.html',{timeout:65000});
    await page.waitForFunction(()=>window.__tynys?.source==='live'&&window.__tynys.scenarioVisuals.windLull);
    await page.waitForSelector('#geology-legend');
    const before=await page.evaluate(()=>window.__tynys.scenarioVisuals.windAngles);
    await page.waitForTimeout(1800);
    const after=await page.evaluate(()=>window.__tynys.scenarioVisuals.windAngles);
    assert.deepEqual(after,before,'lull rotors must actually stop');
    assert.match(await page.locator('#geology-active').innerText(),/GM-/);
    const colored=await page.evaluate(()=>{
      const colors=[];window.__tynys.scene.traverse(o=>{if(o.geometry?.type==='LatheGeometry'&&o.geometry.attributes.color)colors.push(o.geometry.attributes.color.array);});
      return colors.some(a=>new Set(Array.from(a,x=>x.toFixed(3))).size>30);
    });
    assert.ok(colored,'pit must be colored by spatial hardness');
    if(output)await page.screenshot({path:output+'-scene.png'});
    await page.waitForURL('**/futures.html',{timeout:65000});
    await page.waitForFunction(()=>JSON.parse(sessionStorage.getItem('tynys.demo.v1')||'null')?.stage==='done',{},{timeout:90000});
    assert.match(await page.locator('#snapshot-info').innerText(),/исходный час/);
    assert.ok(!await page.locator('#lull').isChecked(),'do not apply a second lull');
    const events=await page.evaluate(async()=>{
      const r=await fetch('ditto/api/2/things/kz.tynys:scenario/features');return JSON.parse((await r.json()).events.properties.value);
    });
    assert.deepEqual(events,foreign,'cleanup must preserve other events');
    if(output)await page.screenshot({path:output+'-futures.png',fullPage:true});
    await page.locator('#demo-cancel').click();
    await page.waitForFunction(()=>!sessionStorage.getItem('tynys.demo.v1'));
    assert.deepEqual(errors,[]);
    console.log(JSON.stringify({headline:headline,geology:'spatial colors and active faces',demo:'one-click auto journey, stopped rotors, real futures, cleanup PASS',pageErrors:errors}));
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
