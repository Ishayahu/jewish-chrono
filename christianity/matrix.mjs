import {createMatrixView} from "./model.mjs";
const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
const $=id=>document.getElementById(id);
const dialog=$("matrix-dialog");
$("matrix-dialog-close").onclick=()=>dialog.close();
dialog.addEventListener("click",e=>{if(e.target===dialog)dialog.close();});
const statusLabel={source:"● Первоисточник",interpretation:"◐ Интерпретация",work_needed:"○ Требует проверки"};
function showPosition(a,author,question){
  $("matrix-dialog-title").textContent=author.label+" — "+question.label;
  $("matrix-dialog-subtitle").textContent=a.sourceLocator||"Сопоставление позиций";
  const body=$("matrix-dialog-body");body.replaceChildren();
  body.append(el("p",a.text,"summary"),el("p",statusLabel[a.evidenceStatus]+" · "+(a.humanReviewStatus==="verified"?"Проверено человеком":"Человеком не проверено"),"note"));
  if(a.note)body.append(el("p",a.note,"note"));
  const refs=el("ul");
  for(const s of a.sources){const li=el("li"),link=el("a",s.label);link.href=s.url;link.target="_blank";link.rel="noopener noreferrer";li.append(link);refs.append(li);}
  if(refs.childElementCount)body.append(el("h3","Источники"),refs);
  dialog.showModal();
}
function render(data){
  const authorSel=$("author-filter"),topicSel=$("topic-filter"),search=$("question-search");
  for(const a of data.authors){const opt=el("option",a.label);opt.value=a.id;authorSel.append(opt);}
  for(const t of data.topics){const opt=el("option",t.label);opt.value=t["@id"];topicSel.append(opt);}
  function refresh(){
    const authors=authorSel.value?data.authors.filter(a=>a.id===authorSel.value):data.authors;
    const text=search.value.trim().toLocaleLowerCase("ru"),topic=topicSel.value;
    const filtered=data.questions.filter(q=>(!topic||q.topicId===topic)&&(!text||(q.label+" "+q.description).toLocaleLowerCase("ru").includes(text)));
    const host=$("matrix");host.replaceChildren();let count=0;
    for(const t of data.topics){
      const qs=filtered.filter(q=>q.topicId===t["@id"]);if(!qs.length)continue;
      const group=el("section",undefined,"matrix-group");group.append(el("h3",t.label),el("p",t.description,"matrix-group-description"));
      const scroller=el("div",undefined,"tablescroll"),table=el("table",undefined,"matrix-table"),thead=el("thead"),head=el("tr");
      head.append(el("th","Богословский вопрос"));for(const a of authors)head.append(el("th",a.label));thead.append(head);table.append(thead);
      const tbody=el("tbody");
      for(const q of qs){const tr=el("tr"),questionCell=el("th");questionCell.scope="row";questionCell.append(el("strong",q.label),el("small",q.description));tr.append(questionCell);
        for(const author of authors){const td=el("td"),found=data.answers.get(author.id+"|"+q.id)||[];
          if(!found.length)td.append(el("span","— Не установлено","matrix-unknown"));
          for(const a of found){const button=el("button",a.summary,"matrix-answer "+a.evidenceStatus);button.type="button";button.setAttribute("aria-label",author.label+": "+a.summary);button.title=statusLabel[a.evidenceStatus]+", "+(a.sourceLocator||"источник в карточке");button.onclick=()=>showPosition(a,author,q);td.append(button);count++;}
          tr.append(td);
        }
        tbody.append(tr);
      }
      table.append(tbody);scroller.append(table);group.append(scroller);host.append(group);
    }
    if(!host.childElementCount)host.append(el("p","Вопросов по запросу не найдено."));
    $("coverage").textContent=filtered.length+" вопросов · "+authors.length+" авторов · "+count+" позиций";
  }
  for(const x of [authorSel,topicSel,search])x.addEventListener(x===search?"input":"change",refresh);
  refresh();
}
fetch("./data/graph.jsonld").then(r=>{if(!r.ok)throw Error("HTTP "+r.status);return r.json();}).then(createMatrixView).then(render).catch(e=>$("matrix").textContent="Не удалось загрузить матрицу: "+e.message);
