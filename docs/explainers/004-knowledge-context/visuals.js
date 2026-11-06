'use strict';
// Synthetic teaching data only. This is not an implementation of Knowledge Core.
const demoRecords = [
  {id:'K-01@2', title:'Граница истечения TTL', cost:180, roles:['developer','public','adversarial'], scope:'project', claim:'На now == expires_at запись уже просрочена; сравнение следует открытому spec.', source:'spec@2 · публичный контракт'},
  {id:'K-02@1', title:'Историческая публичная регрессия', cost:220, roles:['developer','public','adversarial'], scope:'project', claim:'Повторное чтение однажды продлевало TTL. Для сходной логики полезна проверка последовательности чтений.', source:'public-run-17 · до cutoff'},
  {id:'K-03@1', title:'Новые детали текущего candidate', cost:330, roles:['developer','adversarial'], scope:'project', claim:'В текущем candidate timestamp меняется на ветке fresh-hit. Это наблюдение о реализации; его последствия нужно проверить.', source:'candidate-C · после cutoff initial tests'},
  {id:'K-04@3', title:'Управляемое время вместо sleep', cost:260, roles:['developer','public','adversarial'], scope:'general', claim:'Для повторяемых проверок времени можно передавать fake clock, если интерфейс это допускает.', source:'general-procedure@3 · разрешённая проекция'},
  {id:'K-05@1', title:'Измерение в старом окружении', roles:[], excluded:'Stale: среда изменилась; не включать как актуальный факт.'},
  {id:'CLASS-PRIVATE', title:'Закрытые материалы evaluator', roles:[], excluded:'Другой контур доступа; общему Scout не передаются.'},
  {id:'CLASS-OTHER-PROJECT', title:'Внутренние детали другого проекта', roles:[], excluded:'Не опубликованы как general; другой project scope.'}
];
const demoRoleLabels = {
  developer:'Разработчик: требования, решения и применимые детали реализации.',
  public:'Public-test-author: контракт и исторический опыт до появления целевого решения.',
  adversarial:'Adversarial: контракт и наблюдения о frozen candidate для проверки гипотез.'
};
const demoPriorities = {
  developer:['K-01@2','K-03@1','K-02@1','K-04@3'],
  public:['K-01@2','K-02@1','K-04@3'],
  adversarial:['K-01@2','K-03@1','K-04@3','K-02@1']
};
function renderContextDemo() {
  const role = document.getElementById('audience').value;
  const budget = Number(document.getElementById('context-budget').value);
  document.getElementById('budget-value').textContent = budget;
  let used = 0;
  const selected = [];
  demoPriorities[role].forEach(id => {
    const record = demoRecords.find(r => r.id === id);
    if (used + record.cost <= budget) { selected.push(record); used += record.cost; }
  });
  const sourceList = document.getElementById('source-list');
  sourceList.replaceChildren();
  demoRecords.forEach(record => {
    const li = document.createElement('li');
    const title = document.createElement('strong');
    title.textContent = record.title;
    const reason = document.createElement('span');
    if (selected.includes(record)) {
      reason.textContent = `В пакете · ≈${record.cost} токенов · ${record.scope}`;
      reason.className = 'included';
    } else if (record.excluded) reason.textContent = record.excluded;
    else if (!record.roles.includes(role)) reason.textContent = 'Другая стадия: сведения получены после cutoff initial tests.';
    else reason.textContent = `Не поместилось · ≈${record.cost} токенов. Можно запросить отдельно.`;
    li.append(title, reason); sourceList.append(li);
  });
  const packet = document.getElementById('packet-content');
  packet.replaceChildren();
  selected.forEach(record => {
    const li = document.createElement('li');
    li.append(document.createTextNode(record.claim));
    const cite = document.createElement('small');
    cite.textContent = `${record.id} · ${record.source}`;
    li.append(cite); packet.append(li);
  });
  document.getElementById('packet-purpose').textContent = demoRoleLabels[role];
  const sourceNoun = selected.length === 1 ? 'источник' : 'источника';
  document.getElementById('packet-summary').textContent = `${selected.length} ${sourceNoun} · ≈${used} из ${budget} токенов. Только разрешённые active-записи.`;
  document.getElementById('budget-fill').style.width = `${used / budget * 100}%`;
}
const demoUpdates = {
  observation:{state:'active', label:'Active observation', note:'Узкий факт в условиях данного run', explanation:'Evidence сохраняется. После проверки доступности источника, происхождения и области применимости узкое наблюдение может войти в обычную выдачу. Оно не становится универсальным правилом.', receipt:'persisted: evidence + revision · review: not_required_by_this_policy'},
  hypothesis:{state:'candidate', label:'Candidate', note:'Обобщение ждёт подтверждения', explanation:'Сам результат запуска сохраняется как наблюдение. Вывод «всегда быстрее» — отдельный candidate: его нельзя выдавать как установленный факт лишь потому, что два агента согласились.', receipt:'persisted: observation + candidate · review: pending'},
  conflict:{state:'disputed', label:'Disputed', note:'Конфликт условий или источников', explanation:'Сохраняются обе разрешённые позиции и ссылки на evidence. Curator не заменяет прежнюю запись молча; до разрешения конфликта пакет содержит предупреждение вместо уверенного общего вывода.', receipt:'persisted: proposal + conflict · review: pending'},
  nochange:{state:'no_change', label:'No change', note:'Новых записей не требуется', explanation:'Receipt подтверждает обработку задачи и отсутствие полезного нового знания. Повторять известные факты ради обязательного «пополнения» базы не нужно.', receipt:'persisted: task receipt · new_entries: 0'}
};
function renderUpdateDemo() {
  const choice = demoUpdates[document.getElementById('outcome-kind').value];
  document.getElementById('update-state').dataset.state = choice.state;
  document.getElementById('state-name').textContent = choice.label;
  document.getElementById('state-description').textContent = choice.note;
  document.getElementById('update-explanation').textContent = choice.explanation;
  document.getElementById('update-receipt').textContent = choice.receipt;
}
document.getElementById('audience').addEventListener('change', () => {
  document.getElementById('context-budget').value = document.getElementById('audience').value === 'public' ? 900 : 1200;
  renderContextDemo();
});
document.getElementById('context-budget').addEventListener('input', renderContextDemo);
document.getElementById('outcome-kind').addEventListener('change', renderUpdateDemo);
renderContextDemo();
renderUpdateDemo();
