import {importPassword,loadKey,saveKey,deleteKey} from './auth-store.js';
const $=id=>document.getElementById(id);const rub=n=>new Intl.NumberFormat('ru-RU',{style:'currency',currency:'RUB',maximumFractionDigits:2}).format(n);const usd=n=>new Intl.NumberFormat('ru-RU',{style:'currency',currency:'USD',maximumFractionDigits:2}).format(n);const pct=(a,b)=>b>0?Math.max(0,Math.min(100,100*a/b)):0;const fill=(id,p)=>$(id).style.width=p.toFixed(3)+'%';const demo={asOf:'ДЕМОНСТРАЦИЯ',familyDeficit:1120000,deficit:85000,rubDebts:[{name:'Цдока',amount:250000},{name:'Мама',amount:120000},{name:'Бюджет',amount:45000},{name:'Свой ГМАХ',amount:90000}],usdDebt:15000,rate:80,savedRub:12000,reserveTargetRub:16000,day:{target:12000,received:4500},cycles:[{label:'21.11–20.12.2026',income:325000,expenses:350000,possibleReturn:0,budgets:[{name:'Шаббат',limit:30000,spent:0},{name:'Обычные продукты',limit:14000,spent:0},{name:'Дети — прочие расходы',limit:5000,spent:0},{name:'Бытовая химия',limit:7000,spent:0}]},{label:'21.12.2026–20.01.2027',income:345000,expenses:340000,possibleReturn:0,budgets:[{name:'Шаббат',limit:30000,spent:0},{name:'Обычные продукты',limit:14000,spent:0},{name:'Дети — прочие расходы',limit:5000,spent:0},{name:'Бытовая химия',limit:7000,spent:0}]}],children:[{name:'Дочь',amount:65500},{name:'Леви',amount:160000},{name:'Давид',amount:110000}],installments:[{name:'Алиса с экраном',count:2,payment:2300},{name:'Алиса в гостиной',count:4,payment:1600}]};function el(tag,cls,content){const x=document.createElement(tag);if(cls)x.className=cls;if(content!==undefined)x.textContent=content;return x}function line(name,value){const x=el('div','line');x.append(el('span','',name),el('b','',value));return x}function render(d,isDemo){$('gate').hidden=true;$('board').hidden=false;$('demoNotice').hidden=!isDemo;$('date').textContent=d.asOf;$('asof').textContent=d.asOf;$('familyDeficit').textContent=rub(d.familyDeficit);$('deficit').textContent=rub(d.deficit);$('rubDebt').textContent=rub(d.rubDebts.reduce((s,x)=>s+x.amount,0));$('usdDebt').textContent=usd(d.usdDebt);$('usdSaved').textContent=d.savedRub===null?'Нет подтверждённых данных':usd(d.savedRub/d.rate);$('rate').textContent=d.rate+' ₽/USD';$('savedRub').textContent=d.savedRub===null?'Не подтверждено':rub(d.savedRub);$('reserveAmount').textContent=rub(d.reserveTargetRub);$('toTransfer').textContent=d.savedRub===null?'Нет подтверждения переводов':rub(Math.max(0,d.reserveTargetRub-d.savedRub));let p=d.savedRub===null?0:pct(d.savedRub/d.rate,d.usdDebt);$('debtPercent').textContent=d.savedRub===null?'Фактический остаток копилки не подтверждён':p.toFixed(2).replace('.',',')+'% долга';fill('debtFill',p);$('dayTarget').textContent=d.day?rub(d.day.target):'Ещё не зафиксирована';$('dayReceived').textContent=d.day?rub(d.day.received):'—';$('dayShortfall').textContent=d.day?'Недобор: '+rub(Math.max(0,d.day.target-d.day.received)):'Дневная цель появится после первого запуска GitHub Actions за 05:00 МСК';fill('dayFill',d.day?pct(d.day.received,d.day.target):0);const cycles=$('cycles');cycles.replaceChildren();for(const [i,c] of d.cycles.entries()){const x=el('article','cycle'+(i===0?' cycle-current':''));x.append(el('div','cycle-kind',i===0?'ТЕКУЩИЙ ЦИКЛ':i===1?'СЛЕДУЮЩИЙ ЦИКЛ':'ЧЕРЕЗ ОДИН ЦИКЛ'),el('h3','',c.label),line('Прогноз поступлений',c.income===null?'Пока не рассчитан':rub(c.income)),line('План расходов',c.expenses===null?'Пока не рассчитан':rub(c.expenses)));const result=c.income===null||c.expenses===null?null:c.income-c.expenses;x.append(el('div','result'+(result!==null&&result>=0?' positive':''),'Результат: '+(result===null?'Пока не рассчитан':rub(result))));for(const b of c.budgets){const item=el('div','budgetitem'),head=el('div','spread'),remaining=b.spent===null?null:Math.max(0,b.limit-b.spent);head.append(el('span','',b.name),el('b','',remaining===null?('Лимит '+rub(b.limit)):rub(remaining)+' / '+rub(b.limit)));item.append(head);if(!b.informational){const bar=el('div','progress'),inside=el('div');inside.style.width=(remaining===null?100:pct(remaining,b.limit))+'%';bar.append(inside);item.append(bar)}if(b.accountingNote)item.append(el('small','muted',b.accountingNote));x.append(item)}cycles.append(x)}const debts=$('debts');debts.replaceChildren();debts.append(line('1. ГМАХ МЕОЦ',usd(d.usdDebt)));d.rubDebts.forEach((x,i)=>debts.append(line((i+2)+'. '+x.name,rub(x.amount))));debts.append(line('6. Накопления детям','цель, не долг'));const children=$('children');children.replaceChildren();d.children.forEach(x=>children.append(line(x.name,rub(x.amount))));children.append(line('Всего',rub(d.children.reduce((s,x)=>s+x.amount,0))));const inst=$('installments');inst.replaceChildren();d.installments.forEach(x=>inst.append(line(x.name+' · '+x.count+' × '+rub(x.payment),rub(x.count*x.payment))))}function validate(d){if(!d||!Array.isArray(d.cycles)||d.cycles.length!==3||!Array.isArray(d.rubDebts)||!Array.isArray(d.children)||!Array.isArray(d.installments))throw Error('Неполный формат отчёта');for(const k of ['familyDeficit','deficit','usdDebt','rate','savedRub','reserveTargetRub'])if(!(k==='savedRub'&&d[k]===null)&&!Number.isFinite(d[k]))throw Error('Некорректное поле '+k);if(d.rate<=0||d.usdDebt<=0)throw Error('Некорректная цель или курс');return d}async function unlock(keyMaterial){const response=await fetch('./data/owner.enc',{cache:'no-store'});if(!response.ok)throw Error('Зашифрованный отчёт ещё не опубликован. Пока доступен демонстрационный макет.');const env=await response.json();if(env.v!==1||env.kdf!=='PBKDF2-SHA256'||env.cipher!=='AES-256-GCM'||env.iterations<600000)throw Error('Неподдерживаемый формат данных');const b64=s=>Uint8Array.from(atob(s),c=>c.charCodeAt(0));const key=await crypto.subtle.deriveKey({name:'PBKDF2',salt:b64(env.salt),iterations:env.iterations,hash:'SHA-256'},keyMaterial,{name:'AES-GCM',length:256},false,['decrypt']);const clear=await crypto.subtle.decrypt({name:'AES-GCM',iv:b64(env.iv)},key,b64(env.ciphertext));const data=validate(JSON.parse(new TextDecoder().decode(clear)));render(data,String(data.asOf).startsWith('ТЕСТ'))}
const KEY_ID='owner', LEGACY_KEY='finance.owner.password';
function clearLegacy(){try{localStorage.removeItem(LEGACY_KEY)}catch{}}
async function restoreSession(){
 let key;
 try{key=await loadKey(KEY_ID)}catch(err){$('error').textContent='Хранилище ключей недоступно: '+err.message;return}
 if(!key){
  let password=null;try{password=localStorage.getItem(LEGACY_KEY)}catch{}
  if(password){
   try{
    const candidate=await importPassword(password);
    await unlock(candidate);
    await saveKey(KEY_ID,candidate);
    clearLegacy();
   }catch(err){
    if(err.name==='OperationError')clearLegacy();
    $('error').textContent='Не удалось восстановить сохранённый вход: '+err.message;
   }
  }
  return;
 }
 try{await unlock(key);clearLegacy()}
 catch(err){
  if(err.name==='OperationError'){await deleteKey(KEY_ID);$('error').textContent='Сохранённый ключ не подходит. Введите пароль заново.'}
  else $('error').textContent='Не удалось загрузить отчёт: '+err.message;
 }
}
$('unlock').addEventListener('submit',async e=>{
 e.preventDefault();$('error').textContent='';
 try{
  const key=await importPassword($('password').value);
  await unlock(key);
  await saveKey(KEY_ID,key);
  clearLegacy();
 }catch(err){$('error').textContent=err.name==='OperationError'?'Неверный пароль или повреждённые данные.':err.message}
 finally{$('password').value=''}
});
$('demo').addEventListener('click',()=>render(demo,true));
$('lock').addEventListener('click',async()=>{try{await deleteKey(KEY_ID);clearLegacy();location.reload()}catch(err){$('error').textContent='Не удалось удалить ключ: '+err.message;alert('Не удалось завершить выход: '+err.message)}});
restoreSession();
