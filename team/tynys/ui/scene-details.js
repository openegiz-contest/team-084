// Rendering-only details. Twin values and event state are never modified here.
import * as THREE from 'three';
import { mergeGeometries } from './vendor/BufferGeometryUtils.js';

const clamp = (n, a = 0, b = 1) => Math.max(a, Math.min(b, n));
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = n => typeof n === 'number' && Number.isFinite(n) ? n.toLocaleString('ru-RU',{maximumFractionDigits:1}) : '—';
const TITLES = {pit:'Карьер',plant:'Фабрика',flotation:'Флотация','pile-soft':'Склад мягкой руды','pile-hard':'Склад твёрдой руды',wind:'Ветровая станция',pv:'Солнечная станция',bess:'Накопитель',substation:'Подстанция','line-1':'Линия 1','line-2':'Линия 2'};
const FIELDS = {soc:['Заряд','%'],power_mw:['Мощность','МВт'],capacity_mw:['Установлено','МВт'],grid_mw:['Из сети','МВт'],grid_cap_mw:['Предел сети','МВт'],feed_tph:['Подача','т/ч'],ore_tph:['Добыча','т/ч'],ore_plan_tph:['План добычи','т/ч'],load_pct:['Загрузка','%'],tonnes:['Руды на складе','т'],fill_pct:['Заполнение','%'],bwi_est:['Оценка твёрдости','кВт·ч/т'],bwi_true:['Твёрдость','кВт·ч/т'],available:['Доступен',''],running:['Работает',''],lock_h:['До перезапуска','ч'],hard_frac:['Доля твёрдой руды',''],cu_tph:['Медь','т/ч'],recovery:['Извлечение','%'],cf_pct:['Мощность / установленная','%'],energy_mwh:['Энергия','МВт·ч'],payload_t:['Груз звена','т'],state:['Состояние',''],feed_soft_tph:['Мягкая руда','т/ч'],feed_hard_tph:['Твёрдая руда','т/ч'],mill_mw:['Мельницы','МВт'],p80_um:['P80','мкм'],spilled_tph:['Переполнение','т/ч']};
const STATES = {charging:'заряжается',waiting:'ожидает зарядки',loaded:'с грузом',empty:'порожний',digging:'добыча',idle:'остановлен'};
Object.assign(STATES,{running:'работает',fault:'отказ',maintenance:'ТО / ремонт',lockout:'блокировка',unavailable:'недоступен'});
Object.assign(FIELDS,{throughput_tph:['Пропускная способность','т/ч'],inflow_tph:['Входящий поток','т/ч'],
  rate_tph:['Погрузка','т/ч'],waste_tph:['Вскрыша','т/ч'],speed_rpm:['Скорость привода','об/мин'],
  health_pct:['Исправность','%'],availability_pct:['Готовность за прогон','%'],
  repair_remaining_h:['До конца ремонта','ч'],operating_h:['Наработка','ч'],
  flow_m3_h:['Вода в процесс','м³/ч'],fresh_m3_h:['Свежая вода','м³/ч'],recycle_m3_h:['Оборотная вода','м³/ч'],
  grade_pct:['Содержание Cu','%'],assigned_shovel:['Экскаватор',''],assigned_charger:['Зарядная группа','']});
FIELDS.tonnes=['Накоплено','т'];
Object.assign(FIELDS,{maintenance_start_h:['Начало ТО','ч'],maintenance_deadline_h:['Крайний старт','ч'],maintenance_kind:['Работа',''],liner_remaining_pct:['Ресурс футеровки','%'],liner_replacements:['Замен футеровки','']});
Object.assign(STATES,{liner:'замена футеровки',inspection:'плановое ТО'});
Object.assign(FIELDS,{idle_mw:['Постоянная часть мощности','МВт'],stop_reason:['Причина остановки',''],cu_t:['Cu в запасе','т']});
Object.assign(STATES,{equipment_unavailable:'оборудование недоступно',controlled_stop:'штатная остановка',
  capacity_trip:'защита по мощности / производительности',stockout_trip:'недостаточно руды',power_trip:'дефицит электропитания'});
const EVENT_NAMES = {lull:'Штиль',line_trip:'Авария линии 2',kegoc:'Ограничение KEGOC',hard_ore:'Твёрдая руда',plan_up:'План добычи +10 %',bess_fault:'Отказ накопителя'};
Object.assign(EVENT_NAMES,{crusher_fault:'Отказ дробилки',shovel_fault:'Отказ экскаватора 1',
  conveyor_fault:'Отказ конвейера питания',water_fault:'Отказ водовода',
  charger_fault:'Отказ зарядной группы 1',crusher_service:'ТО дробилки'});
Object.assign(EVENT_NAMES,{truck_failure:'Поломка самосвала',excavator_failure:'Поломка экскаватора',grade_drop:'Падение содержания меди',tariff_change:'Смена тарифа сети'});
const eventName=e=>e.kind==='line_trip'?'Авария линии '+(Number(e.line)||2):(EVENT_NAMES[e.kind]||e.kind);

export function scenarioEvents(data) {
  const raw = data.scenario?.events;
  try { const events = Array.isArray(raw) ? raw : JSON.parse(raw || '[]');
    const hour = Number(data.site?.sim_hour ?? 0);
    return Array.isArray(events) ? events.filter(e => e && Number.isFinite(e.t0) && Number.isFinite(e.dur) && e.dur > 0 && e.t0 + e.dur > hour)
      .map(e => ({...e,active:hour >= e.t0,remaining:Math.max(0,e.t0 + e.dur - hour),startsIn:Math.max(0,e.t0 - hour)})) : [];
  } catch { return []; }
}

// Only immutable meshes are folded into world-space batches. Matching both the
// material settings and attribute schema prevents loss of UVs, normals or colours.
export function mergeStaticMeshes(scene, dynamicRoots = [], {local=false,bakeColors=false} = {}) {
  const excluded = new Set(dynamicRoots.filter(Boolean)), buckets = new Map();
  scene.updateWorldMatrix(true,true);
  const rootInverse=local?scene.matrixWorld.clone().invert():null;
  let before = 0;
  scene.traverse(o => { if (o.isMesh) before++; });
  scene.traverse(o => {
    if ((local&&o===scene) || !o.isMesh || o.isInstancedMesh || Array.isArray(o.material) || o.userData.noMerge) return;
    for (let p=o;p;p=p.parent) if(excluded.has(p)||p.userData.noMerge) return;
    const m=o.material;
    if(!m || m.transparent || !(m.isMeshStandardMaterial||m.isMeshLambertMaterial||m.isMeshBasicMaterial))return;
    // Diffuse colour is a vertex multiplier in the Lambert shader. Baking its
    // already-linear RGB keeps the exact shading while joining colour buckets.
    // Materials animated by reference must retain that original reference.
    const colorAttribute=o.geometry.attributes.color;
    const bake=bakeColors&&m.isMeshLambertMaterial&&!m.userData.dynamicColor&&!m.userData.batchKey&&(!m.vertexColors||!colorAttribute||colorAttribute.itemSize===3);
    const attributes=Object.keys(o.geometry.attributes).filter(k=>!bake||k!=='color').sort().map(k=>`${k}:${o.geometry.attributes[k].itemSize}:${o.geometry.attributes[k].normalized}`).join('|')+(bake?'|color:3:false':'');
    const key=JSON.stringify([m.userData.dynamicColor?m.uuid:m.userData.batchKey,m.type,bake?'baked':m.color?.getHex(),m.emissive?.getHex(),m.emissiveIntensity,m.roughness,m.metalness,m.side,bake||m.vertexColors,m.flatShading,m.wireframe,m.opacity,m.depthWrite,m.depthTest,m.fog,m.map?.uuid,m.normalMap?.uuid,m.roughnessMap?.uuid,m.metalnessMap?.uuid,m.alphaMap?.uuid,m.envMap?.uuid,o.castShadow,o.receiveShadow,attributes]);
    if(!buckets.has(key))buckets.set(key,{items:[],bake});buckets.get(key).items.push(o);
  });
  let mergedMeshes=0,batches=0;
  for(const {items,bake} of buckets.values()) {
    if(items.length<2)continue;
    const geos=items.map(o=>{const g=o.geometry.index?o.geometry.toNonIndexed():o.geometry.clone();g.applyMatrix4(local?new THREE.Matrix4().multiplyMatrices(rootInverse,o.matrixWorld):o.matrixWorld);
      if(bake){const original=o.material.vertexColors?g.attributes.color:null,c=o.material.color,colors=new Float32Array(g.attributes.position.count*3);
        for(let i=0;i<g.attributes.position.count;i++){colors[i*3]=c.r*(original?original.getX(i):1);colors[i*3+1]=c.g*(original?original.getY(i):1);colors[i*3+2]=c.b*(original?original.getZ(i):1);}
        g.setAttribute('color',new THREE.BufferAttribute(colors,3));}
      return g;});
    const merged=mergeGeometries(geos,false);geos.forEach(g=>g.dispose());
    if(!merged)continue;
    const material=bake?items[0].material.clone():items[0].material;if(bake){material.color.setRGB(1,1,1);material.vertexColors=true;}
    merged.computeBoundingSphere();const m=new THREE.Mesh(merged,material);
    m.name=local?'rigid-local-batch':'static-batch';m.castShadow=items[0].castShadow;m.receiveShadow=items[0].receiveShadow;
    scene.add(m);items.forEach(o=>o.removeFromParent());mergedMeshes+=items.length;batches++;
  }
  let after=0;scene.traverse(o=>{if(o.isMesh)after++;});
  return {before,after,batches,mergedMeshes};
}

export function installSceneDetails(ctx) {
  const {scene,camera,renderer,label,mesh,M,road,terrainH,PLANT,PILES,CHARGE,BESS,SUB,WIND,PV,PIT,PIT_R=100,trucks,mills,turbines,piles,bessLights,chargers,windows,shovels,flows,getData,getSource,cancelEvent}=ctx;
  const $=id=>document.getElementById(id);
  const dynamicRoots=[...trucks.map(t=>t.g),...mills.flatMap(m=>[m.drum,m.lamp]),...turbines,...Object.values(piles),...bessLights,...chargers,...windows,...shovels];
  let selected=null, events=[], bannerKey='', lastData={};
  const targets=new Map(),proxies=[], bars=[];
  const proxyMaterial=new THREE.MeshBasicMaterial({visible:false});
  const outline=new THREE.Box3Helper(new THREE.Box3(),0x86e7ff);outline.visible=false;outline.material.depthTest=false;outline.renderOrder=10;scene.add(outline);
  function target(id,title,center,size,follow=null) {
    const proxy=new THREE.Mesh(new THREE.BoxGeometry(...size),proxyMaterial);proxy.position.set(...center);proxy.userData.noMerge=true;proxy.userData.objectId=id;scene.add(proxy);
    targets.set(id,{id,title,proxy,follow,size});proxies.push(proxy);
  }
  target('pit','Карьер Актогай',[PIT.x,-36,PIT.z],[195,80,195]);
  target('plant','Фабрика',[PLANT.x+10,15,PLANT.z],[67,30,72]);
  target('flotation','Флотация',[PLANT.x+50,5,PLANT.z+2],[10,11,54]);
  target('pile-soft',TITLES['pile-soft'],[PILES.x,10,PILES.z-20],[43,24,38]);
  target('pile-hard',TITLES['pile-hard'],[PILES.x,10,PILES.z+20],[43,24,38]);
  target('bess',TITLES.bess,[BESS.x+14,4,BESS.z+9],[39,9,37]);
  target('substation',TITLES.substation,[SUB.x,9,SUB.z],[48,20,44]);
  target('wind',TITLES.wind,[WIND.x+245,50,WIND.z-45],[535,145,165]);
  target('pv',TITLES.pv,[PV.x+125,3,PV.z+50],[268,10,110]);
  mills.forEach((m,i)=>target(`line-${i+1}`,TITLES[`line-${i+1}`],[PLANT.x-34,12,PLANT.z+(i?-14:14)*-1],[25,25,23]));
  chargers.forEach((m,i)=>target(`charger-${i+1}`,`Зарядная станция ${i+1}`,[CHARGE.x-30+i*20,5,CHARGE.z-12],[16,12,16]));
  trucks.forEach((t,i)=>target(`truck-${String(i+1).padStart(2,'0')}`,`Звено самосвалов ${String(i+1).padStart(2,'0')}`,[0,3,0],[12,7,8],t.g));

  // Schematic positions, not a surveyed layout of Aktogay. All quantities and
  // stop states in the cards come from the corresponding process twins.
  const processObjects=[
    ['crusher','Дробилка',[8,8,-15],[16,16,18]],
    ['conveyor-crushed','Дроблёная руда',[28,7,-15],[24,4,5]],
    ['conveyor-feed','Питание фабрики',[73,8,-15],[28,18,60]],
    ['waste-dump','Отвал вскрыши',[-235,12,155],[80,26,80]],
    ['tailings','Хвостовое хозяйство',[183,2,132],[58,5,58]],
    ['water','Водовод',[242,7,130],[15,15,15]],
    ['concentrate','Концентрат',[208,7,-20],[22,14,25]],
  ];
  const processSteel=M(0x8b969e,{roughness:.65}),processOre=M(0x8a7462,{roughness:1});
  mesh(new THREE.BoxGeometry(14,9,16),processSteel,8,4.5,-15);
  mesh(new THREE.CylinderGeometry(8,4,7,8),M(0xc4a86a,{roughness:.7}),8,12,-15);
  mesh(new THREE.BoxGeometry(26,1.4,4),processSteel,28,7,-15);
  mesh(new THREE.ConeGeometry(40,24,16),processOre,-235,12,155);
  mesh(new THREE.CylinderGeometry(28,30,4,32),processOre,183,2,132);
  mesh(new THREE.CircleGeometry(27,32).rotateX(-Math.PI/2),M(0x587b7e,{roughness:.3}),183,4.1,132);
  mesh(new THREE.CylinderGeometry(6,6,12,16),processSteel,242,6,130);
  mesh(new THREE.BoxGeometry(22,14,25),processSteel,208,7,-20);
  function pipe(a,b){
    const start=new THREE.Vector3(...a),end=new THREE.Vector3(...b),delta=end.clone().sub(start),mid=start.clone().add(end).multiplyScalar(.5);
    const obj=mesh(new THREE.CylinderGeometry(.65,.65,delta.length(),8),M(0x4e9aa9,{roughness:.6}),mid.x,mid.y,mid.z);
    obj.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),delta.normalize());
  }
  pipe([242,2,130],[183,2,132]);pipe([242,2,130],[170,2,40]);pipe([170,2,40],[170,2,0]);
  for(const[id,title,center,size]of processObjects){
    target(id,title,center,size);
    label(`<b>${title}</b><span id="l-${id}">—</span>`,center[0],center[1]+size[1]/2+8,center[2]);
    const el=document.getElementById(`l-${id}`).closest('.lbl');
    el.dataset.object=id;el.style.pointerEvents='auto';el.style.cursor='pointer';el.onclick=()=>selectObject(id);
  }

  function makeBar(id,spanId,read,caption) {
    const parent=$(spanId)?.closest('.lbl');if(!parent)return;
    parent.dataset.object=id;parent.style.pointerEvents='auto';parent.style.cursor='pointer';
    parent.addEventListener('click',e=>{e.stopPropagation();selectObject(id);});
    const maximum=id.startsWith('line-')?125:100;
    const bar=document.createElement('div');bar.className='mini-bar';bar.setAttribute('role','meter');bar.setAttribute('aria-label',caption);bar.setAttribute('aria-valuemin','0');bar.setAttribute('aria-valuemax',String(maximum));bar.innerHTML='<i></i>';parent.appendChild(bar);
    const badge=document.createElement('span');badge.className='event-badge';badge.hidden=true;parent.appendChild(badge);
    bars.push({id,parent,bar,fill:bar.firstChild,badge,read,caption,maximum});
  }
  for(let i=0;i<2;i++)label(`<b>Линия ${i+1}</b><span id="l-line${i+1}">—</span>`,PLANT.x-35,30,PLANT.z+(i?25:-25));
  makeBar('pile-soft','l-ps',d=>d['pile-soft']?.fill_pct,'Заполнение склада мягкой руды');
  makeBar('pile-hard','l-ph',d=>d['pile-hard']?.fill_pct,'Заполнение склада твёрдой руды');
  makeBar('bess','l-bess',d=>d.bess?.soc,'Заряд накопителя');
  makeBar('wind','l-wind',d=>d.wind?.cf_pct,'Мощность ветра к установленной');
  makeBar('pv','l-pv',d=>d.pv?.capacity_mw?100*d.pv.power_mw/d.pv.capacity_mw:null,'Мощность солнца к установленной');
  makeBar('substation','l-grid',d=>d.substation?.grid_cap_mw?100*d.substation.grid_mw/d.substation.grid_cap_mw:null,'Использование предела сети');
  makeBar('line-1','l-line1',d=>d['line-1']?.load_pct,'Загрузка линии 1');
  makeBar('line-2','l-line2',d=>d['line-2']?.load_pct,'Загрузка линии 2');
  for(const [spanId,id]of[['l-pit','pit'],['l-pl','plant'],['l-fl','flotation'],['l-ch','charger-1']]) {
    const el=$(spanId)?.closest('.lbl');if(el){el.dataset.object=id;el.style.pointerEvents='auto';el.style.cursor='pointer';el.onclick=()=>selectObject(id);}
  }
  const truckLabels=[];
  trucks.forEach((t,i)=>{const id=`truck-${String(i+1).padStart(2,'0')}`;const el=label(`<b>Звено ${i+1}</b><span id="l-${id}">—</span>`,0,11,0,t.g);makeBar(id,`l-${id}`,d=>d[id]?.soc,'Заряд звена самосвалов');truckLabels.push({el,id,truck:t.g});});

  const trackMaterial=M(0x665e52,{roughness:1});
  function ribbon(offset,width,color) {
    const pos=[],idx=[],count=240;
    for(let i=0;i<=count;i++){const p=road.getPointAt(i/count),t=road.getTangentAt(i/count),n=new THREE.Vector3(-t.z,0,t.x).normalize();
      for(const side of[-1,1])pos.push(p.x+n.x*(offset+side*width/2),p.y+0.43,p.z+n.z*(offset+side*width/2));
      if(i<count)idx.push(2*i,2*i+1,2*i+2,2*i+1,2*i+3,2*i+2);}
    const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(pos,3));g.setIndex(idx);g.computeVertexNormals();mesh(g,color,0,0,0,scene,false);
  }
  for(const offset of[-3.1,-1.5,1.5,3.1])ribbon(offset,0.36,trackMaterial);
  const stripe=M(0xd1c8ab,{roughness:1,side:THREE.DoubleSide});
  for(let i=4;i<130;i+=3){const p=road.getPointAt(i/130),t=road.getTangentAt(i/130);const mark=mesh(new THREE.BoxGeometry(3,0.06,0.25),stripe,p.x,p.y+0.49,p.z,scene,false);mark.rotation.y=-Math.atan2(t.z,t.x);}
  const gravelMat=M(0x857b68,{map:ctx.gravel,roughness:1});
  for(const [x,z,w,d]of[[PILES.x,PILES.z,65,88],[PLANT.x+17,PLANT.z+15,130,132],[BESS.x+14,BESS.z+9,49,44],[CHARGE.x,CHARGE.z,94,42]])mesh(new THREE.BoxGeometry(w,0.12,d),gravelMat,x,0.08,z,scene,false);
  // Conveyor trestles and sparse handrails, all eligible for batching.
  const steel=M(0x8293a0,{metalness:.45,roughness:.6});
  for(const b of ctx.belts)for(const f of[.15,.5,.85]){const p=b.a.clone().lerp(b.b,f);for(const dz of[-2,2])mesh(new THREE.BoxGeometry(.5,p.y,.5),steel,p.x,p.y/2,p.z+dz);mesh(new THREE.BoxGeometry(.5,.5,5),steel,p.x,p.y-.3,p.z);}
  function fence(x,z,w,d) {
    const points=[[-w/2,-d/2],[w/2,-d/2],[w/2,d/2],[-w/2,d/2],[-w/2,-d/2]];
    for(let e=0;e<4;e++){const a=points[e],b=points[e+1],len=Math.hypot(b[0]-a[0],b[1]-a[1]);
      for(let k=0;k<=Math.ceil(len/9);k++){const f=k/Math.ceil(len/9);mesh(new THREE.BoxGeometry(.35,3.3,.35),steel,x+a[0]+(b[0]-a[0])*f,1.65,z+a[1]+(b[1]-a[1])*f);}
      for(const y of[1.1,2.6])mesh(new THREE.BoxGeometry(e%2?.18:len,.16,e%2?len:.18),steel,x+(a[0]+b[0])/2,y,z+(a[1]+b[1])/2);}
  }
  fence(SUB.x,SUB.z,55,50);fence(BESS.x+14,BESS.z+9,47,43);
  // Rim railing follows the pit, with an opening where the actual haul-road
  // curve first leaves it. Every post/rail is immutable and joins steel batches.
  const rimRadius=PIT_R+3,rimSegments=48,rimStep=2*Math.PI/rimSegments;
  let exitAngle=null,previous=road.getPointAt(0);
  for(let i=1;i<=256;i++){
    const next=road.getPointAt(i/256),before=Math.hypot(previous.x-PIT.x,previous.z-PIT.z),after=Math.hypot(next.x-PIT.x,next.z-PIT.z);
    if(before<rimRadius&&after>=rimRadius){const crossing=previous.clone().lerp(next,(rimRadius-before)/(after-before));exitAngle=Math.atan2(crossing.z-PIT.z,crossing.x-PIT.x);break;}
    previous=next;
  }
  const gateHalfAngle=Math.asin(8/rimRadius);
  const nearExit=(angle,padding=0)=>exitAngle!==null&&Math.abs(Math.atan2(Math.sin(angle-exitAngle),Math.cos(angle-exitAngle)))<gateHalfAngle+padding;
  for(let i=0;i<rimSegments;i++){
    const a=i*rimStep,b=a+rimStep,x=PIT.x+Math.cos(a)*rimRadius,z=PIT.z+Math.sin(a)*rimRadius;
    if(!nearExit(a))mesh(new THREE.BoxGeometry(.35,3,.35),steel,x,1.5,z);
    if(nearExit(a+rimStep/2,rimStep/2))continue;
    const bx=PIT.x+Math.cos(b)*rimRadius,bz=PIT.z+Math.sin(b)*rimRadius,length=Math.hypot(bx-x,bz-z);
    for(const y of[1,2.5]){const rail=mesh(new THREE.BoxGeometry(length,.18,.18),steel,(x+bx)/2,y,(z+bz)/2);rail.rotation.y=-Math.atan2(bz-z,bx-x);}
  }
  function glowTexture(){const c=document.createElement('canvas');c.width=c.height=64;const g=c.getContext('2d'),r=g.createRadialGradient(32,32,1,32,32,31);r.addColorStop(0,'rgba(255,255,255,1)');r.addColorStop(.18,'rgba(255,255,255,.8)');r.addColorStop(1,'rgba(255,255,255,0)');g.fillStyle=r;g.fillRect(0,0,64,64);return new THREE.CanvasTexture(c);}
  const glowMap=glowTexture(),lightMat=new THREE.SpriteMaterial({map:glowMap,color:0xffedbe,transparent:true,depthWrite:false,opacity:0});
  const headlights=[];
  trucks.forEach(t=>{const s=new THREE.Sprite(lightMat.clone());s.position.set(5.8,3,0);s.scale.set(10,5,1);t.g.add(s);headlights.push(s);});
  const lampMat=M(0xaeb8ba,{emissive:0xffd99b,emissiveIntensity:0}),lampSprites=[];lampMat.userData.dynamicColor=true;
  for(const[x,z]of[[-40,95],[55,95],[74,-68],[178,-65],[188,74],[217,95],[290,-29],[287,92]]){
    mesh(new THREE.BoxGeometry(.55,17,.55),steel,x,8.5,z);mesh(new THREE.BoxGeometry(5,.4,.4),steel,x+2.2,17,z);mesh(new THREE.BoxGeometry(2.8,.5,1.3),lampMat,x+4,16.8,z);
    const s=new THREE.Sprite(lightMat.clone());s.position.set(x+4,16.4,z);s.scale.set(12,12,1);scene.add(s);lampSprites.push(s);
  }
  // One inexpensive instanced blob-shadow draw, even when shadow maps are off.
  const fixedShadows=[[PLANT.x+10,.21,PLANT.z,81,84],[PILES.x,.23,PILES.z-20,48,48],[PILES.x,.23,PILES.z+20,48,48],[BESS.x+14,.22,BESS.z+9,46,42],[CHARGE.x,.45,CHARGE.z,84,32],...turbines.map(t=>[t.position.x,.22+Math.max(0,terrainH(t.position.x,t.position.z)),t.position.z,28,14])];
  const shadowMaterial=new THREE.MeshBasicMaterial({map:glowMap,color:0x141a22,transparent:true,opacity:.27,depthWrite:false,side:THREE.DoubleSide});
  const shadowIM=new THREE.InstancedMesh(new THREE.PlaneGeometry(1,1).rotateX(-Math.PI/2),shadowMaterial,fixedShadows.length+trucks.length);scene.add(shadowIM);const shadowDummy=new THREE.Object3D();
  function shadowAt(i,x,y,z,w,d,ry=0){shadowDummy.position.set(x,y,z);shadowDummy.scale.set(w,1,d);shadowDummy.rotation.set(0,ry,0);shadowDummy.updateMatrix();shadowIM.setMatrixAt(i,shadowDummy.matrix);}
  fixedShadows.forEach((p,i)=>shadowAt(i,...p));
  const hardHalo=mesh(new THREE.RingGeometry(20,22,40).rotateX(-Math.PI/2),new THREE.MeshBasicMaterial({color:0xffa94b,transparent:true,opacity:.8,side:THREE.DoubleSide,depthWrite:false}),PILES.x,.3,PILES.z+20,scene,false);hardHalo.visible=false;hardHalo.userData.noMerge=true;
  const gridBeacon=mesh(new THREE.SphereGeometry(2.2,10,8),M(0xffa34e,{emissive:0xff8b32,emissiveIntensity:0}),SUB.x,20,SUB.z,scene,false);gridBeacon.userData.noMerge=true;dynamicRoots.push(gridBeacon);
  const planHalo=mesh(new THREE.RingGeometry(PIT_R-4,PIT_R,64).rotateX(-Math.PI/2),new THREE.MeshBasicMaterial({color:0xffc65c,transparent:true,opacity:.85,side:THREE.DoubleSide,depthWrite:false}),PIT.x,.55,PIT.z,scene,false);planHalo.visible=false;planHalo.userData.noMerge=true;dynamicRoots.push(planHalo);
  const planLabel=label('<b>Изменение плана добычи</b><span id="l-plan">—</span>',PIT.x,34,PIT.z-PIT_R-28);planLabel.hidden=true;
  const steamMaterial=new THREE.SpriteMaterial({map:glowMap,color:0xd8e8f2,transparent:true,opacity:.13,depthWrite:false});
  const steam= mills.map((m,i)=>{const s=new THREE.Sprite(steamMaterial.clone());s.position.set(PLANT.x-30,25,PLANT.z+(i?14:-14));s.scale.set(11,18,1);scene.add(s);return s;});

  function refreshSelection() {
    if(!selected)return;const entry=targets.get(selected),data=lastData[selected];
    $('selection-name').textContent=entry.title;$('selection-source').textContent=`kz.tynys:${selected} · ${getSource()==='live'?'данные Ditto':getSource()==='stale'?'последний снимок · связь потеряна':'запись стенда'}${ctx.getView()==='now'?' · детали оборудования относятся к основному двойнику «Тыныс»':''}`;
    const rows=Object.entries(data||{}).filter(([k])=>FIELDS[k]);
    $('selection-values').innerHTML=rows.length?rows.map(([k,value])=>{const[name,unit]=FIELDS[k];const text=typeof value==='boolean'?(value?'да':'нет'):typeof value==='number'?fmt(value):STATES[value]||String(value);return`<dt>${esc(name)}</dt><dd>${esc(text)} ${esc(unit)}</dd>`;}).join(''):'<dt>Данные</dt><dd>В снимке отсутствуют</dd>';
  }
  function selectObject(id){if(!targets.has(id))return false;selected=id;$('selection-panel').hidden=false;outline.visible=true;refreshSelection();document.querySelectorAll('.lbl[data-object]').forEach(el=>el.classList.toggle('selected',el.dataset.object===id));return true;}
  function clearSelection(){selected=null;outline.visible=false;$('selection-panel').hidden=true;document.querySelectorAll('.lbl.selected').forEach(el=>el.classList.remove('selected'));}
  $('selection-close').onclick=clearSelection;
  const raycaster=new THREE.Raycaster(),pointer=new THREE.Vector2();let press=null;
  renderer.domElement.addEventListener('pointerdown',e=>{press={x:e.clientX,y:e.clientY,button:e.button};});
  renderer.domElement.addEventListener('pointerup',e=>{if(!press||press.button!==0||Math.hypot(e.clientX-press.x,e.clientY-press.y)>5)return;const rect=renderer.domElement.getBoundingClientRect();pointer.set((e.clientX-rect.left)/rect.width*2-1,-(e.clientY-rect.top)/rect.height*2+1);scene.updateMatrixWorld(true);raycaster.setFromCamera(pointer,camera);const hit=raycaster.intersectObjects(proxies,false)[0];if(hit)selectObject(hit.object.userData.objectId);else clearSelection();press=null;});
  const eventObjectBadges=[['pit','l-pit','excavator_failure'],['flotation','l-fl','grade_drop']].map(([id,spanId,kind])=>{const parent=$(spanId)?.closest('.lbl');if(!parent)return null;const badge=document.createElement('span');badge.className='event-badge';badge.hidden=true;parent.appendChild(badge);return{id,kind,parent,badge};}).filter(Boolean);

  function update(data) {
    for(const[id]of processObjects){
      const d=data[id],el=document.getElementById(`l-${id}`);
      const q=d?.flow_m3_h??d?.throughput_tph??d?.inflow_tph;
      el.textContent=d?`${STATES[d.state]||d.state} · ${fmt(q)} ${id==='water'?'м³/ч':'т/ч'}`:'нет данных в записи';
    }
    lastData=data;events=scenarioEvents(data);const active=events.filter(e=>e.active),kinds=new Set(active.map(e=>e.kind));
    const readable=getSource()==='live';const key=JSON.stringify([events,readable,getSource()]);
    if(key!==bannerKey){bannerKey=key;$('scenario-banner').hidden=!events.length;$('scenario-list').replaceChildren();
      for(const e of events){const row=document.createElement('div');row.className='scenario-row';row.dataset.kind=e.kind;const title=document.createElement('span');title.textContent=`${eventName(e)} · ${e.active?'ещё '+fmt(e.remaining)+' ч':'через '+fmt(e.startsIn)+' ч'}`;const b=document.createElement('button');b.className='scenario-cancel';b.dataset.id=String(e.id);b.textContent='отменить';b.disabled=!readable;b.onclick=async()=>{b.disabled=true;try{await cancelEvent(e.id);}catch(err){$('scenario-note').textContent='Не удалось отменить: '+err.message;b.disabled=getSource()!=='live';}};row.append(title,b);$('scenario-list').appendChild(row);}
      $('scenario-note').textContent=readable?'Из сценария двойника · отмена изменяет сценарий стенда':getSource()==='stale'?'Связь потеряна. Снимок сохранён; отмена недоступна.':'События из записи. Отмена доступна на подключённом стенде.';
    }
    for(const b of bars){const raw=b.read(data),valid=typeof raw==='number'&&Number.isFinite(raw),value=valid?clamp(raw,0,b.maximum):0;b.fill.style.width=`${100*value/b.maximum}%`;if(valid)b.bar.setAttribute('aria-valuenow',String(value));else b.bar.removeAttribute('aria-valuenow');b.bar.setAttribute('aria-valuetext',valid?`${fmt(raw)} %`:'нет данных');
      const unavailable=data[b.id]?.available===false,energyBar=b.id==='bess'||b.id.startsWith('truck-'),lowEnergy=energyBar&&value<20,highFill=b.id.startsWith('pile-')&&value>95;
      const warning=unavailable||(valid&&(lowEnergy||highFill)),caution=!warning&&valid&&((energyBar&&value>=20&&value<40)||(!energyBar&&value>=85));
      b.bar.dataset.warning=String(warning);b.bar.dataset.caution=String(caution);b.bar.dataset.status=unavailable?'unavailable':!valid?'unknown':warning?'warning':caution?'caution':'normal';
      if(unavailable)b.bar.setAttribute('aria-valuetext',`${valid?fmt(raw)+' % · ':''}оборудование недоступно`);
      const kind=({'wind':'lull','substation':'kegoc','line-2':'line_trip','bess':'bess_fault','pile-hard':'hard_ore','truck-01':'truck_failure'})[b.id],ev=active.find(e=>b.id.startsWith('line-')?e.kind==='line_trip'&&Number(e.line??2)===Number(b.id.slice(-1)):e.kind===kind||(b.id==='substation'&&e.kind==='tariff_change'));b.badge.hidden=!ev;b.badge.textContent=ev?eventName(ev)+' · '+fmt(ev.remaining)+' ч':'';b.parent.classList.toggle('event-on',!!ev);
    }
    for(let i=0;i<2;i++){const d=data[`line-${i+1}`];$(`l-line${i+1}`).textContent=d?`${fmt(d.feed_tph)} т/ч · ${d.available?'доступна':'авария'}`:'—';}
    for(let i=0;i<trucks.length;i++){const id=`truck-${String(i+1).padStart(2,'0')}`;$(`l-${id}`).textContent=data[id]?`${fmt(data[id].soc)} %`:'—';}
    for(const item of eventObjectBadges){const ev=active.find(e=>e.kind===item.kind);item.badge.hidden=!ev;item.badge.textContent=ev?eventName(ev)+' · '+fmt(ev.remaining)+' ч':'';item.parent.classList.toggle('event-on',!!ev);}
    hardHalo.visible=kinds.has('hard_ore');
    hardHalo.scale.setScalar(Math.max(1,piles.hard.scale.x*1.15));
    const planEvent=active.find(e=>e.kind==='plan_up');planHalo.visible=!!planEvent;planLabel.hidden=!planEvent;
    const planRate=data.pit?.ore_plan_tph;const actualRate=data.pit?.ore_tph;$('l-plan').textContent=typeof planRate==='number'?fmt(planRate)+' т/ч по плану · факт '+fmt(actualRate)+' т/ч':'повышенная подача · модельное событие';
    bessLights.forEach(l=>l.material.emissive.set(data.bess?.available===false?0xff3d31:0x4fd18b));
    ctx.bessBodyMat.color.set(data.bess?.available===false?0xbc493f:0xeef1f3);
    refreshSelection();
  }
  function tick(now,dayK) {
    const kinds=new Set(events.filter(e=>e.active).map(e=>e.kind));
    const gridLimited=kinds.has('kegoc');
    if(planHalo.visible)planHalo.material.opacity=.55+.3*(.5+.5*Math.sin(now/320));gridBeacon.material.emissiveIntensity=gridLimited?(Math.sin(now/160)>0?3:.15):0;gridBeacon.visible=gridLimited;
    flows.grid.im.material.color.set(gridLimited?(Math.sin(now/220)>0?0xffa23d:0xb77a35):0x9a9a9a);
    const wirePulse=gridLimited&&Math.sin(now/220)>0;
    ctx.gridWireMat.color.set(wirePulse?0xffa23d:0x3a3f44);
    ctx.gridWireMat.emissive.set(gridLimited?0xff8b32:0x000000);ctx.gridWireMat.emissiveIntensity=gridLimited?(wirePulse?1.1:.08):0;
    mills.forEach((m,i)=>{const unavailable=lastData[`line-${i+1}`]?.available===false;if(unavailable){m.lamp.material.color.set(0xff4036);m.lamp.material.emissive.set(0xff4036);m.lamp.material.emissiveIntensity=Math.sin(now/190)>0?3:.2;m.speed=0;}
      steam[i].visible=!unavailable&&Number(lastData[`line-${i+1}`]?.feed_tph)>0;steam[i].position.y=25+((now/1500+i*.5)%1)*8;steam[i].material.opacity=.09*(1-((now/1500+i*.5)%1));});
    const night=clamp((.55-dayK)/.55);lampMat.emissiveIntensity=night*2.5;lampSprites.forEach(s=>{s.visible=night>.02;s.material.opacity=night*.6;});
    headlights.forEach((s,i)=>{s.visible=night>.02;s.material.opacity=night*.82;const t=trucks[i].g;shadowAt(fixedShadows.length+i,t.position.x,t.position.y+.12,t.position.z,12,8,t.rotation.y);});shadowIM.instanceMatrix.needsUpdate=true;
    for(const t of targets.values())if(t.follow){t.proxy.position.copy(t.follow.position);t.proxy.position.y+=3;t.proxy.quaternion.copy(t.follow.quaternion);}
    if(selected){const t=targets.get(selected);t.proxy.updateMatrixWorld(true);outline.box.setFromObject(t.proxy);outline.updateMatrixWorld(true);}
    for(const t of truckLabels)t.el.style.visibility=selected===t.id||camera.position.distanceTo(t.truck.position)<230?'visible':'hidden';
    for(const b of bars.filter(b=>b.id.startsWith('line-'))){const t=targets.get(b.id);b.parent.style.visibility=selected===b.id||camera.position.distanceTo(t.proxy.position)<260?'visible':'hidden';}
    const angle=THREE.MathUtils.radToDeg(Math.atan2(camera.position.x-ctx.controls.target.x,camera.position.z-ctx.controls.target.z));$('compass-arrow').style.transform=`rotate(${-angle}deg)`;
  }
  // CSS2DRenderer owns transform; independent CSS translate separates nearby
  // captions after projection without modifying world positions or picking.
  function layoutLabels(){
    const elements=[...document.querySelectorAll('.lbl')];for(const el of elements)el.style.translate='0px 0px';
    const rects=elements.filter(el=>el.style.visibility!=='hidden'&&el.style.display!=='none').map(el=>({el,r:el.getBoundingClientRect()}))
      .filter(({r})=>r.width&&r.height&&r.right>0&&r.left<innerWidth&&r.bottom>0&&r.top<innerHeight)
      .sort((a,b)=>(a.el.dataset.object===selected?-1:b.el.dataset.object===selected?1:a.r.top-b.r.top));
    const placed=[],offsets=[[0,0],[0,-18],[0,18],[-24,0],[24,0],[0,-36],[0,36],[-42,-18],[42,-18],[-42,18],[42,18],[0,-58],[0,58]];
    for(const {el,r}of rects){let best=[0,0],least=Infinity;for(const [dx,dy]of offsets){const x=r.left+dx,y=r.top+dy;let overlap=0;
        for(const p of placed)overlap+=Math.max(0,Math.min(x+r.width+4,p.right)-Math.max(x-4,p.left))*Math.max(0,Math.min(y+r.height+4,p.bottom)-Math.max(y-4,p.top));
        if(x<3||y<3||x+r.width>innerWidth-3||y+r.height>innerHeight-3)overlap+=100000;
        if(overlap<least){least=overlap;best=[dx,dy];}if(overlap===0)break;}
      el.style.translate=`${best[0]}px ${best[1]}px`;placed.push({left:r.left+best[0],right:r.right+best[0],top:r.top+best[1],bottom:r.bottom+best[1]});}
  }
  return {update,tick,layoutLabels,selectObject,clearSelection,dynamicRoots,targets,get selected(){return selected;},get events(){return events;},get headlights(){return headlights;},get visuals(){return{hardOreHighlighted:hardHalo.visible,gridLimited:gridBeacon.visible,gridWireColor:ctx.gridWireMat.color.getHex(),capMw:lastData.substation?.grid_cap_mw,lineSteam:steam.map(s=>s.visible)};}};
}
