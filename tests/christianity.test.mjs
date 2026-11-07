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
  for(const n of records)for(const key of keys)if(n[key]!==undefined)for(const v of [].concat(n[key]))checkRef(v);
});
test("historical positions, questions and evidence are preserved",()=>{
  const v=createView(d);assert.ok(v.nodes.length>=7);assert.ok(v.splits.length>=2);
  const arian=v.splits.find(s=>s.id.endsWith("/arius-nicaea"));
  const roman=v.splits.find(s=>s.id.endsWith("/roman-father-son"));
  assert.ok(arian);assert.ok(roman);
  assert.equal(arian.questions.length,4);assert.equal(arian.branch_ids.length,2);
  assert.ok(arian.open_questions.some(x=>x.includes("Адама")));
  assert.equal(roman.questions.length,3);assert.equal(roman.branch_ids.length,4);
  assert.ok(roman.open_questions.some(x=>x.includes("Феодот")));
  assert.equal(roman.parent_id,v.root_id,"Roman dispute must start at historical root");
  assert.ok(roman.branch_ids.includes(arian.parent_id),"Pre-Nicene continuation connects Roman and Arian crises");
  assert.ok(arian.parent_id.endsWith("/early"),"Arian crisis must start after the pre-Nicene continuation");
  assert.equal(v.splits[0].id,roman.id,"Chronology: Roman before Arian");
  assert.equal(v.splits[1].id,arian.id);
  for(const q of roman.questions)for(const id of roman.branch_ids)assert.ok(q.answers[id],"Missing Roman comparison cell: "+id);
  const byParent=new Map();
  for(const split of v.splits){const list=byParent.get(split.parent_id)||[];list.push(split);byParent.set(split.parent_id,list);}
  assert.equal(byParent.get(v.root_id).length,1,"Only Roman controversy may directly leave the root");
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
 const code=app.replace('import {createView} from "./model.mjs";',"").split('\nfetch("./data/graph.jsonld')[0];
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
 const firstNode=flatten(roots.get("graph")).find(e=>e.className.startsWith("node "));
 assert.ok(firstNode.children.some(c=>c.textContent==="Раннехристианская традиция"),"Correct historical root");
 const shortcuts=roots.get("split-index").children.map(e=>e.textContent);
 assert.ok(shortcuts.some(s=>s.includes("Арианский кризис")));
 assert.ok(shortcuts.some(s=>s.includes("Римский спор")));
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
