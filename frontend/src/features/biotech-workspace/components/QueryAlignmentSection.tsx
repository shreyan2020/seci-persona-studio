interface Props {
  focusQuestion: string;
  onFocusQuestionChange: (value: string) => void;
  onSubmitQuery: () => void;
  submittingQuery: boolean;
}

export function QueryAlignmentSection({ focusQuestion, onFocusQuestionChange, onSubmitQuery, submittingQuery }: Props) {
  return <section className="rounded-3xl border border-slate-200 bg-white p-6">
    <h3 className="text-xl font-semibold">What are you investigating?</h3>
    <textarea aria-label="Working question" value={focusQuestion} onChange={e=>onFocusQuestionChange(e.target.value)} rows={5} className="mt-4 w-full rounded-xl border border-slate-200 p-4 text-sm" />
    <div className="mt-4 flex justify-end"><button onClick={onSubmitQuery} disabled={!focusQuestion.trim() || submittingQuery} className="rounded-xl bg-slate-950 px-4 py-3 text-sm font-semibold text-white disabled:opacity-50">{submittingQuery ? 'Preparing research focus…' : 'Choose research focus'}</button></div>
  </section>;
}
