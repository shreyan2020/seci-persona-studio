const test = require('node:test');
const assert = require('node:assert/strict');
const ts = require('typescript');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const context = {exports:{}};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src/features/biotech-workspace/lib/utils.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,context);
const normalize=context.exports.normalizeResearchWorkTemplate;
test('partial saved template restores all collections and preserves paper evidence',()=>{
  const input={initial_query:'Compare experiments',literature_findings:[{id:'paper',citation:'Paper',annotations:[{page:2,quote:'Source'}]}]};
  const result=normalize(input);
  for(const field of ['judgment_calls','validation_tracks','common_gaps','proposal_candidates']) assert.equal(Array.isArray(result[field]),true);
  assert.equal(result.literature_findings[0].annotations[0].quote,'Source');
  assert.equal(result.literature_findings[0].knowns.length,0);
  assert.equal(input.judgment_calls,undefined);
});
test('null collections and missing template are safe and normalization is stable',()=>{
  const result=normalize({judgment_calls:null,validation_tracks:null,literature_findings:null},'Restored question');
  assert.equal(result.initial_query,'Restored question');
  assert.equal(result.judgment_calls.length,0);
  assert.equal(JSON.stringify(normalize(result)),JSON.stringify(result));
  assert.equal(normalize(undefined,'Question').initial_query,'Question');
});
