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
  const a=single("HistoricalAtlas");assert.equal(a.schemaVersion,4);checkRef(a.rootPosition);
  const base="https://ishayahu.github.io/jewish-chrono/christianity/data/graph.jsonld#";
  for(const n of records)assert.ok(n["@id"].startsWith(base),n["@id"]);
  const wf=readFileSync(new URL("../.github/workflows/pages.yml",import.meta.url),"utf8");
  assert.ok(!wf.includes("build_christianity_graph"));assert.ok(wf.includes("cp -R src data christianity dist/"));
});
test("every semantic connection is resolvable",()=>{
  const keys=["rootPosition","previousPosition","resultingPositions","relatedResearchProjects","position","inControversy","respondsTo","citedSources","fromClaim","toClaim","relatedClaims"];
  for(const n of records)for(const key of keys)if(n[key]!==undefined)for(const v of [].concat(n[key]))checkRef(v);
});
test("historical positions, questions and evidence are preserved",()=>{
  const v=createView(d);assert.equal(v.nodes.length,3);assert.equal(v.splits.length,1);
  assert.equal(v.splits[0].questions.length,4);assert.equal(v.splits[0].branch_ids.length,2);
  assert.ok(v.splits[0].open_questions.some(x=>x.includes("Адама")));
  assert.equal(ofType("ReasoningLink").length,3);
  assert.ok(ofType("OpenResearchQuestion").length>=6);
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
test("browser view references canonical JSON-LD only",()=>{const app=readFileSync(new URL("../christianity/app.mjs",import.meta.url),"utf8");assert.ok(app.includes('fetch("./data/graph.jsonld")'));assert.ok(!app.includes("splits.json"));});

test("published identifiers pass JSON Schema URI regexp",()=>{const schema=JSON.parse(readFileSync(new URL("../christianity/data/schema.json",import.meta.url),"utf8"));const re=new RegExp(schema.properties["@graph"].items.properties["@id"].pattern);for(const n of records)assert.ok(re.test(n["@id"]),n["@id"]);});

test("Six external projects have an auditable machine access finding",()=>{const p=ofType("Source").filter(x=>x.category==="research_project");assert.equal(p.length,6);const allowed=new Set(["not_documented_publicly","internal_structured_data_only","public_repository_data","claimed_undocumented_api"]);for(const s of p){assert.ok(allowed.has(s.machineAccessStatus));assert.ok(s.machineAccessCheckedAt);assert.ok(s.machineAccessNote);}const cic=p.find(x=>x.label.startsWith("Church in Conversation"));assert.equal(cic.machineAccessStatus,"public_repository_data");assert.ok(cic.dataRepositoryFileUrl.includes("world-census.json"));});
