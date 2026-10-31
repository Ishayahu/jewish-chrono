import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {evaluate,INITIAL,isAllowed,yearLabel,intersect,shift,normalizeImported,validateScenario} from '../src/model.mjs';

const load=name=>JSON.parse(readFileSync(new URL('../data/'+name+'.json',import.meta.url),'utf8'));
const constraintData=load('constraints');
const catalog={events:load('events').events,claims:load('claims').claims,constraints:constraintData.constraints,derivedExamples:constraintData.derivedExamples};
const scenario=(overrides={})=>({...INITIAL,...overrides});

test('two switches only: Rabbi at death of Akiva and Antoninus=emperor contemporary',()=>{
 assert.deepEqual(catalog.constraints.map(x=>x.id).sort(),['antoninus','rabbi']);
 assert.equal(catalog.constraints.find(x=>x.id==='antoninus').lhsEvent,'emperor_birth');
 assert.equal(catalog.constraints.find(x=>x.id==='antoninus').rhsEvent,'rabbi_birth');
 assert.ok(!catalog.events.some(x=>x.id==='antoninus_infant_birth'));
 assert.ok(!('identity' in INITIAL));assert.ok(!('baby' in INITIAL));
});

test('default is a consistent strict scenario, based on an explicitly computed (not attested) date',()=>{
 const r=evaluate(scenario(),catalog);
 assert.equal(r.status,'consistent');
 assert.equal(yearLabel(r.predictedAccession),'3927');
 assert.equal(isAllowed(scenario(),catalog),true);
});

test('3880 + 3900 + 47 with both links: explicit 27-year contradiction',()=>{
 const s=scenario({akivaClaim:'akiva-3880',accessionClaim:'accession-3900'});
 const r=evaluate(s,catalog);
 assert.equal(r.status,'contradictory');
 assert.equal(yearLabel(r.storyBorn),'3880');
 assert.equal(yearLabel(r.ageBorn),'3853');
 assert.equal(r.gap,27);
 assert.equal(isAllowed(s,catalog),false);
 assert.equal(isAllowed({...s,strict:false},catalog),true);
});

test('3880 + 3948 + 47 must be rejected in strict mode with a 21-year discrepancy',()=>{
 const s=scenario({akivaClaim:'akiva-3880',accessionClaim:'computed-3948'});
 const r=evaluate(s,catalog);
 assert.equal(r.status,'contradictory');
 assert.equal(yearLabel(r.storyBorn),'3880');
 assert.equal(yearLabel(r.ageBorn),'3901');
 assert.equal(yearLabel(r.predictedAccession),'3927');
 assert.equal(r.gap,21);
 assert.equal(isAllowed(s,catalog),false);
 assert.equal(isAllowed({...s,strict:false},catalog),true);
});

test('3880 + 3927 + 47 remains compatible',()=>{
 const r=evaluate(scenario({accessionClaim:'computed-3927'}),catalog);
 assert.equal(r.status,'consistent');assert.equal(yearLabel(r.ageComputed),'47');
 assert.equal(r.rows.find(x=>x.label==='Вступление на престол').kind,'computed-example');
});

test('3901 + 3948 + 47 is compatible',()=>{
 const r=evaluate(scenario({akivaClaim:'akiva-3901',accessionClaim:'computed-3948'}),catalog);
 assert.equal(r.status,'consistent');assert.equal(yearLabel(r.emperorBorn),'3901');
});

test('turning off the Antoninus narrative removes both contemporary and identity at once',()=>{
 const r=evaluate(scenario({accessionClaim:'computed-3948',antoninus:false}),catalog);
 assert.equal(r.status,'underdetermined');
 assert.equal(r.storyBorn,null);
 assert.equal(yearLabel(r.ageBorn),'3901');
 assert.equal(isAllowed(scenario({accessionClaim:'computed-3948',antoninus:false}),catalog),true);
});

test('disabling the Rabbi relation or age also leaves the scenario underdetermined',()=>{
 assert.equal(evaluate(scenario({accessionClaim:'computed-3948',rabbi:false}),catalog).status,'underdetermined');
 assert.equal(evaluate(scenario({accessionClaim:'computed-3948',sourceAge:false}),catalog).status,'underdetermined');
 assert.equal(yearLabel(evaluate(scenario({accessionClaim:'computed-3948',sourceAge:false}),catalog).ageComputed),'68');
});

test('3897 yields 3944 when the story and age are both accepted',()=>{
 const s=scenario({akivaClaim:'akiva-3897',accessionClaim:'custom',accessionCustom:3944});
 assert.equal(evaluate(s,catalog).status,'consistent');
 assert.equal(yearLabel(evaluate(s,catalog).predictedAccession),'3944');
});

test('ranges checked by intersection, not naive inequality',()=>{
 const compatible=scenario({akivaClaim:'custom',akivaCustom:{min:3850,max:3860},accessionClaim:'accession-3900'});
 const result=evaluate(compatible,catalog);
 assert.equal(result.status,'consistent');assert.deepEqual(result.emperorBorn,{min:3853,max:3853});
 assert.deepEqual(intersect({min:1,max:4},{min:3,max:5}),{min:3,max:4});
 assert.deepEqual(shift({min:3880,max:3901},47),{min:3927,max:3948});
 assert.equal(evaluate(scenario({akivaClaim:'custom',akivaCustom:{min:3880,max:3901},accessionClaim:'accession-3900'}),catalog).status,'contradictory');
});

test('zero and negative years remain only formal numeric tests',()=>{
 const r=evaluate(scenario({akivaClaim:'custom',akivaCustom:-1,accessionClaim:'custom',accessionCustom:0,sourceAge:false}),catalog);
 assert.equal(r.status,'underdetermined');assert.equal(r.hasYearZero,true);
 assert.equal(yearLabel(r.akiva),'-1');
 assert.ok(validateScenario(scenario({akivaClaim:'custom',akivaCustom:{min:3,max:2}}),catalog));
});

test('v4 scenario export/import and strict validation',()=>{
 const s=scenario();
 const wrap={schema:'chronology-scenario-v4',calendar:'AM',scenario:s};
 assert.deepEqual(normalizeImported(wrap,catalog),s);
 assert.throws(()=>normalizeImported({...wrap,scenario:scenario({accessionClaim:'computed-3948'})},catalog),/противоречив/);
 assert.throws(()=>normalizeImported({...wrap,calendar:'CE'},catalog),/формат/);
});

test('v3 import migrates only the effective combined link: baby AND identity',()=>{
 const legacy={...scenario(),baby:true,identity:false};
 delete legacy.antoninus;
 const without={schema:'chronology-scenario-v3',calendar:'AM',scenario:legacy};
 assert.equal(normalizeImported(without,catalog).antoninus,false);
 legacy.identity=true;
 assert.equal(normalizeImported(without,catalog).antoninus,true);
});

test('dated assertions preserve provenance; computed examples are not source claims',()=>{
 assert.equal(new Set(catalog.events.map(x=>x.id)).size,catalog.events.length);
 assert.equal(new Set(catalog.claims.map(x=>x.id)).size,catalog.claims.length);
 assert.ok(catalog.claims.find(x=>x.id==='age-47').source.url.startsWith('https://jewtex.ru/open/'));
 assert.ok(catalog.claims.every(x=>x.source.url.startsWith('https://jewtex.ru/open/')));
 assert.ok(catalog.constraints.every(x=>x.evidence.url.startsWith('https://jewtex.ru/open/')));
 assert.equal(catalog.claims.find(x=>x.id==='accession-3900').source.url.includes('siman_katan='),true);
 assert.ok(!catalog.claims.some(x=>x.id==='computed-3927'||x.id==='computed-3948'));
 const before=JSON.stringify(catalog);
 evaluate(scenario(),catalog);
 assert.equal(JSON.stringify(catalog),before);
});
