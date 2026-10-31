// Pure chronology model. No browser APIs or external dependencies.
export const YEAR_LIMIT = 100000;
const asRange = value => typeof value === 'number' ? { min:value, max:value } : value && typeof value === 'object' ? { min:value.min, max:value.max } : null;
export function validRange(value) {
  const r=asRange(value);
  return !!r && Number.isInteger(r.min) && Number.isInteger(r.max) &&
    r.min<=r.max && r.min>=-YEAR_LIMIT && r.max<=YEAR_LIMIT;
}
export function range(value) { if (!validRange(value)) throw new Error('Неверный год или диапазон (допустимы целые годы от -100000 до 100000).'); return asRange(value); }
export function shift(value, amount) { const r=range(value); return range({min:r.min+amount,max:r.max+amount}); }
export function intersect(a,b) { const x=range(a), y=range(b), z={min:Math.max(x.min,y.min), max:Math.min(x.max,y.max)}; return z.min>z.max ? null : z; }
export function subtract(a,b) { const x=range(a),y=range(b); return {min:x.min-y.max,max:x.max-y.min}; }
export function yearLabel(value) {
  if(value===null || value===undefined) return '—';
  const r=range(value); return r.min===r.max ? String(r.min) : r.min+'–'+r.max;
}
export const INITIAL = Object.freeze({
  akivaClaim:'akiva-3880',akivaCustom:3880,
  accessionClaim:'accession-3900',accessionCustom:3900,
  rabbi:true,baby:true,identity:false,sourceAge:true,strict:true
});
export const COMPUTED_ACCESSION_OPTIONS = Object.freeze([
  {id:'computed-3927',year:3927,label:'3927 — вычисление: 3880 + 47'},
  {id:'computed-3948',year:3948,label:'3948 — вычисление: 3901 + 47'}
]);
const flags=['rabbi','baby','identity','sourceAge','strict'];
export function validateScenario(s,catalog) {
  if(!s || typeof s!=='object' || Array.isArray(s)) return 'Неверная структура сценария.';
  for(const flag of flags) if(typeof s[flag]!=='boolean') return 'Поле '+flag+' должно быть логическим.';
  if(!catalog || !Array.isArray(catalog.claims) || !Array.isArray(catalog.events) || !Array.isArray(catalog.constraints)) return 'Каталог данных не загружен.';
  const hasClaim=(id,eventId)=>catalog.claims.some(x=>x.id===id && x.eventId===eventId && x.kind==='source-claim' && validRange(x.year));
  if(s.akivaClaim==='custom') {if(!validRange(s.akivaCustom))return 'Недопустимый пользовательский год смерти Акивы.';}
  else if(!hasClaim(s.akivaClaim,'akiva_death'))return 'Неизвестный вариант смерти Акивы.';
  if(s.accessionClaim==='custom') {if(!validRange(s.accessionCustom))return 'Недопустимый пользовательский год воцарения.';}
  else if(!hasClaim(s.accessionClaim,'emperor_accession') &&
    !COMPUTED_ACCESSION_OPTIONS.some(x=>x.id===s.accessionClaim))return 'Неизвестный вариант воцарения.';
  if(!catalog.claims.some(x=>x.id==='age-47' && x.value===47))return 'Нет подтверждённого каталожного свидетельства о возрасте.';
  for(const id of ['rabbi','baby','identity'])if(!catalog.constraints.some(x=>x.id===id))return 'Нет ограничения: '+id;
  return null;
}
function choice(catalog,id,custom) {
  if(id==='custom')return {value:range(custom),kind:'custom',source:null,claimId:null};
  const claim=catalog.claims.find(x=>x.id===id && x.kind==='source-claim');
  if(claim)return {value:range(claim.year),kind:'source',source:claim.source?.url||null,claimId:claim.id};
  const example=COMPUTED_ACCESSION_OPTIONS.find(x=>x.id===id);
  if(example)return {value:range(example.year),kind:'computed-example',source:null,claimId:null};
  throw new Error('Неизвестный вариант: '+id);
}
export function evaluate(s,catalog) {
  const error=validateScenario(s,catalog);
  if(error)return {status:'invalid',error,rows:[]};
  const a=choice(catalog,s.akivaClaim,s.akivaCustom);
  const z=choice(catalog,s.accessionClaim,s.accessionCustom);
  const ageClaim=catalog.claims.find(x=>x.id==='age-47');
  const rabbiBorn=s.rabbi?a.value:null;
  const infantBorn=s.baby && rabbiBorn?rabbiBorn:null;
  const storyBorn=s.identity && infantBorn?infantBorn:null;
  const ageBorn=s.sourceAge?shift(z.value,-ageClaim.value):null;
  const both=!!storyBorn && !!ageBorn;
  const common=both?intersect(storyBorn,ageBorn):null;
  const contradictory=both && !common;
  const emperorBorn=both?(common||null):(storyBorn||ageBorn);
  const ageComputed=storyBorn?subtract(z.value,storyBorn):null;
  const predictedAccession=storyBorn && s.sourceAge?shift(storyBorn,ageClaim.value):null;
  const gap=both && !common ? (ageBorn.max<storyBorn.min ? storyBorn.min-ageBorn.max : ageBorn.min-storyBorn.max) : 0;
  const status=contradictory?'contradictory':both?'consistent':'underdetermined';
  const byId=id=>catalog.constraints.find(x=>x.id===id);
  const sourceOf=(claim)=>claim?.source?.url||null;
  const ageUrl=sourceOf(ageClaim);
  const link=(c)=>c?.evidence?.url||null;
  const rows=[
    {eventId:'akiva_death',label:'Смерть раби Акивы',year:a.value,kind:a.kind,sourceUrls:a.source?[a.source]:[],note:a.kind==='custom'?'Введено пользователем':a.kind==='source'?'Выбранная датировка источника':'Вычислено'},
    {eventId:'rabbi_birth',label:'Рождение Раби',year:rabbiBorn,kind:'inferred',sourceUrls:s.rabbi?[link(byId('rabbi'))].filter(Boolean):[],note:s.rabbi?'Условное равенство со смертью Акивы':'Связь не принята'},
    {eventId:'antoninus_infant_birth',label:'Рождение младенца Антонинуса',year:infantBorn,kind:'inferred',sourceUrls:s.baby&&rabbiBorn?[link(byId('baby'))].filter(Boolean):[],note:infantBorn?'Условное ровесничество с Раби':'Недостаточно связей'},
    {eventId:'emperor_birth',label:'Рождение императора — по свидетельству о возрасте',year:ageBorn,kind:'inferred',sourceUrls:ageBorn?[ageUrl].filter(Boolean):[],note:ageBorn?'Год воцарения минус 47':'Свидетельство о возрасте отключено'},
    {eventId:'emperor_birth',label:'Рождение императора — по рассказу',year:storyBorn,kind:'hypothesis',sourceUrls:storyBorn?[link(byId('identity'))].filter(Boolean):[],note:storyBorn?'Три отдельно принятые связи':'Связь с младенцем не установлена'},
    {eventId:'emperor_accession',label:'Вступление на престол',year:z.value,kind:z.kind,sourceUrls:z.source?[z.source]:[],note:z.kind==='computed-example'?'Вычисленный пример, не свидетельство':z.kind==='custom'?'Введено пользователем':'Выбранное свидетельство'},
    {eventId:'emperor_accession',label:'Вступление, ожидаемое при возрасте 47',year:predictedAccession,kind:'inferred',sourceUrls:predictedAccession?[ageUrl,link(byId('identity'))].filter(Boolean):[],note:predictedAccession?'Применены возраст и три связи':'Недостаточно связей'}
  ];
  return {status, akiva:a.value, accession:z.value, rabbiBorn, infantBorn, storyBorn, ageBorn, emperorBorn, ageComputed, predictedAccession, gap,rows,ageValue:ageClaim.value,identityEnabled:!!s.identity && !!infantBorn,hasYearZero:a.value.min<=0||z.value.min<=0};
}
export function isAllowed(s,catalog) {
  const r=evaluate(s,catalog);return r.status!=='invalid' && (!s.strict || r.status!=='contradictory');
}
export function normalizeImported(raw,catalog) {
  if(!raw || raw.schema!=='chronology-scenario-v3' || raw.calendar!=='AM' || !raw.scenario)throw new Error('Неизвестный формат JSON сценария.');
  const s=raw.scenario;
  const error=validateScenario(s,catalog);
  if(error)throw new Error(error);
  if(!isAllowed(s,catalog))throw new Error('В строгом режиме импортированный сценарий противоречив.');
  return Object.fromEntries(Object.keys(INITIAL).map(key=>[key,s[key]]));
}
