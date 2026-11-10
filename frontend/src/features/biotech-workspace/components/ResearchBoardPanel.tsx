import { useEffect, useRef, useState } from 'react';
import { prepareBoardStages } from '../lib/prepare-evidence';
import { EvidenceComparisonPanel } from './EvidenceComparisonPanel';
import type { ResearchBoard, BoardOperation } from '../board-types';
import { fetchResearchBoard, mutateResearchBoard } from '../lib/api';

interface Props {
  previewBoard?: ResearchBoard;
  workspaceKey: string;
  explicitState: Record<string, unknown>;
  onBoardChange: (board: ResearchBoard | null) => void;
  onPrepareSources?: (progress: (message: string) => void) => Promise<{ state: Record<string, unknown>; notices: string[] }>;
}

const button = 'rounded-xl border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-800 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50';
const resolverLabels: Record<string, string> = { inspect_workspace: 'Inspect project records', search_literature: 'Search literature', run_experiment: 'Measure in an experiment', compare_evidence: 'Compare evidence' };

export function ResearchBoardPanel({ workspaceKey, explicitState, onBoardChange, onPrepareSources, previewBoard }: Props) {
  const [board, setBoard] = useState<ResearchBoard | null>(previewBoard || null);
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(Boolean(previewBoard));
  const [error, setError] = useState('');
  const [accounts, setAccounts] = useState<Record<string, string>>({});
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [replyTo, setReplyTo] = useState('');
  const [reply, setReply] = useState('');
  const [progress, setProgress] = useState('');
  const [notices, setNotices] = useState<string[]>([]);
  const [tab, setTab] = useState<'overview' | 'evidence' | 'discussion'>('evidence');
  const inFlight = useRef(false);
  const activeKey = useRef(workspaceKey);
  activeKey.current = `${workspaceKey}:${String(explicitState.query || '').trim()}`;
  const query = String(explicitState.query || '').replace(/\s+/g, ' ').trim();
  const legacy = Boolean(board && !previewBoard && (board.grounding_version || 0) < 2);
  const stale = legacy || Boolean(board && board.query !== query);

  useEffect(() => {
    if (previewBoard) return;
    let cancelled = false;
    activeKey.current = `${workspaceKey}:${query}`;
    setBoard(null); onBoardChange(null); setLoaded(false); setBusy(inFlight.current);
    setAccounts({}); setEdits({}); setReply(''); setReplyTo(''); setError('');
    setProgress(''); setNotices([]); setTab('evidence');
    fetchResearchBoard(workspaceKey).then((result) => {
      if (!cancelled) { setBoard(result.board); onBoardChange(result.board); setLoaded(true); }
    }).catch((e: Error) => { if (!cancelled) { setError(e.message); setLoaded(true); } });
    return () => { cancelled = true; activeKey.current = ''; };
  }, [workspaceKey, onBoardChange, query, previewBoard]);

  async function act(operation: BoardOperation, values: Record<string, unknown> = {}) {
    if (previewBoard) { setError("This is a read-only saved example. Open your project to save a real review."); return; }
    if (inFlight.current) return;
    inFlight.current = true;
    const requestKey = workspaceKey;
    const requestScope = activeKey.current;
    setBusy(true); setError(''); setProgress(operation === 'compare' ? 'Comparing source passages…' : operation === 'start' ? 'Preparing perspectives and decision options…' : 'Saving your review…');
    try {
      const result = await mutateResearchBoard(operation, { workspace_key: requestKey, expected_revision: board?.revision || 0, ...values });
      if (activeKey.current === requestScope) { setBoard(result.board); onBoardChange(result.board); setReply(''); setReplyTo(''); setProgress('Review saved.'); }
    } catch (e) {
      if (activeKey.current === requestScope) { setError(e instanceof Error ? e.message : 'The board could not be updated.'); setProgress('Update did not finish. Your last saved review is retained.'); }
    } finally { inFlight.current = false; if (activeKey.current) setBusy(false); }
  }

  async function prepare() {
    if (previewBoard) { setError("This is a read-only saved example. Open your project to save a real review."); return; }
    if (inFlight.current) return;
    inFlight.current = true;
    const requestKey = workspaceKey;
    const requestScope = activeKey.current;
    const updateProgress = (message: string) => { if (activeKey.current === requestScope) setProgress(message); };
    setBusy(true); setError(''); setNotices([]);
    try {
      updateProgress('Checking the evidence library…');
      const prepared = onPrepareSources ? await onPrepareSources(updateProgress) : { state: explicitState, notices: [] };
      if (activeKey.current !== requestScope) return;
      setNotices(prepared.notices);
      const completed = await prepareBoardStages({
        board, workspaceKey: requestKey, state: prepared.state,
        isCurrent: () => activeKey.current === requestScope,
        mutate: mutateResearchBoard, progress: updateProgress,
        saved: current => { setBoard(current); onBoardChange(current); },
      });
      if (!completed) return;
      updateProgress('Preparation finished. Review the evidence and any judgments below.');
      setTab('evidence');
    } catch (e) {
      if (activeKey.current === requestScope) { setError(e instanceof Error ? e.message : 'Preparation could not finish.'); updateProgress('Preparation paused. Completed steps are saved.'); }
    } finally { inFlight.current = false; if (activeKey.current) setBusy(false); }
  }

  async function reload() {
    if (previewBoard) { setError("This is a read-only saved example. Open your project to save a real review."); return; }
    if (inFlight.current) return;
    inFlight.current = true;
    const requestKey = workspaceKey;
    const requestScope = activeKey.current;
    setBusy(true);
    try {
      const result = await fetchResearchBoard(requestKey);
      if (activeKey.current === requestScope) { setBoard(result.board); onBoardChange(result.board); setError(''); }
    } catch (e) { if (activeKey.current === requestScope) setError(e instanceof Error ? e.message : 'Reload failed'); }
    finally { inFlight.current = false; if (activeKey.current) setBusy(false); }
  }

  function sources(ids: string[]) {
    const entries = board?.evidence.filter((e) => ids.includes(e.id)) || [];
    return entries.length ? <details className="mt-2 text-xs text-slate-600"><summary className="cursor-pointer font-semibold">Cited excerpts ({entries.length})</summary>
      {entries.map((e) => <blockquote key={e.id} className="mt-2 border-l-2 border-cyan-300 pl-3"><div className="font-medium">{e.citation} · Page {e.page}</div><p className="mt-1">{e.quote}</p></blockquote>)}
    </details> : null;
  }

  return <section className="rounded-3xl border border-cyan-200 bg-slate-50 p-4" aria-label="Research perspective board">
    <div className="flex flex-wrap items-start justify-between gap-4 border-b border-slate-200 pb-5">
      <div><div className="text-xs font-semibold uppercase tracking-widest text-cyan-800">Research overview</div>
        <h2 className="mt-2 text-2xl font-semibold text-slate-950">Review evidence. Choose the next step.</h2>

      </div>
      <button className={`${button} !bg-slate-950 !px-5 !py-3 !text-white`} disabled={Boolean(previewBoard) || busy || !loaded || !query || Boolean(previewBoard)} onClick={prepare}>{busy ? 'Working…' : 'Prepare evidence'}</button>
    </div>
    {(busy || !loaded || progress) && <div role="status" aria-live="polite" className={`sticky top-20 z-10 mt-4 rounded-xl border px-4 py-3 text-sm ${busy ? 'border-cyan-200 bg-cyan-50 text-cyan-900' : 'border-slate-200 bg-white text-slate-600'}`}>
      {busy && <span aria-hidden="true" className="mr-2 inline-block h-2 w-2 animate-pulse rounded-full bg-cyan-600" />}
      {progress || 'Loading saved research…'}
    </div>}
    {error && <p role="alert" className="mt-3 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error} <button className={`${button} ml-2`} disabled={Boolean(previewBoard) || busy} onClick={reload}>Reload saved work</button></p>}
    {!!notices.length && <details className="mt-3 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"><summary className="cursor-pointer font-semibold">Preparation exceptions ({notices.length})</summary>{notices.map((n,i)=><p className="mt-2" key={i}>{n}</p>)}</details>}
    <nav aria-label="Research views" className="mt-5 flex flex-wrap gap-2">{(['overview','evidence','discussion'] as const).map(t=><button key={t} aria-pressed={tab===t} onClick={()=>setTab(t)} className={`${button} ${tab===t ? '!border-cyan-700 !bg-cyan-50 !text-cyan-900' : ''}`}>{t==='overview'?'Overview':t==='evidence'?'Evidence & comparison':'Perspectives & history'}</button>)}</nav>
    {!board && !busy && <div className="mt-5 rounded-2xl border border-dashed border-slate-300 bg-white p-8"><h3 className="text-lg font-semibold">Start with your research question</h3><p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">Prepare evidence to organize your papers and identify the decisions that need your input.</p>{!query && <p className="mt-3 text-sm text-amber-900">Add a working question in the project workspace first.</p>}</div>}
    <div hidden={tab !== 'evidence'}><EvidenceComparisonPanel readOnly={Boolean(previewBoard)} board={legacy ? null : board} busy={busy || !loaded} stale={stale} onAct={act} explicitState={explicitState} /></div>
    {legacy && <p role="alert" className="mt-4 rounded-xl bg-amber-50 p-4 text-sm">Refresh the evidence to update this research board.</p>}
    {board && !legacy && <>

      {stale && <p className="mt-3 rounded-xl bg-amber-50 p-3 text-sm text-amber-900">This board belongs to an earlier question. Prepare evidence for the current question; its old rules will not apply.</p>}
      <div hidden={tab !== 'discussion'}>
      <p className="mt-3 text-xs text-slate-500">Round {board.round} · {board.model} · {new Set(board.evidence.map((e) => e.source_id)).size} distinct source documents · {board.round === 0 ? 'Comparison saved; perspectives not yet prepared' : board.status === 'partial' ? 'Some contributions unavailable' : 'Round finished'}</p>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3"><p className="text-sm text-slate-600">AI perspectives</p><button className={button} disabled={Boolean(previewBoard) || busy || stale} onClick={()=>act('start',{explicit_state:explicitState})}>Refresh perspectives</button></div>
      {!board.posts.some(p => p.round === board.round) && <p className="mt-4 text-sm text-slate-600">No discussion is ready yet. Retry gathering perspectives; your paper comparison remains available.</p>}
      <details open className="mt-4"><summary className="cursor-pointer font-semibold text-slate-700">Agent perspectives and discussion ({board.posts.filter(p=>p.round===board.round).length})</summary><div className="mt-4 grid items-start gap-4 xl:grid-cols-2">
        {board.posts.filter((p) => p.round === board.round).map((post) => <article key={post.id} id={post.id} className={`rounded-2xl border bg-white p-4 ${post.kind === 'challenge' ? 'border-amber-200' : 'border-slate-200'}`}>
          <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="text-sm font-semibold text-slate-950">{post.role}</h3><span className="text-xs text-slate-500">{post.kind === 'challenge' ? 'Challenge' : post.kind === 'user' ? 'User account' : 'Proposed interpretation'}</span></div>
          {post.reply_to && <a className="mt-1 block text-xs text-cyan-800 underline" href={`#${post.reply_to}`}>In reply to {board.posts.find((p) => p.id === post.reply_to)?.role || 'earlier post'}</a>}
          <p className="mt-2 whitespace-pre-wrap text-base leading-7 text-slate-800">{post.text}</p>
          {post.caveat && <p className="mt-2 text-sm text-amber-900">Limit: {post.caveat}</p>}
          {sources(post.evidence_refs)}
          <button className={`${button} mt-3`} disabled={Boolean(previewBoard) || busy || stale} onClick={() => setReplyTo(post.id)}>Reply with context</button>
          {replyTo === post.id && <div className="mt-2"><textarea aria-label="Reply to perspective" value={reply} onChange={(e) => setReply(e.target.value)} className="min-h-24 w-full rounded-xl border p-3 text-sm" placeholder="Add an observation, constraint, or previous experience." /><button className={button} disabled={Boolean(previewBoard) || busy || !reply.trim()} onClick={() => act('comment', { reply_to: post.id, text: reply })}>Post reply</button></div>}
        </article>)}
      </div>
      </details>
      {board.posts.some((p) => p.round < board.round) && <details className="mt-3 text-sm"><summary className="cursor-pointer text-slate-600">Earlier rounds</summary>{board.posts.filter((p) => p.round < board.round).map((p) => <div id={p.id} key={p.id} className="mt-2 rounded-xl bg-white p-3"><strong>{p.role} · Round {p.round}</strong><p>{p.text}</p>{sources(p.evidence_refs)}</div>)}</details>}
      </div>
      <div hidden={tab !== 'overview'}>
      <div className="mt-5 grid gap-3 sm:grid-cols-3">{[
        [new Set(board.evidence.map(e=>e.source_id)).size, 'Source documents'],
        [board.actions.filter(a=>a.disposition==='eligible').length, 'Eligible options'],
        [board.questions.filter(q=>q.status==='pending').length + board.rules.filter(r=>r.status==='draft').length, 'Judgments & draft lessons'],
      ].map(([count,label])=><div key={label} className="rounded-2xl border border-slate-200 bg-white p-4"><p className="text-3xl font-semibold text-slate-950">{count}</p><p className="mt-1 text-sm text-slate-500">{label}</p></div>)}</div>
      <div className="mt-5 space-y-3"><h3 className="font-semibold text-slate-950">Needs your judgment</h3>
        {board.rules.some(r=>r.status==='draft') && <p className="text-sm text-slate-600">Draft lesson ready for review.</p>}
        {!board.rules.some(r=>r.status==='draft') && !board.questions.some((q) => q.status === 'pending') && <p className="text-sm text-slate-600">No pending judgments.</p>}
        {board.questions.filter((q) => q.status === 'pending' && !board.rules.some(r=>r.status==='draft')).slice(0, 1).map((q) => <div key={q.id} className="rounded-2xl border border-violet-200 bg-white p-4">
          <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-violet-800">{board.questions.filter(item=>item.status==='pending').length} pending</div><h4 className="text-lg font-semibold leading-7">{q.question}</h4><div className="mt-3 rounded-xl bg-slate-50 p-3 text-sm"><strong>Affected options</strong><ul className="mt-1 list-inside list-disc">{board.actions.filter(a=>q.action_ids.includes(a.id)).map(a=><li key={a.id}>{a.label}</li>)}</ul></div><details className="mt-3 text-sm text-slate-600"><summary className="cursor-pointer">Why this matters</summary><p className="mt-2">{q.ownership_rationale}</p><p className="mt-2">{q.why_not_retrieve}</p></details>
          <div className="mt-2 flex flex-wrap gap-2">{q.source_post_ids.map((id) => <a className="text-xs text-cyan-800 underline" key={id} onClick={()=>setTab('discussion')} href={`#${id}`}>From {board.posts.find((p) => p.id === id)?.role || 'board post'}</a>)}</div>
          {sources(q.evidence_refs)}
          <div className="mt-3 flex flex-wrap gap-2"><button className={button} disabled={Boolean(previewBoard) || busy || stale} onClick={() => act('answer', { question_id: q.id, answer_type: 'allow' })}>Keep these options</button><button className={button} disabled={Boolean(previewBoard) || busy || stale} onClick={() => act('answer', { question_id: q.id, answer_type: 'avoid' })}>Exclude these options</button><button className={button} disabled={Boolean(previewBoard) || busy || stale} onClick={() => act('answer', { question_id: q.id, answer_type: 'unsure' })}>Decide later</button></div>
          <details className="mt-3"><summary className="cursor-pointer text-xs font-semibold text-slate-600">Add experience</summary><label className="mt-3 block text-xs font-semibold text-slate-700">What happened, and when would this lesson apply?</label>
          <textarea aria-label="Past case and limits" value={accounts[q.id] || ''} onChange={(e) => setAccounts({ ...accounts, [q.id]: e.target.value })} className="mt-1 min-h-24 w-full rounded-xl border p-3 text-sm" />
          <button className={`${button} mt-2`} disabled={Boolean(previewBoard) || busy || stale || (accounts[q.id] || '').trim().length < 12} onClick={() => act('answer', { question_id: q.id, answer_type: 'experience', text: accounts[q.id] })}>Propose a lesson from this case</button></details>
        </div>)}
        {board.questions.filter((q) => ['answered', 'deferred'].includes(q.status)).map((q) => <details key={q.id} className="rounded-xl border p-3 text-xs text-slate-600"><summary className="cursor-pointer">{q.status === 'deferred' ? 'Deferred' : 'Answered'}: {q.question}</summary><p className="mt-2">{q.answer}</p></details>)}
      </div>
      {board.rules.some((r) => ['draft', 'confirmed'].includes(r.status)) && <div className="mt-5 space-y-3"><h3 className="font-semibold">Lessons for this decision</h3>{board.rules.filter((r) => ['draft', 'confirmed'].includes(r.status)).map((r) => <div key={r.id} className="rounded-2xl border border-emerald-200 bg-white p-4">
        <div className="text-xs font-semibold uppercase text-emerald-900">{r.status === 'draft' ? 'Draft' : 'Confirmed'} · {r.effect === 'avoid' ? 'Excludes these options' : 'Keeps these options'}</div>
        <p className="mt-2 text-xs text-slate-500">Applies to: {r.scope}</p>
        <ul className="mt-2 list-inside list-disc text-sm">{board.actions.filter((a) => r.action_ids.includes(a.id)).map((a) => <li key={a.id}>{a.label}</li>)}</ul>
        <blockquote className="my-2 border-l-2 pl-3 text-sm text-slate-600">Your account: {r.user_quote}</blockquote>
        {r.status === 'draft' ? <><textarea aria-label="Edit draft lesson" className="min-h-20 w-full rounded-xl border p-3 text-sm" value={edits[r.id] ?? r.statement} onChange={(e) => setEdits({ ...edits, [r.id]: e.target.value })} /><div className="flex gap-2"><button className={button} disabled={Boolean(previewBoard) || busy || stale} onClick={() => act('rule', { rule_id: r.id, operation: 'confirm', statement: edits[r.id] ?? r.statement })}>Confirm and apply</button><button className={button} disabled={Boolean(previewBoard) || busy || stale} onClick={() => act('rule', { rule_id: r.id, operation: 'reject' })}>Reject draft</button></div></> : <><p className="my-2 text-sm">{r.statement}</p><button className={button} disabled={Boolean(previewBoard) || busy || stale} onClick={() => act('rule', { rule_id: r.id, operation: 'revoke' })}>Undo application</button></>}
      </div>)}</div>}
      <div className="mt-5"><h3 className="font-semibold">Decision summary</h3><div className="mt-2 space-y-2">{board.actions.map((a) => <div key={a.id} className="rounded-xl border bg-white p-3 text-sm"><strong className={a.disposition === 'excluded' ? 'text-rose-800' : 'text-slate-800'}>{a.disposition === 'excluded' ? 'Excluded' : 'Eligible'}:</strong> {a.label}{sources(a.evidence_refs)}{a.applied_rule_ids.length > 0 && <p className="mt-1 text-xs text-emerald-800">Applied lesson: {board.rules.filter((r) => a.applied_rule_ids.includes(r.id)).map((r) => r.statement).join('; ')}</p>}</div>)}</div>{board.actions.length > 0 && board.actions.every((a) => a.disposition === 'excluded') && <p className="mt-2 text-sm text-amber-900">All proposed actions are excluded. Reframe the decision or gather alternatives.</p>}</div>
      {board.resolution_steps.length > 0 && <div className="mt-5"><h3 className="font-semibold">Resolve outside this conversation</h3>{board.resolution_steps.map((step, i) => <p key={i} className="mt-2 text-sm text-slate-700"><strong>{resolverLabels[step.resolver] || step.resolver}:</strong> {step.reason}</p>)}</div>}
      </div>
      {board.rejected_proposals.length > 0 && <details className="mt-4 text-xs text-amber-900"><summary className="cursor-pointer">Review details</summary>{board.rejected_proposals.map((reason, i) => <p className="mt-1" key={i}>{reason}</p>)}</details>}
    </>}
  </section>;
}
