const $=id=>document.getElementById(id);
const rub=n=>new Intl.NumberFormat('ru-RU',{style:'currency',currency:'RUB',maximumFractionDigits:2}).format(n);
function line(a,b){const x=document.createElement('div');x.className='line';const l=document.createElement('span');l.textContent=a;const v=document.createElement('b');v.textContent=b;x.append(l,v);return x}
async function unlock(password){
 const response=await fetch('../data/family.enc',{cache:'no-store'});
 if(!response.ok)throw Error('Семейный отчёт пока не опубликован');
 const env=await response.json();
 if(env.v!==1||env.kdf!=='PBKDF2-SHA256'||env.cipher!=='AES-256-GCM'||env.iterations<600000)throw Error('Неподдерживаемый формат отчёта');
 const b64=s=>Uint8Array.from(atob(s),c=>c.charCodeAt(0));
 const keyMaterial=await crypto.subtle.importKey('raw',new TextEncoder().encode(password),'PBKDF2',false,['deriveKey']);
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
 const box=$('categories');for(const b of c.budgets){
  if(!Number.isFinite(b.limit))continue;
  box.append(line(b.name,b.spent===null?'Лимит '+rub(b.limit):'Осталось '+rub(b.limit-b.spent)+' из '+rub(b.limit)));
 }
 if(Array.isArray(c.unmappedExpenses)&&c.unmappedExpenses.length){const total=c.unmappedExpenses.reduce((sum,x)=>sum+x.amount,0);box.append(line('Расходы без однозначной категории',rub(total)));const note=document.createElement('p');note.className='muted';note.textContent='Не распределено операций: '+c.unmappedExpenses.length+'. Эти суммы не вычтены из лимитов категорий и требуют сверки.';box.append(note)}
}
$('unlock').addEventListener('submit',async e=>{e.preventDefault();$('error').textContent='';try{await unlock($('password').value)}catch(err){$('error').textContent=err.name==='OperationError'?'Неверный пароль':err.message}finally{$('password').value=''}});
$('lock').addEventListener('click',()=>location.reload());
