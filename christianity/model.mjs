// In-browser view model over the ONE canonical JSON-LD file. No other knowledge store.
const one=(graph,type)=>graph.filter(n=>n["@type"]===type);
export function createView(doc){
  if(!doc || !doc["@context"] || !Array.isArray(doc["@graph"]))throw Error("Ожидался документ JSON-LD с @graph");
  const records=doc["@graph"];
  const indexes=new Map(records.map(n=>[n["@id"],n]));
  if(indexes.size!==records.length)throw Error("Повторяющиеся идентификаторы графа");
  const refs=(arr=[])=>arr.map(ref=>{const n=indexes.get(ref);if(!n)throw Error("Отсутствует ссылка "+ref);return n;});
  const atlas=one(records,"HistoricalAtlas")[0];
  if(!atlas)throw Error("Отсутствует HistoricalAtlas");
  const positions=one(records,"DoctrinalPosition");
  const sources=one(records,"Source");
  const splits=one(records,"Controversy").map(c=>{
    const questions=one(records,"ComparativeQuestion").filter(q=>q.inControversy===c["@id"]).map(q=>{
      const answers={};
      for(const claim of one(records,"PositionClaim").filter(x=>x.respondsTo===q["@id"])){
        const id=claim.position;
        if(answers[id])throw Error("Несколько ответов одной стороны на "+q["@id"]);
        answers[id]={status:claim.evidenceStatus,text:claim.text,human_review_status:claim.humanReviewStatus,note:claim.note||"",source_ids:refs(claim.citedSources).map(x=>x["@id"])};
      }
      for(const id of c.resultingPositions)if(!answers[id])throw Error("Не найден ответ для "+id);
      return {id:q["@id"],title:q.label,answers};
    });
    return {id:c["@id"],title:c.label,period:c.period,issue:c.issue,caveat:c.caveat,parent_id:c.previousPosition,branch_ids:c.resultingPositions,questions,open_questions:one(records,"OpenResearchQuestion").filter(x=>x.inControversy===c["@id"]).map(x=>x.label)};
  });
  refs([atlas.rootPosition]);
  return {root_id:atlas.rootPosition,nodes:positions.map(n=>({id:n["@id"],title:n.label,period:n.period,description:n.description})),splits,sources:sources.map(s=>({id:s["@id"],title:s.label,url:s.url,type:s.sourceDescription,category:s.category,human_review_status:s.humanReviewStatus,relevance:s.relevance,limitations:s.limitations,machine_access_status:s.machineAccessStatus,machine_access_note:s.machineAccessNote,data_repository_file_url:s.dataRepositoryFileUrl}))};
}


// Cross-cutting questions and authors use the same canonical @graph as historical branches.
export function createMatrixView(doc) {
  if (!doc || !Array.isArray(doc["@graph"])) throw Error("Ожидался JSON-LD @graph");
  const nodes=doc["@graph"], map=new Map(nodes.map(n=>[n["@id"],n]));
  if(map.size!==nodes.length)throw Error("Повторяющиеся идентификаторы");
  const ofType=t=>nodes.filter(n=>n["@type"]===t);
  const lookup=(ref,type)=>{const n=map.get(ref);if(!n)throw Error("Не найдена ссылка "+ref);if(type&&n["@type"]!==type)throw Error("Ожидался "+type+": "+ref);return n;};
  const sort=(a,b)=>(a.order||0)-(b.order||0);
  const topics=ofType("TheologicalTopic").sort(sort);
  const questions=ofType("TheologicalQuestion").sort(sort).map(q=>({...q,id:q["@id"],topicId:lookup(q.topic,"TheologicalTopic")["@id"]}));
  const authors=ofType("TheologicalAuthor").sort(sort).map(a=>({...a,id:a["@id"]}));
  const answers=new Map();
  for(const a of ofType("AuthorPosition")){
    const author=lookup(a.author,"TheologicalAuthor"),question=lookup(a.question,"TheologicalQuestion");
    if(!["source","interpretation","work_needed"].includes(a.evidenceStatus))throw Error("Неверный статус "+a["@id"]);
    if(!["verified","not_reviewed"].includes(a.humanReviewStatus))throw Error("Неверная проверка "+a["@id"]);
    if(a.humanReviewStatus==="verified"&&(!a.reviewedBy||!a.reviewedAt))throw Error("Нет данных человеческой проверки "+a["@id"]);
    if(a.historicalClaim)lookup(a.historicalClaim,"PositionClaim");
    const key=author["@id"]+"|"+question["@id"];
    const list=answers.get(key)||[];
    list.push({...a,id:a["@id"],sources:(a.citedSources||[]).map(s=>lookup(s,"Source"))});
    answers.set(key,list);
  }
  for(const q of questions)lookup(q.topic,"TheologicalTopic");
  return {topics,questions,authors,answers};
}
