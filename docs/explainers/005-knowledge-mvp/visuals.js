(() => {
 const data = JSON.parse(document.getElementById('retrieval-results').textContent);
 const names = {lexical:'Текстовый',semantic:'Смысловой',hybrid:'Гибридный'};
 const bars = document.getElementById('metric-bars');
 Object.keys(names).forEach(mode => {
  const row=document.createElement('div');row.className='metric-row';row.dataset.mode=mode;
  const label=document.createElement('span');label.textContent=names[mode];
  const track=document.createElement('div');track.className='metric-track';
  const fill=document.createElement('div');fill.className='metric-fill';fill.style.width=(data.summary[mode].recall_at_3*100)+'%';track.append(fill);
  const value=document.createElement('b');value.textContent=Math.round(data.summary[mode].recall_at_3*100)+'%';
  row.append(label,track,value);bars.append(row);
 });
 const select=document.getElementById('query-picker');
 data.results.forEach((q,index)=>{const option=document.createElement('option');option.value=index;option.textContent=q.id+' · '+q.category;select.append(option);});
 function show(){
  const q=data.results[Number(select.value)];document.getElementById('query-text').textContent=q.text;
  const grid=document.getElementById('query-ranking');grid.replaceChildren();
  Object.keys(names).forEach(mode=>{
   const card=document.createElement('article');const title=document.createElement('h4');title.textContent=names[mode];card.append(title);
   q.modes[mode].ranked.forEach((id,index)=>{const p=document.createElement('p');const hit=q.relevant.includes(id);p.className='rank-doc '+(hit?'hit':'miss');p.textContent=(index+1)+'. '+id+(hit?' — нужный источник':'');card.append(p);});
   if(!q.modes[mode].ranked.length){const p=document.createElement('p');p.textContent='Нет совпадений';card.append(p);}
   const target=document.createElement('p');target.textContent='Qrels: '+q.relevant.join(', ');card.append(target);grid.append(card);
  });
 }
 select.addEventListener('change',show);show();
})();
