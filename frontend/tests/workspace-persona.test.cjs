const test = require('node:test');
const assert = require('node:assert/strict');
const ts = require('typescript');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const context = { exports: {} };
vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname, '../src/features/biotech-workspace/lib/workspace-persona.ts'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText, context);
const choose = context.exports.workspacePersonaId;
const profiles = [{persona_id: 7, name: 'Process', role: 'Engineer'}, {persona_id: 9, name: 'Literature', role: 'Analyst'}, {persona_id: 3, name: 'Evidence', role: 'Analyst'}];
test('preserves the saved workspace identity', () => assert.equal(choose(profiles, 7), 7));
test('new or invalid assignments choose the same evidence profile regardless of order', () => {
  assert.equal(choose(profiles), 3);
  assert.equal(choose([...profiles].reverse(), 100), 3);
  assert.deepEqual(profiles.map(p => p.persona_id), [7, 9, 3]);
});
test('uses a stable fallback and handles projects without profiles', () => {
  assert.equal(choose([profiles[0], {persona_id: 2, name: 'Cost', role: 'Analyst'}]), 2);
  assert.equal(choose([], 7), '');
});
