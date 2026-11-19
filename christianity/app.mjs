import {createView} from "./model.mjs?v=20261119-2";
const $=id=>document.getElementById(id);
const el=(tag,text,cls)=>{const x=document.createElement(tag);if(text!==undefined)x.textContent=text;if(cls)x.className=cls;return x;};
const dialog=$("dialog");$("close").onclick=()=>dialog.close();dialog.addEventListener("click",e=>{if(e.target===dialog)dialog.close();});
const show=()=>dialog.showModal();
function sourceLink(s,label){const a=el("a",label||s.title);a.href=s.url;a.target="_blank";a.rel="noopener noreferrer";return a;}
function showNode(node){$("dialog-title").textContent=node.title;$("dialog-subtitle").textContent=node.period;$("dialog-body").replaceChildren(el("p",node.description,"summary"));show();}
function claimContent(a,sourceMap){
 const item=el("div",undefined,"claim-content");
 item.append(el("span",a.status==="source"?"Первоисточник":a.status==="interpretation"?"Интерпретация":"work_needed","badge "+a.status));
 if(a.status==="source")item.append(el("span",a.human_review_status==="verified"?"Проверено человеком":"Человеком не проверено","badge "+(a.human_review_status==="verified"?"source":"work_needed")));
 item.append(el("p",a.text,"claim-text"));
 if(a.note)item.append(el("p",a.note,"note"));
 const refs=el("div",undefined,"refs");
 for(const sid of a.source_ids||[]){const s=sourceMap.get(sid);if(s)refs.append(sourceLink(s,"↗ "+s.title.split(" — ")[0]));}
 item.append(refs);
 return item;
}
function renderObjections(objections,sourceMap){
 const group=el("section",undefined,"objections-group");
 group.append(el("h4","Возражения и ответы · нажмите, чтобы раскрыть","objections-heading"));
 for(let i=0;i<objections.length;i++){
  const o=objections[i],pair=el("details",undefined,"objection-pair");
  // Native <details>: both objection and answer remain hidden until user expands.
  const statusText=o.status==="resolved"?"Снято":o.status==="tentative"?"Предварительно":"Открыто";
  const summary=el("summary",undefined,"objection-challenge");
  summary.append(el("span","ВОЗРАЖЕНИЕ "+(i+1)+" · "+statusText,"objection-kicker "+o.status),el("span",o.text,"objection-body"));
  const reply=el("div",undefined,"objection-reply");
  reply.append(el("span","ОТВЕТ · "+(o.status==="resolved"?"Снято":o.status==="tentative"?"Ответ предварительный":"Вопрос открыт"),"reply-kicker "+o.status),el("p",o.answer,"reply-body"));
  if(o.references?.length){
   const refs=el("div",undefined,"reply-sources");
   refs.append(el("span","Источники и основания ответа","reply-sources-title"));
   for(const entry of o.references){
    const s=sourceMap.get(entry.source);
    if(!s||!s.url)throw Error("Не найден источник ответа: "+entry.source);
    refs.append(sourceLink(s,s.title+(entry.locator?" · "+entry.locator:"")));
   }
   reply.append(refs);
  }
  pair.append(summary,reply);group.append(pair);
 }
 return group;
}
function imperialSummary(context){return (context?.rulers||[]).map(r=>r.name).join(" · ");}
function renderImperialContext(context,sourceMap){
 const section=el("section",undefined,"imperial-context");
 section.append(el("h3",context.heading,"imperial-heading"));
 const strip=el("div",undefined,"imperial-rulers");
 for(const ruler of context.rulers){
  const item=el("div",undefined,"imperial-ruler");
  item.append(el("strong",ruler.name),el("span",ruler.reign,"imperial-years"),el("small",ruler.jurisdiction));
  strip.append(item);
 }
 section.append(strip,el("p",context.scope,"imperial-note"));
 const refs=el("div",undefined,"imperial-sources");
 for(const id of context.sourceIds||[]){
  const source=sourceMap.get(id);
  if(!source||!source.url)throw Error("Не найден источник императорской хронологии: "+id);
  refs.append(sourceLink(source,"Источник: "+source.title));
 }
 section.append(refs);
 return section;
}
function showSplit(split,sourceMap,nodeMap){
 $("dialog-title").textContent=split.title;
 $("dialog-subtitle").textContent="Обсуждение · "+split.period;
 const body=$("dialog-body");
 body.replaceChildren(el("p",split.issue,"summary"));
 if(split.imperialContext)body.append(renderImperialContext(split.imperialContext,sourceMap));
 if(split.reviewLayout==="argument-review"){
  const sequence=el("div",undefined,"argument-sequence");
  for(const q of split.questions){
   const section=el("section",undefined,"argument-section");
   section.append(el("h3",q.title,"argument-title"));
   const positions=el("div",undefined,"argument-positions");
   for(const id of split.branch_ids){
    const position=el("div",undefined,"argument-position");
    position.append(el("h4",nodeMap.get(id)?.title||"Позиция","position-title"));
    const a=q.answers[id];position.append(claimContent(a,sourceMap));positions.append(position);
   }
   section.append(positions);
   for(const id of split.branch_ids)if(q.answers[id].objections?.length)section.append(renderObjections(q.answers[id].objections,sourceMap));
   sequence.append(section);
  }
  body.append(sequence,el("p",split.caveat,"summary"));show();return;
 }
 const wrap=el("div",undefined,"tablescroll"),table=el("table",undefined,"compare"),head=el("thead"),hr=el("tr");
 for(const name of ["Вопрос",...split.branch_ids.map(id=>nodeMap.get(id)?.title||"Позиция")])hr.append(el("th",name));
 head.append(hr);table.append(head);
 const tbody=el("tbody");
 for(const q of split.questions){
  const tr=el("tr");tr.append(el("td",q.title));
  for(const id of split.branch_ids){const td=el("td");td.append(claimContent(q.answers[id],sourceMap));tr.append(td);}
  tbody.append(tr);
 }
 table.append(tbody);wrap.append(table);body.append(wrap,el("p",split.caveat,"summary"));show();
}
function render(d){const nodeMap=new Map(d.nodes.map(n=>[n.id,n])),splitMap=new Map(),srcMap=new Map(d.sources.map(s=>[s.id,s]));
for(const s of d.splits){const list=splitMap.get(s.parent_id)||[];list.push(s);splitMap.set(s.parent_id,list);}
function branch(id,seen=new Set()){if(seen.has(id))throw Error("Цикл в графе");const next=new Set(seen);next.add(id);
const n=nodeMap.get(id);if(!n)throw Error("Отсутствует узел "+id);
const li=el("li"),btn=el("button",undefined,"node "+id);btn.type="button";btn.append(el("span",n.period,"period"),el("strong",n.title),el("small",n.description));btn.onclick=()=>showNode(n);li.append(btn);
const splits=splitMap.get(id)||[];
if(splits.length){const choices=el("ul",undefined,"controversy-branches");
for(const split of splits){const item=el("li",undefined,"controversy-item");const b=el("button","● "+split.title,"split");b.type="button";b.append(el("small","Нажмите для сравнения · "+split.period));
if(split.imperialContext)b.append(el("small","Императоры: "+imperialSummary(split.imperialContext),"imperial-inline"));b.onclick=()=>showSplit(split,srcMap,nodeMap);item.append(b);const ul=el("ul");for(const child of split.branch_ids)ul.append(branch(child,next));item.append(ul);choices.append(item);}
li.append(choices);}return li;}
const index=$("split-index");if(index){index.replaceChildren();for(const split of d.splits){const b=el("button",split.title,"split-shortcut");b.type="button";if(split.imperialContext)b.append(el("small","Императоры: "+imperialSummary(split.imperialContext),"imperial-shortcut"));b.onclick=()=>showSplit(split,srcMap,nodeMap);index.append(b);}}
const tree=el("ul",undefined,"tree");tree.append(branch(d.root_id));$("graph").replaceChildren(tree);
const counter=$("graph-coverage");if(counter)counter.textContent=d.splits.length+" развилки · "+d.nodes.length+" позиций";
const todo=$("todo"),sources=$("sources");todo.replaceChildren();sources.replaceChildren();
for(const split of d.splits)for(const q of split.open_questions)todo.append(el("li",q));
for(const s of d.sources){const li=el("li");li.append(sourceLink(s),el("small",s.type),el("small",s.human_review_status==="verified"?"Человеком проверено":"Человеком не проверено"));if(s.relevance)li.append(el("small","Для чего полезен: "+s.relevance));if(s.limitations)li.append(el("small","Ограничения: "+s.limitations));if(s.machine_access_note)li.append(el("small","Машиночитаемость: "+s.machine_access_note));if(s.data_repository_file_url){const ref=el("small");ref.append(sourceLink({url:s.data_repository_file_url,title:"Исходные данные в GitHub"}));li.append(ref);}sources.append(li);}}
fetch("./data/graph.jsonld?v=20261119-2",{cache:"no-store"}).then(r=>{if(!r.ok)throw Error("HTTP "+r.status);return r.json();}).then(createView).then(render).catch(e=>$("graph").textContent="Не удалось загрузить граф: "+e.message);