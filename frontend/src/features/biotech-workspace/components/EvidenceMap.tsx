import { useState, type ReactNode } from 'react';
import type { ResearchBoard, ExperimentFact } from '../board-types';
import { paperHeading } from '../lib/paper-display';

const glossary: Array<[string,string]> = [
  ['Host / strain','The organism and its particular genetic version. Different strains are different experimental contexts.'],
  ['Carbon source','The main carbon input. Glucose, glycerol and waste oil results are kept separate.'],
  ['Substrate / precursor / product','A substrate is consumed; a precursor is upstream of a product. The product is the compound being produced.'],
  ['Pathway engineering','Changing reactions or transport: overexpression, knockout, promoter strength or gene copy number.'],
  ['Flux / burden','Flux is metabolic flow per time; burden is the cellular cost of engineering. Neither is established by a higher titer alone.'],
  ['Cultivation','Medium, batch or fed-batch feeding, vessel, pH control, aeration, agitation and dissolved oxygen (DO).'],
  ['Titer','Product concentration, commonly g/L.'], ['Yield','Product per substrate, with an explicit mass or molar basis.'],
  ['Productivity','Product per volume per time. Maximum and average productivity are different quantities.'],
];
const stages = [
  {title:'Organism & carbon', dims:['host','carbon_source']},
  {title:'What changed', dims:['intervention','comparator']},
  {title:'How it was grown', dims:['cultivation']},
  {title:'What was measured', dims:['titer','yield','productivity','limitation']},
];

export function EvidenceMap({board, selectedId, onSelect, children}: {board: ResearchBoard; selectedId?: string | null; onSelect: (fact: ExperimentFact)=>void; children?: ReactNode}) {
  const [paper,setPaper]=useState('all');
  const [selectedRecord,setSelectedRecord]=useState<string|null>(null);

  const sources=Array.from(new Map(board.evidence.map(e=>[e.source_id,e.citation])).entries());
  const facts=(board.experiment_facts||[]).filter(f=>f.review!=='rejected');
  const records=(board.experiment_records||[]).filter(r=>r.fact_ids.some(id=>facts.some(f=>f.id===id)) && (paper==='all'||r.evidence_refs.some(id=>board.evidence.some(e=>e.id===id&&e.source_id===paper))));
  const titers=records.flatMap(record=>record.fact_ids.map(id=>facts.find(f=>f.id===id)).filter((f): f is ExperimentFact=>Boolean(f&&f.dimension==='titer')).filter(f=>/g\s*\/\s*(L|liter)\b/i.test(f.value)).map(f=>({record,f,value:Number.parseFloat(f.value)}))).filter(x=>Number.isFinite(x.value)&&x.value>=0);
  const maxTiter=Math.max(1,...titers.map(x=>x.value));
  return <section className="mt-5 bg-white rounded-2xl p-5" aria-label="Living evidence map">
    <div className="flex flex-wrap justify-between items-center gap-3"><div><p className="mt-1 text-sm text-slate-600">Select a result or condition to add your laboratory context.</p></div>
      <label className="text-sm min-w-0">Paper <select className="ml-2 max-w-full sm:max-w-sm rounded-lg border p-2" value={paper} onChange={e=>setPaper(e.target.value)}><option value="all">All papers</option>{sources.map(([id,citation])=><option key={id} value={id}>{paperHeading({citation})}</option>)}</select></label></div>
    {!records.length&&<p className="my-5 text-sm">Build experiment records in Evidence & comparison to populate this map.</p>}
    {titers.length>1&&<div className="my-5 rounded-xl bg-slate-50 p-4"><h4 className="font-semibold">Reported titer · g/L</h4><div className="mt-3 space-y-3">{titers.map(({record,f,value})=><button key={record.id+f.id} onClick={()=>{setSelectedRecord(record.id);onSelect(f);}} className="grid w-full items-center gap-3 text-left text-sm sm:grid-cols-[minmax(12rem,1fr)_2fr_8rem]"><span>{record.title}</span><span className="h-3 rounded bg-slate-200"><span className="block h-3 rounded bg-cyan-700" style={{width:`${100*value/maxTiter}%`}} /></span><span className="font-semibold">{f.value}</span></button>)}</div></div>}
    <div className="mt-5 space-y-5">{records.map(record=>{
      const rows=record.fact_ids.map(id=>facts.find(f=>f.id===id)).filter((f):f is ExperimentFact=>Boolean(f));
      const refs=board.evidence.filter(e=>record.evidence_refs.includes(e.id));
      return <article key={record.id} className="border-b border-slate-200 pb-5"><h4 className="font-semibold">{record.title}</h4>
        <p className="mt-1 text-xs text-slate-600">{paperHeading({citation:refs[0]?.citation||'Source unavailable'})} · Pages {Array.from(new Set(refs.map(e=>e.page))).sort((a,b)=>a-b).join(', ')}{record.link_status==='unresolved'?' · Unresolved grouping':''}</p>
        <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-4">{stages.map(stage=><div key={stage.title} className="border-t-2 border-cyan-700 pt-2"><h5 className="text-sm font-semibold text-cyan-900">{stage.title}</h5>
          {rows.filter(f=>stage.dims.includes(f.dimension)).map(f=><button key={f.id} onClick={()=>{setSelectedRecord(record.id);onSelect(f);}} aria-expanded={selectedRecord===record.id&&selectedId===f.id} className="mt-2 block w-full rounded-lg bg-slate-50 p-3 text-left text-sm hover:bg-cyan-50 focus:outline-cyan-700"><span className="block text-xs text-slate-500">{f.dimension.replace('_',' ')}</span>{f.value}</button>)}
          {!rows.some(f=>stage.dims.includes(f.dimension))&&<p className="mt-2 text-sm text-slate-400">Not linked to this record</p>}
        </div>)}</div>
        {(board.comparison_judgments||[]).filter(j=>record.fact_ids.includes(j.row_id)).map(j=><p key={j.id} className="mt-3 rounded-lg bg-cyan-50 p-3 text-sm"><strong>Your context:</strong> {j.statement}</p>)}
        {selectedRecord===record.id && record.fact_ids.includes(selectedId || "") && children}
      </article>;
    })}</div>
    <details className="mt-5 text-sm"><summary className="font-semibold cursor-pointer">Understand the terms</summary><dl className="mt-3 grid gap-4 sm:grid-cols-2">{glossary.map(([term,meaning])=><div key={term}><dt className="font-semibold">{term}</dt><dd className="mt-1 text-slate-600">{meaning}</dd></div>)}</dl></details>
  </section>;
}
