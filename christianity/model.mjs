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
  return {root_id:atlas.rootPosition,nodes:positions.map(n=>({id:n["@id"],title:n.label,period:n.period,description:n.description})),splits,sources:sources.map(s=>({id:s["@id"],title:s.label,url:s.url,type:s.sourceDescription,category:s.category,human_review_status:s.humanReviewStatus,relevance:s.relevance,limitations:s.limitations}))};
}
