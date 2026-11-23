import {importPassword,loadKey,saveKey,deleteKey} from '../auth-store.js';
const $=id=>document.getElementById(id);
const rub=n=>new Intl.NumberFormat('ru-RU',{style:'currency',currency:'RUB',maximumFractionDigits:2}).format(n);
function line(a,b){const x=document.createElement('div');x.className='line';const l=document.createElement('span');l.textContent=a;const v=document.createElement('b');v.textContent=b;x.append(l,v);return x}
async function unlock(keyMaterial){
 const response=await fetch('../data/family.enc',{cache:'no-store'});
 if(!response.ok)throw Error('Семейный отчёт пока не опубликован');
 const env=await response.json();
 if(env.v!==1||env.kdf!=='PBKDF2-SHA256'||env.cipher!=='AES-256-GCM'||env.iterations<600000)throw Error('Неподдерживаемый формат отчёта');
 const b64=s=>Uint8Array.from(atob(s),c=>c.charCodeAt(0));
 
 const key=await crypto.subtle.deriveKey({name:'PBKDF2',salt:b64(env.salt),iterations:env.iterations,hash:'SHA-256'},keyMaterial,{name:'AES-GCM',length:256},false,['decrypt']);
 const clear=await crypto.subtle.decrypt({name:'AES-GCM',iv:b64(env.iv)},key,b64(env.ciphertext));
 const data=JSON.parse(new TextDecoder().decode(clear));
 if(!data||typeof data.asOf!=='string'||!('cycle' in data))throw Error('Некорректный отчёт');
 $('gate').hidden=true;$('board').hidden=false;$('asof').textContent=data.asOf;
 if(!data.cycle){$('empty').hidden=false;return}
 const c=data.cycle;
 if(!Array.isArray(c.budgets)||!Number.isFinite(c.income)||!Number.isFinite(c.expenses))throw Error('Неполный бюджет');
 $('current').hidden=false;$('label').textContent=c.label;
 $('summary').append(line('Прогноз поступлений',rub(c.income)),line('План расходов',rub(c.expenses)),line('Плановый результат',rub(c.income-c.expenses)));
 const box=$('categories');box.replaceChildren();for(const b of c.budgets){
  if(!Number.isFinite(b.limit))continue;
  const remaining=Number.isFinite(b.remaining)?b.remaining:
                  Number.isFinite(b.spent)?b.limit-b.spent:null;
  const item=document.createElement('div');item.className='budgetitem';
  const headline=document.createElement('div');headline.className='spread';
  const name=document.createElement('span');name.textContent=b.name;
  const amount=document.createElement('b');
  amount.textContent=remaining===null?'Лимит '+rub(b.limit):
      'Осталось '+rub(remaining)+' из '+rub(b.limit);
  headline.append(name,amount);item.append(headline);
  if(remaining!==null&&b.limit>0&&!b.informational){
    const progress=document.createElement('div');progress.className='progress';
    progress.setAttribute('role','progressbar');
    progress.setAttribute('aria-label',b.name+': remaining budget');
    progress.setAttribute('aria-valuemin','0');
    progress.setAttribute('aria-valuemax','100');
    const percent=Math.max(0,Math.min(100,remaining/b.limit*100));
    progress.setAttribute('aria-valuenow',percent.toFixed(1));
    const fill=document.createElement('div');fill.style.width=percent.toFixed(2)+'%';
    progress.append(fill);item.append(progress);
  }
  box.append(item);
 }
 if(Array.isArray(c.unmappedExpenses)&&c.unmappedExpenses.length){const total=c.unmappedExpenses.reduce((sum,x)=>sum+x.amount,0);box.append(line('Расходы без однозначной категории',rub(total)));const note=document.createElement('p');note.className='muted';note.textContent='Не распределено операций: '+c.unmappedExpenses.length+'. Эти суммы не вычтены из лимитов категорий и требуют сверки.';box.append(note)}
}

const KEY_ID='family', LEGACY_KEY='finance.family.password';
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
$('lock').addEventListener('click',async()=>{try{await deleteKey(KEY_ID);clearLegacy();location.reload()}catch(err){$('error').textContent='Не удалось удалить ключ: '+err.message;alert('Не удалось завершить выход: '+err.message)}});
restoreSession();
