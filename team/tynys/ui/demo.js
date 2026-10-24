// A real three-minute path through Ditto. No synthetic telemetry or verdicts.
(() => {
  'use strict';
  const KEY='tynys.demo.v1', API='ditto/api/2/things/kz.tynys:';
  const read=()=>{try{return JSON.parse(sessionStorage.getItem(KEY)||'null');}catch{return null;}};
  let demo=read(), busy=false, banner, message, next, cancel;
  const save=()=>sessionStorage.setItem(KEY,JSON.stringify(demo));
  const feature=(o,k,fallback)=>o?.[k]?.properties?.value??fallback;
  async function api(path,method='GET',body,etag){
    const response=await fetch(API+path,{method,cache:'no-store',headers:{'Content-Type':'application/json',...(etag?{'If-Match':etag}:{})},body:body===undefined?undefined:JSON.stringify(body),signal:AbortSignal.timeout(10000)});
    if(!response.ok)throw new Error(`Ditto HTTP ${response.status}`);
    return {value:method==='GET'?await response.json():null,etag:response.headers.get('etag')};
  }
  async function editEvent(add){
    const {value:features,etag}=await api('scenario/features');
    const events=JSON.parse(feature(features,'events','[]'));
    if(!Array.isArray(events))throw new Error('Некорректный список событий');
    const kept=events.filter(e=>String(e.id)!==demo.id);
    if(add)kept.push({kind:'lull',t0:demo.t0,dur:48,id:demo.id});
    await api('scenario/features','PUT',{...features,events:{properties:{value:JSON.stringify(kept)}},rev:{properties:{value:Number(feature(features,'rev',0))+1}}},etag);
  }
  function makeBanner(){
    if(banner)return;
    banner=document.createElement('aside');banner.id='demo-guide';banner.setAttribute('aria-label','Демо за три минуты');
    Object.assign(banner.style,{position:'fixed',left:'12px',right:'12px',bottom:'12px',zIndex:10000,padding:'12px 16px',borderRadius:'12px',background:'#103e43',color:'white',boxShadow:'0 6px 30px #0008',font:'14px system-ui',display:'flex',gap:'12px',alignItems:'center',flexWrap:'wrap'});
    message=document.createElement('span');message.id='demo-message';message.style.flex='1 1 300px';message.setAttribute('role','status');
    next=document.createElement('button');next.id='demo-next';next.type='button';next.textContent='Далее →';next.onclick=()=>advance(true);
    cancel=document.createElement('button');cancel.id='demo-cancel';cancel.type='button';cancel.textContent='Завершить демо';cancel.onclick=finish;
    for(const b of [next,cancel])Object.assign(b.style,{padding:'9px 12px',borderRadius:'6px',border:'1px solid #6ab7ad',background:'#174e53',color:'#fff',cursor:'pointer'});
    banner.append(message,next,cancel);document.body.appendChild(banner);
  }
  function navigate(stage,url){demo.stage=stage;save();location.assign(url);}
  async function finish(){
    if(busy)return;busy=true;makeBanner();
    try{
      if(demo.stage!=='done')await editEvent(false);
      if(demo.requestId && window.TynysDemoFutures)await window.TynysDemoFutures.cancelOwn(demo.requestId);
      sessionStorage.removeItem(KEY);demo=null;banner.remove();banner=null;
    }catch(e){message.textContent=`Не удалось убрать событие демо: ${e.message}. Повторите завершение. Событие ограничено 48 модельными часами.`;}
    finally{busy=false;}
  }
  async function begin(){
    if(busy||demo)return;busy=true;
    const button=document.getElementById('demo-start');button.disabled=true;
    try{
      const [{value:site},{value:energy}]=await Promise.all([api('site/features'),api('energy/features')]);
      const t=feature(site,'sim_hour',null),grid=feature(energy,'grid_mw',null);
      if(!Number.isFinite(t)||!Number.isFinite(grid))throw new Error('Нет живой телеметрии');
      demo={id:'demo-'+crypto.randomUUID(),started:Date.now(),stage:'dashboard',t0:t+1,baselineGrid:grid,requestId:null,submitted:false};
      // Save before mutation so an interrupted response can still be cleaned up.
      save();makeBanner();await editEvent(true);
      message.textContent='1/3 · Штиль отправлен. Ждём следующий модельный час; затем откроется 3D.';
    }catch(e){if(demo){makeBanner();message.textContent='Запуск не подтверждён: '+e.message+'. Завершите демо для очистки.';}else{button.textContent='Нет связи — повторить демо';}}
    finally{busy=false;button.disabled=false;}
  }
  async function advance(manual=false){
    if(!demo||busy)return;busy=true;makeBanner();
    try{
      const elapsed=(Date.now()-demo.started)/1000;
      if(elapsed>900){busy=false;return finish();}
      if(demo.stage==='dashboard'||demo.stage==='scene'){
        const [{value:site},{value:energy}]=await Promise.all([api('site/features'),api('energy/features')]);
        const t=feature(site,'sim_hour',0),grid=feature(energy,'grid_mw',null);
        const active=t>=demo.t0;
        const delta=Number.isFinite(grid)?grid-demo.baselineGrid:null;
        const windEffect=feature(energy,'lull_grid_delta_mw',null);
        const measurement=delta===null?'ожидание измерения':`сеть ${grid.toFixed(1)} МВт`+(Number.isFinite(windEffect)?`; вклад штиля +${Math.max(0,windEffect).toFixed(1)} МВт при тех же уставках`:`; ${delta>=0?'+':''}${delta.toFixed(1)} МВт к началу`);
        next.disabled=!active;
        if(demo.stage==='dashboard'){
          message.textContent=`1/3 · ${active?'Штиль действует':'Ждём активации штиля'}. ${measurement}. В 3D через ${Math.max(0,Math.ceil(45-elapsed))} с.`;
          if(active&&(manual||elapsed>=45))navigate('scene','3d.html');
        }else{
          document.getElementById('intro')?.classList.add('hide');
          message.textContent=`2/3 · Лопасти остановлены при активном штиле. ${measurement}. Цвет уступов — BWi GeoMet. «Два будущих» через ${Math.max(0,Math.ceil(100-elapsed))} с.`;
          const live=window.__tynys?.source==='live';
          next.disabled=!active||!live;
          if(active&&live&&(manual||elapsed>=100))navigate('futures','futures.html');
        }
      }else if(demo.stage==='futures'){
        next.hidden=true;
        const engine=window.TynysDemoFutures;
        if(!engine){message.textContent='3/3 · Подключаем экран «Два будущих»…';return;}
        if(!demo.submitted){
          if(!engine.ready()){message.textContent='3/3 · Ожидаем свободный сервис расчёта. Чужой запрос не прерывается.';return;}
          // Do not add a second lull: snapshot already contains our live event.
          await engine.start(id=>{demo.requestId=id;demo.submitted=true;save();});
        }
        const status=engine.status(demo.requestId);
        if(status==='complete'){
          await editEvent(false);demo.stage='done';save();
          message.textContent='3/3 · Готово. Сравните сеть, выпуск меди и восстановление. Это результат модели; временный штиль демо убран.';
        }else if(status==='error'){
          message.textContent='3/3 · Расчёт не завершён. Причина показана на экране; результат не подменяется. Завершите демо или повторите расчёт вручную.';
        }else message.textContent=`3/3 · Считаем два будущих на одном снимке. ${elapsed<180?`Ориентир: ещё ${Math.ceil(180-elapsed)} с.`:'Расчёт дольше трёх минут — ждём настоящий результат.'}`;
      }else{
        next.hidden=true;message.textContent='Демо завершено. Отчёт «Двух будущих» остаётся на экране. Временный штиль убран.';
      }
    }catch(e){message.textContent='Демо ожидает связь: '+e.message+'. Можно завершить и повторить.';}
    finally{busy=false;}
  }
  document.getElementById('demo-start')?.addEventListener('click',begin);
  if(demo){makeBanner();if(demo.stage==='scene')document.getElementById('intro')?.classList.add('hide');advance();}
  setInterval(()=>advance(),1500);
})();
