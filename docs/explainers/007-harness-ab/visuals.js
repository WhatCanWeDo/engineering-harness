(() => {
 const baseline={correct:[1,1,1,1,1,1],review:[10,14,7,20,12,9],cost:[1.2,1.6,0.8,2.4,1.5,1.1],fixes:[2,1,0,3,1,1]};
 const candidate={correct:[1,1,1,1,1,1],review:[8,11,6,16,10,7],cost:[1.3,1.8,0.9,2.7,1.7,1.2],fixes:[1,0,0,1,1,0]};
 const control=document.getElementById('ab-scenario');
 const sum=x=>x.reduce((a,b)=>a+b,0);
 function render(){
  const b=structuredClone(candidate),scenario=control.value;
  if(scenario==='regression'){b.correct[3]=0;b.cost=b.cost.map(v=>v*.65);b.review[3]=2;}
  if(scenario==='missing'){b.review=null;b.fixes=null;}
  const grid=document.getElementById('ab-metrics');grid.replaceChildren();
  const metrics=[['Correctness',sum(baseline.correct)+'/6',sum(b.correct)+'/6','Одинаковая initial проверка.'],['Активный review',sum(baseline.review)+' мин',b.review?sum(b.review)+' мин':'не измерен','Отказ от неудачного решения может быть быстрым; это не выигрыш принятого результата.'],['Стоимость runs',sum(baseline.cost).toFixed(2)+' у.е.',sum(b.cost).toFixed(2)+' у.е.','Условные данные; не действующие цены API.'],['Manual corrections',String(sum(baseline.fixes)),b.fixes?String(sum(b.fixes)):'не измерены','Количество issues; rounds и severity в настоящем отчёте отдельно.']];
  metrics.forEach(([name,a,bb,note])=>{const card=document.createElement('article');card.className='metric-card';const h=document.createElement('h4');h.textContent=name;const pa=document.createElement('p');pa.textContent='A: '+a;const pb=document.createElement('p');pb.textContent='B: '+bb;const small=document.createElement('small');small.textContent=note;card.append(h,pa,pb,small);grid.append(card);});
  const messages={promising:['promising_on_dev','Меньше человеческого review, выше цена runs. Это полезный сигнал для проверки на свежих задачах; 3 задачи не доказывают отсутствие регрессий и переносимость.','ok'],regression:['regression_observed','Candidate дешевле, но новая ошибка нарушает обязательный correctness gate. Низкую цену показываем, но не превращаем в разрешение заменить baseline.','error'],missing:['incomplete','Есть автоматические результаты, но время человека и исправления неизвестны. Нельзя подставить нули или заявить экономию человеческого времени.','warning'],leak:['invalid','Разница результатов смешана с утечкой контекста из A в B. Красивые цифры не восстанавливают сопоставимость; нужен новый корректный эксперимент.','error']};
  const [label,body,kind]=messages[scenario];const v=document.getElementById('ab-verdict');v.replaceChildren();v.dataset.kind=kind;const title=document.createElement('b');title.textContent=label;const text=document.createElement('span');text.textContent=body;v.append(title,text);
 }
 control.addEventListener('change',render);render();
})();
