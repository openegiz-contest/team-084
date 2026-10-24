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
})();
