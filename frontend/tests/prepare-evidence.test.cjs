const test = require('node:test');
const assert = require('node:assert/strict');
const ts = require('typescript');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const context = { exports: {} };
vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname, '../src/features/biotech-workspace/lib/prepare-evidence.ts'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText, context);
const { prepareBoardStages } = context.exports;
const base = { board: { revision: 7 }, workspaceKey: 'test', state: { query: 'test' }, isCurrent: () => true, progress: () => {} };

test('stages use the returned revision and persist intermediate progress', async () => {
  const calls = [], saves = [];
  assert.equal(await prepareBoardStages({ ...base, saved: b => saves.push(b.revision), mutate: async (op, payload) => {
    calls.push([op, payload.expected_revision]);
    return { board: { revision: payload.expected_revision + 1 } };
  } }), true);
  assert.deepEqual(calls, [['compare', 7], ['start', 8]]);
  assert.deepEqual(saves, [8, 9]);
});
test('a failed comparison never starts perspective generation', async () => {
  const calls = [];
  await assert.rejects(prepareBoardStages({ ...base, saved: () => assert.fail('must not save'), mutate: async op => {
    calls.push(op); throw new Error('conflict');
  } }), /conflict/);
  assert.deepEqual(calls, ['compare']);
});
test('switching context during a request prevents stale UI writes and subsequent stages', async () => {
  let current = true;
  const calls = [];
  assert.equal(await prepareBoardStages({ ...base, isCurrent: () => current, saved: () => assert.fail('stale write'), mutate: async op => {
    calls.push(op); current = false; return { board: { revision: 8 } };
  } }), false);
  assert.deepEqual(calls, ['compare']);
});
test('a perspective failure preserves the completed comparison', async () => {
  const saves = [];
  await assert.rejects(prepareBoardStages({ ...base, saved: b => saves.push(b.revision), mutate: async op => {
    if (op === 'start') throw new Error('model unavailable');
    return { board: { revision: 8 } };
  } }), /model unavailable/);
  assert.deepEqual(saves, [8]);
});
