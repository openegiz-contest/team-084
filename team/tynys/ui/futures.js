// UI exchanges requests and immutable simulation reports through Eclipse Ditto only.
// There is deliberately no client-side result generator or implicit demo fallback.
const $ = id => document.getElementById(id);
const API = '/ditto/api/2/things/kz.tynys:';
const STATUS = {feasible: 'ВЫПОЛНИМО', partial: 'ЧАСТИЧНО', refused: 'ОТКАЗ'};
const PHASE = {preparation: 'Подготовка', prepare: 'Подготовка', lead: 'Подготовка', request: 'Ограничение', event: 'Ограничение', restriction: 'Ограничение', recovery: 'Восстановление'};
const state = {result: null, pending: null, pendingAccepted: false, superseded: false, frame: 0, online: false, playing: false, playbackTimer: null, pollTimer: null, scenes: {}, initialCameras: {}, syncingCamera: false, lastUpdated: '', lastResultId: '', dirty: false};
const number = value => typeof value === 'number' && Number.isFinite(value);
const fmt = (value, digits = 1) => number(value) ? value.toLocaleString('ru-RU', {maximumFractionDigits: digits}) : '—';
const unit = (value, suffix, digits = 1) => number(value) ? `${fmt(value, digits)} ${suffix}` : '—';
const text = (id, value) => { $(id).textContent = value; };
const feature = (thing, name, fallback = null) => thing?.features?.[name]?.properties?.value ?? fallback;
const element = (tag, className, content) => { const el = document.createElement(tag); if (className) el.className = className; if (content !== undefined) el.textContent = content; return el; };

async function api(method, path, body) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 12000);
  try {
    const response = await fetch(API + path, {method, headers: {'Content-Type': 'application/json'}, body: body === undefined ? undefined : JSON.stringify(body), signal: controller.signal, cache: 'no-store'});
    if (!response.ok) {
      const error = new Error(response.status === 404 ? 'Двойник расчёта ещё не создан. Проверьте запуск сервисов проекта.' : response.status === 401 || response.status === 403 ? 'Ditto не разрешил доступ к расчёту.' : `Ditto вернул HTTP ${response.status}.`);
      error.status = response.status;
      throw error;
    }
    return response.status === 204 || method === 'PUT' ? null : await response.json();
  } finally { clearTimeout(timeout); }
}

function requestId() {
  if (globalThis.crypto?.randomUUID) return crypto.randomUUID();
  if (!globalThis.crypto?.getRandomValues) throw new Error('Браузер не поддерживает безопасный идентификатор запроса.');
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), b => b.toString(16).padStart(2, '0')).join('');
}

function readRequest(mode) {
  return {
    id: requestId(), mode,
    reduction_mw: Number($('reduction').value),
    duration_h: Number($('duration').value),
    lead_h: Number($('lead').value),
    recovery_h: Number($('recovery').value),
    max_copper_loss_pct: Number($('loss').value),
    lull: $('lull').checked,
    bess_fault: $('bess-fault').checked,
    hard_ore: $('hard-ore').checked,
  };
}

function statusMessage(message, isError = false) {
  text('request-status', message);
  $('request-status').classList.toggle('error', isError);
}

function setConnection(kind, message) {
  $('connection').dataset.state = kind;
  $('connection').querySelector('span').textContent = message;
}

function setBusy(busy) {
  for (const id of ['submit', 'boundary', 'reset', 'reduction', 'reduction-range', 'duration', 'lead', 'recovery', 'loss', 'lull', 'bess-fault', 'hard-ore']) $(id).disabled = busy;
  document.querySelectorAll('[data-preset]').forEach(button => { button.disabled = busy; });
  $('cancel').disabled = !busy || state.pending?.mode === 'cancel';
  $('progress').hidden = !busy;
  $('request-form').setAttribute('aria-busy', String(busy));
}

function resultWarning() {
  const warnings = [];
  if (state.result) {
    if (!state.online) warnings.push('Связь с Ditto потеряна. Показан сохранённый расчёт; его результаты не обновляются.');
    if (state.pending) warnings.push('Показан предыдущий расчёт. Новый запрос ещё не завершён.');
    else if (state.superseded) warnings.push('Ваш запрос заменён из другой вкладки. Здесь сохранён предыдущий расчёт; запустите условия заново.');
    else if (state.dirty) warnings.push('Условия в форме изменены. Показанные результаты относятся к предыдущему запросу — запустите новый расчёт.');
  }
  $('result-warning').hidden = !warnings.length;
  text('result-warning', warnings.join(' '));
}

async function submitRequest(mode, onPrepared) {
  if (state.pending || !$('request-form').reportValidity()) return;
  stopPlayback();
  let request;
  try { request = readRequest(mode); } catch (error) { statusMessage(error.message, true); return; }
  state.pending = request;
  onPrepared?.(request.id);
  state.pendingAccepted = false;
  state.superseded = false;
  state.dirty = false;
  $('progress').value = 0;
  setBusy(true);
  resultWarning();
  statusMessage(mode === 'limit' ? 'Отправляем запрос на проверку длительностей…' : 'Отправляем условия в Ditto…');
  try {
    // Feature type is a JSON string, so the scalar is JSON-encoded once by api().
    await api('PUT', 'future-request/features/request_json/properties/value', JSON.stringify(request));
    if (state.pending?.id !== request.id) return;
    state.pendingAccepted = true;
    statusMessage('Запрос принят Ditto. Ожидаем расчёт сервиса…');
    schedulePoll(100);
  } catch (error) {
    if (state.pending?.id !== request.id) return;
    state.pending = null;
    state.dirty = Boolean(state.result);
    setBusy(false);
    resultWarning();
    statusMessage(error.name === 'AbortError' ? 'Ditto не подтвердил получение запроса вовремя. Проверьте соединение и повторите.' : error.message, true);
  }
}

async function cancelRequest() {
  if (!state.pending || state.pending.mode === 'cancel') return;
  const previous = state.pending;
  const cancel = {id: requestId(), mode: 'cancel'};
  state.pending = cancel;
  state.pendingAccepted = false;
  setBusy(true);
  statusMessage('Отправляем отмену расчёта…');
  try {
    await api('PUT', 'future-request/features/request_json/properties/value', JSON.stringify(cancel));
    state.pendingAccepted = true;
    statusMessage('Ожидаем подтверждение отмены…');
    schedulePoll(100);
  } catch (error) {
    state.pending = previous;
    state.pendingAccepted = true;
    setBusy(true);
    statusMessage(`Отмена не подтверждена. ${error.message}`, true);
  }
}

function schedulePoll(delay = 1600) {
  clearTimeout(state.pollTimer);
  state.pollTimer = setTimeout(poll, delay);
}

async function poll() {
  try {
    const twin = await api('GET', 'future-result');
    state.online = true;
    setConnection('online', 'Ditto · подключено');
    const serviceStatus = feature(twin, 'status', 'idle');
    const id = feature(twin, 'request_id', '');
    state.serviceStatus=serviceStatus;state.serviceId=id;
    const updated = feature(twin, 'updated_at', '');
    // A request is a single shared twin. Another browser can replace it. Confirm
    // its current id after our PUT was acknowledged; an old result alone is not
    // proof of replacement because the worker may not have picked up our request.
    if (state.pending && state.pendingAccepted && id !== state.pending.id) {
      const expectedId = state.pending.id;
      const requestTwin = await api('GET', 'future-request');
      const requestRaw = feature(requestTwin, 'request_json', '');
      const currentRequest = typeof requestRaw === 'string' && requestRaw ? JSON.parse(requestRaw) : requestRaw;
      if (currentRequest?.id && currentRequest.id !== expectedId && state.pending?.id === expectedId) {
        state.pending = null;
        state.pendingAccepted = false;
        state.superseded = true;
        state.dirty = true;
        setBusy(false);
        statusMessage('Ваш запрос заменён в другой вкладке. Можно снова отправить выбранные условия.', true);
        resultWarning();
        return;
      }
    }
    const matches = Boolean(state.pending && state.pending.id === id);
    if (matches && serviceStatus === 'running') {
      const progress = feature(twin, 'progress');
      $('progress').value = number(progress) ? Math.max(0, Math.min(100, progress)) : 0;
      statusMessage(`${feature(twin, 'stage', 'Моделируем последствия…')}${number(progress) ? ` · ${fmt(progress, 0)} %` : ''}`);
    } else if ((matches || (!state.pending && !state.result && !state.superseded)) && serviceStatus === 'done') {
      const raw = feature(twin, 'result_json', '');
      const result = typeof raw === 'string' ? JSON.parse(raw) : raw;
      if (!result || !Array.isArray(result.frames) || !result.frames.length || !result.verdict || result.request?.id !== id) throw new Error('Сервис вернул неполный отчёт или несовпадающий идентификатор запроса.');
      state.lastUpdated = updated;
      state.lastResultId = id;
      state.pending = null;
      state.dirty = false;
      setBusy(false);
      acceptResult(result);
      statusMessage('Расчёт завершён. Исследуйте временную шкалу и проверьте последствия.');
    } else if (matches && (serviceStatus === 'error' || serviceStatus === 'cancelled')) {
      state.pending = null;
      state.dirty = Boolean(state.result);
      setBusy(false);
      statusMessage(serviceStatus === 'cancelled' ? 'Расчёт отменён. Можно задать новые условия.' : `Расчёт не завершён: ${feature(twin, 'error', 'сервис не указал причину')}`, serviceStatus === 'error');
      if (!state.result) {
        $('verdict-status').dataset.status = serviceStatus === 'error' ? 'error' : 'idle';
        text('verdict-status', serviceStatus === 'error' ? 'ОШИБКА РАСЧЁТА' : 'ОТМЕНЕНО');
      }
    } else if (!state.pending && !state.result && !state.superseded) {
      if (serviceStatus === 'error') statusMessage(`Последний расчёт сервиса завершился ошибкой: ${feature(twin, 'error', 'причина не указана')}`, true);
      else if (serviceStatus === 'running') statusMessage('Сервис выполняет другой запрос. Вы можете отправить свои условия.');
      else statusMessage('Сервисы доступны. Выберите условия и запустите расчёт.');
    } else if (state.pending && id && id !== state.pending.id && serviceStatus === 'running') {
      statusMessage('В Ditto выполняется другой запрос. Ожидаем результат с идентификатором вашего запроса.');
    }
    resultWarning();
  } catch (error) {
    state.online = false;
    setConnection(state.result ? 'stale' : 'offline', state.result ? 'Нет связи · сохранённый расчёт' : 'Ditto недоступен');
    statusMessage(error.name === 'AbortError' ? 'Ditto не отвечает. Повторим подключение автоматически.' : error instanceof SyntaxError ? 'Не удалось прочитать JSON отчёта сервиса.' : error.message, true);
    resultWarning();
  } finally { schedulePoll(state.online ? 1600 : 4000); }
}

function syncForm(request) {
  const fields = {reduction: 'reduction_mw', duration: 'duration_h', lead: 'lead_h', recovery: 'recovery_h', loss: 'max_copper_loss_pct'};
  for (const [id, field] of Object.entries(fields)) if (number(request?.[field])) $(id).value = request[field];
  $('reduction-range').value = $('reduction').value;
  for (const [id, field] of [['lull', 'lull'], ['bess-fault', 'bess_fault'], ['hard-ore', 'hard_ore']]) $(id).checked = Boolean(request?.[field]);
}

function acceptResult(result) {
  stopPlayback();
  state.result = result;
  state.frame = 0;
  syncForm(result.request);
  renderPassport();
  renderSummary();
  renderBoundary();
  renderEvidence();
  $('timeline').max = result.frames.length - 1;
  $('timeline').value = 0;
  $('timeline').disabled = false;
  $('play').disabled = result.frames.length < 2;
  $('export').disabled = false;
  text('timeline-start', `Час ${fmt(result.frames[0].hour)}`);
  text('timeline-end', `Час ${fmt(result.frames.at(-1).hour)}`);
  text('timeline-caption', `${unit(result.request.duration_h, 'ч ограничения', 0)} · ${unit(result.request.recovery_h, 'ч после', 0)}`);
  renderFrame();
}

function renderPassport() {
  const result = state.result, verdict = result.verdict, delivery = result.summary?.delivery, recovery = result.summary?.recovery;
  const status = Object.hasOwn(STATUS, verdict.status) ? verdict.status : 'idle';
  $('verdict-status').dataset.status = status;
  text('verdict-status', STATUS[status] || 'НЕ ОПРЕДЕЛЕНО');
  text('verdict-title', verdict.title || 'Расчёт завершён');
  text('tested-reduction', fmt(verdict.tested_reduction_mw, 0));
  text('requested-mw', unit(result.request.reduction_mw, 'МВт', 0));
  text('actual-mw', unit(delivery?.actual_grid_reduction_avg_mw, 'МВт'));
  text('delivered-mwh', unit(delivery?.actual_grid_reduction_mwh, 'МВт·ч'));
  text('copper-loss', unit(recovery?.copper_loss_pct, '%', 2));
  const duration = unit(result.request.duration_h, 'ч', 0);
  let description = `Исходный запрос: снижение лимита на ${unit(result.request.reduction_mw, 'МВт', 0)} в течение ${duration}. Графики и сцены показывают именно этот запрос.`;
  if (verdict.alternative && number(verdict.alternative.reduction_mw)) description += ` Проверенная альтернатива: ${unit(verdict.alternative.reduction_mw, 'МВт', 0)} на ${duration}.`;
  text('verdict-description', description);
  const reasons = $('reasons'); reasons.replaceChildren();
  for (const reason of (Array.isArray(verdict.reasons) ? verdict.reasons : []).slice(0, 5)) {
    const item = element('li'), content = element('div');
    content.append(element('strong', '', reason.title || reason.code || 'Ограничение'));
    if (number(reason.hour)) content.append(document.createTextNode(` · час ${fmt(reason.hour)}`));
    if (reason.detail) content.append(document.createTextNode(`. ${reason.detail}`));
    item.append(content); reasons.append(item);
  }
}

function renderSummary() {
  const summary = state.result.summary || {}, recovery = summary.recovery || {};
  text('recovered-at', number(recovery.recovered_at_hour) ? `Час ${fmt(recovery.recovered_at_hour)}` : 'Не восстановлено');
  text('recovery-detail', number(recovery.recovered_at_hour) ? 'По допускам модели после ограничения' : `За ${unit(recovery.recovery_h ?? state.result.request.recovery_h, 'ч после события', 0)}; это не означает, что восстановление невозможно позже`);
  text('cu-debt', unit(recovery.copper_debt_end_t, 'т'));
  text('energy-rebound', unit(recovery.extra_grid_mwh, 'МВт·ч'));
  text('recovery-balances', `Остаток долга энергии: ${unit(recovery.energy_debt_end_mwh, 'МВт·ч')} · BESS: ${unit(recovery.bess_debt_end_mwh, 'МВт·ч')} · техника: ${unit(recovery.fleet_debt_end_mwh, 'МВт·ч')}. Недодобытая руда: ${unit(recovery.ore_debt_end_t, 'т')}.`);
  const rows = [
    ['Выпуск меди, т', 'copper_t', 1], ['Из сети, МВт·ч', 'grid_mwh', 1], ['CO₂, т', 'co2_t', 1],
    ['Добыто руды, т', 'ore_mined_t', 0], ['Недопоставка энергии, МВт·ч', 'unserved_mwh', 2],
    ['Срабатывания защиты', 'trips', 0], ['Потери руды, т', 'spilled_t', 1], ['Шаги резервного управления', 'fallback_steps', 0],
  ];
  const table = $('comparison'); table.replaceChildren();
  for (const [title, field, digits] of rows) {
    const row = element('tr'); row.append(element('td', '', title));
    for (const variant of ['baseline', 'tynys', 'reference']) row.append(element('td', variant === 'tynys' ? 'tynys-text' : '', fmt(summary[variant]?.[field], digits)));
    table.append(row);
  }
}

function renderBoundary() {
  const boundary = Array.isArray(state.result.boundary) ? state.result.boundary : [];
  const grid = $('boundary-grid'); grid.replaceChildren();
  if (!boundary.length) {
    const empty = element('div', 'empty-boundary', 'Этот запрос проверен отдельно. «Найти предел» дополнительно рассчитает шесть длительностей.');
    grid.append(empty);
    text('boundary-hint', 'Увеличьте длительность или добавьте сбой. Проверенные точки показывают границы именно выбранного сценария.');
    return;
  }
  text('boundary-hint', `Снижение лимита на ${unit(state.result.request.reduction_mw, 'МВт', 0)}. Каждая точка — отдельный прогон при тех же исходных данных. Между точками выполнимость не доказана.`);
  for (const point of boundary) {
    const cell = element('div', 'boundary-cell'); cell.dataset.status = point.status || 'idle';
    cell.append(element('strong', '', unit(point.duration_h, 'ч', 0)), element('small', '', STATUS[point.status] || 'Не определено'));
    cell.append(element('span', '', `Потеря меди: ${unit(point.copper_loss_pct, '%', 2)}`));
    if (number(point.energy_debt_end_mwh)) cell.append(element('span', '', `Долг энергии: ${unit(point.energy_debt_end_mwh, 'МВт·ч')}`));
    const reason = Array.isArray(point.reasons) ? point.reasons[0] : null;
    if (reason?.title) cell.append(element('span', '', reason.title));
    grid.append(cell);
  }
}

function renderEvidence() {
  const result = state.result, snapshot = result.snapshot || result.snapshotmetadata || {};
  const parts = [`Запрос ${result.request.id}`];
  if (number(snapshot.sim_hour)) parts.push(`исходный час ${fmt(snapshot.sim_hour)}`);
  if (number(snapshot.seed)) parts.push(`seed ${snapshot.seed}`);
  if (snapshot.scenario_rev !== undefined) parts.push(`ревизия сценария ${snapshot.scenario_rev}`);
  if (snapshot.weather_source) parts.push(`погода: ${snapshot.weather_source}`);
  if (snapshot.source) parts.push(`источник: ${snapshot.source}`);
  if (snapshot.disturbance_sha256) parts.push(`входные воздействия ${String(snapshot.disturbance_sha256).slice(0, 12)}`);
  if (number(result.limits?.mpc_horizon_h)) parts.push(`сценарная модель: горизонт MPC ${unit(result.limits.mpc_horizon_h, 'ч', 0)}`);
  if (state.lastUpdated) {
    const date = new Date(state.lastUpdated);
    if (!Number.isNaN(date.valueOf())) parts.push(`отчёт ${date.toLocaleString('ru-RU')}`);
  }
  text('snapshot-info', parts.join(' · '));
}

function sceneLimits(limits = {}) {
  const capacities = limits.capacities || {};
  return {...limits, pile_capacity_t: limits.pile_capacity_t ?? capacities.pile_t, bess_capacity_mwh: limits.bess_capacity_mwh ?? capacities.bess_mwh, fleet_capacity_mwh: limits.fleet_capacity_mwh ?? capacities.fleet_mwh, wind_capacity_mw: limits.wind_capacity_mw ?? capacities.wind_mw, pv_capacity_mw: limits.pv_capacity_mw ?? capacities.pv_mw};
}

function renderFrame() {
  const result = state.result;
  if (!result?.frames.length) return;
  state.frame = Math.max(0, Math.min(result.frames.length - 1, state.frame));
  const frame = result.frames[state.frame];
  text('frame-hour', `Час ${fmt(frame.hour)}`);
  text('frame-phase', PHASE[frame.phase] || frame.phase || 'Шаг расчёта');
  $('timeline').value = state.frame;
  for (const variant of ['baseline', 'tynys']) {
    const record = frame[variant] || {};
    text(`${variant}-grid`, unit(record.grid_mw, 'МВт'));
    text(`${variant}-cu`, unit(record.cu_t, 'т'));
    text(`${variant}-bess`, unit(record.bess_mwh, 'МВт·ч'));
    const explanations = Array.isArray(record.explanations) ? record.explanations.filter(item => typeof item?.text === 'string') : [];
    text(`${variant}-explanation`, explanations.length ? explanations.slice(0, 2).map(item => item.text).join(' · ') : 'Для этого шага модель не добавила пояснение.');
    state.scenes[variant]?.setFrame(record, sceneLimits(result.limits));
  }
  renderChart();
}

function svgElement(name, attributes = {}, content) {
  const el = document.createElementNS('http://www.w3.org/2000/svg', name);
  for (const [key, value] of Object.entries(attributes)) el.setAttribute(key, String(value));
  if (content !== undefined) el.textContent = content;
  return el;
}

function renderChart() {
  if (!state.result) return;
  const svg = $('chart'), frames = state.result.frames, metric = $('chart-metric').value;
  const values = frames.flatMap(frame => [frame.baseline?.[metric], frame.tynys?.[metric]]).filter(number);
  svg.replaceChildren();
  if (!values.length) { svg.append(svgElement('text', {x: 450, y: 115, 'text-anchor': 'middle', class: 'chart-empty'}, 'В отчёте нет этого показателя')); return; }
  const left = 61, right = 885, top = 17, bottom = 196;
  const hours = frames.map(frame => frame.hour).filter(number);
  if (!hours.length) return;
  const start = Math.min(...hours), end = Math.max(...hours), range = Math.max(1, end - start);
  let min = Math.min(0, ...values), max = Math.max(...values);
  if (max <= min) max = min + 1;
  const margin = (max - min) * .08; max += margin;
  const x = hour => left + (hour - start) / range * (right - left);
  const y = value => bottom - (value - min) / (max - min) * (bottom - top);
  const eventStart = state.result.request.lead_h, eventEnd = eventStart + state.result.request.duration_h;
  if (number(eventStart) && number(eventEnd)) {
    const eventX = x(Math.max(start, eventStart)), eventRight = x(Math.min(end, eventEnd));
    if (eventRight > eventX) svg.append(svgElement('rect', {x: eventX, y: top, width: eventRight - eventX, height: bottom - top, fill: '#a56b3628'}));
  }
  for (let i = 0; i <= 4; i++) {
    const value = min + (max - min) * i / 4, lineY = y(value);
    svg.append(svgElement('line', {x1: left, x2: right, y1: lineY, y2: lineY, class: 'chart-grid'}));
    svg.append(svgElement('text', {x: left - 9, y: lineY + 3, 'text-anchor': 'end', class: 'chart-label'}, fmt(value, value > 100 ? 0 : 1)));
  }
  for (let i = 0; i <= 6; i++) {
    const hour = start + range * i / 6;
    svg.append(svgElement('text', {x: x(hour), y: bottom + 20, 'text-anchor': 'middle', class: 'chart-label'}, `${fmt(hour, 0)} ч`));
  }
  for (const [variant, color] of [['baseline', '#e3a579'], ['tynys', '#6ce0cc']]) {
    let path = '', connected = false;
    for (const frame of frames) {
      const value = frame[variant]?.[metric];
      if (!number(value) || !number(frame.hour)) { connected = false; continue; }
      path += `${connected ? 'L' : 'M'}${x(frame.hour).toFixed(2)},${y(value).toFixed(2)} `;
      connected = true;
    }
    svg.append(svgElement('path', {d: path, fill: 'none', stroke: color, 'stroke-width': 2.4, 'stroke-linejoin': 'round', 'stroke-linecap': 'round'}));
  }
  const current = frames[state.frame];
  if (number(current.hour)) {
    svg.append(svgElement('line', {x1: x(current.hour), x2: x(current.hour), y1: top, y2: bottom, class: 'chart-cursor'}));
    for (const [variant, color] of [['baseline', '#e3a579'], ['tynys', '#6ce0cc']]) {
      if (number(current[variant]?.[metric])) svg.append(svgElement('circle', {cx: x(current.hour), cy: y(current[variant][metric]), r: 4, fill: color, stroke: '#10212c', 'stroke-width': 2}));
    }
  }
  svg.setAttribute('aria-label', `${$('chart-metric').selectedOptions[0].textContent}. Обычное управление и Тыныс, от часа ${fmt(start)} до ${fmt(end)}. Текущий час ${fmt(current.hour)}.`);
}

function stopPlayback() {
  state.playing = false; clearTimeout(state.playbackTimer);
  text('play', '▶'); $('play').setAttribute('aria-label', 'Воспроизвести расчёт');
}

function playbackStep() {
  if (!state.playing || !state.result) return;
  if (state.frame >= state.result.frames.length - 1) { stopPlayback(); return; }
  state.frame++; renderFrame();
  state.playbackTimer = setTimeout(playbackStep, 900 / Number($('speed').value));
}

function togglePlayback() {
  if (state.playing) { stopPlayback(); return; }
  if (!state.result) return;
  if (state.frame >= state.result.frames.length - 1) state.frame = 0;
  state.playing = true; text('play', 'Ⅱ'); $('play').setAttribute('aria-label', 'Приостановить воспроизведение');
  renderFrame();
  state.playbackTimer = setTimeout(playbackStep, 900 / Number($('speed').value));
}

async function initScenes() {
  try {
    const {createFutureScene} = await import('./future-scene.js');
    for (const variant of ['baseline', 'tynys']) {
      const container = $(`scene-${variant}`);
      container.replaceChildren();
      state.scenes[variant] = createFutureScene(container, {variant, onCameraChange(camera) {
        if (state.syncingCamera) return;
        state.syncingCamera = true;
        const other = variant === 'baseline' ? 'tynys' : 'baseline';
        try { state.scenes[other]?.setCamera(camera); } finally { state.syncingCamera = false; }
      }});
      state.initialCameras[variant] = state.scenes[variant].getCamera();
    }
    renderFrame();
  } catch (error) {
    for (const variant of ['baseline', 'tynys']) {
      const container = $(`scene-${variant}`);
      container.replaceChildren(element('div', 'scene-loading', 'Схема рудника недоступна. Числа, график и отчёт остаются доступны.'));
    }
    console.error('Не удалось загрузить схему рудника', error);
  }
}

function markDirty() { state.dirty = Boolean(state.result); resultWarning(); }
$('request-form').addEventListener('submit', event => { event.preventDefault(); submitRequest('evaluate'); });
$('boundary').addEventListener('click', () => submitRequest('limit'));
$('cancel').addEventListener('click', cancelRequest);
$('reduction-range').addEventListener('input', () => { $('reduction').value = $('reduction-range').value; markDirty(); });
$('reduction').addEventListener('input', () => { $('reduction-range').value = $('reduction').value; markDirty(); });
$('request-form').addEventListener('input', markDirty);
$('reset').addEventListener('click', () => { HTMLFormElement.prototype.reset.call($('request-form')); $('reduction-range').value = $('reduction').value; markDirty(); statusMessage('Условия сброшены. Запустите новый расчёт, чтобы проверить их.'); });
document.querySelectorAll('[data-preset]').forEach(button => button.addEventListener('click', () => {
  if (button.dataset.preset === 'base') { $('reduction').value = 80; $('duration').value = 4; $('lead').value = 2; for (const id of ['lull', 'bess-fault', 'hard-ore']) $(id).checked = false; }
  if (button.dataset.preset === 'longer') $('duration').value = Math.min(12, Number($('duration').value) + 2);
  if (button.dataset.preset === 'fault') $('bess-fault').checked = true;
  $('reduction-range').value = $('reduction').value;
  markDirty();
}));
$('timeline').addEventListener('input', () => { stopPlayback(); state.frame = Number($('timeline').value); renderFrame(); });
$('play').addEventListener('click', togglePlayback);
$('chart-metric').addEventListener('change', renderChart);
$('camera-reset').addEventListener('click', () => { for (const variant of ['baseline', 'tynys']) if (state.initialCameras[variant]) state.scenes[variant]?.setCamera(state.initialCameras[variant]); });
$('export').addEventListener('click', () => {
  if (!state.result) return;
  const url = URL.createObjectURL(new Blob([JSON.stringify(state.result, null, 2)], {type: 'application/json;charset=utf-8'}));
  const link = element('a'); link.href = url; link.download = `tynys-futures-${String(state.result.request.id).replace(/[^a-zA-Z0-9-]/g, '').slice(0, 36)}.json`;
  document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
});
document.addEventListener('visibilitychange', () => { if (document.hidden) stopPlayback(); else schedulePoll(100); });
window.addEventListener('pagehide', () => { stopPlayback(); clearTimeout(state.pollTimer); for (const scene of Object.values(state.scenes)) scene.dispose?.(); });
initScenes();
window.TynysDemoFutures = {
  ready:()=>state.online && !state.pending && !['running','queued'].includes(state.serviceStatus),
  async start(onPrepared){
    if(!this.ready())throw new Error('Сервис занят или недоступен');
    const current=await api('GET','future-request');
    const raw=feature(current,'request_json','');
    const queued=raw?JSON.parse(raw):null;
    if(queued?.id && queued.id!==state.serviceId && queued.mode!=='cancel')throw new Error('Другой запрос ожидает обработки');
    syncForm({reduction_mw:80,duration_h:4,lead_h:2,recovery_h:24,max_copper_loss_pct:2,lull:false,bess_fault:false,hard_ore:false});
    markDirty();await submitRequest('evaluate',onPrepared);
    if(!state.pending?.id)throw new Error('Запрос не принят');
    return state.pending.id;
  },
  status:id=>state.result?.request?.id===id?'complete':state.pending?.id===id||(state.serviceId===id&&state.serviceStatus==='running')?'running':'error',
  async cancelOwn(id){
    const twin=await api('GET','future-request');
    const raw=feature(twin,'request_json','');
    if(raw && JSON.parse(raw).id===id && state.serviceStatus==='running') {state.pending={id};await cancelRequest();}
  }
};
poll();
