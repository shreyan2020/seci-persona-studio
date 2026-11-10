const test = require('node:test');
const assert = require('node:assert/strict');
const ts = require('typescript');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const context = { exports: {} };
vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname, '../src/features/biotech-workspace/lib/query-autosave.ts'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText, context);
const needsSave = context.exports.queryNeedsSave;
const draft = { title: 'Investigation', query: 'Compare experiments', state: { note: 'original', findings: [{ page: 1, quote: 'evidence' }] } };

test('a save response with a new timestamp cannot trigger another save', () => {
  for (let i = 0; i < 20; i++) {
    const response = { ...structuredClone(draft), id: 4, updated_at: `timestamp-${i}` };
    assert.equal(needsSave(response, draft), false);
  }
});

test('JSON key order does not count as an edit; array order and content do', () => {
  const reordered = { ...draft, state: { findings: [{ quote: 'evidence', page: 1 }], note: 'original' } };
  assert.equal(needsSave(reordered, draft), false);
  assert.equal(needsSave(draft, { ...draft, state: { ...draft.state, note: 'edited' } }), true);
  assert.equal(needsSave(draft, { ...draft, query: 'A different question' }), true);
});

test('a completed older save does not hide edits made while it was pending', () => {
  const newer = { ...draft, state: { ...draft.state, note: 'newer edit' } };
  assert.equal(needsSave(draft, newer), true);
  assert.equal(needsSave(newer, newer), false);
  assert.equal(needsSave(undefined, newer), false);
});
