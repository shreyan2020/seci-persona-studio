const test = require('node:test');
const assert = require('node:assert/strict');
const ts = require('typescript');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const context = { exports: {} };
vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname, '../src/features/biotech-workspace/lib/paper-display.ts'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText, context);
const { paperHeading, paperLink, orderedHighlights } = context.exports;
test('identifier is a source link rather than heading clutter', () => {
  const finding = { citation:'A useful paper. Journal. 2023. DOI: 10.3390/jof9050573', source_ids:{} };
  assert.equal(paperHeading(finding), 'A useful paper. Journal. 2023');
  assert.equal(paperLink(finding), 'https://doi.org/10.3390/jof9050573');
  assert.equal(paperLink({citation:'A paper. PMID: 19100310'}), 'https://pubmed.ncbi.nlm.nih.gov/19100310/');
});
test('highlights are page ordered without mutating persisted selection or within-page order', () => {
  const original = [{page:6,id:'a'}, {page:1,id:'b'}, {page:1,id:'c'}, {page:4,id:'d'}];
  assert.deepEqual(Array.from(orderedHighlights(original), x=>x.id), ['b','c','d','a']);
  assert.deepEqual(original.map(x=>x.id), ['a','b','c','d']);
});
