'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const frame = $('unity');
  let phase = 'loading';
  function fail(message) {
    phase = 'error';
    $('loading').hidden = false;
    $('fullscreen').disabled = true;
    $('runtime-state').dataset.ready = 'false';
    $('loading-title').textContent = 'Unity пока недоступна';
    $('loading-detail').textContent = message;
    $('runtime-state').textContent = 'Сцена не запущена';
    $('progress').hidden = true;
    $('retry').hidden = false;
  }
  $('retry').addEventListener('click', () => location.reload());
  $('fullscreen').addEventListener('click', async () => {
    try { await frame.requestFullscreen(); } catch (_) { $('runtime-state').textContent = 'Полноэкранный режим недоступен'; }
  });
  window.addEventListener('message', event => {
    if (event.origin !== location.origin || event.source !== frame.contentWindow || event.data?.type !== 'tynys-unity') return;
    const data = event.data;
    if (data.state === 'loading' && phase === 'loading' && Number.isFinite(data.progress)) {
      $('progress').value = Math.max(0, Math.min(1, data.progress));
      $('runtime-state').textContent = `Загрузка Unity · ${Math.round($('progress').value * 100)}%`;
    } else if (data.state === 'ready' && phase !== 'error') {
      phase = 'ready';
      $('loading').hidden = true;
      $('runtime-state').textContent = 'Unity запущена · источник данных указан в сцене';
      $('runtime-state').dataset.ready = 'true';
      $('fullscreen').disabled = !document.fullscreenEnabled;
    } else if (data.state === 'error') {
      fail('Браузер не смог запустить Unity. Можно повторить загрузку или открыть лёгкую 3D-сцену.');
    }
  });
  async function start() {
    try {
      const response = await fetch('unity/index.html', { method: 'HEAD', cache: 'no-store' });
      if (!response.ok) throw new Error('missing build');
      frame.src = 'unity/index.html';
      setTimeout(() => {
        if (phase === 'loading') {
          $('loading-title').textContent = 'Загрузка занимает больше времени';
          $('loading-detail').textContent = 'Unity ещё запускается. Можно подождать или открыть лёгкую 3D; пульт и аналитика доступны в верхнем меню.';
          $('retry').hidden = false;
        }
      }, 90000);
    } catch (_) {
      fail('Файлы Unity не найдены на сервере. Пульт, аналитика и лёгкая 3D доступны в верхнем меню.');
    }
  }
  start();

  // Активные сценарии — только чтение двойников scenario и site через тот же прокси Ditto.
  const NAMES = {lull:'Штиль', line_trip:'Авария линии', kegoc:'Ограничение KEGOC', hard_ore:'Твёрдая руда',
    plan_up:'План добычи +10 %', bess_fault:'Отказ накопителя', crusher_fault:'Отказ дробилки',
    shovel_fault:'Отказ экскаватора 1', conveyor_fault:'Отказ конвейера питания', water_fault:'Отказ водовода',
    charger_fault:'Отказ зарядной группы 1', crusher_service:'ТО дробилки', truck_failure:'Поломка самосвала',
    excavator_failure:'Поломка экскаватора', grade_drop:'Падение содержания меди', tariff_change:'Смена тарифа сети'};
  const esc = s => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'})[c]);
  async function readValue(thing, feature) {
    const r = await fetch(`ditto/api/2/things/kz.tynys:${thing}/features/${feature}/properties/value`, {cache: 'no-store'});
    if (!r.ok) throw new Error(String(r.status));
    return r.json();
  }
  async function strip() {
    const box = $('strip-events');
    try {
      const [hour, raw] = await Promise.all([readValue('site', 'sim_hour'), readValue('scenario', 'events')]);
      const events = (Array.isArray(raw) ? raw : JSON.parse(raw || '[]')).filter(e => Number(e.t0) + Number(e.dur) > Number(hour));
      if (!events.length) {
        box.textContent = 'Сейчас сценариев нет — рудник работает в обычном режиме. Запустите штиль, аварию или ограничение KEGOC и смотрите последствия в сцене.';
      } else {
        box.innerHTML = events.map(e => {
          const name = esc(NAMES[e.kind] || e.kind), t0 = Number(e.t0), end = t0 + Number(e.dur);
          const when = Number(hour) < t0 ? `начнётся через ${t0 - Number(hour)} ч` : `ещё ${end - Number(hour)} ч`;
          return `<b>${name}</b> · ${when}`;
        }).join(' &nbsp;·&nbsp; ');
      }
    } catch (_) {
      box.textContent = 'Нет связи с двойниками Ditto: сценарии можно посмотреть и запустить на пульте.';
    }
  }
  strip();
  setInterval(strip, 6000);
})();
