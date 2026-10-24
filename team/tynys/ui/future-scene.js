/**
 * Two futures, one visual vocabulary.
 * All quantities belong to the selected model record. Motion is decorative:
 * it illustrates the selected flow and never changes the model or its clock.
 * No textures, shadows, external services, or GPU-dependent data processing.
 */
import * as THREE from 'three';
import { OrbitControls } from './vendor/OrbitControls.js';

const C = {
  night: 0x101e2c, sand: 0xbc9269, rock: 0x87654e, bench: 0xd3ab7b,
  dark: 0x233747, steel: 0x8298a3, white: 0xc9d8d8, road: 0x66635b,
  green: 0x4ee0bc, copper: 0xf4b06e, red: 0xff746b, solar: 0x234f78,
};
const clamp = (v, lo = 0, hi = 1) => Math.max(lo, Math.min(hi, v));
const finite = value => typeof value === 'number' && Number.isFinite(value);
const number = (record, key, fallback = 0) => finite(record?.[key]) ? record[key] : fallback;
const fmt = (v, digits = 0) => finite(v)
  ? v.toLocaleString('ru-RU', { maximumFractionDigits: digits })
  : '—';
const capacity = (limits, names) => {
  for (const key of names) if (finite(limits?.[key]) && limits[key] > 0) return limits[key];
  return null;
};
const ratio = (value, cap) => finite(value) && cap ? clamp(value / cap) : 0;
const escapeHtml = text => String(text ?? '').replace(/[&<>"']/g, ch => (
  { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]
));
const normalObject = value => {
  const key = String(value ?? '').toLowerCase().replaceAll('-', '_');
  const aliases = {
    pit: 'mine', mining: 'mine', trucks: 'fleet', truck: 'fleet', charging: 'fleet',
    charger: 'fleet', chargers: 'fleet',
    truck_charge: 'fleet', battery: 'bess', storage: 'bess', substation: 'grid',
    energy: 'grid', kegoc: 'grid', solar: 'pv', plant: 'line1', mill: 'line1',
    line_1: 'line1', line_2: 'line2', pile: 'pile_soft', piles: 'pile_soft',
    soft: 'pile_soft', hard: 'pile_hard', soft_pile: 'pile_soft', hard_pile: 'pile_hard',
  };
  return aliases[key] || key;
};

function quantities(record, limits) {
  const pile = capacity(limits, ['pile_capacity_t', 'pile_cap_t']);
  const soft = capacity(limits, ['pile_soft_capacity_t', 'soft_capacity_t']) || pile;
  const hard = capacity(limits, ['pile_hard_capacity_t', 'hard_capacity_t']) || pile;
  const battery = capacity(limits, ['bess_capacity_mwh', 'bess_mwh']);
  const fleet = capacity(limits, ['fleet_capacity_mwh', 'fleet_mwh']);
  const wind = capacity(limits, ['wind_capacity_mw', 'wind_mw']);
  const pv = capacity(limits, ['pv_capacity_mw', 'pv_mw']);
  const line = capacity(limits, ['line_nominal_tph', 'line_capacity_tph']);
  const mine = capacity(limits, ['mine_nominal_tph', 'mine_capacity_tph']);
  return {
    soft: ratio(record?.pile_soft_t, soft), hard: ratio(record?.pile_hard_t, hard),
    battery: ratio(record?.bess_mwh, battery), fleet: ratio(record?.fleet_mwh, fleet),
    wind: ratio(record?.wind_mw, wind), solar: ratio(record?.pv_mw, pv),
    line1: line ? ratio(record?.line1_tph, line) : number(record, 'line1_tph') > 0 ? 0.5 : 0,
    line2: line ? ratio(record?.line2_tph, line) : number(record, 'line2_tph') > 0 ? 0.5 : 0,
    mine: mine ? ratio(record?.mine_tph, mine) : number(record, 'mine_tph') > 0 ? 0.5 : 0,
    batteryCapacity: battery, fleetCapacity: fleet, softCapacity: soft, hardCapacity: hard,
    gridStress: finite(record?.cap_mw) && record.cap_mw > 0
      ? number(record, 'grid_mw') / record.cap_mw : number(record, 'grid_mw') > 0 ? 2 : 0,
    fault: number(record, 'unserved_mw') > 0.001,
  };
}

const LABELS = [
  { id: 'mine', name: 'КАРЬЕР', p: [-26, 3, -4], value: r => `${fmt(r?.mine_tph)} т/ч` },
  { id: 'fleet', name: 'ЭЛЕКТРОПАРК', p: [-22, 3, 20],
    value: r => `${fmt(r?.fleet_mwh, 1)} МВт·ч` },
  { id: 'pile_soft', name: 'МЯГКАЯ РУДА', p: [-3, 5, 11],
    value: r => `${fmt(r?.pile_soft_t)} т` },
  { id: 'pile_hard', name: 'ТВЁРДАЯ РУДА', p: [5, 5, 16],
    value: r => `${fmt(r?.pile_hard_t)} т` },
  { id: 'line1', name: 'ЛИНИЯ 1', p: [14, 7, -3], value: r => `${fmt(r?.line1_tph)} т/ч` },
  { id: 'line2', name: 'ЛИНИЯ 2', p: [25, 7, 4], value: r => `${fmt(r?.line2_tph)} т/ч` },
  { id: 'wind', name: 'ВЕТЕР', p: [-18, 16, -21], value: r => `${fmt(r?.wind_mw, 1)} МВт` },
  { id: 'pv', name: 'СОЛНЦЕ', p: [10, 3, -19], value: r => `${fmt(r?.pv_mw, 1)} МВт` },
  { id: 'bess', name: 'НАКОПИТЕЛЬ', p: [29, 5, 18],
    value: r => `${fmt(r?.bess_mwh, 1)} МВт·ч` },
  { id: 'grid', name: 'СЕТЬ', p: [38, 9, -14],
    value: r => `${fmt(r?.grid_mw, 1)} / ${fmt(r?.cap_mw, 1)} МВт` },
];

function installStyles() {
  if (document.getElementById('tynys-future-scene-style')) return;
  const style = document.createElement('style');
  style.id = 'tynys-future-scene-style';
  style.textContent = `
    .tynys-future-scene{position:relative;overflow:hidden;background:#101e2c;isolation:isolate}
    .tynys-future-scene canvas{display:block;width:100%;height:100%;touch-action:none;outline:none}
    .tf-label-layer{position:absolute;inset:0;pointer-events:none;overflow:hidden}
    .tf-scene-label{position:absolute;max-width:123px;padding:4px 6px;border:1px solid #7896aa24;
      border-radius:5px;background:#0c192de8;color:#edf7f5;font:10px/1.25 system-ui,sans-serif;
      box-shadow:0 2px 9px #0002;will-change:transform;pointer-events:auto}
    .tf-scene-label strong{display:block;font-size:8px;letter-spacing:.07em;color:#a3b9c7;font-weight:600}
    .tf-scene-label b{display:block;font-size:10px;font-weight:600;white-space:nowrap;margin-top:2px}
    .tf-scene-label em{display:block;font-size:9px;line-height:1.3;font-style:normal;
      color:#dfedea;max-width:119px;margin-top:3px;border-top:1px solid #7896aa33;padding-top:3px}
    .tf-scene-label[data-state="warning"]{border-color:#ff746b88}
    .tf-scene-label[data-state="active"]{border-color:#4ee0bc66}
    .tf-scene-label[data-compact="true"] em{display:none}
    .tf-scene-corner{position:absolute;left:11px;bottom:9px;color:#a3b9c7;
      font:9px/1.35 system-ui,sans-serif;pointer-events:none;text-shadow:0 1px 3px #101e2c}
    .tf-scene-fallback{display:block;width:100%;height:100%;font-family:system-ui,sans-serif}
    .tf-scene-fallback text{fill:#d5e4e9}
    @media(max-width:600px){.tf-scene-label{padding:3px 4px;max-width:103px}
      .tf-scene-label strong{font-size:7px}.tf-scene-label b{font-size:9px}.tf-scene-label em{font-size:8px}}
  `;
  document.head.appendChild(style);
}

function textFor(record, id) {
  return (Array.isArray(record?.explanations) ? record.explanations : [])
    .filter(item => normalObject(item.object) === id && typeof item.text === 'string')
    .map(item => item.text).join(' ');
}

function fallbackScene(container, options) {
  let record = null, limits = {}, disposed = false;
  let cameraState = { position: [75, 68, 92], target: [0, 0, 0], zoom: 1 };
  const accent = options.variant === 'baseline' ? '#f4b06e' : '#4ee0bc';
  const root = document.createElement('div');
  root.style.cssText = 'position:absolute;inset:0';
  container.appendChild(root);
  function update() {
    if (disposed) return;
    const q = quantities(record, limits);
    const f = (key, digits = 0) => fmt(record?.[key], digits);
    const value = (key, unit, digits = 0) => record ? `${f(key, digits)} ${unit}` : '';
    const label = (x, y, title, text) => `<text x="${x}" y="${y}" font-size="9" fill="#8ea8bc">${title}</text>
      <text x="${x}" y="${y + 15}" font-size="12" font-weight="600">${escapeHtml(text)}</text>`;
    const pile = (x, y, t, shade) => {
      const h = 3 + t * 34;
      return `<path d="M${x - 25} ${y}L${x} ${y - h}L${x + 25} ${y}Z" fill="${shade}" opacity="${record ? 1 : 0.35}"/>
        <path d="M${x - 27} ${y}H${x + 27}" stroke="#b5c9c7" stroke-width="2"/>`;
    };
    root.innerHTML = `<svg class="tf-scene-fallback" viewBox="0 0 600 350" role="img"
      aria-label="Схема выбранного состояния рудника. WebGL недоступен.">
      <defs><linearGradient id="tf-bg-${options.variant || 'scene'}" x2="1" y2="1">
        <stop stop-color="#1c3040"/><stop offset="1" stop-color="#10212d"/></linearGradient></defs>
      <rect width="600" height="350" fill="#101e2c"/>
      <path d="M30 55L527 38L574 278L72 310Z" fill="url(#tf-bg-${options.variant || 'scene'})" stroke="#3b5060"/>
      <g fill="none" stroke="#9c7a5d" stroke-width="10">
        <ellipse cx="138" cy="168" rx="76" ry="49"/><ellipse cx="138" cy="168" rx="58" ry="35"/>
        <ellipse cx="138" cy="168" rx="39" ry="22"/></g>
      <path d="M194 176L246 216L310 196M284 216L380 156L470 224" fill="none" stroke="#7f8990" stroke-width="5"/>
      ${pile(251, 218, q.soft, '#c9ad75')}${pile(300, 235, q.hard, '#998b7b')}
      <g stroke="#748ea0" stroke-width="2" fill="${accent}">
        <path d="M86 104V63M86 66L70 51M86 66L109 62M86 66L80 87" fill="none"/>
        <path d="M140 93V52M140 55L124 40M140 55L163 51M140 55L134 76" fill="none"/>
      </g>
      <g fill="${q.solar > 0 ? '#2f7590' : '#274356'}" stroke="#7798b0" stroke-width="1">
        <path d="M255 79L310 76L323 103L268 107Z"/><path d="M320 75L375 72L388 99L333 103Z"/></g>
      <g stroke="#8aa3b3"><rect x="345" y="138" width="58" height="37" rx="6" fill="${q.line1 ? accent : '#405063'}"/>
        <rect x="415" y="166" width="58" height="37" rx="6" fill="${q.line2 ? accent : '#405063'}"/></g>
      <g fill="#233d4c" stroke="#6e8b9b"><rect x="455" y="238" width="65" height="26" rx="3"/>
        <rect x="89" y="248" width="75" height="14" rx="3"/></g>
      <rect x="458" y="241" width="${59 * q.battery}" height="20" rx="2" fill="${q.battery < 0.15 ? '#ff746b' : accent}"/>
      <rect x="92" y="251" width="${69 * q.fleet}" height="8" rx="2" fill="${q.fleet < 0.15 ? '#ff746b' : accent}"/>
      <path d="M494 84V146M481 113H507M484 98H504M487 84H501M481 146L494 84L507 146"
        fill="none" stroke="${q.fault || q.gridStress > 1.005 ? '#ff746b' : '#b4c8d3'}" stroke-width="2"/>
      ${label(65, 192, 'КАРЬЕР', value('mine_tph', 'т/ч'))}
      ${label(70, 279, 'ЭЛЕКТРОПАРК', value('fleet_mwh', 'МВт·ч', 1))}
      ${label(222, 250, 'МЯГКАЯ / ТВЁРДАЯ РУДА', record ? `${f('pile_soft_t')} / ${f('pile_hard_t')} т` : '')}
      ${label(345, 119, 'ЛИНИЯ 1', value('line1_tph', 'т/ч'))}
      ${label(415, 213, 'ЛИНИЯ 2', value('line2_tph', 'т/ч'))}
      ${label(60, 25, 'ВЕТЕР', value('wind_mw', 'МВт', 1))}
      ${label(263, 42, 'СОЛНЦЕ', value('pv_mw', 'МВт', 1))}
      ${label(450, 284, 'НАКОПИТЕЛЬ', value('bess_mwh', 'МВт·ч', 1))}
      ${label(433, 50, 'СЕТЬ / ПРЕДЕЛ', record ? `${f('grid_mw', 1)} / ${f('cap_mw', 1)} МВт` : '')}
      <text x="11" y="337" font-size="10" fill="#a3b9c7">2D-схема · WebGL недоступен · данные того же расчёта</text>
      </svg>`;
    root.title = (Array.isArray(record?.explanations) ? record.explanations : [])
      .map(item => item.text || '').join('\n');
  }
  update();
  return {
    setFrame(next, nextLimits = {}) { record = next; limits = nextLimits; update(); },
    setCamera(next) { if (next) cameraState = next; },
    getCamera() { return { position: [...cameraState.position], target: [...cameraState.target], zoom: cameraState.zoom }; },
    resize() {},
    dispose() { disposed = true; root.remove(); container.classList.remove('tynys-future-scene'); },
  };
}

export function createFutureScene(container, { variant = 'tynys', onCameraChange } = {}) {
  if (!(container instanceof HTMLElement)) throw new TypeError('createFutureScene: container must be an HTML element');
  installStyles();
  container.classList.add('tynys-future-scene');
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ antialias: false, alpha: false, powerPreference: 'low-power' });
  } catch {
    return fallbackScene(container, { variant, onCameraChange });
  }
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.25));
  renderer.setClearColor(C.night, 1);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.3;
  renderer.domElement.setAttribute('aria-label', 'Схематическая модель рудника. Перетаскивание вращает камеру, колесо меняет масштаб.');
  renderer.domElement.setAttribute('role', 'img');
  container.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  const camera = new THREE.OrthographicCamera(-57, 57, 36, -36, 0.1, 350);
  camera.position.set(75, 68, 92);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.target.set(0, 0, 0);
  controls.enableDamping = false;
  controls.enablePan = false;
  controls.minZoom = 0.7;
  controls.maxZoom = 2.5;
  controls.minPolarAngle = 0.28;
  controls.maxPolarAngle = 1.22;
  controls.update();
  let userCameraChange = false, applyingCamera = false, disposed = false;
  const cameraState = () => ({
    position: camera.position.toArray(), target: controls.target.toArray(), zoom: camera.zoom,
  });
  controls.addEventListener('start', () => { userCameraChange = true; });
  controls.addEventListener('end', () => { userCameraChange = false; });
  controls.addEventListener('change', () => {
    if (userCameraChange && !applyingCamera && typeof onCameraChange === 'function') onCameraChange(cameraState());
  });
  scene.add(new THREE.HemisphereLight(0xc3dce8, 0x67523d, 2.1));
  const sun = new THREE.DirectionalLight(0xffe1bc, 2.9);
  sun.position.set(-30, 60, 35);
  scene.add(sun);
  const accent = variant === 'baseline' ? C.copper : C.green;
  const geometries = new Map(), materials = new Map();
  const geometry = (key, factory) => {
    if (!geometries.has(key)) geometries.set(key, factory());
    return geometries.get(key);
  };
  const material = color => {
    if (!materials.has(color)) materials.set(color, new THREE.MeshStandardMaterial({
      color, roughness: 0.86, metalness: 0.12,
    }));
    return materials.get(color);
  };
  const mutableMaterial = color => new THREE.MeshStandardMaterial({ color, roughness: 0.8, metalness: 0.16 });
  const mesh = (geo, mat, pos, scale, parent = scene) => {
    const item = new THREE.Mesh(geo, typeof mat === 'number' ? material(mat) : mat);
    if (pos) item.position.set(...pos);
    if (scale) item.scale.set(...scale);
    parent.add(item);
    return item;
  };
  const boxGeo = geometry('box', () => new THREE.BoxGeometry(1, 1, 1));
  const cylGeo = geometry('cylinder', () => new THREE.CylinderGeometry(1, 1, 1, 12));
  const coneGeo = geometry('cone', () => new THREE.ConeGeometry(1, 1, 12));
  const box = (color, pos, size, parent) => mesh(boxGeo, color, pos, size, parent);
  const cylinder = (color, pos, size, parent) => mesh(cylGeo, color, pos, size, parent);
  const group = (x, y, z, parent = scene) => {
    const item = new THREE.Group();
    item.position.set(x, y, z);
    parent.add(item);
    return item;
  };
  const lineBetween = (a, b, color, width = 0.1, parent = scene) => {
    const va = new THREE.Vector3(...a), vb = new THREE.Vector3(...b), delta = vb.clone().sub(va);
    const beam = cylinder(color, va.clone().add(vb).multiplyScalar(0.5).toArray(), [width, delta.length(), width], parent);
    beam.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), delta.normalize());
    return beam;
  };
  const ellipse = (rx, ry, reverse = false) => {
    const path = new THREE.Path();
    path.absellipse(0, 0, rx, ry, 0, Math.PI * 2, reverse);
    return path;
  };

  // A cut into the terrain, rather than a stack of above-ground discs.
  const terrain = new THREE.Shape();
  terrain.moveTo(-45, -27); terrain.lineTo(43, -27); terrain.lineTo(43, 27);
  terrain.lineTo(-45, 27); terrain.closePath();
  const pitHole = new THREE.Path();
  pitHole.absellipse(-25, 4, 16, 11.2, 0, Math.PI * 2, true);
  terrain.holes.push(pitHole);
  const terrainGeo = geometry('terrain', () => new THREE.ExtrudeGeometry(terrain, {
    depth: 6.5, bevelEnabled: false, curveSegments: 32,
  }));
  const terrainMesh = mesh(terrainGeo, C.sand, [0, -6.75, 0]);
  terrainMesh.rotation.x = -Math.PI / 2;
  box(C.dark, [-1, -7.3, 0], [89, 1.2, 55]);
  for (let i = 0; i < 5; i++) {
    const r = 16 - i * 2.55;
    const shape = new THREE.Shape(ellipse(r, r * 0.7).getPoints(48));
    if (i < 4) shape.holes.push(ellipse(r - 2.5, (r - 2.5) * 0.7, true));
    const ring = mesh(geometry(`bench-${i}`, () => new THREE.ExtrudeGeometry(shape, {
      depth: 1.15, bevelEnabled: false, curveSegments: 32,
    })), i % 2 ? C.sand : C.bench, [-25, -1.4 - i * 1.2, -4]);
    ring.rotation.x = -Math.PI / 2;
  }
  // Mine access road and a few fixed benches visually identify the extraction.
  for (let i = 0; i < 5; i++) {
    const road = box(C.road, [-12.5 - i * 1.75, -0.2 - i * 1.15, -1 + i * 0.8], [5.3, 0.12, 2.2]);
    road.rotation.z = -0.26;
  }
  box(C.road, [2, -0.15, 23], [73, 0.15, 2.9]);
  box(C.road, [-10, -0.14, 13], [3, 0.15, 20]);
  box(C.road, [15, -0.14, 10], [45, 0.15, 2.8]);
  for (let x = -31; x < 36; x += 6) box(0xc8b48e, [x, -0.04, 23], [2.1, 0.03, 0.13]);

  // Stockpile volume is proportional to the cube of the displayed scale.
  const softPile = mesh(coneGeo, 0xc6b171, [-3, 0, 12], [0.1, 0.1, 0.1]);
  const hardPile = mesh(coneGeo, 0x8b8e88, [5, 0, 17], [0.1, 0.1, 0.1]);
  for (const p of [[-3, 12], [5, 17]]) {
    box(C.dark, [p[0], -0.01, p[1]], [8, 0.12, 8]);
    for (let x = -3.8; x <= 3.8; x += 7.6) box(C.steel, [p[0] + x, 0.6, p[1]], [0.12, 1.2, 8]);
  }
  // Re-add piles after the pads only for readability; depth testing controls visibility.
  function makePlant(x, z) {
    const parent = group(x, 0, z);
    const paint = mutableMaterial(C.steel);
    box(C.dark, [0, 0.1, 0], [10, 0.25, 7.6], parent);
    box(paint, [0, 2.2, -1.7], [8.6, 4.2, 3.6], parent);
    const roof = box(C.white, [0, 4.4, -1.7], [9.2, 0.35, 4.1], parent);
    roof.rotation.z = -0.05;
    for (let i = -3; i <= 3; i += 2) box(C.dark, [i, 2.7, 0.15], [0.9, 1.5, 0.15], parent);
    const drum = group(0, 2.1, 2, parent);
    const drumMesh = cylinder(paint, [0, 0, 0], [1.7, 5.5, 1.7], drum);
    drumMesh.rotation.z = Math.PI / 2;
    for (const x of [-2, 2]) {
      const band = cylinder(C.white, [x, 0, 0], [1.78, 0.24, 1.78], drum);
      band.rotation.z = Math.PI / 2;
    }
    box(accent, [0, 1.64, 0], [5.7, 0.2, 0.2], drum);
    for (const x of [-3, 3]) box(C.dark, [x, 0.9, 2], [0.5, 1.8, 2.4], parent);
    return { parent, drum, paint };
  }
  const plant1 = makePlant(13, -3);
  const plant2 = makePlant(25, 4);
  lineBetween([-1, 2.2, 10], [9, 2.8, 0], C.dark, 0.8);
  lineBetween([6, 2.2, 14], [21, 2.8, 7], C.dark, 0.8);
  for (let i = 0; i < 3; i++) {
    cylinder(C.steel, [35, 1.5, 1 + i * 4], [2, 3, 2]);
    cylinder(0x3b6e7e, [35, 3.05, 1 + i * 4], [1.8, 0.12, 1.8]);
  }

  const windRotors = [];
  for (const [x, z] of [[-27, -21], [-15, -21], [-3, -21]]) {
    const tower = group(x, 0, z);
    cylinder(C.white, [0, 6, 0], [0.24, 12, 0.24], tower);
    cylinder(C.dark, [0, 0.15, 0], [1.1, 0.3, 1.1], tower);
    box(C.white, [0, 12, 0], [1.1, 0.9, 1.5], tower);
    const rotor = group(0, 12, 1, tower);
    for (let i = 0; i < 3; i++) {
      const spoke = group(0, 0, 0, rotor);
      spoke.rotation.z = (i / 3) * Math.PI * 2;
      const blade = box(C.white, [0, 2.1, 0], [0.3, 4.5, 0.11], spoke);
      blade.rotation.z = -0.12;
    }
    windRotors.push(rotor);
  }
  const solarPaint = mutableMaterial(C.solar);
  for (let row = 0; row < 3; row++) for (let col = 0; col < 5; col++) {
    const x = 6 + col * 3.6, z = -23 + row * 3.6;
    box(C.steel, [x, 0.5, z], [0.18, 1, 0.18]);
    const panel = box(solarPaint, [x, 1.1, z], [3.1, 0.13, 2.6]);
    panel.rotation.x = -0.3;
    const grid = box(C.steel, [x, 1.19, z], [0.06, 0.03, 2.55]);
    grid.rotation.x = -0.3;
  }

  const batteryPaint = mutableMaterial(accent), fleetPaint = mutableMaterial(accent);
  const batteryCells = [];
  for (let i = 0; i < 3; i++) {
    box(C.dark, [27 + i * 3.3, 1.3, 18], [2.8, 2.6, 5]);
    box(C.white, [27 + i * 3.3, 2.65, 18], [3, 0.18, 5.2]);
    const cell = box(batteryPaint, [27 + i * 3.3, 0.12, 20.55], [2.3, 0.1, 0.08]);
    batteryCells.push(cell);
    for (let z = -1.5; z <= 1.5; z += 1.5) box(C.steel, [28.45 + i * 3.3, 1.3, 18 + z], [0.08, 1.4, 0.55]);
  }
  const fleetBar = box(fleetPaint, [-22, 0.14, 20], [0.1, 0.25, 1.3]);
  box(C.dark, [-22, -0.01, 20], [15, 0.15, 1.8]);
  for (let i = 0; i < 4; i++) {
    box(C.dark, [-28 + i * 3.8, 1, 17], [0.85, 2, 0.7]);
    box(accent, [-28 + i * 3.8, 1.5, 17.38], [0.55, 0.5, 0.08]);
  }
  const gridPaint = mutableMaterial(accent);
  box(C.dark, [38, 0.1, -12], [7, 0.25, 11]);
  for (const z of [-15, -9]) {
    box(C.steel, [38, 1.7, z], [3.3, 3.2, 2.7]);
    for (const x of [-1, 0, 1]) cylinder(gridPaint, [38 + x, 3.9, z], [0.24, 1.4, 0.24]);
  }
  for (const x of [35, 41]) {
    lineBetween([x, 0, -18], [38, 10, -18], C.steel, 0.12);
    lineBetween([x, 0, -18], [38, 6.4, -18], C.steel, 0.1);
  }
  for (const y of [5.5, 7.7, 9.5]) box(C.steel, [38, y, -18], [7, 0.15, 0.3]);
  lineBetween([35, 7.8, -18], [10, 5.2, -10], gridPaint, 0.055);
  lineBetween([41, 7.8, -18], [31, 5.2, -6], gridPaint, 0.055);

  const route = new THREE.CatmullRomCurve3([
    new THREE.Vector3(-11, 0.7, 1), new THREE.Vector3(-10, 0.7, 12),
    new THREE.Vector3(-6, 0.7, 23), new THREE.Vector3(15, 0.7, 23),
    new THREE.Vector3(17, 0.7, 11), new THREE.Vector3(2, 0.7, 10),
  ], true, 'catmullrom', 0.3);
  const trucks = [];
  const wheelGeo = geometry('wheel', () => new THREE.CylinderGeometry(0.47, 0.47, 0.3, 8));
  for (let i = 0; i < 6; i++) {
    const truck = group(0, 0, 0);
    box(accent, [0.9, 0.75, 0], [0.9, 1.5, 1.4], truck);
    box(C.dark, [1.36, 1.04, 0], [0.04, 0.6, 1.15], truck);
    box(C.dark, [-0.25, 0.25, 0], [2.7, 0.4, 1.45], truck);
    box(0xc1a174, [-0.55, 1.05, 0], [1.9, 0.85, 1.45], truck);
    for (const x of [-1.05, 0.95]) for (const z of [-0.8, 0.8]) {
      const wheel = mesh(wheelGeo, C.dark, [x, 0.13, z], null, truck);
      wheel.rotation.x = Math.PI / 2;
    }
    trucks.push(truck);
  }
  // An excavator remains schematic, without pretending to encode a machine count.
  const excavator = group(-26, -4.8, -3);
  box(C.dark, [0, 0.3, 0], [4, 0.5, 2.6], excavator);
  box(accent, [0, 1.1, 0], [2.8, 1.2, 2.2], excavator);
  lineBetween([1, 1.7, 0], [4, 4.3, 0], accent, 0.35, excavator);
  lineBetween([4, 4.3, 0], [6, 1.1, 0], accent, 0.25, excavator);
  box(C.dark, [6, 0.7, 0], [1.2, 0.8, 1.7], excavator);

  const labelLayer = document.createElement('div');
  labelLayer.className = 'tf-label-layer';
  container.appendChild(labelLayer);
  const labels = LABELS.map(spec => {
    const element = document.createElement('div');
    element.className = 'tf-scene-label';
    element.innerHTML = `<strong>${spec.name}</strong><b hidden></b><em hidden></em>`;
    labelLayer.appendChild(element);
    return {
      ...spec, element, point: new THREE.Vector3(...spec.p),
      valueNode: element.querySelector('b'), reasonNode: element.querySelector('em'),
    };
  });
  const corner = document.createElement('div');
  corner.className = 'tf-scene-corner';
  corner.textContent = 'Схематическая геометрия · вращение: мышь';
  container.appendChild(corner);
  let frame = null, limits = {}, q = quantities(null, {}), width = 1, height = 1;
  let truckPhase = 0, rotorPhase = 0, drumPhase1 = 0, drumPhase2 = 0;
  let animationHandle = 0, lastTime = 0, lastDraw = 0, visible = true;
  const tempPosition = new THREE.Vector3(), tangent = new THREE.Vector3();

  function resize() {
    if (disposed) return;
    width = Math.max(container.clientWidth, 1);
    height = Math.max(container.clientHeight, 1);
    const aspect = width / height;
    camera.left = -56;
    camera.right = 56;
    camera.top = 56 / aspect;
    camera.bottom = -56 / aspect;
    camera.updateProjectionMatrix();
    renderer.setSize(width, height, false);
  }
  function updateLabels() {
    const placed = [];
    const projected = labels.map(label => {
      tempPosition.copy(label.point).project(camera);
      return { label, x: (tempPosition.x * 0.5 + 0.5) * width,
        y: (-tempPosition.y * 0.5 + 0.5) * height, z: tempPosition.z };
    }).sort((a, b) => a.y - b.y);
    for (const item of projected) {
      const { label } = item, el = label.element;
      const w = el.offsetWidth, h = el.offsetHeight;
      let x = clamp(item.x - w / 2, 4, Math.max(4, width - w - 4));
      let y = clamp(item.y - h - 5, 4, Math.max(4, height - h - 22));
      el.style.visibility = item.z < -1 || item.z > 1 ? 'hidden' : 'visible';
      for (let attempt = 0; attempt < 6; attempt++) {
        const collision = placed.find(p => x < p.x + p.w + 3 && x + w + 3 > p.x && y < p.y + p.h + 3 && y + h + 3 > p.y);
        if (!collision) break;
        const below = collision.y + collision.h + 3;
        if (below + h < height - 20) y = below;
        else x = clamp(collision.x + collision.w + 4, 4, Math.max(4, width - w - 4));
      }
      el.style.transform = `translate(${Math.round(x)}px,${Math.round(y)}px)`;
      placed.push({ x, y, w, h });
    }
  }
  function setFrame(next, nextLimits = {}) {
    if (disposed) return;
    frame = next;
    limits = nextLimits;
    q = quantities(frame, limits);
    const updatePile = (pile, fill) => {
      const size = Math.cbrt(fill);
      pile.visible = size > 0.001;
      pile.scale.set(3.7 * size, 5 * size, 3.7 * size);
      pile.position.y = 2.5 * size;
    };
    updatePile(softPile, q.soft);
    updatePile(hardPile, q.hard);
    plant1.paint.color.set(q.line1 > 0 ? C.steel : 0x65535a);
    plant2.paint.color.set(q.line2 > 0 ? C.steel : 0x65535a);
    batteryPaint.color.set(q.battery < 0.15 ? C.red : accent);
    for (const cell of batteryCells) {
      cell.scale.y = Math.max(0.015, q.battery * 2.2);
      cell.position.y = 0.22 + q.battery * 1.1;
      cell.visible = q.battery > 0;
    }
    fleetPaint.color.set(q.fleet < 0.15 ? C.red : accent);
    fleetBar.scale.x = Math.max(0.01, q.fleet * 14);
    fleetBar.position.x = -29 + q.fleet * 7;
    fleetBar.visible = q.fleet > 0;
    gridPaint.color.set(q.fault || q.gridStress > 1.005 ? C.red : q.gridStress > 0.96 ? C.copper : accent);
    solarPaint.color.copy(new THREE.Color(C.solar)).lerp(new THREE.Color(0x4382a3), q.solar);
    let visibleReasons = 0;
    for (const label of labels) {
      label.valueNode.hidden = !frame;
      label.valueNode.textContent = frame ? label.value(frame) : '';
      const reason = textFor(frame, label.id);
      label.reasonNode.textContent = reason;
      // Full reasons stay accessible in the tooltip; two short on-object notes
      // are enough to keep a 350px comparison panel readable.
      const shortReason = reason && reason.length <= 115 && visibleReasons < 2;
      label.reasonNode.hidden = !shortReason;
      if (shortReason) visibleReasons++;
      label.element.title = [label.name, frame ? label.value(frame) : '', reason].filter(Boolean).join('\n');
      let warning = false;
      if (label.id === 'grid') warning = q.fault || q.gridStress > 1.005;
      if (label.id === 'bess') warning = !!frame && q.batteryCapacity !== null && q.battery < 0.15;
      if (label.id === 'fleet') warning = !!frame && q.fleetCapacity !== null && q.fleet < 0.15;
      if (label.id === 'pile_soft') warning = q.soft > 0.97;
      if (label.id === 'pile_hard') warning = q.hard > 0.97;
      label.element.dataset.state = warning ? 'warning' : reason ? 'active' : '';
      label.element.dataset.compact = width < 420 ? 'true' : 'false';
    }
    // Start every selected snapshot from a deterministic decorative phase.
    const hour = number(frame, 'hour');
    truckPhase = ((hour * 0.019) % 1 + 1) % 1;
    rotorPhase = hour * 0.7;
    drumPhase1 = hour * 0.53;
    drumPhase2 = hour * 0.53;
    updateMotion(0);
  }
  function updateMotion(dt) {
    truckPhase = (truckPhase + dt * q.mine * 0.019) % 1;
    rotorPhase += dt * q.wind * 2.2;
    drumPhase1 += dt * q.line1 * 0.8;
    drumPhase2 += dt * q.line2 * 0.8;
    for (const rotor of windRotors) rotor.rotation.z = rotorPhase;
    plant1.drum.rotation.x = drumPhase1;
    plant2.drum.rotation.x = drumPhase2;
    for (let i = 0; i < trucks.length; i++) {
      const t = (truckPhase + i / trucks.length) % 1;
      route.getPointAt(t, tempPosition);
      route.getTangentAt(t, tangent);
      trucks[i].position.copy(tempPosition);
      trucks[i].rotation.y = -Math.atan2(tangent.z, tangent.x);
    }
  }
  function tick(time) {
    if (disposed) return;
    animationHandle = requestAnimationFrame(tick);
    if (document.hidden || !visible) {
      lastTime = time;
      return;
    }
    if (time - lastDraw < 32) return;
    const dt = lastTime ? Math.min((time - lastTime) / 1000, 0.1) : 0;
    lastTime = time;
    lastDraw = time;
    updateMotion(dt);
    renderer.render(scene, camera);
    updateLabels();
  }
  const resizeObserver = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(resize) : null;
  resizeObserver?.observe(container);
  if (!resizeObserver) window.addEventListener('resize', resize);
  const intersectionObserver = typeof IntersectionObserver !== 'undefined'
    ? new IntersectionObserver(entries => { visible = entries[0]?.isIntersecting ?? true; }, { rootMargin: '100px' })
    : null;
  intersectionObserver?.observe(container);
  // Restore the same current record if a browser restores a lost WebGL context.
  const contextRestored = () => { resize(); setFrame(frame, limits); };
  renderer.domElement.addEventListener('webglcontextrestored', contextRestored);
  resize();
  setFrame(null, {});
  animationHandle = requestAnimationFrame(tick);
  return {
    setFrame,
    setCamera(next) {
      if (disposed || !next || !Array.isArray(next.position) || next.position.length !== 3 ||
          !Array.isArray(next.target) || next.target.length !== 3 ||
          ![...next.position, ...next.target].every(finite)) return;
      applyingCamera = true;
      camera.position.fromArray(next.position);
      controls.target.fromArray(next.target);
      if (finite(next.zoom)) camera.zoom = clamp(next.zoom, 0.7, 2.5);
      camera.updateProjectionMatrix();
      controls.update();
      applyingCamera = false;
    },
    getCamera: cameraState,
    resize,
    dispose() {
      if (disposed) return;
      disposed = true;
      cancelAnimationFrame(animationHandle);
      resizeObserver?.disconnect();
      intersectionObserver?.disconnect();
      window.removeEventListener('resize', resize);
      renderer.domElement.removeEventListener('webglcontextrestored', contextRestored);
      controls.dispose();
      const allGeometries = new Set(), allMaterials = new Set();
      scene.traverse(object => {
        if (object.geometry) allGeometries.add(object.geometry);
        if (object.material) for (const mat of Array.isArray(object.material) ? object.material : [object.material]) allMaterials.add(mat);
      });
      for (const geo of allGeometries) geo.dispose();
      for (const mat of allMaterials) mat.dispose();
      renderer.dispose();
      renderer.domElement.remove();
      labelLayer.remove();
      corner.remove();
      container.classList.remove('tynys-future-scene');
    },
  };
}
