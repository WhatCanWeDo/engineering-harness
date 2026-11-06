(() => {
  document.querySelectorAll('.graph-node').forEach(button => button.addEventListener('click', () => {
    const figure = button.closest('.spec-map');
    const active = button.getAttribute('aria-pressed') !== 'true';
    figure.classList.toggle('focused', active);
    figure.querySelectorAll('.graph-node').forEach(b => b.setAttribute('aria-pressed', String(active && b.dataset.node === button.dataset.node)));
    figure.querySelectorAll('[data-from]').forEach(edge => edge.classList.toggle('connected', active && [edge.dataset.from,edge.dataset.to].includes(button.dataset.node)));
  }));
  const meta = JSON.parse(document.getElementById('spec-review-meta').textContent);
  const output = document.getElementById('feedback-text');
  const copy = document.getElementById('copy-review');
  const status = document.getElementById('copy-status');
  const inputs = [...document.querySelectorAll('[data-review]')];
  function updateFeedback() {
    const notes = inputs.filter(input => input.value.trim()).map(input => `${input.dataset.review === 'general' ? 'Общая поправка' : input.dataset.review}: ${input.value.trim()}`);
    output.value = notes.length ? [
      `Замечания к ${meta.spec_id}, revision ${meta.revision}`,
      `SHA-256: ${meta.sha256}`,
      'Это замечания, не автоматическое согласование.'
    ].join('\n') + '\n\n' + notes.join('\n\n') : '';
    copy.disabled = notes.length === 0;
    status.textContent = '';
  }
  inputs.forEach(input => {
    input.addEventListener('input', updateFeedback);
    input.addEventListener('change', updateFeedback);
  });
  copy.addEventListener('click', async () => {
    const text = output.value;
    if (!text) return;
    try {
      if (!navigator.clipboard?.writeText) throw new Error('Clipboard unavailable');
      await navigator.clipboard.writeText(text);
      status.textContent = output.value === text ? 'Скопировано. Вставь текст в чат.' : 'Скопирована предыдущая версия. Нажми ещё раз, чтобы скопировать новые правки.';
    } catch {
      output.focus();
      output.select();
      status.textContent = 'Текст выделен. Нажми ⌘C на Mac или Ctrl+C, затем вставь его в чат.';
    }
  });
  updateFeedback();
})();
