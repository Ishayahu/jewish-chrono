#!/usr/bin/env node
// Generated JSON-LD is derived from the canonical splits.json; edit that file, not graph.jsonld.
import {readFileSync,writeFileSync} from "node:fs";
import {fileURLToPath} from "node:url";
const input=new URL("../christianity/data/splits.json",import.meta.url);
const output=new URL("../christianity/data/graph.jsonld",import.meta.url);
const root="https://ishayahu.github.io/jewish-chrono/christianity/";
const iri=(kind,id)=>root+"id/"+kind+"/"+encodeURIComponent(id);
const claimIri=(split,q,branch)=>iri("claim",split+"--"+q+"--"+branch);
export function build(inputData){
 const graph=[];
 for(const n of inputData.nodes)graph.push({"@id":iri("position",n.id),"@type":"DoctrinalPosition",label:n.title,period:n.period,description:n.description});
 for(const s of inputData.sources)graph.push({"@id":iri("source",s.id),"@type":"Source",label:s.title,url:s.url,category:s.category,sourceDescription:s.type,humanReviewStatus:s.human_review_status,editorialCaveat:s.limitations||null});
 for(const split of inputData.splits){
   graph.push({"@id":iri("controversy",split.id),"@type":"Controversy",label:split.title,period:split.period,issue:split.issue,previousPosition:iri("position",split.parent_id),resultingPositions:split.branch_ids.map(id=>iri("position",id)),relatedResearchProjects:(split.secondary_project_ids||[]).map(id=>iri("source",id))});
   for(const q of split.questions)for(const branch of split.branch_ids){
     const a=q.answers[branch];
     graph.push({"@id":claimIri(split.id,q.id,branch),"@type":"PositionClaim",label:q.title,text:a.text,questionId:q.id,position:iri("position",branch),inControversy:iri("controversy",split.id),evidenceStatus:a.status,humanReviewStatus:a.human_review_status,note:a.note||"",citedSources:a.source_ids.map(id=>iri("source",id))});
   }
   for(const edge of split.argument_edges||[])graph.push({"@id":iri("reasoning-link",split.id+"--"+edge.id),"@type":"ReasoningLink",fromClaim:claimIri(split.id,edge.from.question_id,edge.from.branch_id),toClaim:claimIri(split.id,edge.to.question_id,edge.to.branch_id),relationKind:edge.relation,evidenceStatus:edge.status,humanReviewStatus:edge.human_review_status,note:edge.note,citedSources:edge.source_ids.map(id=>iri("source",id))});
   for(const rq of split.research_questions||[])graph.push({"@id":iri("research-question",split.id+"--"+rq.id),"@type":"OpenResearchQuestion",label:rq.question,inControversy:iri("controversy",split.id),relatedClaims:rq.related_claims.map(a=>claimIri(split.id,a.question_id,a.branch_id)),evidenceStatus:rq.status,humanReviewStatus:rq.human_review_status,citedSources:rq.source_ids.map(id=>iri("source",id))});
 }
 return {"@context":{"@vocab":root+"vocab#","label":"http://www.w3.org/2000/01/rdf-schema#label","url":{"@id":"https://schema.org/url","@type":"@id"},"previousPosition":{"@id":root+"vocab#previousPosition","@type":"@id"},"resultingPositions":{"@id":root+"vocab#resultingPositions","@type":"@id"},"relatedResearchProjects":{"@id":root+"vocab#relatedResearchProjects","@type":"@id"},"position":{"@id":root+"vocab#position","@type":"@id"},"inControversy":{"@id":root+"vocab#inControversy","@type":"@id"},"citedSources":{"@id":"http://www.w3.org/ns/prov#wasDerivedFrom","@type":"@id"},"fromClaim":{"@id":root+"vocab#fromClaim","@type":"@id"},"toClaim":{"@id":root+"vocab#toClaim","@type":"@id"},"relatedClaims":{"@id":root+"vocab#relatedClaims","@type":"@id"}},"@graph":graph};
}
const data=JSON.parse(readFileSync(input,"utf8"));
const result=JSON.stringify(build(data),null,2)+"\n";
if(process.argv.includes("--check")){
  if(readFileSync(output,"utf8")!==result){console.error("graph.jsonld is not in sync with splits.json");process.exitCode=1;}
}else writeFileSync(output,result);
