/* Actual Unity WebGL QA. Reads real Ditto; blocks requests only for failure tests.
 * Usage: node check_unity_web.cjs [http://127.0.0.1:8095/]
 * CHROME_PATH and TYNYS_UNITY_ARTIFACT_DIR are optional. No FPS target is invented.
 * FPS counts browser callbacks that actually submit Unity WebGL draws, not empty RAF.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const zlib = require('node:zlib');
const crypto = require('node:crypto');
const {chromium} = require('playwright');

const url = process.argv[2] || 'http://127.0.0.1:8095/';
const out = path.resolve(process.env.TYNYS_UNITY_ARTIFACT_DIR || '.unity-test-output');
const viewport = {width:1400,height:900};
const args = ['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader',
  '--disable-background-timer-throttling','--disable-renderer-backgrounding'];
const report = {status:'FAIL',url,viewport,host:{platform:os.platform(),release:os.release(),logicalCPUs:os.cpus().length},
  method:'Actual Unity WebGL + live Ditto, then browser-route network failures; no scenario writes',
  launchArgs:args,checks:[],errors:[],console:[],resources:[],readOnlyViolations:[],dittoSamples:[],performanceTarget:null};
const diagnosticReads = new Set();

function instrumentDraws() {
  const qa = window.__unityQA = {frames:0,draws:0,outsideDraws:0,times:[],frameDraws:[],statusHistory:[],contexts:[]};
  let depth = 0;
  function run(callback, receiver, values) {
    const outer = depth === 0, before = qa.draws;
    depth++;
    try { return callback.apply(receiver, values); }
    finally {
      depth--;
      if (outer && qa.draws > before) {
        qa.frames++; qa.times.push(performance.now()); qa.frameDraws.push(qa.draws-before);
        if (qa.times.length > 4000) { qa.times.shift(); qa.frameDraws.shift(); }
      }
    }
  }
  const raf = window.requestAnimationFrame;
  window.requestAnimationFrame = function(callback) {
    return raf.call(this,function(...values) { return run(callback,this,values); });
  };
  const timeout = window.setTimeout;
  window.setTimeout = function(callback,delay,...values) {
    return timeout.call(this,typeof callback === 'function'
      ? function() { return run(callback,this,values); } : callback,delay);
  };
  for (const Type of [window.WebGLRenderingContext,window.WebGL2RenderingContext]) {
    if (!Type) continue;
    for (const name of ['drawArrays','drawElements','drawArraysInstanced','drawElementsInstanced','drawRangeElements']) {
      const original = Type.prototype[name]; if (!original || original.__tynysWrapped) continue;
      function wrapped(...values) {
        const result = original.apply(this,values);
        if (this.canvas?.id === 'unity-canvas') {
          qa.draws++; if (!depth) qa.outsideDraws++;
          if (!qa.contexts.includes(this)) qa.contexts.push(this);
        }
        return result;
      }
      wrapped.__tynysWrapped = true; Type.prototype[name] = wrapped;
    }
  }
  window.addEventListener('message',event => {
    if (event.origin === location.origin && event.data?.type === 'tynys-unity-data')
      qa.statusHistory.push({time:performance.now(),...event.data.status});
  });
}

function readMetrics() {
  const qa=window.__unityQA,gl=qa?.contexts[0],canvas=document.getElementById('unity-canvas');
  const ext=gl?.getExtension('WEBGL_debug_renderer_info');
  return {now:performance.now(),frames:qa?.frames,draws:qa?.draws,outsideDraws:qa?.outsideDraws,
    times:qa?.times.slice(),frameDraws:qa?.frameDraws.slice(),status:window.tynysStatus,
    runtime:window.tynysRuntime,renderer:gl?gl.getParameter(ext?ext.UNMASKED_RENDERER_WEBGL:gl.RENDERER):null,
    glVersion:gl?.getParameter(gl.VERSION),contextLost:gl?.isContextLost(),
    drawingBuffer:gl?[gl.drawingBufferWidth,gl.drawingBufferHeight]:null,
    canvas:canvas?{width:canvas.width,height:canvas.height,clientWidth:canvas.clientWidth,clientHeight:canvas.clientHeight}:null,
    browser:navigator.userAgent,hardwareConcurrency:navigator.hardwareConcurrency};
}

const percentile=(values,q)=>{const a=[...values].sort((x,y)=>x-y),p=(a.length-1)*q,l=Math.floor(p),h=Math.ceil(p);return a[l]+(a[h]-a[l])*(p-l);};
async function measure(frame,page) {
  await page.waitForTimeout(3000);
  const first=await frame.evaluate(readMetrics),samples=[],times=new Set();
  assert.match(String(first.renderer),/swiftshader/i,'Actual software WebGL renderer not confirmed');
  assert.equal(first.contextLost,false);
  assert.equal(first.status.softwareRenderer,true,'Unity software-renderer profile was not activated');
  assert.ok(first.status.batchedObjects>0,'Unity static geometry was not batched');
  while (true) {
    await page.waitForTimeout(400);
    const sample=await frame.evaluate(readMetrics);samples.push(sample);
    for(const time of sample.times) if(time>=first.now) times.add(time);
    if(sample.now-first.now>=10000) break;
  }
  const last=samples.at(-1),elapsed=(last.now-first.now)/1000,count=last.frames-first.frames;
  assert.ok(count>0,'Unity submitted no rendered frames');
  assert.equal(last.outsideDraws-first.outsideDraws,0,'Unity draws outside measured callbacks; FPS coverage would be incomplete');
  assert.ok(Math.abs(times.size-count)<=1,'Draw-frame counter disagrees with completion timestamps');
  assert.ok(last.status.frameCount>first.status.frameCount,'Unity game-loop frameCount did not advance');
  assert.ok(Number.isFinite(first.status.renderedFrameCount)&&last.status.renderedFrameCount>first.status.renderedFrameCount,
    'Unity WaitForEndOfFrame counter did not advance');
  const bins=Array.from({length:Math.floor(elapsed)},(_,i)=>[...times].filter(t=>t>=first.now+i*1000&&t<first.now+(i+1)*1000).length);
  const drawCounts=last.frameDraws.slice(-count);
  return {method:'Completion of browser callbacks containing Unity WebGL draw submissions; includes instrumentation; not a GPU presentation-time metric',
    elapsedSeconds:elapsed,drawFrames:count,drawCalls:last.draws-first.draws,oneSecondFPS:bins,
    averageFPS:count/elapsed,medianFPS:percentile(bins,.5),p10FPS:percentile(bins,.1),minFPS:Math.min(...bins),
    drawCallsPerFrame:{min:Math.min(...drawCounts),median:percentile(drawCounts,.5),max:Math.max(...drawCounts)},
    unityFrameCount:{before:first.status.frameCount,after:last.status.frameCount},
    unityRenderedFrameCount:{before:first.status.renderedFrameCount,after:last.status.renderedFrameCount},
    softwareProfile:{active:last.status.softwareRenderer,batchedObjects:last.status.batchedObjects},
    sourceIssues:[first,...samples].filter(s=>s.status.mode!=='LIVE'||!s.status.connected||s.status.stale||!s.status.hasSnapshot)
      .map(s=>({time:s.now-first.now,...s.status})),
    environment:{renderer:last.renderer,glVersion:last.glVersion,drawingBuffer:last.drawingBuffer,
      canvas:last.canvas,browser:last.browser,hardwareConcurrency:last.hardwareConcurrency},target:null};
}

function pixelEvidence(png) {
  assert.equal(png.subarray(1,4).toString(),'PNG');
  let offset=8,width,height,channels;const chunks=[];
  while(offset<png.length) {
    const length=png.readUInt32BE(offset),type=png.toString('ascii',offset+4,offset+8),data=png.subarray(offset+8,offset+8+length);
    if(type==='IHDR') {
      width=data.readUInt32BE(0);height=data.readUInt32BE(4);
      assert.equal(data[8],8);assert.ok([2,6].includes(data[9]));assert.equal(data[12],0);
      channels=data[9]===6?4:3;
    }
    if(type==='IDAT')chunks.push(data);offset+=12+length;
  }
  const raw=zlib.inflateSync(Buffer.concat(chunks)),stride=width*channels,decoded=Buffer.alloc(stride*height);
  const paeth=(a,b,c)=>{const p=a+b-c,pa=Math.abs(p-a),pb=Math.abs(p-b),pc=Math.abs(p-c);return pa<=pb&&pa<=pc?a:pb<=pc?b:c;};
  let pos=0;
  for(let y=0;y<height;y++) {
    const filter=raw[pos++];assert.ok(filter<=4);
    for(let x=0;x<stride;x++) {
      const left=x>=channels?decoded[y*stride+x-channels]:0,up=y?decoded[(y-1)*stride+x]:0,corner=y&&x>=channels?decoded[(y-1)*stride+x-channels]:0;
      const predictor=filter===0?0:filter===1?left:filter===2?up:filter===3?Math.floor((left+up)/2):paeth(left,up,corner);
      decoded[y*stride+x]=(raw[pos++]+predictor)&255;
    }
  }
  let samples=0,nonBlack=0,min=255,max=0,sum=0;const colors=new Set();
  // Central scene excludes the top status strip and both side HUD panels.
  for(let y=Math.floor(height*.20);y<height*.70;y+=3) for(let x=Math.floor(width*.24);x<width*.70;x+=3) {
    const i=y*stride+x*channels,r=decoded[i],g=decoded[i+1],b=decoded[i+2],l=(r+g+b)/3;
    samples++;sum+=l;min=Math.min(min,l);max=Math.max(max,l);if(l>10)nonBlack++;
    colors.add(((r>>4)<<8)|((g>>4)<<4)|(b>>4));
  }
  const evidence={width,height,roi:'x24–70%, y20–70%',samples,nonBlackFraction:nonBlack/samples,
    meanBrightness:sum/samples,brightnessRange:max-min,quantizedColors:colors.size,sha256:crypto.createHash('sha256').update(png).digest('hex')};
  assert.ok(evidence.nonBlackFraction>.3 && evidence.brightnessRange>15 && evidence.quantizedColors>12,
    'Central Unity image is black or flat; HUD alone is insufficient visual evidence: '+JSON.stringify(evidence));
  return evidence;
}

async function status(frame){return frame.evaluate(()=>({...window.tynysStatus}));}
async function ready(page) {
  await page.goto(url,{waitUntil:'domcontentloaded',timeout:60000});
  await page.waitForFunction(()=>document.getElementById('runtime-state')?.dataset.ready==='true',null,{timeout:180000});
  const frame=await (await page.$('#unity')).contentFrame();
  assert.ok(frame,'Root does not contain the Unity iframe');
  await frame.waitForFunction(()=>window.tynysRuntime?.state==='ready'&&window.tynysStatus,null,{timeout:60000});
  return frame;
}

async function main() {
  fs.mkdirSync(out,{recursive:true});
  let browser,page,phase='startup',blockDitto=false;
  try {
    browser=await chromium.launch({headless:true,args,
      ...(process.env.CHROME_PATH?{executablePath:process.env.CHROME_PATH}:{})});
    report.browserVersion=browser.version();report.playwrightVersion=require('playwright/package.json').version;
    const context=await browser.newContext({viewport,deviceScaleFactor:1});
    await context.addInitScript(instrumentDraws);
    await context.route('**/ditto/api/2/**',async route=>{
      if(route.request().method()!=='GET') {
        report.readOnlyViolations.push({phase,method:route.request().method(),url:route.request().url()});
        return route.abort('blockedbyclient');
      }
      if(blockDitto)return route.abort('failed');
      return route.continue();
    });
    function watch(target) {
      target.on('pageerror',error=>report.errors.push({phase,message:String(error)}));
      target.on('console',message=>{if(['error','warning'].includes(message.type()))report.console.push({phase,type:message.type(),text:message.text().slice(0,1800)});});
      target.on('response',response=>{
        if(response.url().includes('/unity/')) report.resources.push({phase,url:response.url(),status:response.status(),headers:response.headers()});
        if(response.url().includes('/ditto/api/2/')&&response.request().method()==='GET'&&response.ok()) {
          const responsePhase=phase;
          // Keep the exact truck enums that reached Unity, including a rejected snapshot.
          // This is diagnostic response reading; it never sends another HTTP request.
          const pending=response.json().then(body=>{
            const things=Array.isArray(body)?body:body?.items;
            if(!Array.isArray(things))return;
            const value=(thing,feature)=>thing?.features?.[feature]?.properties?.value;
            const site=things.find(thing=>thing.thingId==='kz.tynys:site');
            const states=Object.fromEntries(things.filter(thing=>/^kz\.tynys:truck-\d+$/.test(thing.thingId||''))
              .map(thing=>[thing.thingId,value(thing,'state')]));
            report.dittoSamples.push({phase:responsePhase,receivedAt:new Date().toISOString(),hour:value(site,'sim_hour'),truckStates:states});
            if(report.dittoSamples.length>120)report.dittoSamples.shift();
          }).catch(error=>{report.dittoSamples.push({phase:responsePhase,diagnosticError:String(error)});});
          diagnosticReads.add(pending);pending.finally(()=>diagnosticReads.delete(pending));
        }
      });
    }
    page=await context.newPage();watch(page);phase='live';
    const frame=await ready(page);
    await frame.waitForFunction(()=>{const s=window.tynysStatus;return s.mode==='LIVE'&&s.connected&&!s.stale&&s.hasSnapshot&&s.snapshotCount>0;},null,{timeout:60000});
    const first=await status(frame);report.live={first};
    assert.ok(Number.isFinite(first.hour)&&first.hour>=0);
    await frame.waitForFunction(count=>window.tynysStatus.snapshotCount>count,first.snapshotCount,{timeout:45000});
    report.performance=await measure(frame,page);report.live.after=await status(frame);
    assert.ok(report.live.after.snapshotCount>first.snapshotCount,'No further valid Ditto snapshots');
    assert.ok(Number.isFinite(report.live.after.hour)&&report.live.after.hour>first.hour,
      'The live model clock did not advance; repeated reads of one snapshot are insufficient LIVE evidence');
    const canvas=await frame.locator('#unity-canvas').screenshot({path:path.join(out,'unity-canvas-live.png')});
    report.live.pixels=pixelEvidence(canvas);
    await page.screenshot({path:path.join(out,'unity-live.png')});
    console.log(JSON.stringify({stage:'LIVE evidence',screenshot:path.join(out,'unity-live.png'),performance:report.performance,live:report.live}));
    assert.deepEqual(report.performance.sourceIssues,[],'Live data became stale or invalid before the controlled failure test');
    assert.ok(report.live.after.connected&&!report.live.after.stale,'LIVE disconnected during measurement');
    report.checks.push('Actual Unity runtime, live Ditto snapshots, advancing Unity frames and nonblack scene');

    // These are actual IMGUI toolbar clicks; the read-only diagnostic only confirms the selected view.
    assert.equal(report.live.after.presentation,'pit','The close quarry composition is not the default');
    const toolbarCanvas=await frame.locator('#unity-canvas').boundingBox();
    const toolbarScale=Math.min(toolbarCanvas.width/1600,toolbarCanvas.height/900);
    report.presentations={pit:report.live.after};
    for(const [view,rightInset,file] of [['digital',583,'unity-digital.png'],['site',433,'unity-site.png'],['pit',733,'unity-pit-return.png']]) {
      await page.mouse.click(toolbarCanvas.x+toolbarCanvas.width-rightInset*toolbarScale,toolbarCanvas.y+132*toolbarScale,{delay:120});
      await frame.waitForFunction(expected=>window.tynysStatus?.presentation===expected,view,{timeout:15000});
      const selected=await status(frame);
      assert.equal(selected.mode,'LIVE');assert.equal(selected.connected,true);assert.equal(selected.stale,false);
      assert.ok(selected.snapshotCount>=report.live.after.snapshotCount,'View selection reset the data source');
      report.presentations[view]=selected;
      await page.screenshot({path:path.join(out,file)});
    }
    report.checks.push('Close quarry, digital outlines and whole-site views switch by toolbar without changing LIVE data');

    phase='stale';blockDitto=true;
    await frame.waitForFunction(()=>window.tynysStatus.mode==='LIVE'&&window.tynysStatus.stale&&!window.tynysStatus.connected,null,{timeout:45000});
    const stale=await status(frame);assert.equal(stale.hasSnapshot,true);
    await page.waitForTimeout(3500);const held=await status(frame);
    assert.equal(held.mode,'LIVE');assert.equal(held.hasSnapshot,true);assert.equal(held.hour,stale.hour);
    assert.equal(held.snapshotCount,stale.snapshotCount,'Offline mode invented another snapshot');
    assert.match(held.status,/последний снимок|предыдущий снимок/);
    report.stale={first:stale,held};await page.screenshot({path:path.join(out,'unity-stale.png')});
    phase='recovery';blockDitto=false;
    await frame.waitForFunction(count=>{const s=window.tynysStatus;return s.mode==='LIVE'&&s.connected&&!s.stale&&s.snapshotCount>count;},held.snapshotCount,{timeout:60000});
    report.recovery=await status(frame);report.checks.push('Network loss retains last LIVE snapshot; recovery resumes valid snapshots');
    await page.close();

    phase='fresh-offline';blockDitto=true;page=await context.newPage();watch(page);
    const waitingFrame=await ready(page);
    await waitingFrame.waitForFunction(()=>{const s=window.tynysStatus;return s.mode==='LIVE'&&!s.connected&&s.stale&&!s.hasSnapshot&&s.snapshotCount===0&&s.hour===-1;},null,{timeout:45000});
    await page.waitForTimeout(3500);report.freshOffline=await status(waitingFrame);
    assert.equal(report.freshOffline.mode,'LIVE');assert.equal(report.freshOffline.hasSnapshot,false);
    assert.equal(report.freshOffline.snapshotCount,0);assert.equal(report.freshOffline.hour,-1);
    await page.screenshot({path:path.join(out,'unity-waiting.png')});
    report.checks.push('Fresh blocked backend stays LIVE waiting, with no snapshot and no automatic DEMO');
    // This IMGUI button was visually reviewed in unity-waiting.png. Its center
    // follows MineHUD.DrawInspector's GUI.matrix scale, not a hidden mode API.
    phase='manual-demo';
    const box=await waitingFrame.locator('#unity-canvas').boundingBox();
    assert.ok(box,'Unity canvas is not visible for the explicit DEMO action');
    const hudScale=Math.min(box.width/1600,box.height/900);
    const click={x:box.x+box.width-172*hudScale,y:box.y+box.height-211*hudScale};
    await page.mouse.click(click.x,click.y,{delay:180});
    await waitingFrame.waitForFunction(()=>window.tynysStatus?.mode==='DEMO',null,{timeout:15000});
    const demo=await status(waitingFrame);
    assert.equal(demo.connected,false);assert.equal(demo.snapshotCount,0);
    assert.match(demo.status,/демо|иллюстратив/i);
    report.manualDemo={tested:true,method:'Actual mouse click on the visible IMGUI DEMO button',click,status:demo};
    await page.screenshot({path:path.join(out,'unity-explicit-demo.png')});
    report.checks.push('DEMO starts only after an explicit click on its visible HUD button');
    await page.close();

    phase='missing-build';page=await context.newPage();watch(page);
    await page.route('**/unity/index.html',route=>route.fulfill({status:404,body:'controlled missing-build test'}));
    await page.goto(url,{waitUntil:'domcontentloaded'});
    await page.waitForFunction(()=>document.getElementById('loading-title')?.textContent==='Unity пока недоступна');
    assert.equal(await page.locator('#retry').isVisible(),true);
    assert.notEqual(await page.locator('#runtime-state').getAttribute('data-ready'),'true');
    for(const href of ['dashboard.html','futures.html','3d.html']) {
      assert.ok(await page.locator(`nav a[href="${href}"]`).count());
      assert.ok((await context.request.get(new URL(href,url).href)).ok(),'Fallback route unavailable: '+href);
    }
    await page.screenshot({path:path.join(out,'unity-missing-build.png')});
    report.checks.push('Missing Unity build has explicit recovery UI and usable dashboard/futures/light-3D links');
    assert.deepEqual(report.errors,[],'Unexpected JavaScript runtime errors');
    assert.deepEqual(report.readOnlyViolations,[],'Unity attempted to modify the live backend');
    const assets=report.resources.filter(r=>r.phase==='live'&&r.url.includes('/Build/'));
    assert.ok(assets.some(r=>/\.wasm(?:$|\?)/.test(r.url)),'Actual Wasm asset was not observed');
    assert.ok(assets.every(r=>r.status===200),'A Unity build asset did not load successfully');
    for(const asset of assets.filter(r=>/\.wasm(?:$|\?)/.test(r.url)))
      assert.match(asset.headers['content-type']||'',/application\/wasm/,'Wrong Wasm MIME type');
    report.status='PASS';
  } catch(error) {
    report.failure={phase,message:String(error),stack:error.stack};
    if(page&&!page.isClosed())try{await page.screenshot({path:path.join(out,'unity-failure.png')});}catch(_){}
    throw error;
  } finally {
    await Promise.allSettled([...diagnosticReads]);
    fs.writeFileSync(path.join(out,'report.json'),JSON.stringify(report,null,2));
    if(browser)await browser.close();
    console.log(JSON.stringify({status:report.status,checks:report.checks,report:path.join(out,'report.json'),failure:report.failure?.message}));
  }
}
main().catch(error=>{console.error(error);process.exitCode=1;});
