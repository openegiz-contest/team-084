// Экран «Тыныс»: все данные — из двойников Eclipse Ditto (через прокси /ditto).
const NS = 'kz.tynys';
const ASSETS = {
  'shovel-1':'Экскаватор 1','shovel-2':'Экскаватор 2',crusher:'Дробилка',
  'conveyor-crushed':'Конвейер дроблёной руды','conveyor-feed':'Конвейер питания',
  'waste-dump':'Отвал вскрыши',water:'Водовод',tailings:'Хвостовое хозяйство',
  concentrate:'Концентрат',dewatering:'Водоотлив','pit-services':'Службы карьера',
  workshops:'Мастерские',camp:'Посёлок','line-1':'Линия 1','line-2':'Линия 2',flotation:'Флотация',
  'charger-1':'Зарядная группа 1','charger-2':'Зарядная группа 2',
  'charger-3':'Зарядная группа 3','charger-4':'Зарядная группа 4',
};
const NAMES = ['site','pit','plant','energy','geology','coordinator','scenario','shadow-v0','shadow-v1','pile-soft','pile-hard',
  ...Object.keys(ASSETS),'wind','pv','bess','substation', ...Array.from({length:14},(_,i)=>`truck-${String(i+1).padStart(2,'0')}`)];
const EVENTS = {lull:['Штиль на сутки',3,24], line_trip:['Авария линии',0,8], kegoc:['Ограничение KEGOC',2,4],
  hard_ore:['Пошла твёрдая руда',0,72], plan_up:['План добычи +10 %',0,48], bess_fault:['Отказ накопителя',0,12],
  crusher_fault:['Отказ дробилки',0,8], shovel_fault:['Отказ экскаватора 1',0,8],
  conveyor_fault:['Отказ конвейера питания',0,4], water_fault:['Отказ водовода',0,4],
  charger_fault:['Отказ зарядной группы 1',0,8], crusher_service:['ТО дробилки',2,4],
  truck_failure:['Поломка самосвала',0,8], excavator_failure:['Поломка экскаватора',0,8],
  grade_drop:['Падение содержания меди',0,24], tariff_change:['Смена тарифа сети',0,24]};
const $ = id => document.getElementById(id);
const SVGNS = 'http://www.w3.org/2000/svg';
let T = {};
const v = (n, f, d = 0) => { try { return T[n].features[f].properties.value; } catch (e) { return d; } };
const numeric = x => (typeof x === 'number' || (typeof x === 'string' && x.trim() !== '')) && Number.isFinite(Number(x)) ? Number(x) : null;
const fmt = (x, k = 0) => numeric(x) === null ? '—' : Number(x).toLocaleString('ru-RU', {maximumFractionDigits: k, minimumFractionDigits: k});
const GOALS = {copper: 'Больше меди', green: 'Меньше CO₂'};
const goalNote = goal => goal === 'copper'
  ? 'Приоритет ценности меди: разрешён более тонкий помол. Выпуск может вырасти вместе с энергопотреблением и CO₂ относительно V0.'
  : goal === 'green'
    ? 'Выбрана цель снижения CO₂. Результат зависит от доступных ВИЭ, выпуска и запасов; снижение относительно V0 в каждом периоде не гарантировано.'
    : 'Выбранная цель не получена из Ditto; режим по умолчанию не подставляется.';

function describeFlexStats(row) {
  if (!row) return 'Статистика резерва не передана в Ditto. Оценка текущего часа показана выше.';
  const value = key => { const n = numeric(row[key]); return n !== null && n >= 0 ? n : null; };
  const median = (key, unit) => value(key) === null ? 'медиана не передана' : `медиана ${fmt(value(key), 1)} ${unit}`;
  const interval = (prefix, unit) => {
    const low = value(prefix + '_p10'), high = value(prefix + '_p90');
    return low !== null && high !== null && low <= high
      ? `p10–p90: ${fmt(low, 1)}–${fmt(high, 1)} ${unit}` : 'интервал p10–p90 не передан или некорректен';
  };
  const mean = (key, unit) => value(key) === null ? 'не передано' : `${fmt(value(key), 1)} ${unit}`;
  return [
    'Предрасчёт: 4 сезона × 14 суток на погоде 2024.',
    `Мощность: ${median('mw_median', 'МВт')}; ${interval('mw', 'МВт')}.`,
    `Длительность: ${median('h_median', 'ч')}; ${interval('h', 'ч')}.`,
    `Среднее мощности: ${mean('mw_mean', 'МВт')}; среднее длительности: ${mean('h_mean', 'ч')}.`,
    'Редкие длительные оценки до 48 ч повышают среднее. Медианы мощности и длительности рассчитаны отдельно и не задают проверенное сочетание МВт и часов. Это статистика мгновенных оценок модели, а не гарантия помощи сети.'
  ].join('\n\n');
}

function renderComparisonContext() {
  const selected = v('scenario', 'goal', null), decision = v('coordinator', 'goal', null);
  const source = v('plant', 'decision_source', null);
  const chosen = Object.hasOwn(GOALS, selected) ? `Выбрано: «${GOALS[selected]}».` : 'Выбранная цель не передана в Ditto.';
  const last = source === 'fallback_v1' ? 'Последний час отработан по резервному правилу V1.'
    : source === 'coordinator' && Object.hasOwn(GOALS, decision)
      ? `Цель последнего решения координатора: «${GOALS[decision]}».`
      : 'Цель последнего применённого решения не подтверждена.';
  $('comparison-goal').textContent = chosen + ' ' + last;
  const elapsed = numeric(v('site', 'elapsed_hours', null));
  const time = v('site', 'sim_time', null);
  $('comparison-period').textContent = elapsed !== null && elapsed >= 0
    ? `Накоплено за ${fmt(elapsed)} завершённых модельных ч${typeof time === 'string' && time ? ' к ' + time : ''}.`
    : 'Итоги с начала прогона; точная длительность накопления не передана.';
  const co0 = numeric(v('shadow-v0', 'co2_t', null)), co2 = numeric(v('site', 'co2_t', null));
  const emissions = $('comparison-emissions');
  const delta = co0 !== null && co2 !== null ? co2 - co0 : null;
  emissions.dataset.direction = delta === null ? 'unknown' : delta > 0 ? 'higher' : delta < 0 ? 'lower' : 'equal';
  emissions.textContent = delta === null ? 'Сравнение CO₂ из сети ожидает данных обоих вариантов.'
    : delta === 0 ? 'Накопленный CO₂ из сети у Тыныс и V0 совпадает в переданных данных.'
      : `Накопленный CO₂ из сети у Тыныс на ${fmt(Math.abs(delta), 1)} т ${delta > 0 ? 'выше' : 'ниже'} V0 за показанный период.`;
  for (const [id, goal] of [['g-copper', 'copper'], ['g-green', 'green']]) {
    $(id).className = selected === goal ? 'on' : '';
    $(id).setAttribute('aria-pressed', String(selected === goal));
  }
  $('g-note').textContent = goalNote(selected);
}

async function api(method, path, body) {
  const r = await fetch('ditto/api/2/' + path, {method, headers: {'Content-Type': 'application/json'}, body: body ? JSON.stringify(body) : undefined});
  if (!r.ok && r.status !== 204) throw new Error(r.status);
  return r.status === 204 ? null : r.json().catch(() => null);
}

// ---------- статичные элементы ----------
const road = $('road'), roadLen = road.getTotalLength();
const trucksG = $('trucks');
for (let i = 0; i < 14; i++) { const c = document.createElementNS(SVGNS, 'rect'); c.setAttribute('width', 14); c.setAttribute('height', 9); c.setAttribute('rx', 2); trucksG.appendChild(c); }
for (let i = 0; i < 6; i++) {
  const g = document.createElementNS(SVGNS, 'g'); g.setAttribute('transform', `translate(${(i % 3) * 32},${Math.floor(i / 3) * 52})`);
  g.innerHTML = `<line x1="0" y1="0" x2="0" y2="45" stroke="#cfd8e0" stroke-width="2"/><g transform="translate(0,0)"><g class="rot"><path d="M0,0 L-2,-18 L2,-18Z M0,0 L15,9 L13,12Z M0,0 L-15,9 L-13,12Z" fill="#e6edf3"/></g></g>`;
  $('windfarm').appendChild(g);
}
for (let i = 0; i < 8; i++) { const r = document.createElementNS(SVGNS, 'rect');
  r.setAttribute('x', (i % 4) * 20); r.setAttribute('y', Math.floor(i / 4) * 22); r.setAttribute('width', 17); r.setAttribute('height', 18);
  r.setAttribute('fill', '#2b4b78'); r.setAttribute('class', 'pvp'); $('pvfield').appendChild(r); }
const tune = document.createElement('div');
tune.style.cssText = 'display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:8px;font-size:11px;color:var(--muted)';
tune.innerHTML = '<label>Линия аварии <select id="ev-line"><option value="1">1</option><option value="2" selected>2</option></select></label>' +
  '<label>Длительность, ч <input id="ev-duration" type="number" min="1" max="168" value="24"></label>' +
  '<label>Снижение KEGOC, МВт <input id="ev-grid-drop" type="number" min="0" max="300" step="5" value="80"></label>' +
  '<label>Отказ самосвалов, % <input id="ev-truck-loss" type="number" min="0" max="100" value="25"></label>' +
  '<label>Отказ экскаватора, % <input id="ev-exc-loss" type="number" min="0" max="100" value="50"></label>' +
  '<label>Падение содержания, % <input id="ev-grade-drop" type="number" min="0" max="100" value="10"></label>' +
  '<label>Изменение тарифа, % <input id="ev-tariff-change" type="number" min="-90" max="500" value="50"></label>';
$('btns').before(tune);
for (const [k, [title]] of Object.entries(EVENTS)) {
  const b = document.createElement('button'); b.textContent = title; b.onclick = () => addEvent(k); $('btns').appendChild(b);
}

// ---------- what-if через двойник scenario ----------
async function writeScenario(events, goal) {
  const retainedGoal = goal ?? v('scenario', 'goal', null);
  if (!Object.hasOwn(GOALS, retainedGoal)) {
    $('g-note').textContent = 'Изменение не отправлено: текущая цель ещё не получена. Дождитесь данных или выберите цель явно.';
    return;
  }
  const rev = (v('scenario', 'rev', 0) || 0) + 1;
  await api('PUT', `things/${NS}:scenario/features`, {events: {properties: {value: JSON.stringify(events)}},
    rev: {properties: {value: rev}}, goal: {properties: {value: retainedGoal}}});
  await poll();
}
function curEvents() { try { return JSON.parse(v('scenario', 'events', '[]') || '[]'); } catch (e) { return []; } }
async function addEvent(kind) {
  const [, lead, defaultDur] = EVENTS[kind]; const t = v('site', 'sim_hour', 0);
  const num = (id, fallback) => Number.isFinite(+$(id).value) ? +$(id).value : fallback;
  const dur = Math.max(1, Math.min(168, num('ev-duration', defaultDur)));
  const ev = {kind, t0: t + 1 + lead, dur, id: Date.now()};
  if (kind === 'line_trip') ev.line = num('ev-line', 2);
  if (kind === 'kegoc') ev.grid_drop_mw = num('ev-grid-drop', 80);
  if (kind === 'truck_failure') ev.loss_pct = num('ev-truck-loss', 25);
  if (kind === 'excavator_failure') ev.loss_pct = num('ev-exc-loss', 50);
  if (kind === 'grade_drop') ev.drop_pct = num('ev-grade-drop', 10);
  if (kind === 'tariff_change') ev.change_pct = num('ev-tariff-change', 50);
  await writeScenario([...curEvents().filter(e => e.t0 + e.dur > t), ev]);
}
async function cancelEvent(id) { await writeScenario(curEvents().filter(e => e.id !== id)); }

$('g-copper').onclick = () => writeScenario(curEvents(), 'copper');
$('g-green').onclick = () => writeScenario(curEvents(), 'green');

// ---------- отрисовка ----------
let rot = 0;
function render() {
  const t = v('site', 'sim_hour', null); if (t == null) return;
  $('geo-active').textContent = ['soft','hard'].map(d => `${d==='soft'?'Мягкий':'Твёрдый'} забой ${v('geology','active_'+d,'—')}: BWi ${fmt(v('geology','bwi_'+d,null),1)} кВт·ч/т; Cu ${fmt(v('geology','grade_'+d+'_pct',null),2)}%; LCT ${fmt(v('geology','recovery_'+d+'_pct',null),1)}%`).join(' · ');
  const maint = $('maintenance-plan'); maint.replaceChildren();
  for (const id of ['line-1','line-2']) {
    const line = document.createElement('p'), start = v(id,'maintenance_start_h',-1);
    const kind = v(id,'maintenance_kind')==='liner'?'футеровка':'ТО';
    line.textContent = `${ASSETS[id]}: ${start>=t?`${kind} с часа ${start}, крайний старт ${v(id,'maintenance_deadline_h')}`:v(id,'state')==='maintenance'?`${kind} выполняется`:'окно ещё не назначено'}; ресурс футеровки ${fmt(v(id,'liner_remaining_pct',100))}%.`;
    maint.appendChild(line);
  }
  const states = {running:'Работает',idle:'Простой',fault:'Отказ',maintenance:'ТО / ремонт',lockout:'Блокировка'};
  const body = $('equipment-rows'); body.replaceChildren();
  for (const [id, title] of Object.entries(ASSETS)) {
    const row = document.createElement('tr');
    const flow = v(id,'flow_m3_h',null) ?? v(id,'throughput_tph',null) ?? v(id,'rate_tph',null) ?? v(id,'feed_tph',null) ?? v(id,'inflow_tph',null);
    const speed = v(id,'speed_rpm',null);
    const cells = [title,states[v(id,'state')] || '—',
      flow === null ? '—' : fmt(flow,1)+(id==='water'?' м³/ч':' т/ч'),
      fmt(v(id,'power_mw',null),2), speed===null?'—':fmt(speed,1),fmt(v(id,'p80_um',null)),
      fmt(v(id,'health_pct',null),1),fmt(v(id,'availability_pct',null),1)];
    for (const value of cells) { const cell=document.createElement('td');cell.textContent=value;row.appendChild(cell); }
    body.appendChild(row);
  }
  $('material-stocks').textContent = `С начала прогона: вскрыша ${fmt(v('waste-dump','tonnes'))} т · хвосты ${fmt(v('tailings','tonnes'))} т · концентрат ${fmt(v('concentrate','tonnes'))} т. Вода: свежая ${fmt(v('water','fresh_m3_h'))} + оборотная ${fmt(v('water','recycle_m3_h'))} = ${fmt(v('water','flow_m3_h'))} м³/ч.`;
  $('clock').textContent = `модельное время ${v('site', 'sim_time', '')} · час ${t}`;
  const mode = v('coordinator', 'mode', '—');
  $('mode-t').textContent = mode === 'вдох' ? 'ВДОХ · копим энергию' : mode === 'выдох' ? 'ВЫДОХ · экономим' : '—';
  $('mode').className = 'mode ' + (mode === 'вдох' ? 'inhale' : 'exhale');
  $('whybox').className = 'panel why ' + (mode === 'вдох' ? '' : 'exhale');
  // главные показатели
  const cu0 = numeric(v('shadow-v0', 'cu_adj_t', null)), cu2 = numeric(v('site', 'cu_adj_t', null));
  $('k-co2').textContent = fmt(v('substation', 'co2_t_h', null));
  $('k-ren').textContent = fmt(v('energy', 'renew_share_pct', null)) + ' %';
  $('k-cur').textContent = fmt(v('energy', 'curtail_mw', null));
  $('k-cu').textContent = cu0 > 0 && cu2 !== null ? (cu2 >= cu0 ? '+' : '') + fmt(100 * (cu2 - cu0) / cu0, 1) + ' %' : '—';
  $('k-res').textContent = fmt(v('substation', 'flex_down_mw', null));
  $('why').textContent = v('coordinator', 'why', '—');
  $('src').textContent = v('plant', 'decision_source') === 'coordinator'
    ? `решение MPC за ${v('coordinator', 'solve_ms', 0)} мс · теневая цена энергии ${fmt(v('coordinator', 'shadow_kzt_kwh'), 1)} ₸/кВт·ч`
    : 'координатор не ответил — работает запасное правило V1';
  // карьер, склады, линии
  $('t-pit').textContent = `${fmt(v('pit', 'ore_tph'))} т/ч руды · твёрдой ${fmt(100 * v('pit', 'hard_frac'))} %`;
  for (const [d, id, tid, name] of [['soft', 'pile-soft', 't-ps', 'мягкая'], ['hard', 'pile-hard', 't-ph', 'твёрдая']]) {
    const f = v(id, 'fill_pct', 0) / 100; $(id).firstElementChild.setAttribute('transform', `scale(${0.3 + 0.9 * f})`);
    $(tid).textContent = `${name} ${fmt(v(id, 'tonnes') / 1000)} кт (${fmt(100 * f)} %)`;
  }
  for (let l = 0; l < 2; l++) {
    const n = `line-${l + 1}`, g = $('line' + l), q = v(n, 'feed_tph', 0);
    g.querySelector('.t').textContent = !v(n, 'available', true) ? 'АВАРИЯ' : q > 0 ? `${fmt(q)} т/ч · ${fmt(v(n, 'load_pct'))} %` : 'остановлена';
    g.querySelector('rect').setAttribute('stroke', !v(n, 'available', true) ? '#e0675a' : q > 0 ? '#4fd18b' : '#3d5a78');
    g.dataset.q = q;
  }
  $('t-flot').textContent = `${fmt(v('flotation', 'cu_tph'), 1)} т меди/ч · извл. ${fmt(v('flotation', 'recovery'), 1)} %`;
  // энергия
  $('t-wind').textContent = `${fmt(v('wind', 'power_mw'))} из 300 МВт`;
  $('t-pv').textContent = `${fmt(v('pv', 'power_mw'))} из 250 МВт`;
  const soc = v('bess', 'soc', 0); $('bessbar').setAttribute('y', 54 - 0.48 * soc); $('bessbar').setAttribute('height', 0.48 * soc);
  $('t-bess').textContent = v('bess', 'available', true) ? `${fmt(soc)} %` : 'ОТКАЗ';
  $('t-grid').textContent = `${fmt(v('substation', 'grid_mw'))} / ${fmt(v('substation', 'grid_cap_mw'))} МВт`;
  $('t-charge').textContent = `${fmt(v('energy', 'charge_mw'))} МВт`;
  $('t-curt').textContent = v('energy', 'curtail_mw', 0) > 1 ? `сброс ВИЭ ${fmt(v('energy', 'curtail_mw'))} МВт` : '';
  document.querySelectorAll('.pvp').forEach(r => r.setAttribute('fill', v('pv', 'power_mw', 0) > 5 ? '#4a7fc0' : '#22334a'));
  $('flow-grid').setAttribute('stroke-width', 1 + v('substation', 'grid_mw', 0) / 30);
  $('flow-ren').setAttribute('stroke-width', 1 + (v('wind', 'power_mw', 0) + v('pv', 'power_mw', 0)) / 50);
  // KPI
  const cols = ['shadow-v0', 'shadow-v1', 'site'];
  const rows = [['Медь, т', 'cu_t', 0], ['Медь с учётом склада, т', 'cu_adj_t', 0], ['Из сети, МВт·ч', 'grid_mwh', 0], ['CO₂ из сети, т', 'co2_t', 0], ['CO₂ с учётом запасов, т', 'co2_adj_t', 0], ['CO₂ на т меди (с учётом запасов)', 'co2_per_t_cu', 2],
    ['Сброс ВИЭ, МВт·ч', 'curtail_mwh', 0], ['Оплата сети, млн ₸', 'grid_cost_mkzt', 0]];
  const CU_MKZT = 9500 * 480 * 0.85 / 1e6;   // оплачиваемая медь, млн ₸/т (допущение, params.py)
  const margin = c => {
    const copper = numeric(v(c, 'cu_adj_t', null)), cost = numeric(v(c, 'grid_cost_mkzt', null));
    return copper !== null && cost !== null ? copper * CU_MKZT - cost : null;
  };
  const best = Math.max(...cols.map(margin).filter(x => x !== null));
  // Older field services used the same intensity key for gross CO₂. Do not
  // label that value as inventory-adjusted without the new companion metric.
  const metric = (c, f) => f === 'co2_per_t_cu' && numeric(v(c, 'co2_adj_t', null)) === null
    ? null : v(c, f, null);
  rows.push(['<b>Медь − энергия, млн ₸</b>', null, 0]);
  $('kt').innerHTML = rows.map(([lbl, f, k]) => f === null
    ? `<tr><td>${lbl}</td>${cols.map(c => `<td style="${margin(c) === best ? 'color:var(--v2);font-weight:700' : ''}">${fmt(margin(c))}</td>`).join('')}</tr>`
    : `<tr><td>${lbl}</td>${cols.map(c => `<td>${fmt(metric(c, f), k)}</td>`).join('')}</tr>`).join('');
  renderComparisonContext();
  $('flex').textContent = fmt(v('substation', 'flex_down_mw', null)); $('flexh').textContent = fmt(v('substation', 'flex_down_h', null), 1);
  const now = [['Нагрузка', fmt(v('energy', 'load_mw')) + ' МВт'], ['ВИЭ', fmt(v('energy', 'renew_mw')) + ' МВт'],
    ['Доля ВИЭ', fmt(v('energy', 'renew_share_pct')) + ' %'], ['Сеть', fmt(v('energy', 'grid_mw')) + ' МВт'],
    ['CO₂ сейчас', fmt(v('substation', 'co2_t_h')) + ' т/ч'], ['Переработка', fmt(v('plant', 'feed_tph')) + ' т/ч'],
    ['Твёрдость (оценка)', `${fmt(v('pile-soft', 'bwi_est'), 1)} / ${fmt(v('pile-hard', 'bwi_est'), 1)} кВт·ч/т`]];
  $('now').innerHTML = now.map(([a, b]) => `<tr><td>${a}</td><td>${b}</td></tr>`).join('');
  // события
  const evs = curEvents();
  $('events').innerHTML = evs.length ? '' : '<span class="mute">Сценариев нет — обычная работа.</span>';
  for (const e of evs) {
    const d = document.createElement('div');
    const st = t < e.t0 ? `через ${e.t0 - t} ч` : t < e.t0 + e.dur ? `идёт, ещё ${e.t0 + e.dur - t} ч` : 'завершён';
    d.innerHTML = `<span>${EVENTS[e.kind][0]} <span class="mute">· ${st}</span></span>`;
    const b = document.createElement('button'); b.textContent = 'отменить'; b.onclick = () => cancelEvent(e.id); d.appendChild(b);
    $('events').appendChild(d);
  }
  drawPlan();
}

function drawPlan() {
  let P; try { P = JSON.parse(v('coordinator', 'plan_json', '{}')); } catch (e) { return; }
  if (!P.renew_mw) return;
  const H = P.renew_mw.length, W = 640, Hh = 170, bw = W / H;
  const max = Math.max(300, ...P.renew_mw, ...P.grid_cap_mw);
  const y = x => Hh - (x / max) * (Hh - 10);
  let s = '';
  for (let h = 0; h < H; h++) {
    const x = h * bw;
    s += `<rect x="${x + 1}" y="${y(P.renew_mw[h])}" width="${bw / 2 - 1}" height="${Hh - y(P.renew_mw[h])}" fill="var(--wind)" opacity=".8"/>`;
    s += `<rect x="${x + bw / 2}" y="${y(P.grid_mw[h])}" width="${bw / 2 - 1}" height="${Hh - y(P.grid_mw[h])}" fill="var(--grid)" opacity=".8"/>`;
    const hf = P.feed_tph[h] ? P.hard_tph[h] / P.feed_tph[h] : 0;
    s += `<rect x="${x + 1}" y="${Hh + 6}" width="${bw - 2}" height="10" fill="var(--hard)" opacity="${0.15 + 0.85 * hf}"/>`;
  }
  const cap = P.grid_cap_mw.map((c, h) => `${h ? 'L' : 'M'}${h * bw},${y(c)} L${(h + 1) * bw},${y(c)}`).join(' ');
  s += `<path d="${cap}" stroke="#e0675a" stroke-dasharray="4 3" fill="none"/>`;
  const sm = Math.max(1, ...P.shadow_kzt_kwh.filter(x => x != null));
  const sp = P.shadow_kzt_kwh.map((c, h) => `${h ? 'L' : 'M'}${h * bw + bw / 2},${Hh - ((c ?? 0) / sm) * (Hh - 20)}`).join(' ');
  s += `<path d="${sp}" stroke="#fff" stroke-width="2" fill="none"/>`;
  for (const h of [0, 6, 12, 18]) s += `<text x="${h * bw + 2}" y="198" class="lbl">+${h} ч</text>`;
  $('plan').innerHTML = s;
}

function animate(ts) {
  rot = (rot + 0.4 + 6 * v('wind', 'cf_pct', 0) / 100) % 360;
  document.querySelectorAll('.rot').forEach(g => g.setAttribute('transform', `rotate(${rot})`));
  let slotC = 0, slotW = 0;
  for (let i = 0; i < 14; i++) {
    const n = `truck-${String(i + 1).padStart(2, '0')}`, r = trucksG.children[i], st = v(n, 'state', 'empty');
    let x, y;
    if (['charging','waiting','idle','unavailable','fault','maintenance'].includes(st)) { const k = st === 'charging' ? slotC++ : 7 + (slotW++ % 7); x = 304 + (k % 7) * 19; y = st === 'charging' ? 474 : 496; }
    else { const ph = (i / 14 + ts / 1000 / 90) % 1;   // анимация: полный рейс за 90 с
      const f = ph < 0.5 ? ph * 2 : 2 - ph * 2;
      const p = road.getPointAtLength(f * roadLen); x = p.x - 7; y = p.y - 4 + (ph < 0.5 ? -7 : 7); }
    r.setAttribute('x', x); r.setAttribute('y', y);
    r.setAttribute('fill', st === 'charging' ? '#5ec8e5' : st === 'waiting' ? '#ebcb88' : st === 'loaded' ? '#6ce0cc' : '#9aa6b2');
  }
  requestAnimationFrame(animate);
}

async function poll() {
  try {
    const data = await api('GET', `things?ids=${NAMES.map(n => NS + ':' + n).join(',')}&fields=thingId,features`);
    T = {}; for (const t of data) T[t.thingId.split(':')[1]] = t;
    render();
    $('connection').dataset.state = 'online'; $('conn-t').textContent = 'Ditto · подключено';
  } catch (e) { $('connection').dataset.state = 'offline'; $('conn-t').textContent = 'нет связи с Ditto'; }
}
// ---------- «сколько строить»: результаты расчёта из атрибута двойника energy ----------
let SZ = [];
function drawSizing() {
  if (!SZ.length) return;
  const w = +$('sz-w').value, p = +$('sz-p').value;
  const base = SZ.find(r => r.wind_mw == 0 && r.pv_mwp == 0 && r.variant == 'V0');
  const a = SZ.find(r => r.wind_mw == w && r.pv_mwp == p && r.variant == 'V0');
  const b = SZ.find(r => r.wind_mw == w && r.pv_mwp == p && r.variant == 'V2');
  const g = SZ.find(r => r.wind_mw == w && r.pv_mwp == p && r.variant == 'V2green');
  const x = SZ.find(r => r.wind_mw == w && r.pv_mwp == p && r.variant == 'V2fixed');
  if (!base || !a || !b) return;
  const cs = [base, a, ...(x ? [x] : []), b, ...(g ? [g] : [])];
  const row = (lbl, f, k) => [lbl, ...cs.map(r => fmt(f(r), k))];
  const adjustedIntensity = r => {
    const co2 = numeric(r.co2_adj_kt), copper = numeric(r.cu_adj_t);
    return co2 !== null && copper !== null && copper > 0 ? co2 * 1000 / copper : null;
  };
  const rows = [['', 'Сегодня', 'ВИЭ', ...(x ? ['+ Тыныс, P80 150'] : []), '+ Тыныс: медь', ...(g ? ['+ Тыныс: CO₂'] : [])],
    row('CO₂ из сети в год, тыс. т', r => r.co2_kt, 0),
    row('CO₂ с учётом запасов*, тыс. т/год', r => r.co2_adj_kt, 0),
    row('Медь в год, тыс. т', r => r.cu_adj_t / 1000, 1),
    row('CO₂ на т меди с учётом запасов*, т', adjustedIntensity, 2),
    row('Доля ВИЭ, %', r => r.renew_share_pct, 0),
    row('Сброс ВИЭ, ГВт·ч', r => r.curtail_mwh / 1000, 0)];
  $('sizing').innerHTML = rows.map((r, i) => `<tr>${r.map(c => i ? `<td>${c}</td>` : `<th>${c}</th>`).join('')}</tr>`).join('');
}
async function loadSizing() {
  try {
    const attrs = await api('GET', `things/${NS}:energy/attributes`) || {};
    SZ = attrs.sizing || [];
    const eq = attrs.wind_equivalent, current = attrs.wind_equivalent_current;
    if (eq?.status==='ok') {
      $('page-title').textContent = `Тыныс: эквивалент ${fmt(eq.equivalent_wind_mw)} МВт ВЭС${eq.archived?' в архивном расчёте':''}.`;
      $('equivalent-note').textContent = `ВЭС ${fmt(eq.wind_mw)} + СЭС ${fmt(eq.pv_mwp)}: одинаковый CO₂ при выпуске Cu в пределах ${fmt(eq.copper_tolerance_pct,1)} %. Медь ${eq.copper_change_pct!=null?(eq.copper_change_pct>0?'+':'')+fmt(eq.copper_change_pct,1)+' %':'—'}. Без координатора — ${fmt(eq.required_baseline_wind_mw)} МВт ВЭС по интерполяции (${fmt(eq.grid_step_equivalent_mw)} МВт добавления по сетке). Это эквивалент по выбросам, не гарантированная замена оборудования.`;
      if (eq.archived) $('equivalent-note').textContent += ' Архив legacy-v1. '+(current?.status==='unavailable'?'Новая модель: сопоставимый эквивалент пока не подтверждён.':'');
    }
  } catch (e) { return setTimeout(loadSizing, 5000); }
  if (!SZ.length) return;
  const uniq = k => [...new Set(SZ.map(r => r[k]))].sort((a, b) => a - b);
  $('sz-w').innerHTML = uniq('wind_mw').map(x => `<option ${x == 300 ? 'selected' : ''}>${x}</option>`).join('');
  $('sz-p').innerHTML = uniq('pv_mwp').map(x => `<option ${x == 250 ? 'selected' : ''}>${x}</option>`).join('');
  $('sz-w').onchange = $('sz-p').onchange = drawSizing; drawSizing();
}
loadSizing();
async function loadFlex() {
  try {
    const attrs = await api('GET', `things/${NS}:substation/attributes`) || {};
    const F = attrs.flex_stats || [];
    const y = Array.isArray(F) ? F.find(r => typeof r?.season === 'string' && (r.season === 'all' || r.season.startsWith('весь год'))) : null;
    const source = attrs.flex_stats_model === 'physics-v4-geomet-maintenance' ? 'Расчёт physics-v4.' : 'Архив прежней модели.';
    $('flexstat').textContent = y ? `${source} ${describeFlexStats(y)} Длительность — предел по запасам при неизменных условиях, а не гарантия выдачи резерва.` : describeFlexStats(y);
  } catch (e) {
    $('flexstat').textContent = 'Статистика резерва недоступна: нет ответа от Ditto. Повторяем подключение…';
    setTimeout(loadFlex, 5000);
  }
}
loadFlex();
poll(); setInterval(poll, 1000); requestAnimationFrame(animate);
