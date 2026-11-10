import { API_BASE } from '../lib/api-base';
import { useSearchParams } from 'next/navigation';
import { paperHeading, paperLink } from '../lib/paper-display';
import { literatureMatches } from '../lib/literature-matches';
import { useEffect, useState, useRef } from 'react';
import type {
  JudgmentCall,
  ResearchFinding,
  ResearchGap,
  ResearchWorkTemplate,
  ValidationTrack,
} from '@/features/biotech-workspace/types';
import { classNames, normalizeResearchWorkTemplate } from '@/features/biotech-workspace/lib/utils';

interface ResearchWorkTemplateSectionProps {
  workTemplate: ResearchWorkTemplate;
  onWorkTemplateChange: (next: ResearchWorkTemplate) => void;
  onFetchLiterature: () => void;
  fetchingLiterature: boolean;
  onSynthesizeGaps: () => void;
  synthesizingGaps: boolean;
  onRunValidationTrack: (findingId: string, trackId: string) => void;
  runningValidationId?: string | null;
  literatureObjectiveLens?: string | null;
  literatureProcessingSummary?: string | null;
  literatureElicitationQuestions?: string[];
  onPreparePaperPdf?: (finding: ResearchFinding) => void;
  onBuildPaperOntology?: (finding: ResearchFinding) => void;
  preparingPdfFindingId?: string | null;
  buildingPaperOntologyId?: string | null;
  pdfAnnotationStatus?: string | null;
  pdfAnnotationFindingId?: string | null;
  reviewStage: 'review' | 'summary';
  onCompleteReview: (summary: string) => void;
}

function makeId(prefix: string) {
  return `${prefix}_${Math.random().toString(36).slice(2, 10)}`;
}

function splitLines(value: string) {
  return value
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean);
}

function joinLines(values: string[]) {
  return values.join('\n');
}

function cardButtonClass(kind: 'primary' | 'secondary' = 'secondary') {
  return classNames(
    'rounded-2xl px-3 py-2 text-xs font-semibold transition',
    kind === 'primary'
      ? 'border border-slate-900 bg-slate-950 text-white hover:bg-slate-800'
      : 'border border-slate-200 bg-white text-slate-900 hover:bg-slate-50'
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
  rows = 3,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  rows?: number;
}) {
  return (
    <label className="block">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-600">{label}</div>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        rows={rows}
        className="mt-1 w-full rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900"
        placeholder={placeholder}
      />
    </label>
  );
}

function EmptyState({
  title,
  body,
  actionLabel,
  onAction,
}: {
  title: string;
  body?: string;
  actionLabel: string;
  onAction: () => void;
}) {
  return (
    <div className="rounded-2xl border border-dashed border-slate-300 bg-white/75 p-4">
      <div className="text-sm font-semibold text-slate-900">{title}</div>
      {body ? <div className="mt-1 text-sm leading-6 text-slate-600">{body}</div> : null}
      <button onClick={onAction} className={classNames(cardButtonClass(), 'mt-3')}>
        {actionLabel}
      </button>
    </div>
  );
}

function SectionHeader({
  eyebrow,
  title,
  description,
  actionLabel,
  onAction,
}: {
  eyebrow: string;
  title: string;
  description?: string;
  actionLabel: string;
  onAction: () => void;
}) {
  return (
    <div className="flex items-start justify-between gap-3">
      <div>
        <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-600">{eyebrow}</div>
        <div className="mt-1 text-base font-semibold text-slate-950">{title}</div>
        {description ? <div className="mt-1 text-sm leading-6 text-slate-600">{description}</div> : null}
      </div>
      <button onClick={onAction} className={cardButtonClass()}>
        {actionLabel}
      </button>
    </div>
  );
}

function listBlock(title: string, values: string[]) {
  const clean = values.map((item) => item.trim()).filter(Boolean);
  if (!clean.length) {
    return '';
  }
  return [`${title}:`, ...clean.map((item) => `- ${item}`)].join('\n');
}

function reviewedFindingsForSummary(workTemplate: ResearchWorkTemplate) {
  const reviewed = workTemplate.literature_findings.filter((finding) =>
    Boolean(
      (finding.annotation_insights || []).length ||
        (finding.judgment_calls || []).length ||
        (finding.validation_tracks || []).length ||
        finding.synthesis_memo?.trim()
    )
  );
  return reviewed.length ? reviewed : workTemplate.literature_findings;
}

function compactValidationLabel(track: ValidationTrack) {
  const target = track.target?.trim();
  const method = track.method?.trim();
  if (target && method) return `${target} via ${method}`;
  return target || method || '';
}

function validationResultSummary(track: ValidationTrack) {
  const result = track.execution_result || {};
  const resultCount = typeof result.result_count === 'number' ? result.result_count : null;
  const tool = typeof result.tool === 'string' ? result.tool : 'Validation tool';
  const query = typeof result.query === 'string' ? result.query : '';
  if (resultCount !== null) {
    return `${tool} returned ${resultCount} candidate record${resultCount === 1 ? '' : 's'}${query ? ` for "${query}"` : ''}.`;
  }
  const message = typeof result.message === 'string' ? result.message : '';
  return message || 'Validation run captured.';
}

function compileCrossPaperMyView(workTemplate: ResearchWorkTemplate): JudgmentCall {
  const findings = reviewedFindingsForSummary(workTemplate);
  const judgmentStances = findings
    .flatMap((finding, index) =>
      (finding.judgment_calls || []).map((judgment) => `${sourceKey(index)}: ${judgment.stance}`).filter(Boolean)
    )
    .slice(0, 8);
  const gapThemes = workTemplate.common_gaps
    .map((gap) => [gap.theme, gap.next_question].filter(Boolean).join(' -> '))
    .filter(Boolean)
    .slice(0, 6);
  const validationLabels = findings
    .flatMap((finding, index) =>
      (finding.validation_tracks || []).map((track) => `${sourceKey(index)}: ${compactValidationLabel(track)}`).filter(Boolean)
    )
    .slice(0, 6);
  const sourceSignals = findings
    .map((finding, index) => {
      const firstKnown = finding.knowns[0] || finding.relevance || finding.annotation_insights?.[0] || '';
      const firstUnknown = finding.generated_questions?.[0] || finding.unknowns[0] || '';
      return [firstKnown ? `${sourceKey(index)} known: ${firstKnown}` : '', firstUnknown ? `${sourceKey(index)} open: ${firstUnknown}` : '']
        .filter(Boolean)
        .join(' | ');
    })
    .filter(Boolean)
    .slice(0, 8);

  return {
    id: 'cross_paper_my_view',
    stance:
      judgmentStances.join('\n') ||
      gapThemes.join('\n') ||
      sourceSignals.join('\n') ||
      'Cross-paper view is ready to edit once paper-level judgments, gaps, or annotations are captured.',
    rationale:
      [
        sourceSignals.length ? `Evidence signals:\n${sourceSignals.join('\n')}` : '',
        gapThemes.length ? `Recurring gaps:\n${gapThemes.join('\n')}` : '',
      ]
        .filter(Boolean)
        .join('\n\n') || 'Compiled from reviewed literature sources and current summary-stage gap clusters.',
    implication:
      validationLabels.length
        ? `Prioritize proposals that resolve or use these validation paths:\n${validationLabels.join('\n')}`
        : 'Use this cross-paper view to decide which gaps become proposal candidates and which analogies need validation before experiment design.',
  };
}

function sourceKey(index: number) {
  return `S${index + 1}`;
}

function buildLiteratureReviewSummary(
  workTemplate: ResearchWorkTemplate,
  literatureObjectiveLens?: string | null,
  literatureProcessingSummary?: string | null
) {
  const sourceFindings = reviewedFindingsForSummary(workTemplate);
  const paperSummaries = sourceFindings.map((finding, index) => {
    const judgments = (finding.judgment_calls || []).map((item) => item.stance).filter(Boolean);
    const validations = (finding.validation_tracks || [])
      .map((track) => {
        const label = compactValidationLabel(track);
        const result = track.execution_result && Object.keys(track.execution_result).length > 0 ? ` (${validationResultSummary(track)})` : '';
        return label ? `${label}${result}` : '';
      })
      .filter(Boolean);
    const key = sourceKey(index);
    return [
      `${key} - ${finding.citation || 'Untitled literature source'}`,
      listBlock('System annotation notes', finding.annotation_insights || []),
      listBlock('Inferred research questions from conclusion/discussion', finding.generated_questions || []),
      listBlock('Known evidence', finding.knowns),
      listBlock('Open questions / gaps', finding.unknowns),
      finding.relevance ? `Project relevance:\n${finding.relevance}` : '',
      listBlock('User judgments', judgments),
      listBlock('Validation / method or tool paths', validations),
      finding.synthesis_memo ? `Paper memo:\n${finding.synthesis_memo}` : '',
    ]
      .filter(Boolean)
      .join('\n');
  });

  const globalJudgments = workTemplate.judgment_calls
    .map((item) => [item.stance, item.rationale ? `Rationale: ${item.rationale}` : '', item.implication ? `Implication: ${item.implication}` : ''].filter(Boolean).join('\n'))
    .filter(Boolean);
  const globalValidations = workTemplate.validation_tracks
    .map((track) => {
      return compactValidationLabel(track);
    })
    .filter(Boolean);

  return [
    `Literature review summary for query:\n${workTemplate.initial_query || 'No query recorded'}`,
    literatureObjectiveLens ? `Objective-conditioned lens:\n${literatureObjectiveLens}` : '',
    literatureProcessingSummary ? `Search and processing summary:\n${literatureProcessingSummary}` : '',
    paperSummaries.length ? `Reviewed sources:\n\n${paperSummaries.join('\n\n')}` : 'Reviewed sources:\nNo literature sources have been reviewed yet.',
    listBlock('Cross-paper user judgments and boundary conditions', globalJudgments),
    listBlock('Cross-paper validation / method or tool paths', globalValidations),
  ]
    .filter(Boolean)
    .join('\n\n');
}

export function ResearchWorkTemplateSection({
  workTemplate: savedWorkTemplate,
  onWorkTemplateChange,
  onFetchLiterature,
  fetchingLiterature,
  onSynthesizeGaps,
  synthesizingGaps,
  onRunValidationTrack,
  runningValidationId,
  literatureObjectiveLens,
  literatureProcessingSummary,
  literatureElicitationQuestions = [],
  onPreparePaperPdf,
  onBuildPaperOntology,
  preparingPdfFindingId,
  buildingPaperOntologyId,
  pdfAnnotationStatus,
  pdfAnnotationFindingId,
  reviewStage,
  onCompleteReview,
}: ResearchWorkTemplateSectionProps) {
  const workTemplate = normalizeResearchWorkTemplate(savedWorkTemplate);
  const projectId = useSearchParams().get('projectId');
  const currentUploadContext = useRef({projectId, workTemplate, onWorkTemplateChange});
  currentUploadContext.current = {projectId, workTemplate, onWorkTemplateChange};
  const [editingSourceId, setEditingSourceId] = useState('');
  const [uploadStatus, setUploadStatus] = useState('');
  const [uploading, setUploading] = useState(false);
  async function attachPdf(finding: ResearchFinding, file?: File) {
    if (!file || !projectId || uploading) return;
    setUploading(true); setUploadStatus('Uploading PDF…');
    try {
      const body = new FormData(); body.append('file', file);
      const response = await fetch(`${API_BASE}/api/projects/${projectId}/literature/upload`, { method: 'POST', body });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || 'Upload failed');
      const current = currentUploadContext.current;
      if (current.projectId !== projectId) return;
      current.onWorkTemplateChange({...current.workTemplate, literature_findings:current.workTemplate.literature_findings.map(item=>item.id===finding.id ? {...item, source_ids:{...item.source_ids, uploaded_id:result.paper_id}, annotations:[], pdf_reader:undefined} : item)});
      setUploadStatus('PDF attached. Select Review paper to prepare highlights.');
    } catch (error) { setUploadStatus(error instanceof Error ? error.message : 'Upload failed'); }
    finally { setUploading(false); }
  }
  const [activeFindingIndex, setActiveFindingIndex] = useState(0);
  const findingCount = workTemplate.literature_findings.length;
  const activeFinding = findingCount > 0 ? workTemplate.literature_findings[Math.min(activeFindingIndex, findingCount - 1)] : null;
  const activeJudgments = activeFinding?.judgment_calls || [];
  const activeValidationTracks = activeFinding?.validation_tracks || [];
  const summaryFindings = reviewedFindingsForSummary(workTemplate);
  const summaryJudgments = [
    ...workTemplate.judgment_calls,
    ...summaryFindings.flatMap((finding) => finding.judgment_calls || []),
  ].filter((item) => item.stance.trim());
  const summaryValidationTracks = [
    ...workTemplate.validation_tracks,
    ...summaryFindings.flatMap((finding) => finding.validation_tracks || []),
  ].filter((track) => compactValidationLabel(track));
  const literatureReviewSummary =
    workTemplate.synthesis_memo ||
    buildLiteratureReviewSummary(workTemplate, literatureObjectiveLens, literatureProcessingSummary);

  useEffect(() => {
    const lastIndex = Math.max(findingCount - 1, 0);
    if (activeFindingIndex > lastIndex) {
      setActiveFindingIndex(lastIndex);
    }
  }, [activeFindingIndex, findingCount]);

  const setInitialQuery = (value: string) => onWorkTemplateChange({ ...workTemplate, initial_query: value });
  const addLiteratureFinding = () => {
    const nextItem: ResearchFinding = {
      id: makeId('finding'),
      citation: '',
      labels: [],
      knowns: [],
      unknowns: [],
      relevance: '',
      source_ids: {},
      judgment_calls: [],
      validation_tracks: [],
      synthesis_memo: '',
    };
    onWorkTemplateChange({
      ...workTemplate,
      literature_findings: [...workTemplate.literature_findings, nextItem],
    });
    setActiveFindingIndex(workTemplate.literature_findings.length);
  };

  const updateLiteratureFinding = (id: string, patch: Partial<ResearchFinding>) => {
    onWorkTemplateChange({
      ...workTemplate,
      literature_findings: workTemplate.literature_findings.map((item) => (item.id === id ? { ...item, ...patch } : item)),
    });
  };

  const removeLiteratureFinding = (id: string) => {
    const removedIndex = workTemplate.literature_findings.findIndex((item) => item.id === id);
    const nextLength = Math.max(workTemplate.literature_findings.length - 1, 0);
    onWorkTemplateChange({
      ...workTemplate,
      literature_findings: workTemplate.literature_findings.filter((item) => item.id !== id),
    });
    setActiveFindingIndex(Math.min(Math.max(removedIndex, 0), Math.max(nextLength - 1, 0)));
  };

  const addJudgment = () => {
    if (!activeFinding) {
      return;
    }
    const nextItem: JudgmentCall = {
      id: makeId('judgment'),
      stance: '',
      rationale: '',
      implication: '',
    };
    updateLiteratureFinding(activeFinding.id, {
      judgment_calls: [...(activeFinding.judgment_calls || []), nextItem],
    });
  };

  const updateJudgment = (id: string, patch: Partial<JudgmentCall>) => {
    if (!activeFinding) {
      return;
    }
    updateLiteratureFinding(activeFinding.id, {
      judgment_calls: (activeFinding.judgment_calls || []).map((item) => (item.id === id ? { ...item, ...patch } : item)),
    });
  };

  const removeJudgment = (id: string) => {
    if (!activeFinding) {
      return;
    }
    updateLiteratureFinding(activeFinding.id, {
      judgment_calls: (activeFinding.judgment_calls || []).filter((item) => item.id !== id),
    });
  };

  const addValidationTrack = () => {
    if (!activeFinding) {
      return;
    }
    const nextItem: ValidationTrack = {
      id: makeId('validation'),
      target: '',
      method: '',
      questions: [],
      success_signal: '',
    };
    updateLiteratureFinding(activeFinding.id, {
      validation_tracks: [...(activeFinding.validation_tracks || []), nextItem],
    });
  };

  const updateValidationTrack = (id: string, patch: Partial<ValidationTrack>) => {
    if (!activeFinding) {
      return;
    }
    updateLiteratureFinding(activeFinding.id, {
      validation_tracks: (activeFinding.validation_tracks || []).map((item) => (item.id === id ? { ...item, ...patch } : item)),
    });
  };

  const removeValidationTrack = (id: string) => {
    if (!activeFinding) {
      return;
    }
    updateLiteratureFinding(activeFinding.id, {
      validation_tracks: (activeFinding.validation_tracks || []).filter((item) => item.id !== id),
    });
  };

  const addGap = () => {
    const nextGap: ResearchGap = {
      id: makeId('gap'),
      theme: '',
      supporting_signals: [],
      next_question: '',
      priority_note: '',
    };
    onWorkTemplateChange({ ...workTemplate, common_gaps: [...workTemplate.common_gaps, nextGap] });
  };

  const updateGap = (id: string, patch: Partial<ResearchGap>) => {
    onWorkTemplateChange({
      ...workTemplate,
      common_gaps: workTemplate.common_gaps.map((gap) => (gap.id === id ? { ...gap, ...patch } : gap)),
    });
  };

  const removeGap = (id: string) => {
    onWorkTemplateChange({
      ...workTemplate,
      common_gaps: workTemplate.common_gaps.filter((gap) => gap.id !== id),
    });
  };

  const compileMyView = () => {
    const compiled = compileCrossPaperMyView(workTemplate);
    const existing = workTemplate.judgment_calls.some((judgment) => judgment.id === compiled.id);
    onWorkTemplateChange({
      ...workTemplate,
      judgment_calls: existing
        ? workTemplate.judgment_calls.map((judgment) => (judgment.id === compiled.id ? compiled : judgment))
        : [compiled, ...workTemplate.judgment_calls],
    });
  };

  const updateGlobalJudgment = (id: string, patch: Partial<JudgmentCall>) => {
    onWorkTemplateChange({
      ...workTemplate,
      judgment_calls: workTemplate.judgment_calls.map((judgment) => (judgment.id === id ? { ...judgment, ...patch } : judgment)),
    });
  };

  return (
    <div className="relative mt-5 rounded-[1.5rem] border border-slate-200 bg-white/85 p-4">
      {reviewStage === 'review' && (
        <>
          <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-600">Literature search</div>
            </div>
          </div>

          <div className="mt-4 rounded-[1.4rem] border border-slate-200 bg-slate-50 p-4">
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-600">Search question</div>
            </div>
            <textarea
              value={workTemplate.initial_query}
              onChange={(e) => setInitialQuery(e.target.value)}
              rows={4}
              className="mt-3 w-full rounded-[1.25rem] border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900"
              placeholder="Working literature query"
            />
            <div className="mt-3 flex justify-end">
              <button onClick={onFetchLiterature} disabled={fetchingLiterature} className={cardButtonClass('primary')}>
                {fetchingLiterature ? 'Fetching...' : 'Fetch literature'}
              </button>
            </div>


          </div>
        </>
      )}

      {reviewStage === 'summary' ? (
        <section className="mt-4 rounded-[1.5rem] border border-sky-200 bg-[linear-gradient(135deg,rgba(239,246,255,0.96),rgba(255,255,255,0.92))] p-5">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-wide text-sky-800">Final Literature Review</div>
              <div className="mt-1 text-lg font-semibold text-slate-950">Compiled evidence summary</div>
            </div>
          </div>

          <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(360px,0.9fr)]">
            <div className="space-y-3">
              <div className="rounded-[1.25rem] border border-white bg-white/85 p-4">
                <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Evidence Map</div>
                <div className="mt-3 space-y-3">
                  {summaryFindings.length === 0 ? (
                    <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-3 text-sm text-slate-500">
                      No reviewed sources yet.
                    </div>
                  ) : (
                    summaryFindings.map((finding, index) => (
                      <div key={finding.id} className="rounded-2xl border border-slate-200 bg-slate-50 p-3">
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <div className="inline-flex rounded-full bg-slate-950 px-2 py-0.5 text-[10px] font-semibold text-white">
                              {sourceKey(index)}
                            </div>
                            <div className="mt-1 line-clamp-2 text-sm font-semibold leading-5 text-slate-950">
                              {finding.citation || 'Untitled source'}
                            </div>
                          </div>
                          {finding.annotation_insights?.length ? (
                            <span className="rounded-full bg-sky-100 px-2 py-0.5 text-[10px] font-semibold text-sky-900">
                              annotated
                            </span>
                          ) : null}
                        </div>
                        <div className="mt-2 grid gap-2 md:grid-cols-2">
                          {(finding.knowns[0] || finding.relevance) && (
                            <div className="rounded-xl bg-white px-3 py-2 text-xs leading-5 text-slate-700">
                              <span className="font-semibold text-slate-950">Known [{sourceKey(index)}]:</span> {finding.knowns[0] || finding.relevance}
                            </div>
                          )}
                          {finding.unknowns[0] && (
                            <div className="rounded-xl bg-white px-3 py-2 text-xs leading-5 text-slate-700">
                              <span className="font-semibold text-slate-950">Open [{sourceKey(index)}]:</span> {finding.unknowns[0]}
                            </div>
                          )}
                        </div>
                        {(finding.annotation_insights || []).length > 0 && (
                          <div className="mt-2 rounded-xl border border-sky-100 bg-sky-50 px-3 py-2 text-xs leading-5 text-sky-950">
                            <span className="font-semibold">Annotation [{sourceKey(index)}]:</span>{' '}
                            {(finding.annotation_insights || [])[0]}
                          </div>
                        )}
                        {(finding.generated_questions || []).length > 0 && (
                          <div className="mt-2 rounded-xl border border-amber-100 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-950">
                            <span className="font-semibold">Inferred question [{sourceKey(index)}]:</span>{' '}
                            {(finding.generated_questions || [])[0]}
                          </div>
                        )}
                      </div>
                    ))
                  )}
                </div>
              </div>

              <div className="rounded-[1.25rem] border border-white bg-white/85 p-4">
                <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Judgment And Validation</div>
                <div className="mt-3 grid gap-3 lg:grid-cols-2">
                  <div className="rounded-2xl border border-slate-200 bg-slate-50 p-3">
                    <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">User judgments</div>
                    <div className="mt-2 space-y-2">
                      {summaryJudgments.length ? (
                        summaryJudgments.slice(0, 5).map((judgment) => (
                          <div key={judgment.id} className="rounded-xl bg-white px-3 py-2 text-xs leading-5 text-slate-700">
                            {judgment.stance}
                          </div>
                        ))
                      ) : (
                        <div className="text-sm text-slate-500">None captured.</div>
                      )}
                    </div>
                  </div>
                  <div className="rounded-2xl border border-slate-200 bg-slate-50 p-3">
                    <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Tool paths</div>
                    <div className="mt-2 space-y-2">
                      {summaryValidationTracks.length ? (
                        summaryValidationTracks.slice(0, 5).map((track) => (
                          <div key={track.id} className="rounded-xl bg-white px-3 py-2 text-xs leading-5 text-slate-700">
                            {compactValidationLabel(track)}
                          </div>
                        ))
                      ) : (
                        <div className="text-sm text-slate-500">None captured.</div>
                      )}
                    </div>
                  </div>
                </div>
              </div>

              <div className="rounded-[1.25rem] border border-white bg-white/85 p-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Gap Clusters</div>
                    <div className="mt-1 text-sm font-semibold text-slate-950">Editable research gaps</div>
                  </div>
                  <div className="flex flex-wrap justify-end gap-2">
                    <button
                      onClick={onSynthesizeGaps}
                      disabled={synthesizingGaps}
                      className={classNames(cardButtonClass('primary'), 'disabled:cursor-not-allowed disabled:opacity-50')}
                    >
                      {synthesizingGaps ? 'Synthesizing...' : 'Synthesize gaps'}
                    </button>
                    <button onClick={addGap} className={cardButtonClass()}>
                      Add gap
                    </button>
                  </div>
                </div>

                <div className="mt-3 space-y-3">
                  {workTemplate.common_gaps.length === 0 ? (
                    <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-3 text-sm text-slate-500">
                      No gap clusters yet.
                    </div>
                  ) : (
                    workTemplate.common_gaps.map((gap, index) => (
                      <div key={gap.id} className="rounded-2xl border border-slate-200 bg-slate-50 p-3">
                        <div className="flex items-center justify-between gap-3">
                          <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Gap {index + 1}</div>
                          <button onClick={() => removeGap(gap.id)} className="text-xs font-semibold text-slate-500 hover:text-slate-950">
                            Remove
                          </button>
                        </div>
                        <input
                          value={gap.theme}
                          onChange={(event) => updateGap(gap.id, { theme: event.target.value })}
                          className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-950"
                          placeholder="Gap theme"
                        />
                        <textarea
                          value={joinLines(gap.supporting_signals)}
                          onChange={(event) => updateGap(gap.id, { supporting_signals: splitLines(event.target.value) })}
                          rows={3}
                          className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900"
                          placeholder="Supporting signals"
                        />
                        <div className="mt-2 grid gap-2 md:grid-cols-2">
                          <textarea
                            value={gap.next_question}
                            onChange={(event) => updateGap(gap.id, { next_question: event.target.value })}
                            rows={3}
                            className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900"
                            placeholder="Next question"
                          />
                          <textarea
                            value={gap.priority_note}
                            onChange={(event) => updateGap(gap.id, { priority_note: event.target.value })}
                            rows={3}
                            className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900"
                            placeholder="Priority note"
                          />
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>

            <div className="space-y-4">
            <div className="rounded-[1.25rem] border border-emerald-200 bg-[linear-gradient(135deg,rgba(236,253,245,0.95),rgba(255,255,255,0.92))] p-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="text-[11px] font-semibold uppercase tracking-wide text-emerald-800">Cross-Paper View</div>
                  <div className="mt-1 text-sm font-semibold text-slate-950">Your compiled interpretation</div>
                </div>
                <button onClick={compileMyView} className={cardButtonClass('primary')}>
                  Compile my view
                </button>
              </div>
              <div className="mt-3 space-y-3">
                {workTemplate.judgment_calls.length === 0 ? (
                  <div className="rounded-2xl border border-dashed border-emerald-200 bg-white/75 p-3 text-sm text-slate-600">
                    Compile paper-level judgments, gap clusters, and validation paths into a reviewable cross-paper stance.
                  </div>
                ) : (
                  workTemplate.judgment_calls.map((judgment) => (
                    <div key={judgment.id} className="rounded-2xl border border-emerald-100 bg-white/85 p-3">
                      <Field
                        label="Stance"
                        value={judgment.stance}
                        onChange={(value) => updateGlobalJudgment(judgment.id, { stance: value })}
                        placeholder="Cross-paper user view"
                        rows={4}
                      />
                      <Field
                        label="Rationale"
                        value={judgment.rationale}
                        onChange={(value) => updateGlobalJudgment(judgment.id, { rationale: value })}
                        placeholder="Why this view follows from the reviewed papers"
                        rows={4}
                      />
                      <Field
                        label="Planning implication"
                        value={judgment.implication}
                        onChange={(value) => updateGlobalJudgment(judgment.id, { implication: value })}
                        placeholder="What this means for proposal selection"
                        rows={3}
                      />
                    </div>
                  ))
                )}
              </div>
            </div>

            <div className="rounded-[1.25rem] border border-sky-200 bg-white p-4">
              <div className="flex items-center justify-between gap-3">
                <div className="text-[11px] font-semibold uppercase tracking-wide text-sky-800">Editable Narrative</div>
                <div className="rounded-full border border-sky-200 bg-sky-50 px-2 py-0.5 text-[10px] font-semibold text-sky-900">
                  Use [S1], [S2] tags
                </div>
              </div>
              <textarea
                value={workTemplate.synthesis_memo}
                onChange={(event) => onWorkTemplateChange({ ...workTemplate, synthesis_memo: event.target.value })}
                rows={24}
                className="mt-3 w-full rounded-[1.25rem] border border-sky-200 bg-white px-4 py-3 text-sm leading-6 text-slate-900"
                placeholder="Compiled literature review summary..."
              />
            </div>
            </div>
          </div>
        </section>
      ) : reviewStage === 'review' ? (
      <>
      <div className="mt-4">
        <section className="rounded-[1.6rem] border border-slate-200 bg-slate-50 p-5">
          <SectionHeader
            eyebrow="Evidence Library"
            title="Literature findings"
            actionLabel="Add finding"
            onAction={addLiteratureFinding}
          />
          <div className="mt-4 space-y-3">
            {workTemplate.literature_findings.length === 0 ? (
              <EmptyState
                title="No literature findings yet"
                actionLabel="Add first finding"
                onAction={addLiteratureFinding}
              />
            ) : activeFinding ? (
              <>
                <div className="flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-slate-200 bg-white/80 px-3 py-2">
                  <button
                    onClick={() => setActiveFindingIndex((current) => Math.max(current - 1, 0))}
                    disabled={activeFindingIndex <= 0}
                    className={classNames(cardButtonClass(), 'disabled:cursor-not-allowed disabled:opacity-40')}
                  >
                    Previous
                  </button>
                  <div className="text-xs font-semibold uppercase tracking-wide text-slate-600">
                    Finding {Math.min(activeFindingIndex + 1, findingCount)} of {findingCount}
                  </div>
                  <button
                    onClick={() => setActiveFindingIndex((current) => Math.min(current + 1, findingCount - 1))}
                    disabled={activeFindingIndex >= findingCount - 1}
                    className={classNames(cardButtonClass(), 'disabled:cursor-not-allowed disabled:opacity-40')}
                  >
                    Next
                  </button>
                </div>

                <div key={activeFinding.id} className="rounded-[1.4rem] border border-slate-200 bg-white p-5">
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-sm font-semibold text-slate-950">Finding {activeFindingIndex + 1}</div>
                    <div className="flex flex-wrap justify-end gap-2">
                      {onPreparePaperPdf && (
                        <button
                          onClick={() => onPreparePaperPdf(activeFinding)}
                          disabled={Boolean(preparingPdfFindingId)}
                          className={classNames(cardButtonClass(), 'disabled:cursor-not-allowed disabled:opacity-50')}
                        >
                          {preparingPdfFindingId === activeFinding.id ? 'Opening paper…' : 'Review paper'}
                        </button>
                      )}
                      <button onClick={() => removeLiteratureFinding(activeFinding.id)} className={cardButtonClass()}>
                        Remove
                      </button>
                    </div>
                  </div>

                  {pdfAnnotationStatus && pdfAnnotationFindingId === activeFinding.id && (
                    <div role="status" aria-live="polite" className="mt-3 flex items-start gap-3 rounded-xl border border-cyan-200 bg-cyan-50 px-4 py-3 text-sm text-cyan-950">
                      {preparingPdfFindingId === activeFinding.id && <span aria-hidden="true" className="mt-1 h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-cyan-200 border-t-cyan-700" />}
                      <span>{pdfAnnotationStatus}</span>
                    </div>
                  )}

                  <div className="mt-3 rounded-2xl border border-slate-200 bg-slate-50 p-3">
                    <div className="line-clamp-2 text-sm font-semibold leading-6 text-slate-950">
                      {paperHeading(activeFinding)}
                    </div>
                    <div className="mt-2 line-clamp-4 text-sm leading-6 text-slate-700">
                      {activeFinding.relevance ||
                        activeFinding.knowns[0] ||
                        'No summary captured yet.'}
                    </div>
                    {literatureMatches(activeFinding.labels).length > 0 && (
                      <p className="mt-3 text-xs leading-5 text-slate-500">
                        <span className="font-medium">Matches: </span>{literatureMatches(activeFinding.labels).join(' · ')}
                      </p>
                    )}
                  </div>

                  {paperLink(activeFinding) && <a href={paperLink(activeFinding)} target="_blank" rel="noreferrer" className="mt-3 inline-block text-sm text-cyan-800 underline">Open publisher page</a>}
                  {projectId && <label className="ml-4 inline-block cursor-pointer text-sm text-cyan-800 underline">{uploading ? 'Uploading…' : 'Attach PDF'}<input type="file" accept="application/pdf,.pdf" disabled={uploading} className="sr-only" onChange={event=>{void attachPdf(activeFinding,event.target.files?.[0]);event.target.value='';}} /></label>}
                  {uploadStatus && <p role="status" className="mt-2 text-sm text-slate-600">{uploadStatus}</p>}
                  {(!activeFinding.citation || editingSourceId === activeFinding.id) && <div><Field placeholder="Paper title or source link" label="Paper title or source link" value={activeFinding.citation} onChange={value=>{setEditingSourceId(activeFinding.id);updateLiteratureFinding(activeFinding.id,{citation:value});}} /><button className="mt-2 text-sm underline" disabled={!activeFinding.citation.trim()} onClick={()=>setEditingSourceId('')}>Done</button></div>}
                  <div className="mt-4 rounded-2xl border border-slate-200 p-4">
                    <h3 className="text-sm font-semibold">Paper summary</h3>
                    <p className="mt-2 whitespace-pre-wrap text-sm leading-7 text-slate-700">{activeFinding.knowns.join('\n\n') || 'No paper summary available yet.'}</p>
                  </div>
                  {(activeJudgments.length > 0 || (activeFinding.validation_tracks || []).length > 0) && <details className="mt-4"><summary className="cursor-pointer text-sm text-slate-600">Saved review notes</summary>
                  <div className="mt-5 grid gap-4 xl:grid-cols-2">
                    <section className="rounded-[1.25rem] border border-slate-200 bg-slate-50 p-4">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-600">Your View</div>
                          <div className="mt-1 text-sm font-semibold text-slate-950">Judgment for this source</div>
                        </div>
                        <button onClick={addJudgment} className={cardButtonClass()}>
                          Add judgment
                        </button>
                      </div>

                      <div className="mt-4 space-y-3">
                        {activeJudgments.length === 0 ? (
                          <EmptyState
                            title="No judgments for this finding yet"
                            actionLabel="Add first judgment"
                            onAction={addJudgment}
                          />
                        ) : (
                          activeJudgments.map((judgment, index) => (
                            <div key={judgment.id} className="rounded-[1.25rem] border border-slate-200 bg-white p-4">
                              <div className="flex items-center justify-between gap-3">
                                <div className="text-sm font-semibold text-slate-950">Judgment {index + 1}</div>
                                <button onClick={() => removeJudgment(judgment.id)} className={cardButtonClass()}>
                                  Remove
                                </button>
                              </div>

                              <Field
                                label="Stance"
                                value={judgment.stance}
                                onChange={(value) => updateJudgment(judgment.id, { stance: value })}
                                placeholder="Your judgment"
                              />

                              <Field
                                label="Rationale"
                                value={judgment.rationale}
                                onChange={(value) => updateJudgment(judgment.id, { rationale: value })}
                                placeholder="Why do you hold this view?"
                              />

                              <Field
                                label="Implication for the next plan"
                                value={judgment.implication}
                                onChange={(value) => updateJudgment(judgment.id, { implication: value })}
                                placeholder="Planning implication"
                              />
                            </div>
                          ))
                        )}
                      </div>
                    </section>

                    <section className="rounded-[1.25rem] border border-slate-200 bg-slate-50 p-4">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-600">Validation Agenda</div>
                          <div className="mt-1 text-sm font-semibold text-slate-950">Validation for this source</div>
                        </div>
                        <button onClick={addValidationTrack} className={cardButtonClass()}>
                          Add validation
                        </button>
                      </div>

                      <div className="mt-4 space-y-3">
                        {activeValidationTracks.length === 0 ? (
                          <EmptyState
                            title="No validation tracks for this finding yet"
                            actionLabel="Add first validation"
                            onAction={addValidationTrack}
                          />
                        ) : (
                          activeValidationTracks.map((track, index) => (
                            <div key={track.id} className="rounded-[1.25rem] border border-slate-200 bg-white p-4">
                              <div className="flex items-center justify-between gap-3">
                                <div className="text-sm font-semibold text-slate-950">Validation {index + 1}</div>
                                <div className="flex gap-2">
                                  <button
                                    onClick={() => onRunValidationTrack(activeFinding.id, track.id)}
                                    disabled={runningValidationId === track.id}
                                    className={classNames(cardButtonClass(), 'disabled:cursor-not-allowed disabled:opacity-50')}
                                  >
                                    {runningValidationId === track.id ? 'Running...' : 'Run'}
                                  </button>
                                  <button onClick={() => removeValidationTrack(track.id)} className={cardButtonClass()}>
                                    Remove
                                  </button>
                                </div>
                              </div>

                              <Field
                                label="Target"
                                value={track.target}
                                onChange={(value) => updateValidationTrack(track.id, { target: value })}
                                placeholder="Validation target"
                              />

                              <Field
                                label="Method Or Tool Path"
                                value={track.method}
                                onChange={(value) => updateValidationTrack(track.id, { method: value })}
                                placeholder="Database query, modeling, sequence analysis..."
                              />

                              <Field
                                label="Questions to resolve"
                                value={joinLines(track.questions)}
                                onChange={(value) => updateValidationTrack(track.id, { questions: splitLines(value) })}
                                placeholder="One validation question per line"
                                rows={4}
                              />

                              <Field
                                label="Success signal"
                                value={track.success_signal}
                                onChange={(value) => updateValidationTrack(track.id, { success_signal: value })}
                                placeholder="What outcome would make this validation track decision-useful?"
                              />
                              {track.execution_result && Object.keys(track.execution_result).length > 0 && (
                                <div className="mt-3 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-xs leading-5 text-emerald-950">
                                  <div className="font-semibold">Validation result</div>
                                  <div className="mt-1">{validationResultSummary(track)}</div>
                                  {Array.isArray(track.execution_result.results) && track.execution_result.results.length > 0 && (
                                    <div className="mt-2 space-y-2">
                                      {track.execution_result.results.slice(0, 3).map((record, resultIndex) => {
                                        const item = record as Record<string, unknown>;
                                        return (
                                          <div key={`${track.id}-result-${resultIndex}`} className="rounded-lg bg-white/80 px-2 py-1.5">
                                            <div className="font-semibold text-emerald-950">
                                              {[item.accession, item.name || item.id].filter(Boolean).join(' - ')}
                                            </div>
                                            <div className="text-emerald-900">
                                              {[item.organism, item.reviewed ? 'reviewed' : 'unreviewed'].filter(Boolean).join(' | ')}
                                            </div>
                                          </div>
                                        );
                                      })}
                                    </div>
                                  )}
                                </div>
                              )}
                            </div>
                          ))
                        )}
                      </div>
                    </section>
                  </div>

                  </details>}
                  <section className="mt-4 rounded-[1.25rem] border border-slate-200 bg-slate-50 p-4">
                    <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-600">Reading notes</div>
                    <textarea
                      value={activeFinding.synthesis_memo || ''}
                      onChange={(e) => updateLiteratureFinding(activeFinding.id, { synthesis_memo: e.target.value })}
                      rows={5}
                      className="mt-3 w-full rounded-[1.25rem] border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900"
                      placeholder="An observation, exception, or relevant experience…"
                    />
                  </section>
                </div>
              </>
            ) : null}
          </div>
        </section>
      </div>

      {reviewStage === 'review' && workTemplate.literature_findings.length > 0 && (
        <section className="mt-4 rounded-[1.4rem] border border-dashed border-slate-300 bg-white/80 p-5 text-center">
          <div className="text-sm font-semibold text-slate-950">Ready to compile the reviewed literature?</div>
          <button
            onClick={() =>
              onCompleteReview(buildLiteratureReviewSummary(workTemplate, literatureObjectiveLens, literatureProcessingSummary))
            }
            className={classNames(cardButtonClass('primary'), 'mt-4')}
          >
            Finish literature review
          </button>
        </section>
      )}
      </>
      ) : null}

    </div>
  );
}
