'use client';

import { useState } from 'react';
import { ResearchBoardPanel } from '@/features/biotech-workspace/components/ResearchBoardPanel';
import type { ResearchBoard } from '@/features/biotech-workspace/board-types';

const query = 'Which approach should we investigate next, given our laboratory capabilities?';
const example: ResearchBoard = {
  workspace_key: 'layout-example', decision_key: 'example', query, revision: 1, round: 1,
  status: 'ready', model: 'Illustrative content',
  evidence: [
    { id: 'e1', source_id: 's1', citation: 'Illustrative case A — not a published paper', page: 2, quote: 'The comparison used a controlled bioreactor.', source_sha256: 'example' },
    { id: 'e2', source_id: 's2', citation: 'Illustrative case B — not a published paper', page: 3, quote: 'The comparison used shake flasks.', source_sha256: 'example' },
  ],
  actions: [
    { id: 'a1', label: 'Evaluate cultivation conditions in a controlled bioreactor', evidence_refs: ['e1'], disposition: 'eligible', applied_rule_ids: [] },
    { id: 'a2', label: 'Compare candidate interventions in shake flasks', evidence_refs: ['e2'], disposition: 'eligible', applied_rule_ids: [] },
  ],
  questions: [{ id: 'q1', round: 1, question: 'Can your team access a controlled bioreactor for this investigation?', ownership: 'local_constraint', ownership_rationale: 'Equipment access is a local constraint that determines whether this option is practical.', why_not_retrieve: 'The papers cannot establish your current laboratory access.', action_ids: ['a1'], evidence_refs: ['e1'], source_post_ids: ['p1'], status: 'pending', answer: '', options: [] }],
  posts: [{ id: 'p1', round: 1, role: 'Process perspective', kind: 'perspective', text: 'Check equipment access before prioritizing the controlled-bioreactor option.', caveat: 'This example illustrates the interface, not a scientific recommendation.', evidence_refs: ['e1'], reply_to: null, action_ids: ['a1'] }],
  rules: [], resolution_steps: [{ resolver: 'compare_evidence', reason: 'The example cases use different cultivation settings; their results should not be treated as directly interchangeable.' }], rejected_proposals: [],
  comparison_rows: [
    { id: 'r1', evidence_id: 'e1', cells: { cultivation: { value: 'controlled bioreactor', review: 'unreviewed' } } },
    { id: 'r2', evidence_id: 'e2', cells: { cultivation: { value: 'shake flasks', review: 'unreviewed' } } },
  ],
  experiment_facts: [
    { id:'f1', evidence_id:'e1', dimension:'cultivation', value:'controlled bioreactor', anchors:[], intervention_type:'none', ontology_terms:[{namespace:'OBI',term_id:'OBI:0000011',label:'planned process'}], review:'unreviewed' },
    { id:'f2', evidence_id:'e2', dimension:'cultivation', value:'shake flasks', anchors:[], intervention_type:'none', ontology_terms:[{namespace:'OBI',term_id:'OBI:0000011',label:'planned process'}], review:'unreviewed' },
  ],
  experiment_records: [
    { id:'x1', title:'Controlled-bioreactor setting', category:'cultivation', fact_ids:['f1'], evidence_refs:['e1'], link_anchors:[], link_status:'single_passage', important_differences:['Cultivation differs from another experiment record.'] },
    { id:'x2', title:'Shake-flask setting', category:'cultivation', fact_ids:['f2'], evidence_refs:['e2'], link_anchors:[], link_status:'single_passage', important_differences:['Cultivation differs from another experiment record.'] },
  ],
};
const ignoreChange = () => {};

export function ResearchPreview() {
  const [draft, setDraft] = useState(false);
  const board: ResearchBoard = draft ? { ...example,
    questions: example.questions.map(q=>({...q,status:'answered',answer:'Equipment is unavailable.'})),
    rules: [{ id:'rule1',question_id:'q1',decision_key:'example',statement:'Defer the bioreactor option while equipment is unavailable; revisit when access changes.',scope:query,effect:'avoid',action_ids:['a1'],user_quote:'Equipment is unavailable.',status:'draft' }],
  } : example;
  return <main className="min-h-screen bg-slate-50 p-4 sm:p-8 lg:p-12">
    <div className="mx-auto max-w-6xl">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950">
        <p><strong>Layout example.</strong> Synthetic cases; no project data is changed. Review actions are read-only.</p>
        <button className="rounded-lg border border-amber-300 bg-white px-3 py-2" onClick={()=>setDraft(!draft)}>{draft?'Show pending judgment':'Show draft lesson'}</button>
      </div>
      <ResearchBoardPanel key={String(draft)} workspaceKey="layout-example" explicitState={{query}} previewBoard={board} onBoardChange={ignoreChange} />
    </div>
  </main>;
}
