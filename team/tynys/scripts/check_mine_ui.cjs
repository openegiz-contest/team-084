// Run against tests/serve_mine_fixture.py. This is not a Ditto/MQTT E2E test.
const {chromium}=require('playwright');
const fs=require('fs');
const url=process.argv[2]||'http://127.0.0.1:18098';
const output=process.argv[3];
(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||undefined,
    args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
  try {
    const page=await browser.newPage({viewport:{width:1440,height:1050}});
    const errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.goto(url+'/dashboard.html');
    await page.waitForFunction(()=>document.querySelectorAll('#equipment-rows tr').length===20);
    await page.waitForFunction(()=>document.querySelector('#flexstat').textContent.includes('physics-v4'));
    const line=page.locator('#equipment-rows tr').filter({hasText:'Линия 1'});
    if(await line.locator('td').nth(5).innerText()==='—')throw Error('Per-line P80 is missing');
    const crusher=page.locator('#equipment-rows tr').filter({hasText:'Дробилка'});
    if(!await crusher.innerText().then(s=>s.includes('Работает')))throw Error('Crusher is not running');
    await page.getByRole('button',{name:'Отказ дробилки',exact:true}).click();
    await page.waitForFunction(()=>[...document.querySelectorAll('#equipment-rows tr')].some(r=>r.textContent.includes('Дробилка')&&r.textContent.includes('Отказ')));
    if(output)await page.screenshot({path:output+'-dashboard.png',fullPage:true});
    await page.goto(url+'/3d.html?quality=low');
    await page.waitForFunction(()=>window.__tynys?.data?.crusher?.state==='fault');
    await page.locator('#skip').click();
    await page.waitForFunction(()=>Number(getComputedStyle(document.getElementById('intro')).opacity)<.05);
    for(const id of ['crusher','conveyor-crushed','conveyor-feed','waste-dump','tailings','concentrate','water']){
      if(!await page.evaluate(id=>window.__tynys.selectObject(id),id))throw Error('Missing 3D object: '+id);
      const text=await page.locator('#selection-values').innerText();
      if(text.includes('В снимке отсутствуют'))throw Error('No telemetry: '+id);
    }
    await page.evaluate(()=>window.__tynys.selectObject('crusher'));
    if(output)await page.screenshot({path:output+'-scene.png'});
    if(errors.length)throw Error(errors.join('\n'));
    await page.evaluate(()=>window.__tynys.selectObject('line-1'));
    const mill=await page.locator('#selection-values').innerText();
    if(!mill.includes('Постоянная часть мощности')||!mill.includes('P80'))throw Error('Mill physics telemetry missing');
    console.log(JSON.stringify({dashboardRows:20,crusherFault:'PASS',processObjects:7,perLinePhysics:'PASS',reserveModel:'physics-v4',pageErrors:errors}));
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
