'use strict';
(function () {
  const jobs = new Set();
  const buttons = [...document.querySelectorAll('[data-action]')];
  const title = document.getElementById('resultTitle');
  const text = document.getElementById('resultText');
  const details = document.getElementById('details');
  const download = document.getElementById('download');
  const chip = document.getElementById('status');
  const tabs = [...document.querySelectorAll('[data-tab]')];
  function showTab(name) {
    const selected = ['service','sprut','docs'].includes(name) ? name : 'service';
    tabs.forEach(b => b.classList.toggle('active', b.dataset.tab === selected));
    document.querySelectorAll('.page').forEach(p => p.classList.toggle('active', p.id === selected));
  }
  tabs.forEach(b => b.addEventListener('click', () => { location.hash = b.dataset.tab; }));
  window.addEventListener('hashchange', () => showTab(location.hash.slice(1)));
  showTab(location.hash.slice(1));
  const sleep = t => new Promise(resolve => setTimeout(resolve, t));
  async function request(url, options) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch(url, {cache:'no-store', credentials:'same-origin', signal:controller.signal, ...options});
      const value = await response.json();
      if (!response.ok) throw Error(value.error || 'HTTP ' + response.status);
      return value;
    } finally { clearTimeout(timeout); }
  }
  async function run(action) {
    if (jobs.size) return;
    jobs.add(action);
    buttons.forEach(b => b.disabled = true);
    chip.textContent = 'Выполняется';
    title.textContent = 'NST: ' + action;
    text.textContent = 'Получение информации с контроллера…';
    details.textContent = '';
    download.hidden = true;
    download.removeAttribute('href');
    try {
      const started = await request('/api/jobs/' + action, {
        method:'POST', headers:{'X-NST-Intent':'ui', 'Content-Type':'application/json'}, body:'{}'
      });
      let state;
      for (let i = 0; i < 130; i++) {
        await sleep(2000);
        state = await request('/api/jobs/' + started.job);
        if (state.state !== 'running') break;
      }
      if (!state || state.state !== 'complete') throw Error(state?.error || 'Не получен результат диагностики');
      chip.textContent = 'Готово';
      title.textContent = 'Операция завершена';
      text.textContent = state.result?.filename ? 'Архив собран и проверен. Скачайте его для анализа.' : 'Состояние получено';
      details.textContent = JSON.stringify(state.result, null, 2);
      if (state.download && state.download.startsWith('/api/download/')) {
        download.href = state.download;
        download.download = state.result.filename || 'nst-diagnostics.tar.gz';
        download.hidden = false;
      }
    } catch (error) {
      chip.textContent = 'Ошибка';
      title.textContent = 'Не удалось выполнить операцию';
      text.textContent = String(error.message || error);
    } finally {
      jobs.delete(action);
      buttons.forEach(b => b.disabled = false);
    }
  }
  buttons.forEach(b => b.addEventListener('click', () => run(b.dataset.action)));
}());