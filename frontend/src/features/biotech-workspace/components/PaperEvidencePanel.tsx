import { orderedHighlights } from '../lib/paper-display';
import { useState } from 'react';
import type { ResearchFinding } from '../types';

interface Props {
  finding: ResearchFinding;
  onPage: (page: number) => void;
  onNoteChange: (note: string) => void;
  onOpenBoard: () => void;
}

export function PaperEvidencePanel({ finding, onPage, onNoteChange, onOpenBoard }: Props) {
  const [selected, setSelected] = useState(0);
  const passages = orderedHighlights(finding.annotations);
  const index = Math.min(selected, Math.max(0, passages.length - 1));
  const passage = passages[index];
  const button = 'rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-800 disabled:opacity-40';
  function select(next: number) {
    setSelected(next);
    const page = passages[next]?.page;
    if (page) onPage(page);
  }
  return <aside aria-label="Paper evidence" className="overflow-y-auto border-t border-slate-200 bg-white p-5 lg:border-l lg:border-t-0">
    <div className="flex items-center justify-between gap-3"><h2 className="text-lg font-semibold">Highlighted excerpts</h2><span className="text-sm text-slate-500">{passages.length ? `${index + 1} of ${passages.length}` : 'None extracted'}</span></div>
    {passage ? <>
      <button className="mt-4 text-sm font-semibold text-cyan-800 underline" onClick={()=>onPage(passage.page)}>Page {passage.page}</button>
      <blockquote className="mt-3 border-l-2 border-cyan-300 pl-4 text-sm leading-7 text-slate-800">{passage.snippet}</blockquote>

      <div className="mt-5 flex justify-between gap-2"><button className={button} disabled={index===0} onClick={()=>select(index-1)}>Previous</button><button className={button} disabled={index===passages.length-1} onClick={()=>select(index+1)}>Next</button></div>
    </> : <p className="mt-4 text-sm text-slate-600">Read the PDF directly or prepare the paper again to extract passages.</p>}
    <details className="mt-6 border-t border-slate-200 pt-4"><summary className="cursor-pointer text-sm font-semibold">Reading notes</summary>
      <textarea aria-label="Reading notes" value={finding.synthesis_memo || ''} onChange={e=>onNoteChange(e.target.value)} rows={5} className="mt-3 w-full rounded-xl border border-slate-200 p-3 text-sm" placeholder="An observation, exception, or relevant experience…" />
    </details>
    <button className={`${button} mt-6 w-full !bg-slate-950 !text-white`} onClick={onOpenBoard}>Compare in research board</button>
  </aside>;
}
