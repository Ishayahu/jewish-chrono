import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync,existsSync} from "node:fs";
import {createView} from "../christianity/model.mjs";
const path=new URL("../christianity/data/graph.jsonld",import.meta.url);
const d=JSON.parse(readFileSync(path,"utf8"));
const records=d["@graph"];
const byId=new Map(records.map(n=>[n["@id"],n]));
const ofType=type=>records.filter(n=>n["@type"]===type);
const single=type=>{const a=ofType(type);assert.equal(a.length,1);return a[0];};
const checkRef=(id)=>assert.ok(byId.has(id),"Dangling IRI: "+id);
test("one canonical JSON-LD knowledge file",()=>{
  assert.ok(d["@context"]);assert.ok(Array.isArray(records));assert.equal(byId.size,records.length);
  assert.ok(!existsSync(new URL("../christianity/data/splits.json",import.meta.url)));
  const a=single("HistoricalAtlas");assert.equal(a.schemaVersion,5);checkRef(a.rootPosition);
  const base="https://ishayahu.github.io/jewish-chrono/christianity/data/graph.jsonld#";
  for(const n of records)assert.ok(n["@id"].startsWith(base),n["@id"]);
  const wf=readFileSync(new URL("../.github/workflows/pages.yml",import.meta.url),"utf8");
  assert.ok(!wf.includes("build_christianity_graph"));assert.ok(wf.includes("cp -R src data christianity dist/"));
});
test("every semantic connection is resolvable",()=>{
  const keys=["rootPosition","previousPosition","resultingPositions","relatedResearchProjects","position","inControversy","respondsTo","citedSources","fromClaim","toClaim","relatedClaims","topic","author","question","historicalClaim"];
 for(const claim of records.filter(n=>n["@type"]==="PositionClaim"))for(const o of claim.objections||[])for(const r of o.references||[])checkRef(r.source);
  for(const n of records)for(const key of keys)if(n[key]!==undefined)for(const v of [].concat(n[key]))checkRef(v);
});
test("historical positions, questions and evidence are preserved",()=>{
  const v=createView(d);assert.ok(v.nodes.length>=7);assert.ok(v.splits.length>=2);
  const arian=v.splits.find(s=>s.id.endsWith("/arius-nicaea"));
  const roman=v.splits.find(s=>s.id.endsWith("/roman-father-son"));
  const jerusalem=v.splits.find(s=>s.id.endsWith("/jerusalem-council"));
  assert.ok(arian);assert.ok(roman);assert.ok(jerusalem);
  assert.equal(arian.questions.length,4);assert.equal(arian.branch_ids.length,2);
  assert.ok(arian.open_questions.some(x=>x.includes("Адама")));
  assert.equal(roman.questions.length,3);assert.equal(roman.branch_ids.length,4);
  assert.ok(roman.open_questions.some(x=>x.includes("Феодот")));
  assert.equal(jerusalem.parent_id,v.root_id,"Jerusalem is the historical root");
  assert.ok(jerusalem.branch_ids.includes(roman.parent_id),"Jerusalem continues into the Roman controversy");
  assert.ok(roman.branch_ids.includes(arian.parent_id),"Pre-Nicene continuation connects Roman and Arian crises");
  assert.ok(arian.parent_id.endsWith("/early"),"Arian crisis must start after the pre-Nicene continuation");
  assert.equal(v.splits[0].id,jerusalem.id,"Jerusalem first");
  assert.equal(v.splits[1].id,roman.id,"Roman second");
  assert.equal(v.splits[2].id,arian.id,"Arian third");
  assert.equal(jerusalem.questions.length,5);
  assert.ok(!jerusalem.open_questions.some(x=>x.includes("Билам")),"Resolved Balaam objection is no longer open");
  assert.ok(!jerusalem.open_questions.some(x=>x.includes("Корнилий получил Духа до крещения")),"Resolved baptism objection is no longer open");
  assert.ok(!jerusalem.open_questions.some(x=>x.includes("случай Корнилия")),"Generalization objection has been resolved");
  assert.ok(!jerusalem.open_questions.some(x=>x.includes("очищение сердца")),"Heart-cleansing objection has been resolved");
  assert.ok(!jerusalem.open_questions.some(x=>x.includes("ярмо")),"Yoke interpretation objection is resolved");
  assert.ok(jerusalem.open_questions.some(x=>x.includes("тшува")),"Repentance question remains open");
  for(const q of roman.questions)for(const id of roman.branch_ids)assert.ok(q.answers[id],"Missing Roman comparison cell: "+id);
  const byParent=new Map();
  for(const split of v.splits){const list=byParent.get(split.parent_id)||[];list.push(split);byParent.set(split.parent_id,list);}
  assert.equal(byParent.get(v.root_id).length,1,"Only Jerusalem controversy directly leaves root");
  assert.equal(byParent.get(roman.parent_id).length,1,"Roman controversy follows Jerusalem");
  assert.equal(byParent.get(arian.parent_id).length,1,"Arian controversy must continue from the pre-Nicene branch");
  const reachable=new Set();
  const visit=(id,ancestry=new Set())=>{assert.ok(!ancestry.has(id),"Cycle in visible tree");reachable.add(id);const next=new Set(ancestry);next.add(id);for(const split of byParent.get(id)||[])for(const child of split.branch_ids)visit(child,next);};
  visit(v.root_id);assert.equal(reachable.size,v.nodes.length,"Every position must be accessible from the root");
  assert.equal(ofType("ReasoningLink").length,3);
  assert.ok(ofType("OpenResearchQuestion").length>=7);
  assert.equal(ofType("Source").filter(s=>s.category==="research_project").length,6);
  const q=ofType("ComparativeQuestion").find(x=>x.questionCode==="salvation");
  const arius=ofType("PositionClaim").find(x=>x.respondsTo===q["@id"]&&x.position.endsWith("/arius"));
  assert.equal(arius.evidenceStatus,"work_needed");
});
test("political rulers are an independent sourced context on every controversy",()=>{
 const v=createView(d);
 assert.equal(v.splits.length,3);
 for(const split of v.splits){
  const ctx=split.imperialContext;
  assert.ok(ctx?.heading&&ctx.scope,"Missing imperial context: "+split.title);
  assert.ok(ctx.rulers.length,"Missing rulers: "+split.title);
  assert.ok(ctx.sourceIds.length,"Missing sources: "+split.title);
  for(const ruler of ctx.rulers)assert.ok(ruler.name&&ruler.reign&&ruler.jurisdiction);
  for(const id of ctx.sourceIds){checkRef(id);assert.equal(byId.get(id)["@type"],"Source");}
 }
 const arian=v.splits.find(s=>s.id.endsWith("/arius-nicaea"));
 const jerusalem=v.splits.find(s=>s.id.endsWith("/jerusalem-council"));
 assert.ok(arian.imperialContext.rulers.some(r=>r.name==="Константин I"&&r.reign==="306–337"));
 assert.ok(arian.imperialContext.rulers.some(r=>r.name==="Феодосий I"));
 assert.equal(jerusalem.imperialContext.rulers[0].name,"Клавдий");
});
test("Jerusalem objections and responses are individual, status-aware records",()=>{
 const split=createView(d).splits.find(s=>s.id.endsWith("/jerusalem-council"));
 assert.equal(split.reviewLayout,"argument-review");
 const get=key=>split.questions.find(q=>q.id.endsWith("--"+key)).answers[split.branch_ids[1]].objections;
 const spirit=get("spirit"),yoke=get("yoke"),grace=get("grace"),signs=get("signs");
 assert.equal(spirit.length,4);assert.ok(spirit.every(o=>o.status==="resolved"));
 assert.equal(yoke.length,2);assert.equal(yoke[0].status,"resolved");assert.equal(yoke[1].status,"open");
 assert.equal(grace.length,3);assert.equal(signs.length,2);
 for(const o of [...spirit,...yoke,...grace,...signs]){
  assert.ok(o.id&&o.text&&o.answer&&["resolved","tentative","open"].includes(o.status));
  assert.ok(o.references?.length,"Every objection answer has cited sources: "+o.id);
  for(const ref of o.references){checkRef(ref.source);assert.equal(byId.get(ref.source)["@type"],"Source");assert.ok(byId.get(ref.source).url);assert.ok(ref.locator);}
 }
 assert.ok(grace[0].answer.includes("Павла"));
});
test("source kind and human review are independent",()=>{
 const kinds=new Set(["primary","secondary_study","research_project"]);
 for(const s of ofType("Source")){assert.ok(kinds.has(s.category));assert.ok(["verified","not_reviewed"].includes(s.humanReviewStatus));if(s.humanReviewStatus==="verified"){assert.ok(s.reviewedBy);assert.ok(s.reviewedAt);}}
 for(const n of records.filter(x=>["PositionClaim","ReasoningLink","OpenResearchQuestion"].includes(x["@type"]))){assert.ok(["source","interpretation","work_needed"].includes(n.evidenceStatus));assert.ok(["verified","not_reviewed"].includes(n.humanReviewStatus));if(n.humanReviewStatus==="verified"){assert.ok(n.reviewedBy);assert.ok(n.reviewedAt);}}
});
test("reasoning links are interpretations, not proven implication",()=>{const relations=new Set(["motivates","supports","challenges","contradicts","depends_on"]);for(const e of ofType("ReasoningLink")){assert.ok(relations.has(e.relationKind));assert.equal(e.evidenceStatus,"interpretation");}});
test("browser view references canonical JSON-LD only",()=>{const app=readFileSync(new URL("../christianity/app.mjs",import.meta.url),"utf8");assert.match(app,/fetch\("\.\/data\/graph\.jsonld(?:\?[^"]*)?"/);assert.ok(app.includes('const choices=el("ul",undefined,"controversy-branches")'));assert.ok(!app.includes("splits.json"));});

test("browser renderer connects earlier Roman controversy to later Arian crisis",async()=>{
 const {runInNewContext}=await import("node:vm");
 const view=createView(d);
 class Element{
  constructor(tag){this.tag=tag;this.children=[];this.className="";this.textContent="";}
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this.children=[...children];}
  addEventListener(){}
  showModal(){}
  close(){}
 }
 const roots=new Map();
 const document={createElement:tag=>new Element(tag),getElementById:id=>{
  if(!roots.has(id))roots.set(id,new Element("div"));return roots.get(id);
 }};
 const app=readFileSync(new URL("../christianity/app.mjs",import.meta.url),"utf8");
 const code=app.replace(/^import \{createView\} from "\.\/model\.mjs(?:\?[^"]*)?";\n/,"").split('\nfetch("./data/graph.jsonld')[0];
 assert.ok(code.includes("function render(d)"));
 runInNewContext(code+"\nrender(view);",{document,view});
 const displayed=[];
 const visit=e=>{if(e.className==="split")displayed.push(e.textContent);for(const child of e.children||[])visit(child);};
 visit(roots.get("graph"));
 assert.ok(displayed.some(s=>s.includes("Арианский кризис")),displayed.join("; "));
 assert.ok(displayed.some(s=>s.includes("Римский спор")),displayed.join("; "));
 const flatten=e=>[e,...(e.children||[]).flatMap(flatten)];
 const romanItem=flatten(roots.get("graph")).find(e=>e.className==="controversy-item"&&e.children[0]?.textContent?.includes("Римский спор"));
 assert.ok(romanItem,"Roman split must exist");
 assert.ok(flatten(romanItem).some(e=>e.className==="split"&&e.textContent.includes("Арианский кризис")),"Arian split must be nested in the Roman continuation");
 const councilItem=flatten(roots.get("graph")).find(e=>e.className==="controversy-item"&&e.children[0]?.textContent?.includes("Иерусалиме"));
 assert.ok(councilItem,"Jerusalem council exists");
 assert.ok(flatten(councilItem).some(e=>e.className==="split"&&e.textContent.includes("Римский спор")),"Roman controversy nested in Jerusalem continuation");
 const firstNode=flatten(roots.get("graph")).find(e=>e.className.startsWith("node "));
 assert.ok(firstNode.children.some(c=>c.textContent==="Иерусалимская община до собрания"),"Correct historical root");
 const shortcuts=roots.get("split-index").children.map(e=>e.textContent);
 assert.ok(shortcuts.some(s=>s.includes("Арианский кризис")));
 assert.ok(shortcuts.some(s=>s.includes("Римский спор")));
 assert.ok(shortcuts.some(s=>s.includes("Иерусалиме")));
 assert.ok(roots.get("split-index").children.some(b=>b.children.some(c=>c.className==="imperial-shortcut"&&c.textContent.includes("Константин I"))),"Imperial names visible without opening a controversy");
 const councilButton=roots.get("split-index").children.find(b=>b.textContent.includes("Иерусалиме"));
 assert.ok(typeof councilButton.onclick==="function");
 councilButton.onclick();
 const allNodes=flatten(roots.get("dialog-body"));
 assert.equal(allNodes.filter(n=>n.className==="imperial-context").length,1);
 assert.ok(allNodes.some(n=>n.className==="imperial-ruler"&&n.children.some(c=>c.textContent==="Клавдий")));
 assert.equal(allNodes.filter(n=>n.className==="objection-pair").length,11);
 assert.equal(allNodes.filter(n=>n.className==="objection-challenge").length,11);
 assert.equal(allNodes.filter(n=>n.className==="objection-reply").length,11);
 assert.equal(allNodes.filter(n=>n.tag==="details"&&n.className==="objection-pair").length,11);
 assert.equal(allNodes.filter(n=>n.tag==="summary"&&n.className==="objection-challenge").length,11);
 assert.ok(allNodes.filter(n=>n.tag==="details").every(n=>!n.open),"All objection pairs collapsed by default");
 assert.ok(allNodes.some(n=>n.className==="reply-sources"&&n.children.some(c=>c.tag==="a")),"Citations shown within each expanded response");
 assert.ok(allNodes.some(n=>n.className.startsWith("reply-kicker")&&n.textContent.includes("Снято")));
 assert.ok(roots.get("graph-coverage").textContent.startsWith(view.splits.length+" развил"));
});

test("published identifiers pass JSON Schema URI regexp",()=>{const schema=JSON.parse(readFileSync(new URL("../christianity/data/schema.json",import.meta.url),"utf8"));const re=new RegExp(schema.properties["@graph"].items.properties["@id"].pattern);for(const n of records)assert.ok(re.test(n["@id"]),n["@id"]);});

test("Six external projects have an auditable machine access finding",()=>{const p=ofType("Source").filter(x=>x.category==="research_project");assert.equal(p.length,6);const allowed=new Set(["not_documented_publicly","internal_structured_data_only","public_repository_data","claimed_undocumented_api"]);for(const s of p){assert.ok(allowed.has(s.machineAccessStatus));assert.ok(s.machineAccessCheckedAt);assert.ok(s.machineAccessNote);}const cic=p.find(x=>x.label.startsWith("Church in Conversation"));assert.equal(cic.machineAccessStatus,"public_repository_data");assert.ok(cic.dataRepositoryFileUrl.includes("world-census.json"));});

test("cross-cutting questions and author opinions share the canonical JSON-LD", async()=>{
 const {createMatrixView}=await import("../christianity/model.mjs");
 const v=createMatrixView(d);
 assert.equal(v.topics.length,4);assert.equal(v.authors.length,5);assert.ok(v.questions.length>=13);
 assert.equal(ofType("AuthorPosition").length,10);
 assert.ok(!existsSync(new URL("../christianity/data/matrix.json",import.meta.url)));
 for(const a of ofType("AuthorPosition")){
  assert.ok(a.sourceLocator);assert.ok(a.citedSources?.length);assert.equal(a.humanReviewStatus,"not_reviewed");
  assert.ok(["source","interpretation","work_needed"].includes(a.evidenceStatus));
 }
 const ath=v.authors.find(a=>a.label.includes("Афанасий"));
 const q=v.questions.find(q=>q.label.includes("посредника"));
 assert.ok(v.answers.get(ath.id+"|"+q.id)?.length);
 const html=readFileSync(new URL("../christianity/matrix.html",import.meta.url),"utf8");
 assert.ok(html.includes("matrix.mjs"));
 const js=readFileSync(new URL("../christianity/matrix.mjs",import.meta.url),"utf8");
 assert.ok(js.includes('fetch("./data/graph.jsonld")'));
});
