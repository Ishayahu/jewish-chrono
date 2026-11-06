const $=id=>document.getElementById(id);
const el=(tag,text,cls)=>{const x=document.createElement(tag);if(text!==undefined)x.textContent=text;if(cls)x.className=cls;return x;};
const dialog=$("dialog");$("close").onclick=()=>dialog.close();dialog.addEventListener("click",e=>{if(e.target===dialog)dialog.close();});
const show=()=>dialog.showModal();
function sourceLink(s,label){const a=el("a",label||s.title);a.href=s.url;a.target="_blank";a.rel="noopener noreferrer";return a;}
function showNode(node){$("dialog-title").textContent=node.title;$("dialog-subtitle").textContent=node.period;$("dialog-body").replaceChildren(el("p",node.description,"summary"));show();}
function showSplit(split,sourceMap){$("dialog-title").textContent=split.title;$("dialog-subtitle").textContent="Разделение · "+split.period;
const body=$("dialog-body");body.replaceChildren(el("p",split.issue,"summary"));
const wrap=el("div",undefined,"tablescroll"),table=el("table",undefined,"compare"),head=el("thead"),hr=el("tr");
for(const name of ["Вопрос","Арий","Александр → Никея → Афанасий"])hr.append(el("th",name));
head.append(hr);table.append(head);const tbody=el("tbody");
for(const q of split.questions){const tr=el("tr");tr.append(el("td",q.title));
for(const id of split.branch_ids){const a=q.answers[id],td=el("td");
td.append(el("span",a.status==="source"?"Первоисточник":a.status==="interpretation"?"Интерпретация":"work_needed","badge "+a.status));if(a.status==="source")td.append(el("span",a.human_review_status==="verified"?"Проверено человеком":"Человеком не проверено","badge "+(a.human_review_status==="verified"?"source":"work_needed")));
td.append(el("div",a.text));if(a.note)td.append(el("p",a.note,"note"));
const refs=el("div",undefined,"refs");
for(const sid of a.source_ids||[]){const s=sourceMap.get(sid);if(s)refs.append(sourceLink(s,"↗ "+s.title.split(" — ")[0]));}
td.append(refs);tr.append(td);}
tbody.append(tr);}
table.append(tbody);wrap.append(table);body.append(wrap,el("p",split.caveat,"summary"));show();}
function render(d){const nodeMap=new Map(d.nodes.map(n=>[n.id,n])),splitMap=new Map(d.splits.map(s=>[s.parent_id,s])),srcMap=new Map(d.sources.map(s=>[s.id,s]));
function branch(id,seen=new Set()){if(seen.has(id))throw Error("Цикл в графе");const next=new Set(seen);next.add(id);
const n=nodeMap.get(id);if(!n)throw Error("Отсутствует узел "+id);
const li=el("li"),btn=el("button",undefined,"node "+id);btn.type="button";btn.append(el("span",n.period,"period"),el("strong",n.title),el("small",n.description));btn.onclick=()=>showNode(n);li.append(btn);
const split=splitMap.get(id);if(split){li.append(el("div",undefined,"spine"));const b=el("button","● "+split.title,"split");b.type="button";b.append(el("small","Нажмите для сравнения · "+split.period));b.onclick=()=>showSplit(split,srcMap);li.append(b);const ul=el("ul");for(const child of split.branch_ids)ul.append(branch(child,next));li.append(ul);}return li;}
const tree=el("ul",undefined,"tree");tree.append(branch(d.root_id));$("graph").replaceChildren(tree);
const todo=$("todo"),sources=$("sources");todo.replaceChildren();sources.replaceChildren();
for(const split of d.splits)for(const q of split.open_questions)todo.append(el("li",q));
for(const s of d.sources){const li=el("li");li.append(sourceLink(s),el("small",s.type),el("small",s.human_review_status==="verified"?"Человеком проверено":"Человеком не проверено"));if(s.relevance)li.append(el("small","Для чего полезен: "+s.relevance));if(s.limitations)li.append(el("small","Ограничения: "+s.limitations));sources.append(li);}}
fetch("./data/splits.json").then(r=>{if(!r.ok)throw Error("HTTP "+r.status);return r.json();}).then(render).catch(e=>$("graph").textContent="Не удалось загрузить граф: "+e.message);