// «Тыныс 3D»: трёхмерная сцена рудника Актогай.
// Данные: на стенде — живые двойники Eclipse Ditto (через прокси /ditto);
// если Ditto недоступен (страница открыта отдельно) — запись 96 ч работы того же стенда (trace.json).
// Масштаб схематичный: 1 ед. ≈ 10 м.
import * as THREE from 'three';
import { OrbitControls } from './vendor/OrbitControls.js';
import { CSS2DRenderer, CSS2DObject } from './vendor/CSS2DRenderer.js';
import { installSceneDetails, mergeStaticMeshes } from './scene-details.js';

const NS = 'kz.tynys';
const NAMES = ['site', 'pit', 'plant', 'energy', 'geology', 'coordinator', 'scenario', 'shadow-v0', 'shadow-v1', 'pile-soft', 'pile-hard', 'line-1', 'line-2',
  'flotation', 'wind', 'pv', 'bess', 'substation', 'shovel-1', 'shovel-2',
  'crusher','conveyor-crushed','conveyor-feed','waste-dump','water','tailings','concentrate',
  ...Array.from({ length: 4 }, (_, i) => `charger-${i+1}`), ...Array.from({ length: 14 }, (_, i) => `truck-${String(i + 1).padStart(2, '0')}`)];
const $ = id => document.getElementById(id);
const fmt = (x, k = 0) => (x == null || isNaN(x)) ? '—' : Number(x).toLocaleString('ru-RU', { maximumFractionDigits: k, minimumFractionDigits: k });

// ---------- источник данных ----------
let D = {};
let source = 'connecting', lastLiveAt = null;
let view = 'tynys';         // 'now' — как сейчас (V0), 'tynys' — с координатором (V2)
const v = (n, f, d = 0) => { const x = D[n] && D[n][f]; return x ?? d; };
async function pollLive() {
  const r = await fetch(`ditto/api/2/things?ids=${NAMES.map(n => NS + ':' + n).join(',')}&fields=thingId,features`);
  if (!r.ok) throw new Error(r.status);
  const data = await r.json(); if (!Array.isArray(data) || !data.length) throw new Error('empty');
  const o = {}; for (const t of data) { const f = {}; for (const [k, x] of Object.entries(t.features || {})) f[k] = x.properties && x.properties.value; o[t.thingId.split(':')[1]] = f; }
  if(!o.site)throw new Error('В ответе нет двойника site');
  D = o; source = 'live'; lastLiveAt = Date.now(); sourceLabel();
}
let TRACE = null, tStart = 0;
async function loadTrace() { if (window.TYNYS_TRACE) return window.TYNYS_TRACE; const r = await fetch('trace.json'); return r.json(); }
function pollTrace() { const k = ((performance.now() - tStart) / 1000 / 4.0) % TRACE.length; D = TRACE[Math.floor(k)]; }
async function start() {
  try { if (window.TYNYS_TRACE) throw 0; await pollLive(); setInterval(() => pollLive().catch(() => {source='stale';sourceLabel();}), 1500); }
  catch (e) { try { TRACE = await loadTrace(); if(!Array.isArray(TRACE)||!TRACE.length)throw new Error('Нет записи');source='replay';tStart=performance.now();pollTrace();setInterval(pollTrace,250); }
    catch {source='unavailable';} sourceLabel(); }
}
function sourceLabel(){const text=source==='live'?'● живые двойники OpenEgiz':source==='replay'?'● запись стенда · не живые данные':source==='stale'?`● связь потеряна · снимок ${new Date(lastLiveAt).toLocaleTimeString('ru-RU')}`:source==='unavailable'?'● данные недоступны':'подключение…';$('src').textContent=text;$('source-line').textContent=text+' · движение самосвалов ускорено ×6';document.querySelectorAll('[data-scenario]').forEach(b=>b.disabled=source!=='live');}
async function cancelScenarioEvent(id){
  if(source!=='live')throw new Error('Отмена доступна только при связи с Ditto');
  await pollLive();let events;try{const raw=v('scenario','events','[]');events=Array.isArray(raw)?raw:JSON.parse(raw);}catch{throw new Error('Некорректный сценарий');}
  const body={events:{properties:{value:JSON.stringify(events.filter(e=>String(e.id)!==String(id)))}},rev:{properties:{value:Number(v('scenario','rev',0))+1}},goal:{properties:{value:v('scenario','goal','green')}}};
  const r=await fetch(`ditto/api/2/things/${NS}:scenario/features`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});if(!r.ok)throw new Error(`Ditto: ${r.status}`);await pollLive();hud();
}
const SCENARIOS={lull:[3,24],line_trip:[0,8],kegoc:[2,4],hard_ore:[0,72],plan_up:[0,48],bess_fault:[0,12],truck_failure:[0,12],excavator_failure:[0,12],grade_drop:[0,24],tariff_change:[0,24],crusher_fault:[0,8],conveyor_fault:[0,4],water_fault:[0,4]};
async function addScenarioEvent(kind){
  const feedback=$('scenario-feedback'),buttons=[...document.querySelectorAll('[data-scenario]')];
  if(source!=='live'){feedback.textContent='Запуск доступен при связи с живыми двойниками Ditto.';return;}
  buttons.forEach(b=>b.disabled=true);feedback.textContent='Передаю сценарий в Ditto…';
  try{
    await pollLive();const t=Number(v('site','sim_hour',0));let events;const raw=v('scenario','events','[]');events=Array.isArray(raw)?raw:JSON.parse(raw||'[]');
    const [lead,dur]=SCENARIOS[kind];if(!Number.isFinite(t)||!Number.isFinite(dur))throw new Error('Нет модельного времени');
    const parameter=(id,fallback)=>{
      const el=$(id);if(!el||!el.value.trim())return fallback;
      if(!el.checkValidity()||!Number.isFinite(Number(el.value)))throw new Error('Проверьте параметры сценария');
      return Number(el.value);
    };
    events=events.filter(e=>Number(e.t0)+Number(e.dur)>t);
    const event={kind,t0:t+1+lead,dur:parameter('scenario-duration',dur),id:Date.now()};
    if(kind==='line_trip')event.line=parameter('scenario-line',2);
    if(kind==='kegoc')event.grid_drop_mw=parameter('scenario-kegoc-mw',80);
    if(kind==='truck_failure'||kind==='excavator_failure')event.loss_pct=parameter('scenario-loss-pct',30);
    if(kind==='grade_drop')event.drop_pct=parameter('scenario-grade-pct',10);
    if(kind==='tariff_change')event.change_pct=parameter('scenario-tariff-pct',20);
    if(kind==='plan_up')event.mine_mult=parameter('scenario-plan-pct',1.1);
    events.push(event);
    const body={events:{properties:{value:JSON.stringify(events)}},rev:{properties:{value:Number(v('scenario','rev',0))+1}},goal:{properties:{value:v('scenario','goal','green')}}};
    const r=await fetch('ditto/api/2/things/'+NS+':scenario/features',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});if(!r.ok)throw new Error('Ditto: '+r.status);
    await pollLive();hud();feedback.textContent='Сценарий записан в двойник; 3D покажет его по модельному времени.';
  }catch(err){feedback.textContent='Не удалось запустить: '+err.message;}
  finally{buttons.forEach(b=>b.disabled=source!=='live');}
}
document.querySelectorAll('[data-scenario]').forEach(b=>b.addEventListener('click',()=>addScenarioEvent(b.dataset.scenario)));
start();

// энергобаланс «как сейчас» (V0) или «Тыныс» (V2)
function E() {
  const ren = v('energy', 'renew_mw');
  if (view === 'now') { const g = v('shadow-v0', 'grid_mw'), c = v('shadow-v0', 'curtail_mw'); return { grid: g, curtail: c, used: ren - c, co2: g * 0.79, charge: 0 }; }
  const g = v('energy', 'grid_mw'), c = v('energy', 'curtail_mw'); return { grid: g, curtail: c, used: ren - c, co2: g * 0.79, charge: v('energy', 'charge_mw') };
}

// ---------- рендер ----------
const Q = new URLSearchParams(location.search);
// Программный WebGL (нет GPU: SwiftShader / llvmpipe) или телефон → облегчённый режим:
// без теней, меньше пикселей, ~15 кадров/с — сцена остаётся живой и не душит процессор.
const SOFT_GL = (() => { try { const g = document.createElement('canvas').getContext('webgl2') || document.createElement('canvas').getContext('webgl');
  const e = g.getExtension('WEBGL_debug_renderer_info'); const r = e ? g.getParameter(e.UNMASKED_RENDERER_WEBGL) : g.getParameter(g.RENDERER);
  return /swiftshader|llvmpipe|software|softpipe/i.test(r); } catch (e) { return false; } })();
const LOW = Q.get('q') === 'low' || (Q.get('q') !== 'high' && (SOFT_GL || /Mobi|Android|iPhone/i.test(navigator.userAgent)));
document.body.classList.toggle('low-render',LOW);
const renderer = new THREE.WebGLRenderer({ canvas: $('c'), antialias: !LOW, powerPreference: 'high-performance' });
renderer.setPixelRatio(LOW ? 0.9 : Math.min(devicePixelRatio, 2));
renderer.shadowMap.enabled = !LOW; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.outputColorSpace = THREE.SRGBColorSpace;
const labels = new CSS2DRenderer();
labels.domElement.style.cssText = 'position:fixed;inset:0;pointer-events:none;z-index:2';
document.body.appendChild(labels.domElement);

const scene = new THREE.Scene();
scene.fog = new THREE.FogExp2(0xd2dde3, 0.00075);
const camera = new THREE.PerspectiveCamera(42, 1, 1, 9000);
const HOME = { pos: new THREE.Vector3(300, 280, 460), tgt: new THREE.Vector3(20, -20, -20) };
camera.position.copy(HOME.pos);
const controls = new OrbitControls(camera, renderer.domElement);
controls.target.copy(HOME.tgt); controls.enableDamping = true; controls.maxPolarAngle = Math.PI * 0.48;
controls.minDistance = 30; controls.maxDistance = 2200;

const hemi = new THREE.HemisphereLight(0xcfe3ff, 0x8a7458, 0.9); scene.add(hemi);
const nightAmbient=new THREE.AmbientLight(0x88a8d4,0);scene.add(nightAmbient);
const sun = new THREE.DirectionalLight(0xfff1d6, 2.6);
sun.castShadow = true; sun.shadow.mapSize.set(LOW ? 1024 : 4096, LOW ? 1024 : 4096); sun.shadow.bias = -0.0004; sun.shadow.normalBias = 0.8;
Object.assign(sun.shadow.camera, { left: -480, right: 480, top: 480, bottom: -480, near: 10, far: 2500 });
scene.add(sun, sun.target);
function resize() { const w = innerWidth, h = innerHeight; renderer.setSize(w, h, false); labels.setSize(w, h); camera.aspect = w / h;camera.fov=THREE.MathUtils.radToDeg(2*Math.atan(Math.tan(THREE.MathUtils.degToRad(42)/2)/Math.min(1,w/h)));camera.updateProjectionMatrix(); }
addEventListener('resize', resize); resize();

// ---------- процедурные текстуры ----------
const hash = (x, y) => { const s = Math.sin(x * 127.1 + y * 311.7) * 43758.5453; return s - Math.floor(s); };
function vnoise(x, y) { const xi = Math.floor(x), yi = Math.floor(y), xf = x - xi, yf = y - yi, u = xf * xf * (3 - 2 * xf), w = yf * yf * (3 - 2 * yf);
  const a = hash(xi, yi), b = hash(xi + 1, yi), c = hash(xi, yi + 1), d = hash(xi + 1, yi + 1); return a + (b - a) * u + (c - a) * w + (a - b - c + d) * u * w; }
const fbm = (x, y) => { let s = 0, a = 0.5, f = 1; for (let i = 0; i < 5; i++) { s += a * vnoise(x * f, y * f); f *= 2; a *= 0.5; } return s; };
function tex(size, fn) {
  const c = document.createElement('canvas'); c.width = c.height = size; const g = c.getContext('2d'); const img = g.createImageData(size, size);
  for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) { const [r, gg, b] = fn(x, y); img.data.set([r, gg, b, 255], (y * size + x) * 4); }
  g.putImageData(img, 0, 0); const t = new THREE.CanvasTexture(c); t.wrapS = t.wrapT = THREE.RepeatWrapping; t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = LOW?1:8; return t;
}
// бесшовный шум: периодический по размеру тайла
const tile = (x, y, s, sc) => { const fx = x / s, fy = y / s; const a = fbm(x / sc, y / sc), b = fbm((x - s) / sc, y / sc), c = fbm(x / sc, (y - s) / sc), d = fbm((x - s) / sc, (y - s) / sc);
  return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy; };
const steppe = tex(256, (x, y) => { const n = tile(x, y, 256, 26), g = hash(x, y) * 0.16, tuft = hash(x * 3, y * 7) > 0.97 ? -0.18 : 0; const k = 0.8 + 0.28 * n + g + tuft;
  return [182 * k, 160 * k, 112 * k]; });
const rock = tex(256, (x, y) => { const n = tile(x, y, 256, 12), g = hash(x, y) * 0.22; const k = 0.68 + 0.4 * n + g; return [160 * k, 140 * k, 120 * k]; });
const gravel = tex(128, (x, y) => { const k = 0.72 + 0.38 * hash(x, y); return [118 * k, 108 * k, 96 * k]; });

// Software WebGL does not benefit from per-pixel metal/roughness BRDFs on
// these matte surfaces. Lambert keeps sunlight, hemisphere light, textures,
// vertex colours and emissive fault signals; HIGH retains the PBR materials.
const M = (c, o = {}) => {
  if(!LOW)return new THREE.MeshStandardMaterial({color:c,roughness:.85,metalness:.05,...o});
  const {roughness,metalness,...diffuse}=o;
  return new THREE.MeshLambertMaterial({color:c,...diffuse});
};
function mesh(geo, mat, x = 0, y = 0, z = 0, parent = scene, shadow = true) {
  const m = new THREE.Mesh(geo, mat); m.position.set(x, y, z); m.castShadow = shadow; m.receiveShadow = true; parent.add(m); return m;
}
function label(html, x, y, z, parent = scene) {
  const d = document.createElement('div'); d.className = 'lbl'; d.innerHTML = html;
  const o = new CSS2DObject(d); o.position.set(x, y, z); parent.add(o); labels.domElement.appendChild(d); return d;
}
function setInst(im, i, x, y, z, sx = 1, sy = 1, sz = 1, rx = 0, ry = 0) { const o = setInst.o || (setInst.o = new THREE.Object3D()); o.position.set(x, y, z); o.rotation.set(rx, ry, 0); o.scale.set(sx, sy, sz); o.updateMatrix(); im.setMatrixAt(i, o.matrix); }

// ---------- небо ----------
const skyMat = new THREE.ShaderMaterial({
  side: THREE.BackSide, depthWrite: false, fog: false,
  uniforms: { top: { value: new THREE.Color(0x3f7fc0) }, bot: { value: new THREE.Color(0xe3e9ea) }, sunDir: { value: new THREE.Vector3(0, 1, 0) }, day: { value: 1 } },
  vertexShader: 'varying vec3 vP; void main(){ vP = normalize(position); gl_Position = projectionMatrix*modelViewMatrix*vec4(position,1.0); }',
  fragmentShader: `uniform vec3 top; uniform vec3 bot; uniform vec3 sunDir; uniform float day; varying vec3 vP;
    void main(){ float h = clamp(vP.y*1.8+0.06,0.0,1.0); vec3 c = mix(bot, top, pow(h,0.65));
      vec3 sd = normalize(sunDir); float s = max(dot(vP, sd),0.0);
      c += vec3(1.0,0.9,0.7)*(pow(s,900.0)*4.0 + pow(s,10.0)*0.22)*smoothstep(-0.05,0.1,sd.y);
      float hz = pow(1.0-abs(vP.y),10.0); c += vec3(1.0,0.55,0.3)*hz*0.5*smoothstep(0.0,0.3,sd.y+0.1)*(1.0-smoothstep(0.15,0.5,sd.y));
      gl_FragColor = vec4(c,1.0); }`,
});
scene.add(new THREE.Mesh(new THREE.SphereGeometry(6000, LOW?20:32, LOW?12:16), skyMat));
const starPos = []; for (let k = 0; k < 1500; k++) { const a = hash(k, 1) * 6.283, b = Math.acos(hash(k, 2) * 0.9 + 0.1); starPos.push(5500 * Math.sin(b) * Math.cos(a), 5500 * Math.cos(b), 5500 * Math.sin(b) * Math.sin(a)); }
const stars = new THREE.Points(new THREE.BufferGeometry().setAttribute('position', new THREE.Float32BufferAttribute(starPos, 3)),
  new THREE.PointsMaterial({ color: 0xffffff, size: 1.6, sizeAttenuation: false, transparent: true, opacity: 0, fog: false }));
scene.add(stars);

// ---------- рельеф ----------
const PIT = new THREE.Vector3(-130, 0, 10), PIT_R = 100, PIT_D = 78, BENCH = 12, SITE_R = 520;
let geologyPit, geologyCells = [];
const geologyMarkers = new THREE.Group(); scene.add(geologyMarkers);
async function loadGeology() {
  if(window.TYNYS_TRACE)return; // archival standalone scene has no live geology
  try {
    const response=await fetch('ditto/api/2/things/kz.tynys:geology/attributes/model');
    if(!response.ok)throw new Error('GeoMet недоступен');
    const data=await response.json();
    if(!Array.isArray(data.cells)||!data.cells.length)throw new Error('Нет проб');
    geologyCells=data.cells;
    const min=Math.min(...geologyCells.map(c=>c.bwi)),max=Math.max(...geologyCells.map(c=>c.bwi));
    const positions=geologyPit.geometry.attributes.position, colors=geologyPit.geometry.attributes.color;
    const color=new THREE.Color();
    for(let i=0;i<positions.count;i++){
      const u=positions.getX(i)/PIT_R,vv=positions.getZ(i)/PIT_R,depth=-positions.getY(i)/PIT_D;
      let closest=null,distance=Infinity;
      for(const c of geologyCells){const d=(u-c.u)**2+(vv-c.v)**2+(depth-c.depth)**2;if(d<distance){distance=d;closest=c;}}
      color.setHSL(.48*(1-(closest.bwi-min)/(max-min)),.62,.48);
      colors.setXYZ(i,color.r,color.g,color.b);
    }
    colors.needsUpdate=true;
    for(const c of geologyCells){
      const marker=new THREE.Mesh(new THREE.SphereGeometry(2.5,8,6),new THREE.MeshBasicMaterial({color:0xffffff,depthTest:false}));
      marker.position.set(PIT.x+c.u*PIT_R,-c.depth*PIT_D,PIT.z+c.v*PIT_R);
      marker.userData.cellId=c.id;marker.visible=false;marker.renderOrder=50;geologyMarkers.add(marker);
    }
    const legend=document.createElement('aside');legend.id='geology-legend';
    Object.assign(legend.style,{position:'fixed',left:'16px',bottom:'100px',zIndex:5,maxWidth:'330px',padding:'10px 14px',background:'#102830e8',color:'#fff',font:'12px system-ui',borderRadius:'10px',pointerEvents:'none'});
    const title=document.createElement('strong');title.textContent=`GeoMet · BWi ${fmt(min,1)}–${fmt(max,1)} кВт·ч/т`;
    const gradient=document.createElement('div');Object.assign(gradient.style,{height:'6px',margin:'6px 0',background:'linear-gradient(90deg,#2ec4a0,#d7cd30,#d74b30)'});
    const active=document.createElement('p');active.id='geology-active';
    const note=document.createElement('small');note.textContent='Мягче → твёрже. Белые точки — текущие забои. Пространственный аналог, не геология Актогая. Hoffimann et al. · CC BY 4.0';
    legend.append(title,gradient,active,note);document.body.appendChild(legend);
    // Легенда стоит над блоком «Почему так» и не перекрывает его при любой длине текста.
    const placeLegend=()=>{const w=document.getElementById('why');if(w&&w.offsetParent!==null)legend.style.bottom=`${w.offsetHeight+16+12}px`;};
    placeLegend();setInterval(placeLegend,500);
  } catch(e) { console.info('GeoMet: '+e.message); }
}
function terrainH(x, z) {
  const r = Math.hypot(x - PIT.x, z - PIT.z); const k = THREE.MathUtils.smoothstep(r, SITE_R, SITE_R + 420);
  return k * (fbm(x / 300, z / 300) * 170 - 50 + fbm(x / 70, z / 70) * 14);
}
{
  const site = new THREE.RingGeometry(PIT_R, SITE_R + 2, LOW?96:160, LOW?6:14); site.rotateX(-Math.PI / 2);
  const p = site.attributes.position, uv = site.attributes.uv; for (let i = 0; i < p.count; i++) uv.setXY(i, p.getX(i) / 40, p.getZ(i) / 40);
  mesh(site, M(0xffffff, { map: steppe, roughness: 1 }), PIT.x, 0, PIT.z, scene, false);
  const outer = new THREE.RingGeometry(SITE_R, 4200, LOW?64:260, LOW?20:70); outer.rotateX(-Math.PI / 2);
  const op = outer.attributes.position, ouv = outer.attributes.uv;
  for (let i = 0; i < op.count; i++) { const x = op.getX(i) + PIT.x, z = op.getZ(i) + PIT.z; op.setY(i, terrainH(x, z)); ouv.setXY(i, x / 40, z / 40); }
  outer.computeVertexNormals();
  mesh(outer, M(0xffffff, { map: steppe, roughness: 1 }), PIT.x, 0, PIT.z, scene, false);

  // карьер: уступы «полка — откос»
  const prof = [new THREE.Vector2(0, -PIT_D)]; const n = Math.round(PIT_D / BENCH);
  for (let i = 0; i <= n; i++) { const y = -PIT_D + i * BENCH, r0 = 26 + i * (PIT_R - 30) / n; prof.push(new THREE.Vector2(r0, y), new THREE.Vector2(r0 + 3.8, Math.min(0, y + BENCH))); }
  prof.push(new THREE.Vector2(PIT_R, 0));
  const lg = new THREE.LatheGeometry(prof, LOW?96:180);
  const pos = lg.attributes.position, col = [], c = new THREE.Color(), uvs = lg.attributes.uv;
  for (let i = 0; i < pos.count; i++) {
    const y = -pos.getY(i), t = y / PIT_D, ang = Math.atan2(pos.getZ(i), pos.getX(i));
    const ox = fbm(ang * 4 + 7, y / 18);   // бурая зона окисления сверху, серые сульфиды в глубине
    c.setRGB(0.92 - 0.38 * t + 0.12 * ox, 0.74 - 0.22 * t + 0.06 * ox, 0.56 - 0.1 * t);
    if ((y % BENCH) < 0.9) c.multiplyScalar(1.18);
    col.push(c.r, c.g, c.b); uvs.setXY(i, ang / Math.PI * 14, y / 9);
  }
  lg.setAttribute('color', new THREE.Float32BufferAttribute(col, 3)); lg.computeVertexNormals();
  geologyPit = mesh(lg, M(0xffffff,{ vertexColors: true, map: rock, side: THREE.BackSide, roughness: 1, metalness: 0, flatShading: true }), PIT.x, 0, PIT.z, scene, false);
  mesh(new THREE.CircleGeometry(27, 48).rotateX(-Math.PI / 2), M(0x8a7a66, { map: gravel }), PIT.x, -PIT_D + 0.1, PIT.z, scene, false);
  mesh(new THREE.CircleGeometry(10, 40).rotateX(-Math.PI / 2), new THREE.MeshStandardMaterial({ color: 0x3d8f86, roughness: 0.06, metalness: 0.5 }), PIT.x + 12, -PIT_D + 0.3, PIT.z - 9, scene, false);
  // террасированные отвалы пустой породы
  for (const [x, z, r, h] of [[-350, -170, 95, 36], [-390, 160, 80, 30], [-90, -260, 66, 26]]) {
    const g = new THREE.Group(); g.position.set(x, 0, z); scene.add(g);
    for (let k = 0; k < 3; k++) mesh(new THREE.CylinderGeometry(r * (0.95 - k * 0.22) - 7, r * (1 - k * 0.22), h / 3, LOW?32:56), M(0xd8c7ad, { map: rock, roughness: 1 }), 0, h / 6 + k * h / 3, 0, g);
  }
}
label('<b>Карьер Актогай</b><span id="l-pit">—</span>', PIT.x, 22, PIT.z - PIT_R);

// ---------- дорога ----------
const PILES = new THREE.Vector3(40, 0, -15);
const roadPts = [];
for (let i = 0; i <= 80; i++) { const s = i / 80, a = -0.5 + s * Math.PI * 2.35, r = 28 + s * (PIT_R - 28); roadPts.push(new THREE.Vector3(PIT.x + Math.cos(a) * r, -PIT_D + 1 + s * PIT_D, PIT.z + Math.sin(a) * r)); }
const rim = roadPts[roadPts.length - 1];
roadPts.push(new THREE.Vector3(rim.x + 30, 0.4, rim.z + 6), new THREE.Vector3(-10, 0.4, -2), new THREE.Vector3(PILES.x - 26, 0.4, PILES.z + 6));
const road = new THREE.CatmullRomCurve3(roadPts);
const ROAD_LEN = road.getLength();   // ед. сцены (≈ 10 м)
const TRUCK_TIMELAPSE = 6;            // показ движения ускорен ×6
{
  const N = LOW?360:700, pos = [], idx = [], uv = [];
  for (let i = 0; i <= N; i++) {
    const p = road.getPointAt(i / N), t = road.getTangentAt(i / N), s = new THREE.Vector3(-t.z, 0, t.x).normalize().multiplyScalar(5);
    pos.push(p.x + s.x, p.y + 0.35, p.z + s.z, p.x - s.x, p.y + 0.35, p.z - s.z); uv.push(0, i / 5, 1, i / 5);
    if (i < N) idx.push(2 * i, 2 * i + 1, 2 * i + 2, 2 * i + 1, 2 * i + 3, 2 * i + 2);
  }
  const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3)); g.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
  g.setIndex(idx); g.computeVertexNormals(); mesh(g, M(0x9b8f80, { map: gravel, side: THREE.DoubleSide, roughness: 1 }), 0, 0, 0, scene, false);
  const pts = road.getSpacedPoints(LOW?160:320), berm = new THREE.InstancedMesh(new THREE.SphereGeometry(1.4, 6, 4), M(0x8c7a64, { roughness: 1 }), pts.length);
  pts.forEach((p, i) => { const t = road.getTangentAt(i / (pts.length - 1)), s = new THREE.Vector3(-t.z, 0, t.x).normalize().multiplyScalar(-6.2); setInst(berm, i, p.x + s.x, p.y + 0.6, p.z + s.z, 1.3, 0.6, 1.5); });
  scene.add(berm);
}

// ---------- экскаваторы ----------
const shovels = [];
for (const [dx, dz] of [[-12, 6], [10, -12]]) {
  const g = new THREE.Group(); g.position.set(PIT.x + dx, -PIT_D + 0.3, PIT.z + dz); scene.add(g);
  mesh(new THREE.BoxGeometry(10, 2.4, 3), M(0x2a2a2a), 0, 1.2, 3, g); mesh(new THREE.BoxGeometry(10, 2.4, 3), M(0x2a2a2a), 0, 1.2, -3, g);
  const body = new THREE.Group(); body.position.y = 2.6; g.add(body);
  mesh(new THREE.BoxGeometry(9, 5, 7), M(0xf2b632, { metalness: 0.3, roughness: 0.5 }), -1, 2.5, 0, body);
  mesh(new THREE.BoxGeometry(3, 3.2, 3), M(0x2b3440, { metalness: 0.5, roughness: 0.2 }), 3.5, 6.6, 2, body);
  const boom = mesh(new THREE.BoxGeometry(14, 1.4, 1.4), M(0xf2b632), 8, 7, 0, body); boom.rotation.z = 0.55;
  const stick = mesh(new THREE.BoxGeometry(1.2, 9, 1.2), M(0xd99a1c), 14, 6, 0, body); stick.rotation.z = -0.3;
  mesh(new THREE.BoxGeometry(4, 3.5, 5), M(0x4b4b4b, { metalness: 0.7 }), 15.5, 1.8, 0, body);
  shovels.push(body);
}

// ---------- зарядка и самосвалы ----------
const CHARGE = new THREE.Vector3(10, 0, 110);
const chargingArea = new THREE.Group(); scene.add(chargingArea);
mesh(new THREE.BoxGeometry(84, 0.4, 32), M(0x5f666e, { roughness: 0.9 }), CHARGE.x, 0.2, CHARGE.z, chargingArea, false);
const chargers = [];
for (let i = 0; i < 4; i++) {
  const x = CHARGE.x - 30 + i * 20;
  mesh(new THREE.BoxGeometry(4, 8, 3), M(0xe9edf0, { metalness: 0.3 }), x, 4, CHARGE.z - 14, chargingArea);
  mesh(new THREE.BoxGeometry(14, 0.6, 10), M(0x9aa3ab, { metalness: 0.6 }), x, 11.5, CHARGE.z - 8, chargingArea);
  for (const dz of [-12.5, -3.5]) mesh(new THREE.BoxGeometry(0.6, 11.5, 0.6), M(0x9aa3ab, { metalness: 0.6 }), x - 6.5, 5.7, CHARGE.z + dz, chargingArea);
  chargers.push(mesh(new THREE.BoxGeometry(3.2, 1, 0.3), M(0x111111, { emissive: 0x2aa7d6, emissiveIntensity: 0 }), x, 6, CHARGE.z - 12.4, chargingArea));
}
const chargeLabel=label('<b>Зарядка электросамосвалов</b><span id="l-ch">—</span>', CHARGE.x, 20, CHARGE.z);
const trucks = [];
const oreMat = { soft: M(0x86a873, { roughness: 1 }), hard: M(0xb0684a, { roughness: 1 }) };
const yellow = M(0xffbf1a, { metalness: 0.25, roughness: 0.45 }), dark = M(0x1c1c1c, { roughness: 0.9 });
for (let i = 0; i < 14; i++) {
  const g = new THREE.Group(); scene.add(g);
  mesh(new THREE.BoxGeometry(10, 1.6, 4.4), dark, 0, 2.6, 0, g);
  const bed = new THREE.Group(); bed.position.set(-1.2, 4.6, 0); g.add(bed);
  mesh(new THREE.BoxGeometry(7.4, 0.5, 5.6), yellow, 0, -1.3, 0, bed);
  mesh(new THREE.BoxGeometry(7.4, 2.6, 0.4), yellow, 0, 0, 2.6, bed); mesh(new THREE.BoxGeometry(7.4, 2.6, 0.4), yellow, 0, 0, -2.6, bed);
  mesh(new THREE.BoxGeometry(0.4, 2.6, 5.6), yellow, -3.5, 0, 0, bed);
  mesh(new THREE.BoxGeometry(3.4, 0.4, 5.6), yellow, 4.6, 1.4, 0, bed);
  mesh(new THREE.BoxGeometry(2.2, 2.2, 1.8), yellow, 4.4, 4.8, 1.6, g);
  mesh(new THREE.BoxGeometry(2.25, 1, 1.85), M(0x24313d, { metalness: 0.6, roughness: 0.15 }), 4.5, 5.3, 1.6, g);
  mesh(new THREE.BoxGeometry(1.6, 2.6, 4.6), M(0x2f6fb0, { metalness: 0.4 }), 4.6, 3.1, -0.6, g);
  const load = mesh(new THREE.SphereGeometry(3, LOW?8:12, LOW?4:6, 0, Math.PI * 2, 0, Math.PI / 2), oreMat.hard, -1.2, 4.6, 0, g); load.scale.set(1.2, 0.75, 0.9);
  for (const [x, z] of [[3.6, 2.5], [3.6, -2.5], [-2.8, 2.5], [-2.8, -2.5], [-2.8, 3.6], [-2.8, -3.6]]) mesh(new THREE.CylinderGeometry(1.6, 1.6, 1.2, LOW?10:16).rotateX(Math.PI / 2), dark, x, 1.6, z, g);
  // Charging is indicated by emissive panels; avoid fourteen dynamic point lights.
  const glow = new THREE.Object3D(); glow.intensity=0; glow.position.y = 9; g.add(glow);
  g.scale.setScalar(1.6);   // увеличены для наглядности: в масштабе карьера настоящий самосвал — точка
  trucks.push({ g, load, glow, phase: i / 14 });
}
const dustIM = new THREE.InstancedMesh(new THREE.SphereGeometry(1, 8, 6), new THREE.MeshStandardMaterial({ color: 0xcdb89a, transparent: true, opacity: 0.22, depthWrite: false }), 14 * 8);
scene.add(dustIM);
dustIM.visible=!LOW;

// ---------- склады, конвейеры, фабрика ----------
const piles = {};
for (const [d, dz] of [['soft', -20], ['hard', 20]]) {
  const geo = new THREE.ConeGeometry(20, 15, LOW?32:56, LOW?3:5); const p = geo.attributes.position;
  for (let i = 0; i < p.count; i++) { const k = 1 + 0.07 * (fbm(p.getX(i) / 4, p.getZ(i) / 4) - 0.5); p.setX(i, p.getX(i) * k); p.setZ(i, p.getZ(i) * k); }
  geo.computeVertexNormals(); piles[d] = mesh(geo, oreMat[d], PILES.x, 7.5, PILES.z + dz);
}
label('<b>Склад мягкой руды</b><span id="l-ps">—</span>', PILES.x - 10, 34, PILES.z - 34);
label('<b>Склад твёрдой руды</b><span id="l-ph">—</span>', PILES.x - 10, 14, PILES.z + 36);
const PLANT = new THREE.Vector3(120, 0, -5);
const belts = [];
for (const dz of [-20, 20]) {
  const a = new THREE.Vector3(PILES.x + 18, 2, PILES.z + dz), b = new THREE.Vector3(PLANT.x - 32, 13, PLANT.z + (dz < 0 ? -14 : 14));
  const len = a.distanceTo(b), mid = a.clone().add(b).multiplyScalar(0.5);
  const m = mesh(new THREE.BoxGeometry(len, 1.2, 3.4), M(0x9aa3ab, { metalness: 0.5 }), mid.x, mid.y, mid.z); m.lookAt(b); m.rotateY(Math.PI / 2);
  const roof = mesh(new THREE.BoxGeometry(len, 0.3, 4.6), M(0xd0d5da, { metalness: 0.4 }), mid.x, mid.y + 2.2, mid.z); roof.quaternion.copy(m.quaternion);
  const dots = new THREE.InstancedMesh(new THREE.DodecahedronGeometry(0.9), dz < 0 ? oreMat.soft : oreMat.hard, 30); scene.add(dots);
  belts.push({ a, b, dots, rate: 0, off: 0 });
}
const wall = M(0xb9c3cc, { metalness: 0.35, roughness: 0.55 });
mesh(new THREE.BoxGeometry(60, 26, 70), wall, PLANT.x + 6, 13, PLANT.z);
mesh(new THREE.BoxGeometry(62, 2, 72), M(0x6f7c88, { metalness: 0.5 }), PLANT.x + 6, 27, PLANT.z);
const windows = [];
for (let k = 0; k < 8; k++) windows.push(mesh(new THREE.BoxGeometry(0.3, 3, 6), M(0x2c3e50, { emissive: 0xffd28a, emissiveIntensity: 0 }), PLANT.x - 24.2, 18, PLANT.z - 28 + k * 8));
mesh(new THREE.BoxGeometry(20, 36, 20), wall, PLANT.x + 28, 18, PLANT.z - 30);
const mills = [];
for (const dz of [-14, 14]) {
  const grp = new THREE.Group(); grp.position.set(PLANT.x - 34, 11, PLANT.z + dz); scene.add(grp);
  const drum = mesh(new THREE.CylinderGeometry(8, 8, 14, 36).rotateZ(Math.PI / 2), M(0xc9d1d8, { metalness: 0.75, roughness: 0.3 }), 0, 0, 0, grp);
  for (let k = 0; k < 8; k++) mesh(new THREE.BoxGeometry(14.4, 0.6, 1.4), M(0x55606b, { metalness: 0.6 }), 0, Math.cos(k * 0.785) * 8, Math.sin(k * 0.785) * 8, drum);
  mesh(new THREE.CylinderGeometry(9, 9, 1.6, 36).rotateZ(Math.PI / 2), M(0x39434d, { metalness: 0.6 }), -7.6, 0, 0, grp);
  mesh(new THREE.BoxGeometry(6, 6, 6), M(0x2f6fb0, { metalness: 0.4 }), 9, -3, 0, grp);
  const lamp = mesh(new THREE.SphereGeometry(1.2, 12, 8), M(0x4fd18b, { emissive: 0x4fd18b, emissiveIntensity: 2 }), 0, 10, 0, grp);
  mills.push({ drum, lamp, speed: 1 });
}
const cells = [];
for (let k = 0; k < 6; k++) cells.push(mesh(new THREE.CylinderGeometry(3.6, 3.6, 6, 24), M(0x7d8c99, { metalness: 0.5, roughness: 0.4 }), PLANT.x + 50, 3, PLANT.z - 22 + k * 9));
const froth = new THREE.InstancedMesh(new THREE.SphereGeometry(0.6, 6, 4), M(0xd9b44a, { emissive: 0x6b4f10, metalness: 0.6, roughness: 0.3 }), 80); scene.add(froth);
mesh(new THREE.CylinderGeometry(18, 18, 3, 48), M(0x9aa3ab, { metalness: 0.4 }), PLANT.x + 20, 1.5, PLANT.z + 70);
mesh(new THREE.CircleGeometry(17, 48).rotateX(-Math.PI / 2), M(0x4a5b5a, { roughness: 0.12, metalness: 0.3 }), PLANT.x + 20, 3.05, PLANT.z + 70, scene, false);
label('<b>Фабрика · две линии</b><span id="l-pl">—</span>', PLANT.x + 10, 52, PLANT.z - 20);
label('<b>Флотация → медь</b><span id="l-fl">—</span>', PLANT.x + 50, 16, PLANT.z + 34);

// ---------- ВЭС на холмах ----------
const turbines = [];
const WIND = new THREE.Vector3(-60, 0, -380);
for (let i = 0; i < 14; i++) {
  const x = WIND.x + (i % 7) * 75 + (Math.floor(i / 7) % 2) * 37, z = WIND.z - Math.floor(i / 7) * 95, y0 = Math.max(0, terrainH(x, z));
  mesh(new THREE.CylinderGeometry(1.1, 2.3, 80, 16), M(0xf3f5f7, { roughness: 0.35 }), x, y0 + 40, z);
  mesh(new THREE.CapsuleGeometry(1.8, 6, 4, 12).rotateX(Math.PI / 2), M(0xf3f5f7, { roughness: 0.35 }), x, y0 + 81, z + 1.5);
  const hub = new THREE.Group(); hub.position.set(x, y0 + 81, z + 6); scene.add(hub);
  const bg = new THREE.BoxGeometry(1.8, 38, 0.35); bg.translate(0, 19, 0);
  const bp = bg.attributes.position; for (let k = 0; k < bp.count; k++) { const t = bp.getY(k) / 38; bp.setX(k, bp.getX(k) * (1.5 - 1.1 * t)); }
  bg.computeVertexNormals();
  for (let k = 0; k < 3; k++) { const piv = new THREE.Group(); piv.rotation.z = k * Math.PI * 2 / 3; mesh(bg, M(0xfafbfc, { roughness: 0.3 }), 0, 0, 0, piv); hub.add(piv); }
  mesh(new THREE.SphereGeometry(1.6, 12, 8), M(0xe8eaec), 0, 0, 0.6, hub);
  turbines.push(hub);
}
label('<b>ВЭС 300 МВт</b><span id="l-wind">—</span>', WIND.x + 250, 150, WIND.z);

// ---------- СЭС ----------
const PV = new THREE.Vector3(60, 0, 180);
const panelMat = new THREE.MeshStandardMaterial({ color: 0x1b2f52, metalness: 0.85, roughness: 0.18, emissive: 0x1e5aa8, emissiveIntensity: 0 });
const panels = new THREE.InstancedMesh(new THREE.BoxGeometry(12, 0.35, 5), panelMat, 240);
const legs = new THREE.InstancedMesh(new THREE.BoxGeometry(0.4, 3, 0.4), M(0x9aa3ab, { metalness: 0.6 }), 240);
const solarField = new THREE.Group(); scene.add(solarField);
{ let k = 0; for (let r = 0; r < 12; r++) for (let c = 0; c < 20; c++) { setInst(panels, k, PV.x + c * 13, 3, PV.z + r * 9, 1, 1, 1, 0.48); setInst(legs, k, PV.x + c * 13, 1.5, PV.z + r * 9); k++; }
  panels.castShadow = !LOW; panels.receiveShadow = true; solarField.add(panels, legs); }
const solarLabel=label('<b>СЭС 250 МВт</b><span id="l-pv">—</span>', PV.x + 125, 18, PV.z + 50);

// ---------- накопитель, подстанция ----------
const BESS = new THREE.Vector3(230, 0, 60);
const bessLights = [], bessAssets = [];
const bessBodyMat=M(0xeef1f3,{metalness:0.2});bessBodyMat.userData.batchKey='bess-enclosures';
for (let i = 0; i < 8; i++) {
  const x = BESS.x + (i % 4) * 9, z = BESS.z + Math.floor(i / 4) * 18;
  bessAssets.push(mesh(new THREE.BoxGeometry(7, 7, 15), bessBodyMat, x, 3.5, z));
  const indicator=mesh(new THREE.BoxGeometry(0.3, 5, 11), M(0x111111, { emissive: 0x4fd18b, emissiveIntensity: 1.2 }), x + 3.6, 3.5, z);bessAssets.push(indicator);bessLights.push(indicator);
}
const bessLabel=label('<b>Накопитель 60 МВт</b><span id="l-bess">—</span>', BESS.x + 14, 18, BESS.z + 9);
const SUB = new THREE.Vector3(260, 0, -60);
mesh(new THREE.BoxGeometry(46, 0.8, 42), M(0xa69b8c, { map: gravel }), SUB.x, 0.4, SUB.z, scene, false);
for (let i = 0; i < 4; i++) {
  mesh(new THREE.BoxGeometry(6, 8, 7), M(0x6a737c, { metalness: 0.5 }), SUB.x - 14 + i * 9, 4.8, SUB.z - 8);
  for (let k = 0; k < 3; k++) mesh(new THREE.CylinderGeometry(0.35, 0.35, 7, 8), M(0xc8b28a), SUB.x - 16 + i * 9 + k * 2, 12, SUB.z - 8);
}
for (let i = 0; i < 6; i++) mesh(new THREE.BoxGeometry(0.6, 16, 0.6), M(0x9aa3ab, { metalness: 0.7 }), SUB.x - 18 + i * 7, 8, SUB.z + 10);
label('<b>Подстанция 220 кВ</b><span id="l-grid">—</span>', SUB.x, 28, SUB.z);

// ---------- ЛЭП и угольная ТЭС на горизонте ----------
const COAL = new THREE.Vector3(1500, 0, -1100);
const towerPts = [];
function pylon(x, z) {
  const y0 = Math.max(0, terrainH(x, z)), g = new THREE.Group(); g.position.set(x, y0, z); scene.add(g);
  g.lookAt(COAL.x, y0, COAL.z);
  const steel = M(0xa7afb6, { metalness: 0.7, roughness: 0.4 });
  for (const [sx, sz] of [[1, 1], [1, -1], [-1, 1], [-1, -1]]) { const l = mesh(new THREE.BoxGeometry(0.6, 50, 0.6), steel, sx * 2.2, 25, sz * 2.2, g); l.rotation.z = -sx * 0.06; l.rotation.x = sz * 0.06; }
  for (let k = 0; k < 6; k++) mesh(new THREE.BoxGeometry(6 - k * 0.6, 0.35, 0.35), steel, 0, 6 + k * 8, 0, g);
  mesh(new THREE.BoxGeometry(24, 0.8, 0.8), steel, 0, 46, 0, g); mesh(new THREE.BoxGeometry(16, 0.8, 0.8), steel, 0, 38, 0, g);
  return { p: new THREE.Vector3(x, y0 + 45, z), g };
}
const pyl = [];
for (let i = 0; i <= 10; i++) { const k = i / 10; pyl.push(pylon(SUB.x + 40 + (COAL.x - 120 - SUB.x - 40) * k, SUB.z - 30 + (COAL.z + 60 - SUB.z + 30) * k)); }
for (const t of pyl) towerPts.push(t.p);
const gridWireMat=M(0x3a3f44);gridWireMat.userData.batchKey='grid-wires';
for (let i = 0; i < pyl.length - 1; i++) for (const off of [-11, 0, 11]) {
  const a = new THREE.Vector3(off, 45, 0), b = new THREE.Vector3(off, 45, 0);
  pyl[i].g.localToWorld(a); pyl[i + 1].g.localToWorld(b);
  const m = a.clone().add(b).multiplyScalar(0.5); m.y -= 8;
  mesh(new THREE.TubeGeometry(new THREE.QuadraticBezierCurve3(a, m, b), 16, 0.2, 4), gridWireMat, 0, 0, 0, scene, false);
}
{
  const y0 = Math.max(0, terrainH(COAL.x, COAL.z));
  const prof = []; for (let i = 0; i <= 14; i++) { const t = i / 14; prof.push(new THREE.Vector2(42 - 28 * Math.sin(t * Math.PI * 0.8) + 7 * t, t * 120)); }
  for (const dx of [-70, 30]) mesh(new THREE.LatheGeometry(prof, LOW?32:56), M(0xcfcac0, { side: THREE.DoubleSide, roughness: 0.9 }), COAL.x + dx, y0, COAL.z);
  for (const dx of [110, 140]) { mesh(new THREE.CylinderGeometry(4.5, 8, 200, 16), M(0xb3aaa0), COAL.x + dx, y0 + 100, COAL.z + 20);
    for (const yy of [170, 190]) mesh(new THREE.CylinderGeometry(4.8, 4.8, 8, 16), M(0xc0392b), COAL.x + dx, y0 + yy, COAL.z + 20); }
  mesh(new THREE.BoxGeometry(100, 55, 55), M(0x8e8a84), COAL.x + 170, y0 + 27, COAL.z - 50);
  mesh(new THREE.ConeGeometry(45, 22, 8), M(0x1e1e1e, { roughness: 1 }), COAL.x + 260, y0 + 11, COAL.z + 40);   // угольный склад
}
label('<b>Угольная ТЭС · сеть KEGOC</b><span id="l-coal">—</span>', COAL.x + 40, 260, COAL.z);
const SMOKE_N = LOW?128:320;
const smokeMat = M(0x8c8780,{ transparent: true, opacity: 0.32, depthWrite: false, roughness: 1, metalness: 0 });
const smoke = new THREE.InstancedMesh(new THREE.IcosahedronGeometry(1, 1), smokeMat, SMOKE_N); scene.add(smoke);
const smokeSrc = [[110, 205, 20], [140, 205, 20], [-70, 120, 0], [30, 120, 0]];

// ---------- потоки энергии ----------
function flow(points, color) {
  const curve = new THREE.CatmullRomCurve3(points);
  mesh(new THREE.TubeGeometry(curve, LOW?80:160, 0.25, LOW?4:6), new THREE.MeshBasicMaterial({ color: 0x334455, transparent: true, opacity: 0.3 }), 0, 0, 0, scene, false);
  const n = LOW?30:60, im = new THREE.InstancedMesh(new THREE.SphereGeometry(1.6, LOW?6:10, LOW?4:8), new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.95, fog: false }), n);
  scene.add(im); return { curve, im, n, mw: 0, off: Math.random() };
}
const flows = {
  grid: flow([...towerPts.slice().reverse().map(p => p.clone().setY(p.y - 3)), new THREE.Vector3(SUB.x, 16, SUB.z)], 0x9a9a9a),
  wind: flow([new THREE.Vector3(WIND.x + 250, 60, WIND.z + 30), new THREE.Vector3(SUB.x - 40, 34, SUB.z - 150), new THREE.Vector3(SUB.x - 4, 16, SUB.z - 12)], 0x5ec8e5),
  pv: flow([new THREE.Vector3(PV.x + 125, 12, PV.z - 6), new THREE.Vector3(SUB.x - 10, 22, SUB.z + 100), new THREE.Vector3(SUB.x + 6, 16, SUB.z + 12)], 0xf2c14e),
  plant: flow([new THREE.Vector3(SUB.x - 20, 16, SUB.z), new THREE.Vector3(PLANT.x + 60, 36, PLANT.z - 30), new THREE.Vector3(PLANT.x + 20, 28, PLANT.z)], 0x9ff5c6),
  charge: flow([new THREE.Vector3(SUB.x - 20, 16, SUB.z + 8), new THREE.Vector3(120, 30, 90), new THREE.Vector3(CHARGE.x + 26, 11, CHARGE.z - 9)], 0x4cc3ff),
};
const dummy = new THREE.Object3D();
function updFlow(f, dt) {
  f.off = (f.off + dt * (0.025 + Math.min(f.mw, 300) / 5000)) % 1;
  const vis = Math.round(Math.min(f.n, f.mw / 270 * f.n));
  for (let i = 0; i < f.n; i++) {
    if (i < vis) { dummy.position.copy(f.curve.getPointAt((i / f.n + f.off) % 1)); dummy.scale.setScalar(1); } else dummy.scale.setScalar(0);
    dummy.rotation.set(0, 0, 0); dummy.updateMatrix(); f.im.setMatrixAt(i, dummy.matrix);
  }
  f.im.instanceMatrix.needsUpdate = true;
}

const details = installSceneDetails({scene,camera,controls,renderer,label,mesh,M,road,terrainH,gravel,PLANT,PILES,CHARGE,BESS,SUB,WIND,PV,PIT,PIT_R,trucks,mills,turbines,piles,bessLights,bessBodyMat,gridWireMat,chargers,windows,shovels,flows,belts,getData:()=>D,getSource:()=>source,getView:()=>view,cancelEvent:cancelScenarioEvent});
// Components stay in each animated root's local coordinates. Cargo, lights,
// labels and independently moving parts are not baked into the rigid body.
const rigidMergeStats=LOW?[
  ...trucks.map(t=>mergeStaticMeshes(t.g,[t.load,t.glow],{local:true,bakeColors:true})),
  ...turbines.map(hub=>mergeStaticMeshes(hub,[],{local:true,bakeColors:true})),
  ...mills.map(m=>mergeStaticMeshes(m.drum,[],{local:true,bakeColors:true})),
]:[];
const mergeStats = mergeStaticMeshes(scene,[...details.dynamicRoots,geologyPit,geologyMarkers],{bakeColors:LOW});
loadGeology();
mergeStats.rigid={batches:0,mergedMeshes:0,savedMeshes:0};
for(const stat of rigidMergeStats){mergeStats.before+=stat.before-stat.after;mergeStats.batches+=stat.batches;mergeStats.mergedMeshes+=stat.mergedMeshes;mergeStats.rigid.batches+=stat.batches;mergeStats.rigid.mergedMeshes+=stat.mergedMeshes;mergeStats.rigid.savedMeshes+=stat.before-stat.after;}

// ---------- HUD ----------
const set = (id, h) => { const e = document.getElementById(id); if (e) e.innerHTML = h; };
function hud() {
  if (!D.site) return;
  for (const marker of geologyMarkers.children) {
    const active = marker.userData.cellId===v('geology','active_soft') || marker.userData.cellId===v('geology','active_hard');
    marker.visible=active; marker.scale.setScalar(active?1:0);
  }
  const geoLabel=$('geology-active'); if(geoLabel)geoLabel.textContent=`Забои ${v('geology','active_soft','—')} / ${v('geology','active_hard','—')} · BWi ${fmt(v('geology','bwi_soft',null),1)} / ${fmt(v('geology','bwi_hard',null),1)} кВт·ч/т`;
  const e = E(), mode = v('coordinator', 'mode', '—');
  if (view === 'now') { $('mode').textContent = 'КАК СЕЙЧАС · без координации'; $('mode').className = 'now'; }
  else { $('mode').textContent = mode === 'вдох' ? 'ТЫНЫС · ВДОХ — копим энергию' : 'ТЫНЫС · ВЫДОХ — экономим'; $('mode').className = mode === 'вдох' ? 'inhale' : 'exhale'; }
  $('clock').textContent = v('site', 'sim_time', '');
  $('whyt').innerHTML = view === 'now'
    ? `<b class="bad">Проблема.</b> Рудник работает «ровно» и не слушает ветер и солнце: из угольной сети ${fmt(e.grid)} МВт${e.curtail > 1 ? `, а <b class="bad">${fmt(e.curtail)} МВт ветра и солнца сейчас выбрасывается</b>` : ''}. Твёрдая руда мелется в любой час.`
    : '<b class="good">Почему так.</b> ';
  if(view!=='now')$('whyt').appendChild(document.createTextNode(v('coordinator','why','—')));
  set('l-pit', `${fmt(v('pit', 'ore_tph'))} т/ч · твёрдой ${fmt(100 * v('pit', 'hard_frac'))} %`);
  if (view === 'now') {
    set('l-ps', `${fmt(v('shadow-v0', 'pile_soft_t') / 1000)} тыс. т · ${fmt(v('shadow-v0', 'pile_soft_fill_pct'))} % · как сейчас`);
    set('l-ph', `${fmt(v('shadow-v0', 'pile_hard_t') / 1000)} тыс. т · ${fmt(v('shadow-v0', 'pile_hard_fill_pct'))} % · как сейчас`);
  } else {
    set('l-ps', `${fmt(v('pile-soft', 'tonnes') / 1000)} тыс. т · ${fmt(v('pile-soft', 'fill_pct'))} %`);
    set('l-ph', `${fmt(v('pile-hard', 'tonnes') / 1000)} тыс. т · ${fmt(v('pile-hard', 'fill_pct'))} %`);
  }
  set('l-pl', view==='now'
    ? `как сейчас · смесь руды ${fmt(v('shadow-v0', 'feed_tph'))} т/ч · P80 150 мкм`
    : `твёрдой ${fmt(v('plant', 'feed_hard_tph'))} · мягкой ${fmt(v('plant', 'feed_soft_tph'))} т/ч · P80 ${fmt(v('plant', 'p80_um'))} мкм`);
  set('l-fl', `${fmt(v('flotation', 'cu_tph'), 1)} т меди/ч`);
  set('l-wind', `${fmt(v('wind', 'power_mw'))} МВт${e.curtail > 1 ? ` · <span class="bad">сброс ${fmt(e.curtail)}</span>` : ''}`);
  set('l-pv', `${fmt(v('pv', 'power_mw'))} МВт`);
  set('l-bess', view === 'now' ? 'не управляется' : v('bess', 'available', true) ? `заряд ${fmt(v('bess', 'soc'))} %` : 'ОТКАЗ');
  const gridCap=v('substation','grid_cap_mw',null),gridNominal=v('substation','grid_nominal_mw',null);
  set('l-grid', gridNominal===null ? `${fmt(e.grid)} / ${fmt(gridCap)} МВт · предел`
    : `Предел ${fmt(gridCap)} / ${fmt(gridNominal)} МВт · из сети ${fmt(e.grid)}`);
  set('l-coal', `<span class="bad">${fmt(e.co2)} т CO₂ в час</span> — из‑за рудника`);
  set('l-ch', view === 'now' ? 'по графику смен' : `${fmt(e.charge)} МВт`);
  const a = { cu: v('shadow-v0', 'cu_adj_t'), co2: v('shadow-v0', 'co2_adj_t', v('shadow-v0', 'co2_t')), curt: v('shadow-v0', 'curtail_mwh') };
  const b = { cu: v('site', 'cu_adj_t'), co2: v('site', 'co2_adj_t', v('site', 'co2_t')), curt: v('site', 'curtail_mwh') };
  const co2Adj = x => Number(x) < 0 ? '≈ 0' : fmt(x);   // поправка на запасы в первые часы
  const d = (x, y, inv) => { if (!(Math.abs(x) >= 100)) return '';   // первые часы: база слишком мала для процентов
    const p = 100 * (y - x) / Math.max(1, x); const good = inv ? p < 0 : p > 0; return `<small class="${good ? 'good' : 'bad'}">${p > 0 ? '+' : ''}${fmt(p, 1)} %</small>`; };
  $('kt').innerHTML = `<tr><th></th><th class="bad">Как сейчас</th><th class="good">Тыныс</th></tr>
    <tr><td>Медь, т</td><td>${fmt(a.cu)}</td><td>${fmt(b.cu)} ${d(a.cu, b.cu)}</td></tr>
    <tr><td>Выброшено ВИЭ, МВт·ч</td><td>${fmt(a.curt)}</td><td>${fmt(b.curt)} ${a.curt > 0 ? d(a.curt, b.curt, 1) : ''}</td></tr>
    <tr><td title="поправка на склады и заряд батарей в конце">CO₂ с учётом запасов, т</td><td>${co2Adj(a.co2)}</td><td>${co2Adj(b.co2)}</td></tr>`;
  set('g-co2', fmt(e.co2)); set('g-ren', fmt(100 * e.used / Math.max(1, e.used + e.grid))); set('g-cur', fmt(e.curtail));
  flows.grid.mw = e.grid; flows.wind.mw = Math.max(0, v('wind', 'power_mw') - e.curtail * 0.7); flows.pv.mw = Math.max(0, v('pv', 'power_mw') - e.curtail * 0.3);
  // «Как сейчас»: склады, конвейеры и мельницы берутся из тени V0 (свой рудник без
  // координации на той же погоде), а не из рудника «Тыныс».
  const now = view === 'now', s0 = (k, d) => v('shadow-v0', k, d);
  flows.plant.mw = now ? s0('mill_mw', v('plant', 'mill_mw')) : v('plant', 'mill_mw'); flows.charge.mw = e.charge;
  for (const [dd, n] of [['soft', 'pile-soft'], ['hard', 'pile-hard']]) { const fill = now ? s0(`pile_${dd}_fill_pct`, v(n, 'fill_pct', 50)) : v(n, 'fill_pct', 50); const f = 0.35 + 0.9 * fill / 100; piles[dd].scale.set(f, f, f); piles[dd].position.y = 7.5 * f; }
  belts[0].rate = (now ? s0('feed_soft_tph', 0) : v('plant', 'feed_soft_tph')) / 4000; belts[1].rate = (now ? s0('feed_hard_tph', 0) : v('plant', 'feed_hard_tph')) / 4000;
  for (let l = 0; l < 2; l++) {
    const n = `line-${l + 1}`, ok = v(n, 'available', true), q = now ? s0(`line${l + 1}_tph`, v(n, 'feed_tph', 3330)) : v(n, 'feed_tph', 3330);
    mills[l].speed = ok ? (now ? (q > 0 ? 10.5 : 0) : v(n,'speed_rpm',q>0?10.5:0)) * 2*Math.PI/60 : 0; const c = !ok ? 0xe0675a : q > 0 ? 0x4fd18b : 0x888888; mills[l].lamp.material.color.set(c); mills[l].lamp.material.emissive.set(c);mills[l].lamp.material.emissiveIntensity=2;
  }
  panelMat.emissiveIntensity = Math.min(1, v('pv', 'power_mw') / 250) * 0.45;
  const soc = v('bess', 'soc', 0) / 100; bessLights.forEach(x => { x.scale.y = Math.max(0.05, soc); });
  chargers.forEach((c, i) => c.material.emissiveIntensity = v(`charger-${i+1}`,'power_mw',0)>0 ? 2.5 : 0);
  details.update(D);
}
setInterval(hud, 400);

// ---------- время суток ----------
let dayK = 1, lightingOverride = Q.has('h') && Number.isFinite(Number(Q.get('h'))) ? THREE.MathUtils.clamp(Number(Q.get('h')),0,23.99) : 9, lightingHour=9;
function setLightingHour(hour){lightingOverride=hour===null?null:THREE.MathUtils.clamp(Number(hour),0,23.99);if(lightingOverride!==null&&!Number.isFinite(lightingOverride))lightingOverride=null;skyUpd(true);}
$('light-hour').addEventListener('input',e=>setLightingHour(Number(e.target.value)));$('light-auto').onclick=()=>setLightingHour(null);
function skyUpd(immediate=false) {
  const s = String(v('site', 'sim_time', '2026-04-15 12:00'));
  const h = lightingOverride ?? (Number(s.slice(11,13)) + Number(s.slice(14,16)||0)/60);lightingHour=Number.isFinite(h)?h:12;
  $('light-hour').value=String(lightingHour);$('light-value').textContent=`${String(Math.floor(lightingHour)).padStart(2,'0')}:${String(Math.floor(lightingHour%1*60)).padStart(2,'0')} · ${lightingOverride===null?'модель':'просмотр'}`;$('light-auto').classList.toggle('on',lightingOverride===null);$('light-hour').title='Меняет только освещение. Состояние двойников и модельное время не меняются.';
  const a = (h + 0.5 - 6) / 12 * Math.PI, el = Math.sin(a);
  const day = THREE.MathUtils.clamp(el * 1.8 + 0.2, 0, 1); dayK = immediate ? day : dayK + (day - dayK) * 0.03;
  const dir = new THREE.Vector3(Math.cos(a) * 0.85, Math.max(0.06, el), 0.5).normalize().lerp(new THREE.Vector3(-.45,.8,.35).normalize(),1-dayK).normalize();
  sun.position.copy(dir).multiplyScalar(1200);
  sun.intensity = 0.85 + 2.05 * dayK; hemi.intensity = 0.6 + 0.6 * dayK;nightAmbient.intensity=.18*(1-dayK);
  sun.color.lerpColors(new THREE.Color(0x9bbcf0),new THREE.Color(0xffefd6),dayK);hemi.color.lerpColors(new THREE.Color(0x719fcf),new THREE.Color(0xcfe3ff),dayK);hemi.groundColor.lerpColors(new THREE.Color(0x7086aa),new THREE.Color(0x8a7458),dayK);
  skyMat.uniforms.sunDir.value.set(Math.cos(a) * 0.85, el, 0.5).normalize(); skyMat.uniforms.day.value = dayK;
  skyMat.uniforms.top.value.lerpColors(new THREE.Color(0x1a2a4a), new THREE.Color(0x3a78bb), dayK);
  skyMat.uniforms.bot.value.lerpColors(new THREE.Color(0x3a4a6e), new THREE.Color(0xe2e8e9), dayK);
  scene.fog.color.lerpColors(new THREE.Color(0x3a4a6e), new THREE.Color(0xd3dde2), dayK);
  stars.material.opacity = (1 - dayK) * 0.9;
  renderer.toneMappingExposure = 1 + 0.25 * dayK;
  windows.forEach(w => w.material.emissiveIntensity = (1 - dayK) * 2.2);
}

// ---------- переключатель ----------
function setView(x) { view = x; const upgraded=x==='tynys'; solarField.visible=upgraded; solarLabel.style.display=upgraded?'':'none'; bessAssets.forEach(a=>a.visible=upgraded); bessLabel.style.display=upgraded?'':'none'; chargingArea.visible=upgraded; chargeLabel.style.display=upgraded?'':'none'; $('vnow').classList.toggle('on', x === 'now'); $('vtyn').classList.toggle('on', upgraded); document.body.dataset.view = x; $('mode').dataset.view=x; hud(); }
$('vnow').onclick = () => setView('now'); $('vtyn').onclick = () => setView('tynys');

// ---------- история: проблема → решение ----------
const STORY = [
  { v: 'now', p: [1150, 300, -620], t: [1500, 120, -1100], h: 'Проблема', s: 'Актогай круглосуточно берёт из сети ≈ 230 МВт. Две трети электроэнергии Казахстана — уголь: ≈ 1,6 млн т CO₂ в год только из‑за этого рудника.' },
  { v: 'now', p: [330, 200, -60], t: [130, 80, -400], h: 'Ветер и солнце есть — но их выбрасывают', s: 'Ветряки дают энергию не тогда, когда она нужна. Рудник работает «ровно», и лишнюю энергию сбрасывают — часть ветряков просто стоит.' },
  { v: 'now', p: [-30, 100, 190], t: [-130, -40, 10], h: 'Руда бывает мягкая и твёрдая', s: 'Твёрдую молоть в ≈ 1,4 раза дороже по энергии (BWi 16 против 11,5 кВт·ч/т). Сегодня её мелют вперемешку — в любой час, даже когда энергия самая «угольная».' },
  { v: 'tynys', p: [-40, 120, -190], t: [70, 0, 0], h: 'Решение: рудник «дышит»', s: 'ВДОХ — энергии много: мелем твёрдую руду и тоньше, заряжаем самосвалы. ВЫДОХ — мало: мелем мягкую, твёрдую копим на складе.' },
  { v: 'tynys', p: [80, 55, 200], t: [10, 0, 110], h: 'Электросамосвалы — тоже батарея', s: 'Самосвалы заряжаются, когда дует ветер, и возят руду на заряде, когда ветра нет.' },
  { v: 'tynys', p: [360, 130, 140], t: [250, 10, -20], h: 'Мозг считает на сутки вперёд', s: 'Каждый час — план на 24 ч по прогнозу погоды и объяснение словами. В «Двух будущих» можно проверить ограничение сети, последствия для производства и восстановление запасов.' },
  { v: 'tynys', p: [300, 280, 460], t: [20, -20, -20], h: 'Итог за год на реальной погоде 2024', s: 'ВЭС 300 + СЭС 250 МВт: CO₂ 1 661 → 978 тыс. т в год (−41 %). «Тыныс» с целью «CO₂» сверху: сброс ветра и солнца почти вдвое меньше (94 → 49 ГВт·ч) и CO₂ ещё −4,4 % (935 тыс. т) при меди −1 %. Цель «медь»: +0,9 % меди, но CO₂ +2,3 %.' },
];
let tour = null;
function startStory() { tour = { i: 0, t0: performance.now(), stepMs:Q.get('demo')==='1'?25000:11000, from: { p: camera.position.clone(), t: controls.target.clone() } }; setView(STORY[0].v); }
function stopStory() { tour = null; $('caption').classList.remove('show'); $('dots').innerHTML = ''; }
$('tour').onclick = startStory;
$('reset').onclick = () => {
  stopStory();
  // OrbitControls retains angular/pan velocity after a drag. Flush it before
  // restoring HOME; otherwise the next frames move the reset camera again.
  const damping=controls.enableDamping;
  controls.enableDamping=false;controls.update();
  camera.position.copy(HOME.pos);controls.target.copy(HOME.tgt);controls.update();
  controls.enableDamping=damping;
};
renderer.domElement.addEventListener('pointerdown', () => { if (tour) stopStory(); });
addEventListener('keydown', ev => {
  if (!tour) return;
  if (ev.key === 'ArrowRight' || ev.key === ' ') { tour.t0 = -1e9; }
  if (ev.key === 'Escape') stopStory();
});
function tourStep(now) {
  if (!tour) return;
  const st = STORY[tour.i], k = Math.min(1, (now - tour.t0) / 4500), e = k < 0.5 ? 4 * k * k * k : 1 - (-2 * k + 2) ** 3 / 2;
  camera.position.lerpVectors(tour.from.p, new THREE.Vector3(...st.p), e);
  controls.target.lerpVectors(tour.from.t, new THREE.Vector3(...st.t), e);
  if (view !== st.v) setView(st.v);
  $('caption').innerHTML = `<span class="${st.v === 'now' ? 'bad' : 'good'}">${st.h}</span><small>${st.s}</small>`; $('caption').classList.add('show');
  $('dots').innerHTML = STORY.map((s, i) => `<i class="${i === tour.i ? 'on' : ''} ${s.v}"></i>`).join('');
  if (now - tour.t0 > tour.stepMs) {
    tour.i++; if (tour.i >= STORY.length) { stopStory(); return; }
    tour.t0 = now; tour.from = { p: camera.position.clone(), t: controls.target.clone() };
  }
}
$('go').onclick = () => { $('intro').classList.add('hide'); startStory(); };
$('skip').onclick = () => { $('intro').classList.add('hide'); setView('tynys'); };
setView('tynys');
if(Q.get('demo')==='1'){$('intro').classList.add('hide');startStory();}

// ---------- анимация ----------
let last = performance.now(), rot = 0, smokeT = 0, fps = 60;
let lastDraw = 0, renderedFrames=0; const frameTimes=[];
function frame(now) {
  if (LOW && now - lastDraw < 66) { requestAnimationFrame(frame); return; }
  lastDraw = now;
  const dt = Math.min(0.1, (now - last) / 1000); last = now; fps = fps * 0.95 + (1 / Math.max(dt, 1e-3)) * 0.05;
  skyUpd();
  const e = E();
  const feather = e.curtail > 1 ? Math.min(0.9, e.curtail / Math.max(1, v('wind', 'power_mw'))) : 0;
  const lull=details.events.some(e=>e.active&&e.kind==='lull');
  rot += dt * (lull ? 0 : 3.4 * Math.max(0,v('wind', 'cf_pct', 0)) / 100);
  turbines.forEach((hh, i) => { if (i >= Math.round(feather * turbines.length)) hh.rotation.z = rot + i; });
  mills.forEach(m => m.drum.rotation.x += dt * (m.speed || 0));
  shovels.forEach((s, i) => {
    const name=`shovel-${i+1}`, rate=Number(v(name,'rate_tph',0));
    const load=v(name,'available',false)?Math.min(1,rate/Math.max(1,Number(v(name,'capacity_tph',1)))):0;
    const phase=Math.sin(now/1800+i*2);
    s.rotation.y=phase*0.28*load;s.position.y=2.6+Math.max(0,phase)*0.8*load;
  });
  const hf = v('pit', 'hard_frac', 0.5);
  const slots = { c: 0, w: 0 };
  trucks.forEach((tr, i) => {
    const n = `truck-${String(i + 1).padStart(2, '0')}`; let st = v(n, 'state', 'empty');
    // Звено заряжается часть часа (мощность / 18 МВт трёх машин), остальное время возит руду:
    // у зарядки показываем только звенья, которые стоят на ней большую часть часа.
    if (st === 'charging' && Number(v(n, 'charge_mw', 18)) / 18 < 0.5) st = 'empty';
    tr.glow.intensity = st === 'charging' ? 5 : 0;
    if(!LOW)for (let k = 0; k < 8; k++) setInst(dustIM, i * 8 + k, 0, -500, 0, 0, 0, 0);
    if (st === 'charging') { const k = Number(String(v(n,'assigned_charger',`charger-${i%4+1}`)).split('-').pop())-1; tr.g.position.set(CHARGE.x - 30 + k * 20, 0.4, CHARGE.z - 8 + Math.floor(i/4)*13); tr.g.rotation.set(0, Math.PI / 2, 0); tr.load.visible = false; return; }
    if (['waiting','idle','unavailable','fault','maintenance'].includes(st)) { const k = slots.w++; tr.g.position.set(CHARGE.x - 40 + (k % 6) * 17, 0.4, CHARGE.z + 40 + Math.floor(k / 6) * 13); tr.g.rotation.set(0, Math.PI / 2, 0); tr.load.visible = false; return; }
    // Скорость — как у карьерного самосвала: гружёный в подъём ≈ 12 км/ч, порожний ≈ 30 км/ч
    // (1 ед. сцены ≈ 10 м), показ ускорен в TRUCK_TIMELAPSE раз. Модель часовая, поэтому
    // положение на дороге — анимация; заряд, состояние и груз звена — из двойника.
    const upNow = tr.phase < 0.5, kmh = upNow ? 12 : 30;
    tr.phase = ((tr.phase + Math.max(0, dt) * TRUCK_TIMELAPSE * (kmh / 3.6 / 10) / (2 * ROAD_LEN)) % 1 + 1) % 1;
    const up = tr.phase < 0.5, f = up ? tr.phase * 2 : 2 - tr.phase * 2;
    const p = road.getPointAt(f), t = road.getTangentAt(f), side = new THREE.Vector3(-t.z, 0, t.x).normalize().multiplyScalar(up ? 2.3 : -2.3);
    tr.g.position.copy(p).add(side); tr.g.position.y = p.y + 0.35;
    tr.g.rotation.set(0, Math.atan2(-t.z, t.x) + (up ? 0 : Math.PI), 0);
    tr.g.rotateZ((up ? 1 : -1) * Math.asin(THREE.MathUtils.clamp(t.y, -0.3, 0.3)));
    tr.load.visible = up;   // в подъём — с рудой, обратно — порожний
    tr.load.material = hash(i, 9) < hf ? oreMat.hard : oreMat.soft;
    if (p.y > -6 && !LOW) for (let k = 0; k < 8; k++) {
      const ph = (now / 900 + k / 8 + i * 0.13) % 1, back = t.clone().multiplyScalar((up ? -1 : 1) * (6 + ph * 14));
      setInst(dustIM, i * 8 + k, tr.g.position.x + back.x, 1 + ph * 5, tr.g.position.z + back.z, 1 + ph * 3, 1 + ph * 2, 1 + ph * 3);
    }
  });
  if(!LOW)dustIM.instanceMatrix.needsUpdate = true;
  belts.forEach(b => {
    b.off = (b.off + dt * 0.06 * Math.max(0.05, b.rate)) % 1;
    for (let i = 0; i < 30; i++) {
      if (b.rate > 0.02) { dummy.position.lerpVectors(b.a, b.b, (i / 30 + b.off) % 1); dummy.position.y += 1.2; dummy.rotation.set(i, i * 2, 0); dummy.scale.setScalar(1); } else dummy.scale.setScalar(0);
      dummy.updateMatrix(); b.dots.setMatrixAt(i, dummy.matrix);
    }
    b.dots.instanceMatrix.needsUpdate = true;
  });
  const cu = v('flotation', 'cu_tph', 0);
  for (let i = 0; i < 80; i++) { const c = cells[i % 6].position, ph = (now / 1700 + i * 0.37) % 1; setInst(froth, i, c.x + Math.sin(i * 7.1) * 2.4, 6 + ph * 3, c.z + Math.cos(i * 3.3) * 2.4, cu > 0 ? 1 - ph : 0, cu > 0 ? 1 - ph : 0, cu > 0 ? 1 - ph : 0); }
  froth.instanceMatrix.needsUpdate = true;
  // дым угольной ТЭС: его количество следует за мощностью, которую рудник берёт из сети
  smokeT += dt; const dens = THREE.MathUtils.clamp(e.grid / 250, 0.04, 1.15), y0 = Math.max(0, terrainH(COAL.x, COAL.z));
  for (let i = 0; i < SMOKE_N; i++) {
    const src = smokeSrc[i % 4], ph = (smokeT * 0.045 + i / SMOKE_N * 7.3) % 1, show = (i / SMOKE_N) < dens * 0.87, s = show ? (i % 4 < 2 ? 8 : 16) + ph * 46 : 0;
    setInst(smoke, i, COAL.x + src[0] + ph * 190 + Math.sin(i) * 10 * ph, y0 + src[1] + ph * 140 + Math.cos(i * 1.7) * 7, COAL.z + src[2] + ph * 70, s, s * 0.8, s, i, i);
  }
  smoke.instanceMatrix.needsUpdate = true;
  smokeMat.color.setHSL(0.08, 0.04, 0.3 + 0.32 * dayK);
  Object.values(flows).forEach(f => updFlow(f, dt));
  tourStep(now);
  controls.update();
  details.tick(now,dayK);
  renderer.render(scene, camera); labels.render(scene, camera);details.layoutLabels();
  renderedFrames++;frameTimes.push(performance.now());if(frameTimes.length>300)frameTimes.shift();
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
window.__tynys = { scene,camera,controls,renderer,setView,startStory,low:LOW,softGL:SOFT_GL,mergeStats,setLightingHour,selectObject:details.selectObject,clearSelection:details.clearSelection,get fps(){return fps;},get renderedFrames(){return renderedFrames;},get frameTimes(){return [...frameTimes];},get events(){return details.events;},get selected(){return details.selected;},get lightingHour(){return lightingHour;},get lightingOverride(){return lightingOverride;},get pixelRatio(){return renderer.getPixelRatio();},get source(){return source;},get dayK(){return dayK;},get data(){return structuredClone(D);},get scenarioVisuals(){return{...details.visuals,windLull:details.events.some(e=>e.active&&e.kind==='lull'),windAngles:turbines.map(t=>t.rotation.z),bessColor:bessLights[0].material.emissive.getHex(),line2Speed:mills[1].speed,headlights:details.headlights.filter(x=>x.visible).length};}};
