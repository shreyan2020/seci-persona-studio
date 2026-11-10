const test = require('node:test');
const assert = require('node:assert/strict');
const ts = require('typescript');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const context = { exports: {} };
vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname, '../src/features/biotech-workspace/lib/literature-matches.ts'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText, context);
const matches = labels => Array.from(context.exports.literatureMatches(labels));
test('legacy search badges produce a concise domain-only summary', () => {
  assert.deepEqual(matches(['crossref','literature fetch','2020','relevance score: 108.32', 'matched terms: production, lipolytica, yarrowia, acid, glucose, for', 'matched phrases: in yarrowia lipolytica']), ['yarrowia lipolytica','glucose']);
});
test('preserves domain phrases, deduplicates casing and does not change saved metadata', () => {
  const labels = ['matched phrases: itaconic acid, Yarrowia lipolytica', 'matched terms: acid, glucose, Glucose, yarrowia, lipolytica'];
  const before = [...labels];
  assert.deepEqual(matches(labels), ['itaconic acid','Yarrowia lipolytica','glucose']);
  assert.deepEqual(labels,before);
});
test('generic or metadata-only labels produce no matches', () => {
  assert.deepEqual(matches(['matched terms: for, production, first, produced','matched phrases: production of, research using','evidence role: background','custom label']), []);
});
