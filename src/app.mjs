import {INITIAL, computedAccessionOptions, evaluate, isAllowed, normalizeImported, range, validRange, yearLabel} from './model.mjs';

const $ = id => document.getElementById(id);
const STORAGE_KEY='jewish-chrono-scenario-v3';
let catalog=null;
let state={...INITIAL};
const sourceIds=['akiva','accession'];
const switches=['rabbi','baby','identity','sourceAge','strict'];
const switchInput={rabbi:'constraint-rabbi',baby:'constraint-baby',identity:'constraint-identity',sourceAge:'source-age',strict:'strict'};
function node(tag,text,attrs={}){
  const el=document.createElement(tag);
  if(text!==undefined && text!==null)el.textContent=String(text);
  for(const [key,value] of Object.entries(attrs))el.setAttribute(key,String(value));
  return el;
}
function safeLink(url,label) {
  if(typeof url!=='string'||!/^https:\/\/(github\.com|raw\.githubusercontent\.com|he\.wikisource\.org|www\.sefaria\.org)\//.test(url))return node('span',label);
  return node('a',label,{href:url,target:'_blank',rel:'noopener noreferrer'});
}
function validYearInput(id){const raw=$(id).value.trim();return raw===''?NaN:Number(raw);}
function readCustom(prefix){
  const min=validYearInput(prefix+'-min'),max=validYearInput(prefix+'-max');
  return min===max?min:{min,max};
}
function readForm(){
  const s={
    akivaClaim:$('akiva').value,akivaCustom:readCustom('akiva'),
    accessionClaim:$('accession').value,accessionCustom:readCustom('accession')
  };
  for(const key of switches)s[key]=$(switchInput[key]).checked;
  return s;
}
function setForm(s){
  $('akiva').value=s.akivaClaim;
  $('accession').value=s.accessionClaim;
  for(const prefix of sourceIds){
    const r=validRange(s[prefix+'Custom'])?range(s[prefix+'Custom']):{min:3880,max:3880};
    $(prefix+'-min').value=r.min;
    $(prefix+'-max').value=r.max;
  }
  for(const key of switches)$(switchInput[key]).checked=!!s[key];
  showCustomInputs();
}
function showCustomInputs(){
  $('akiva-custom-wrap').hidden=$('akiva').value!=='custom';
  $('accession-custom-wrap').hidden=$('accession').value!=='custom';
}
function notice(message=''){$('ui-notice').textContent=message;}
function option(value,label){
  const el=node('option',label);el.value=value;return el;
}
function setupOptions(){
  const death=catalog.claims.filter(x=>x.eventId==='akiva_death' && x.kind==='source-claim');
  const accession=catalog.claims.filter(x=>x.eventId==='emperor_accession' && x.kind==='source-claim');
  $('akiva').replaceChildren(...death.map(x=>option(x.id,yearLabel(x.year)+' — '+x.source.work+(x.status==='needs-primary-attribution'?' (атрибуция уточняется)':''))),option('custom','Другой год / интервал'));
  $('accession').replaceChildren(...accession.map(x=>option(x.id,yearLabel(x.year)+' — '+x.source.work)),...computedAccessionOptions(catalog).map(x=>option(x.id,x.label)),option('custom','Другой год / интервал'));
  const wrap=$('constraints');
  for(const c of catalog.constraints){
    const label=node('label',null,{class:'toggle'});
    const input=node('input',null,{id:'constraint-'+c.id,type:'checkbox'});
    const span=node('span');
    span.append(node('span',c.label),node('small',c.kind==='identity-hypothesis'?'Гипотеза, тождество не установлено':c.kind==='research-inference'?'Вывод из текста, не датировка': 'Сообщаемая традиция; точная ссылка требует проверки'));
    label.append(input,span);wrap.appendChild(label);
  }
}
function renderSources(){
  const host=$('sources');host.replaceChildren();
  for(const c of catalog.claims){
    const card=node('article',null,{class:'source-card'});
    card.append(node('strong',c.title),node('span',c.status,{class:'tag'+(c.status.startsWith('needs')?' review':'')}));
    const src=c.source||{};
    card.append(node('p',(src.work||'')+' — '+(src.location||'')));
    if(src.originalQuote)card.append(node('p','«'+src.originalQuote+'»'));
    if(src.review)card.append(node('p',src.review));
    if(src.url)card.append(safeLink(src.url,'Открыть XML-источник'));
    host.appendChild(card);
  }
  for(const c of catalog.constraints){
    const card=node('article',null,{class:'source-card'});
    card.append(node('strong',c.label),node('span',c.kind+' · '+c.status,{class:'tag review'}));
    card.append(node('p',c.evidence?.review||''));
    if(c.evidence?.url)card.append(safeLink(c.evidence.url,'Перейти к тексту'));
    host.appendChild(card);
  }
}
function renderRows(r){
  const tbody=$('rows');tbody.replaceChildren();
  for(const item of r.rows){
    const tr=node('tr');
    tr.append(node('td',item.label));
    const yearCell=node('td',yearLabel(item.year));
    if(r.status==='contradictory' && item.eventId==='emperor_birth')yearCell.className='conflict';
    tr.append(yearCell);
    const provenance=node('td');provenance.append(node('span',item.note,{class:'muted'}));
    const urls=[...new Set(item.sourceUrls||[])];
    for(let i=0;i<urls.length;i++){
      provenance.append(document.createTextNode(' '));
      const a=safeLink(urls[i],urls.length===1?'↗ Источник':'↗ Источник '+(i+1));
      a.className='source-link';provenance.append(a);
    }
    tr.append(provenance);tbody.append(tr);
  }
}
function statusBlock(r,s){
  const host=$('status');host.replaceChildren();
  host.className=r.status==='contradictory'?'error':r.status==='underdetermined'?'warn':'';
  const headline=r.status==='contradictory'?'Есть противоречие между принятыми условиями':
    r.status==='consistent'?'Выбранные условия арифметически совместимы':'Недостаточно принятых связей для проверки совпадения';
  let explanation='';
  if(r.status==='contradictory')explanation='От возраста 47 лет и года вступления следует рождение '+yearLabel(r.ageBorn)+', но рассказ с тремя принятыми связями указывает '+yearLabel(r.storyBorn)+'. Минимальное расхождение: '+r.gap+' лет.';
  else if(r.status==='consistent')explanation='Свидетельство о возрасте совместимо с цепочкой принятых связей. Это не доказывает историческую достоверность.';
  else if(!s.identity && r.ifIdentityAccession){
    explanation='Отождествление младенца с императором НЕ принято. Младенец родился в '+yearLabel(r.infantBorn)+', а император при выбранном возрасте 47 лет — в '+yearLabel(r.ageBorn)+'. Если принять тождество, год вступления должен быть '+yearLabel(r.ifIdentityAccession)+(r.ifIdentityConflict?', то есть выбранный год '+yearLabel(r.accession)+' отличается на '+r.ifIdentityGap+' лет.':' — это совпадает с выбранным годом.')+' Пока тождество не принято, это два разных исторических лица и арифметического противоречия нет.';
  }
  else explanation='Отсутствие противоречия не означает подтверждения: нет полной цепочки связей либо независимой возрастной проверки.';
  host.append(node('strong',headline),node('p',explanation));
  $('result-mode').textContent=s.strict?'Строгий режим':'Исследовательский режим';
  const show=(id,value)=>{const el=$(id);el.textContent=value===null?'—':yearLabel(value);el.classList.toggle('na',value===null);};
  show('rabbi-year',r.rabbiBorn);show('emperor-year',r.emperorBorn);
  $('age').textContent=s.sourceAge?'47 (ист.)':r.ageComputed?yearLabel(r.ageComputed):'—';
  const explain=$('explanation');explain.replaceChildren();
  const add=(str,cls)=>explain.append(node('p',str,cls?{class:cls}:{}));
  add('Шаг 1. Смерть раби Акивы: '+yearLabel(r.akiva)+'. '+(s.rabbi?'Принято, что Раби родился тогда же.':'Связь с рождением Раби отключена.'));
  add('Шаг 2. '+(r.infantBorn?'По принятому ровесничеству младенец Антонинус родился в '+yearLabel(r.infantBorn)+'.':'Год рождения младенца из рассказа не установлен.'));
  add('Шаг 3. '+(r.storyBorn?'Принято тождество младенца с императором; его рождение тогда '+yearLabel(r.storyBorn)+'.':s.identity?'Гипотеза о тождестве включена, но предыдущих связей недостаточно, чтобы датировать рождение императора.':'Гипотеза «младенец Антонинус = император» ОТКЛЮЧЕНА. Возраст младенца нельзя автоматически приписывать императору.'));
  add('Шаг 4. '+(s.sourceAge?'При возрасте 47 лет и восшествии '+yearLabel(r.accession)+' рождение императора следует датировать '+yearLabel(r.ageBorn)+'.':'Свидетельство о возрасте 47 лет не включено.'));
  if(r.predictedAccession)add('Из всех трёх связей вместе с возрастом 47 следует ожидаемый год восшествия '+yearLabel(r.predictedAccession)+'.');
  if(!s.identity && r.ifIdentityAccession)add('ПРОВЕРКА ГИПОТЕЗЫ (НЕ принятой в сценарии): если младенец и император — одно лицо, ожидаемое вступление '+yearLabel(r.ifIdentityAccession)+'; выбранное '+yearLabel(r.accession)+(r.ifIdentityConflict?' даёт разницу '+r.ifIdentityGap+' лет.':' совместимо.')+' Эта условная проверка не делает тождество доказанным.');
  if(r.status==='contradictory')add('Несовместимость: одно и то же рождение должно одновременно приходиться на '+yearLabel(r.storyBorn)+' и '+yearLabel(r.ageBorn)+'. Для разрешения конфликта измените год или снимите хотя бы одну связь / возрастное свидетельство.','error-text');
  if(r.hasYearZero)add('Предупреждение: выбран формальный нулевой или отрицательный год АМ; это математический тест, а не историческая дата.');
}
const SVGNS='http://www.w3.org/2000/svg';
function sv(tag,attrs={},label){
  const el=document.createElementNS(SVGNS,tag);
  for(const [k,v]of Object.entries(attrs))el.setAttribute(k,String(v));
  if(label!==undefined)el.textContent=String(label);
  return el;
}
function tickStep(span){
  const raw=Math.max(1,span/8), mag=Math.pow(10,Math.floor(Math.log10(raw)));
  for(const v of [1,2,5,10])if(v*mag>=raw)return v*mag;
  return 10*mag;
}
function renderTimeline(r){
  const svg=$('timeline');svg.replaceChildren();
  const items=r.rows.filter(x=>x.year!==null);
  if(!items.length)return;
  const values=items.flatMap(x=>[x.year.min,x.year.max]);
  let min=Math.min(...values),max=Math.max(...values);
  const pad=Math.max(4,Math.round((max-min)*.07));
  min-=pad;max+=pad;
  if(min===max)max=min+10;
  const x0=250,x1=1080,scale=v=>x0+(v-min)/(max-min)*(x1-x0);
  const n=items.length, height=76+n*34+34;
  svg.setAttribute('viewBox','0 0 1120 '+height);
  const step=tickStep(max-min);
  const axisY=height-22;
  let ticks=0;
  for(let y=Math.ceil(min/step)*step;y<=max&&ticks<18;y+=step,ticks++){
    const x=scale(y);
    svg.append(sv('line',{x1:x,y1:30,x2:x,y2:axisY-16,stroke:'#e0e9ef'}));
    svg.append(sv('text',{x,y:axisY,fill:'#6b7d8b','font-size':12,'text-anchor':'middle'},y));
  }
  items.forEach((item,i)=>{
    const cy=52+i*34;
    const isError=r.status==='contradictory'&&item.eventId==='emperor_birth';
    const color=isError?'#a82f38':item.kind==='source'?'#214f79':item.kind==='hypothesis'?'#a46420':'#087a81';
    svg.append(sv('line',{x1:x0,y1:cy,x2:x1,y2:cy,stroke:'#e3eaf0'}));
    const shortened=item.label.replace('Рождение императора — ','Император: ').replace('Вступление, ожидаемое при возрасте 47','Вступление (при 47)');
    const name=sv('text',{x:12,y:cy+4,fill:'#354a5d','font-size':12},shortened.length>35?shortened.slice(0,34)+'…':shortened);
    name.append(sv('title',{},item.label));svg.append(name);
    const target=item.sourceUrls?.find(u=>/^https:\/\//.test(u));
    const group=target?sv('a',{href:target,target:'_blank',rel:'noopener noreferrer'}):sv('g');
    group.append(sv('title',{},item.label+': '+yearLabel(item.year)+' АМ. '+item.note+(target?' Открыть источник.':'')));
    if(item.year.min!==item.year.max){
      const left=scale(item.year.min),right=scale(item.year.max);
      group.append(sv('rect',{x:left,y:cy-6,width:Math.max(3,right-left),height:12,rx:4,fill:color,opacity:.75}));
    } else {
      group.append(sv('circle',{cx:scale(item.year.min),cy,r:7,fill:color,stroke:'#fff','stroke-width':2}));
    }
    group.append(sv('text',{x:scale((item.year.min+item.year.max)/2),y:cy-12,fill:color,'font-size':12,'text-anchor':'middle','font-weight':'bold'},yearLabel(item.year)));
    if(target)group.setAttribute('style','cursor:pointer');
    svg.append(group);
  });
}
function updateAssumptionInfo(r,s){
  const el=$('assumption-info');if(!el)return;
  el.classList.toggle('active',s.identity);
  if(s.identity){
    el.replaceChildren(node('strong','Гипотеза тождества принята для этого сценария'),
      node('span','Младенец Антонинус и император считаются одним человеком. Строгий режим проверяет согласованность их дат при наличии остальных связей.'));
  }else{
    const message=r.ifIdentityAccession
      ? 'Если включить тождество, возраст 47 лет потребует вступления в '+yearLabel(r.ifIdentityAccession)+' году. '+(r.ifIdentityConflict?'Выбранный '+yearLabel(r.accession)+' год расходится на '+r.ifIdentityGap+' лет.':'Выбранный год совместим.')+' Пока гипотеза отключена, строгий режим не блокирует комбинацию.'
      : 'Строгий режим не связывает годы рождения младенца и императора без принятия этой гипотезы.';
    el.replaceChildren(node('strong','Гипотеза «младенец = император» отключена'),node('span',message));
  }
}
function disableImpossible(){
  const s=state;
  for(const [id,field] of [['akiva','akivaClaim'],['accession','accessionClaim']]){
    for(const o of $(id).options){
      if(o.value==='custom'){o.disabled=false;continue;}
      const trial={...s,[field]:o.value};
      o.disabled=s.strict&&!isAllowed(trial,catalog);
      o.title=o.disabled?'Не совместимо с уже выбранными предпосылками':'';
    }
  }
  for(const field of ['rabbi','baby','identity','sourceAge']){
    const input=$(switchInput[field]),trial={...s,[field]:!s[field]};
    const disable=s.strict&&!isAllowed(trial,catalog);
    input.disabled=disable;input.closest('.toggle').classList.toggle('disabled',disable);
    input.title=disable?'Для принятия измените другую дату, связь или режим':'';
  }
}
function render(){
  const r=evaluate(state,catalog);
  if(r.status==='invalid'){notice(r.error);return;}
  setForm(state);disableImpossible();updateAssumptionInfo(r,state);statusBlock(r,state);renderRows(r);renderTimeline(r);
}
function persist(){
  try{localStorage.setItem(STORAGE_KEY,JSON.stringify(state));$('save-status').textContent='Сценарий сохранён локально.';}
  catch(e){$('save-status').textContent='Локальное сохранение недоступно — используйте экспорт.';}
}
function changed(){
  showCustomInputs();
  const candidate=readForm();
  if(!isAllowed(candidate,catalog)){
    setForm(state);
    notice('Этот вариант несовместим с принятыми ограничениями либо содержит недопустимый диапазон. Измените условие или отключите строгий режим.');
    return;
  }
  state=candidate;notice('');persist();render();
}
function setupControls(){
  for(const id of ['akiva','accession','akiva-min','akiva-max','accession-min','accession-max',...switches.map(x=>switchInput[x])])$(id).addEventListener('change',changed);
  $('reset').addEventListener('click',()=>{state={...INITIAL};notice('');persist();render();});
  $('export').addEventListener('click',()=>{
    const json={
      schema:'chronology-scenario-v3',calendar:'AM',scenario:state,
      selected_claims:[state.akivaClaim,state.accessionClaim,...(state.sourceAge?['age-47']:[])].filter(x=>!x.startsWith('computed')&&x!=='custom'),
      active_constraints:['rabbi','baby','identity'].filter(x=>state[x]),overrides:{
        ...(state.akivaClaim==='custom'?{akiva_death:state.akivaCustom}:{}),
        ...(state.accessionClaim==='custom'?{emperor_accession:state.accessionCustom}:{})
      },savedAt:new Date().toISOString(),note:'Исследовательский сценарий — не установленная историческая хронология'
    };
    const url=URL.createObjectURL(new Blob([JSON.stringify(json,null,2)],{type:'application/json'}));
    const a=node('a');a.href=url;a.download='jewish-chronology-scenario.json';a.click();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
  });
  $('import').addEventListener('change',async e=>{
    const file=e.target.files?.[0];if(!file)return;
    try{
      if(file.size>1024*1024)throw new Error('Слишком большой файл сценария.');
      const value=JSON.parse(await file.text());
      state=normalizeImported(value,catalog);notice('Сценарий импортирован.');persist();render();
    }catch(err){notice('Не удалось импортировать сценарий: '+err.message);}
    finally{e.target.value='';}
  });
}
async function loadCatalog(){
  try{
    const urls=['./data/events.json','./data/claims.json','./data/constraints.json'];
    const json=await Promise.all(urls.map(async u=>{
      const r=await fetch(u,{cache:'no-cache'});if(!r.ok)throw new Error('HTTP '+r.status+' — '+u);return r.json();
    }));
    catalog={events:json[0].events,claims:json[1].claims,constraints:json[2].constraints,derivedExamples:json[2].derivedExamples};
    setupOptions();setupControls();renderSources();
    try{
      const stored=JSON.parse(localStorage.getItem(STORAGE_KEY)||'null');
      if(stored && isAllowed(stored,catalog))state=Object.fromEntries(Object.keys(INITIAL).map(k=>[k,stored[k]]));
    }catch(e){}
    render();
  }catch(error){
    $('status').className='error';
    $('status').replaceChildren(node('strong','Каталог JSON не загружен'),node('p','Запустите сайт через HTTP, а не file://. '+error.message));
    notice('Ошибка загрузки данных.');
  }
}
loadCatalog();
