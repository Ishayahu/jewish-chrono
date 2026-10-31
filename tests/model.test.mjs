import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {evaluate,INITIAL,isAllowed,yearLabel,intersect,shift,normalizeImported,validateScenario} from '../src/model.mjs';
const load=(name)=>JSON.parse(readFileSync(new URL('../data/'+name+'.json',import.meta.url),'utf8'));
const catalog={events:load('events').events,claims:load('claims').claims,constraints:load('constraints').constraints};
const scenario=(overrides={})=>({...INITIAL,...overrides,identity:true});
test('3880 + 3900 + 47 with all links: explicit 27-year contradiction',()=>{
 const r=evaluate(scenario(),catalog);
 assert.equal(r.status,'contradictory');
 assert.deepEqual(r.storyBorn,{min:3880,max:3880});
 assert.deepEqual(r.ageBorn,{min:3853,max:3853});
 assert.equal(r.gap,27);assert.equal(yearLabel(r.predictedAccession),'3927');
 assert.equal(isAllowed(scenario(),catalog),false);
 assert.equal(isAllowed(scenario({strict:false}),catalog),true);
});
test('3880 + 3927 + 47: compatible (computed accession, not a source claim)',()=>{
 const r=evaluate(scenario({accessionClaim:'computed-3927'}),catalog);
 assert.equal(r.status,'consistent');
 assert.equal(yearLabel(r.ageComputed),'47');
 assert.equal(r.rows.find(x=>x.label==='Вступление на престол').kind,'computed-example');
});
test('3901 + 3948 + 47 compatible',()=>{
 const r=evaluate(scenario({akivaClaim:'akiva-3901',accessionClaim:'computed-3948'}),catalog);
 assert.equal(r.status,'consistent');assert.equal(yearLabel(r.emperorBorn),'3901');
});
test('identity not silently assumed, and off means underdetermined',()=>{
 const r=evaluate(scenario({identity:false}),catalog);
 assert.equal(r.status,'underdetermined');assert.equal(r.storyBorn,null);
 assert.equal(yearLabel(r.ageBorn),'3853');
 assert.equal(isAllowed(scenario({identity:false}),catalog),true);
});
test('disabled link does not lock a date merely because the numeric years clash',()=>{
 assert.equal(evaluate(scenario({baby:false}),catalog).status,'underdetermined');
 assert.equal(evaluate(scenario({rabbi:false}),catalog).status,'underdetermined');
 assert.equal(evaluate(scenario({sourceAge:false}),catalog).status,'underdetermined');
 assert.equal(yearLabel(evaluate(scenario({sourceAge:false}),catalog).ageComputed),'20');
});
test('ranges are supported and checked by intersection, not naive inequality',()=>{
 const compatible=scenario({akivaClaim:'custom',akivaCustom:{min:3850,max:3860}});
 const result=evaluate(compatible,catalog);
 assert.equal(result.status,'consistent');assert.deepEqual(result.emperorBorn,{min:3853,max:3853});
 assert.equal(yearLabel(result.akiva),'3850–3860');
 assert.deepEqual(intersect({min:1,max:4},{min:3,max:5}),{min:3,max:4});
 assert.deepEqual(shift({min:3880,max:3901},47),{min:3927,max:3948});
 const incompatible=scenario({akivaClaim:'custom',akivaCustom:{min:3880,max:3901}});
 assert.equal(evaluate(incompatible,catalog).status,'contradictory');
});
test('year zero and negative AM years remain numeric tests; no Gregorian conversion',()=>{
 const r=evaluate(scenario({akivaClaim:'custom',akivaCustom:-1,accessionClaim:'custom',accessionCustom:0,sourceAge:false}),catalog);
 assert.equal(r.status,'underdetermined');assert.equal(r.hasYearZero,true);
 assert.equal(yearLabel(r.akiva),'-1');assert.equal(yearLabel(r.accession),'0');
 assert.ok(validateScenario(scenario({akivaClaim:'custom',akivaCustom:{min:3,max:2}}),catalog));
});
test('exported scenario round-trips; invalid strict imports cannot bypass checks',()=>{
 const s=scenario({accessionClaim:'computed-3927'});
 const wrap={schema:'chronology-scenario-v3',calendar:'AM',scenario:s};
 assert.deepEqual(normalizeImported(wrap,catalog),s);
 assert.throws(()=>normalizeImported({...wrap,scenario:scenario()},catalog),/противоречив/);
 assert.throws(()=>normalizeImported({...wrap,calendar:'CE'},catalog),/формат/);
});
test('dates have source links and stable IDs, while computed options are not source assertions',()=>{
 assert.equal(new Set(catalog.events.map(x=>x.id)).size,catalog.events.length);
 assert.equal(new Set(catalog.claims.map(x=>x.id)).size,catalog.claims.length);
 assert.ok(catalog.claims.find(x=>x.id==='age-47').source.url.startsWith('https://github.com/'));
 assert.ok(!catalog.claims.some(x=>x.id==='computed-3927' || x.id==='computed-3948'));
 const before=JSON.stringify(catalog);evaluate(scenario(),catalog);assert.equal(JSON.stringify(catalog),before);
});
