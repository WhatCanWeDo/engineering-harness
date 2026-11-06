(() => {
  const $ = id => document.getElementById(id);
  const scene = `<rect width="640" height="360" fill="#cce5ec"/><path d="M0 170 Q150 100 290 155 T640 130 V360 H0Z" fill="#9ebba5"/><rect x="30" y="75" width="130" height="130" rx="4" fill="#e8e0cf"/><rect x="44" y="93" width="34" height="39" fill="#76939f"/><rect x="91" y="93" width="44" height="39" fill="#76939f"/><rect x="81" y="152" width="37" height="53" fill="#867d69"/><path d="M240 140 L410 140 L640 360 H0Z" fill="#63727a"/><path d="M329 155 L324 198 M320 221 L312 285 M306 315 L300 360" stroke="#eee8cd" stroke-width="8"/><ellipse cx="490" cy="131" rx="32" ry="45" fill="#497b61"/><path d="M490 154V209" stroke="#73614c" stroke-width="10"/><g><rect x="365" y="203" width="112" height="46" rx="10" fill="#d7824f"/><path d="M382 203 L396 177 H445 L464 203Z" fill="#d7824f"/><path d="M400 182 H440 L452 201 H390Z" fill="#abc6ce"/><circle cx="388" cy="250" r="12" fill="#24343c"/><circle cx="454" cy="250" r="12" fill="#24343c"/></g>`;
  function svg(body,title) { return `<svg viewBox="0 0 640 360" role="img" aria-label="${title}">${body}</svg>`; }
  $('seg-input').innerHTML=svg(scene,'Учебная дорожная сцена, не снимок камеры');
  function renderSeg() {
    const shifted=$('seg-sample').value==='shifted';
    const cls=$('seg-class').value;
    const opacity=Number($('seg-opacity').value)/100;
    const road=cls==='object'?'':`<path d="M240 140 L410 140 L640 360 H0Z" fill="#4279cb"/>`;
    const object=cls==='road'?'':`<g transform="translate(${shifted?38:0} 0)" fill="#edc54b"><path d="M382 203 L396 177 H445 L464 203 H467 Q477 203 477 213 V239 Q477 249 467 249 H375 Q365 249 365 239 V213 Q365 203 375 203Z"/><circle cx="388" cy="250" r="12"/><circle cx="454" cy="250" r="12"/></g>`;
    $('seg-output').innerHTML=svg(scene+`<g opacity="${opacity}">${road}${object}</g>`,'Та же учебная сцена с вручную заданной маской');
    $('opacity-value').textContent=Math.round(opacity*100)+'%';
    $('seg-status').textContent=`Fixture: ${shifted?'scene-mask-shifted':'scene-mask-aligned'}. `+(shifted?'Маска автомобиля сдвинута вправо на 38 px в учебном пространстве 640 × 360. ':'Маска согласована с геометрией учебной сцены. ')+(cls==='road'&&shifted?'Сейчас выбран только класс «дорога», поэтому смещённый объект скрыт. ':'')+'Изменения прозрачности и класса не запускают inference.';
  }
  ['seg-sample','seg-class','seg-opacity'].forEach(id=>$(id).addEventListener('input',renderSeg));renderSeg();
  const pages={
    normal:'<article class="product" data-product-id="fixture-17"><div class="shop-name">Учебный магазин</div><div class="product-picture" aria-hidden="true">◉</div><h5 class="title">  Камера   Север M2 </h5><p class="price"> 12 490 ₽ </p><p class="availability"> В наличии </p></article>',
    missing:'<article class="product" data-product-id="fixture-17"><div class="shop-name">Учебный магазин</div><div class="product-picture" aria-hidden="true">◉</div><h5 class="title">  Камера   Север M2 </h5><p data-cost="12490"> 12 490 ₽ </p><p class="availability"> В наличии </p></article>',
    ambiguous:'<article class="product" data-product-id="fixture-17"><div class="shop-name">Учебный магазин</div><div class="product-picture" aria-hidden="true">◉</div><h5 class="title">  Камера   Север M2 </h5><p>Обычная цена <span class="price">14 990 ₽</span></p><p>По акции <span class="price">12 490 ₽</span></p><p class="availability"> В наличии </p></article>'
  };
  const definitions={
    price:{selector:'.product .price',output:'price',steps:['Убрать пробелы и знак ₽','Заменить десятичную запятую точкой','Преобразовать в number; RUB задан в fixture-контракте'],convert:raw=>{const amount=Number(raw.replace(/[\s₽]/g,'').replace(',','.'));if(!Number.isFinite(amount))throw Error('invalid_number');return {amount,currency:'RUB'};}},
    title:{selector:'.product .title',output:'title',steps:['Свернуть последовательности пробелов','Убрать пробелы по краям'],convert:raw=>raw.replace(/\s+/g,' ').trim()},
    stock:{selector:'.product .availability',output:'in_stock',steps:['Убрать пробелы по краям','Сопоставить с явным словарём статусов'],convert:raw=>{const text=raw.trim();if(text==='В наличии')return true;if(text==='Нет в наличии')return false;throw Error('unknown_stock_label');}}
  };
  function element(tag,text,className){const el=document.createElement(tag);el.textContent=text;if(className)el.className=className;return el;}
  function renderParser() {
    const key=$('parser-case').value, field=$('parser-field').value, source=pages[key];
    // Only authored, inert fixtures enter this container. Never inject arbitrary site HTML here.
    $('source-page').innerHTML=source;
    $('source-html').textContent=source;
    const doc=new DOMParser().parseFromString(source,'text/html');
    const extracted={},traces={},errors=[];
    for(const [name,def] of Object.entries(definitions)){
      const matches=[...doc.querySelectorAll(def.selector)];
      const trace={selector:def.selector,matches:matches.length,raw:matches.map(n=>n.textContent),steps:def.steps,value:null,status:'ok'};
      if(matches.length!==1){trace.status=matches.length===0?'missing':'ambiguous';errors.push({field:def.output,status:trace.status,matches:matches.length});}
      else {try{trace.value=def.convert(matches[0].textContent);}catch(e){trace.status='parse_error';errors.push({field:def.output,status:trace.status,reason:e.message});}}
      extracted[def.output]=trace.value;traces[name]=trace;
    }
    const chosen=traces[field];
    $('source-page').querySelectorAll(chosen.selector).forEach(n=>n.classList.add('matched-node'));
    const box=$('parser-trace');box.replaceChildren();
    box.append(element('div',`Selector: ${chosen.selector}`,'trace-step'),element('div',`Совпадений: ${chosen.matches} · ${chosen.status}`,'trace-step '+(chosen.status==='ok'?'ok':'problem')));
    box.append(element('pre','Raw: '+JSON.stringify(chosen.raw,null,2)));
    if(chosen.status==='ok'){
      const steps=document.createElement('ol');chosen.steps.forEach(t=>steps.append(element('li',t)));box.append(steps,element('pre','Output: '+JSON.stringify(chosen.value,null,2)));
    } else box.append(element('p','Преобразование не выполняется: нужен ровно один однозначный source node. Поле остаётся null.','problem'));
    $('parser-result').textContent=JSON.stringify({fixture:`product-${key}`,data:extracted,errors},null,2);
    $('parser-observation').textContent=chosen.status==='ok'?'Выбранное поле получено из подсвеченного узла этой fixture. Смена поля меняет trace, а не исходный результат извлечения.':chosen.status==='missing'?'Selector не нашёл узел. Цена видна в учебной странице, но её новая разметка не соответствует правилу extractor. Значение не подставляется.':'Найдены два узла. Прототип не выбирает цену молча: ambiguity видна и в trace, и в errors.';
  }
  ['parser-case','parser-field'].forEach(id=>$(id).addEventListener('change',renderParser));renderParser();
})();
