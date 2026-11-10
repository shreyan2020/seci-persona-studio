'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useEffect, useMemo, useRef, useState } from 'react';

import { ModeBackdrop } from '@/features/biotech-workspace/components/ModeBackdrop';
import { ObjectiveClusteringSection } from '@/features/biotech-workspace/components/ObjectiveClusteringSection';
import { OntologyPanel } from '@/features/biotech-workspace/components/OntologyPanel';
import { ProjectLandingShell } from '@/features/biotech-workspace/components/ProjectLandingShell';
import { ProjectOverview } from '@/features/biotech-workspace/components/ProjectOverview';
import { PaperEvidencePanel } from '@/features/biotech-workspace/components/PaperEvidencePanel';
import { workspacePersonaId } from '@/features/biotech-workspace/lib/workspace-persona';
import { queryNeedsSave } from '@/features/biotech-workspace/lib/query-autosave';
import { QueryAlignmentSection } from '@/features/biotech-workspace/components/QueryAlignmentSection';
import { LiteratureSurveySection } from '@/features/biotech-workspace/components/LiteratureSurveySection';
import { ResearchBoardPanel } from '@/features/biotech-workspace/components/ResearchBoardPanel';
import type { ResearchBoard } from '@/features/biotech-workspace/board-types';
import { fetchResearchBoard } from '@/features/biotech-workspace/lib/api';
import { WorkflowStateSidebar } from '@/features/biotech-workspace/components/WorkflowStateSidebar';
import { WorkspaceHeader } from '@/features/biotech-workspace/components/WorkspaceHeader';
import {
  API_BASE,
  buildPaperOntology,
  clusterObjectives,
  createProject,
  createProjectQuery,
  deleteProject,
  diagnosticsExportUrl,
  fetchExecutionRun,
  fetchLatestExecutionRun,
  fetchStoredOntology,
  logProjectEvent,
  fetchProjectLiterature,
  fetchProjectQueries,
  fetchProjects,
  fetchWorkspaceMemory,
  fetchWorkspaceState,
  preparePaperPdf,
  reviewProjectOntologyItem,
  runValidationTrack,
  saveWorkspaceMemory,
  saveWorkspaceState,
  syncProjectOntology,
  synthesizeLiteratureGaps,
  updateProjectQuery,
} from '@/features/biotech-workspace/lib/api';
import {
  classNames,
  createEmptyResearchWorkTemplate,
  normalizeResearchWorkTemplate,
  defaultFocusQuestion,
  getModeVisualKey,
  inferObjectiveFrame,
} from '@/features/biotech-workspace/lib/utils';
import type {
  AdaptiveElicitationSession,
  AgenticPlan,
  JudgmentCall,
  ObjectiveCluster,
  OntologyPreviewResponse,
  OntologyUsageTrace,
  ProjectExecutionEvent,
  ProjectExecutionRun,
  Project,
  ProjectFormState,
  ProjectQuerySession,
  ResearchFinding,
  ResearchWorkTemplate,
  StatusState,
  TacitElicitationQuestion,
  TacitMemoryItem,
} from '@/features/biotech-workspace/types';

type FlowStep = 'collaborator' | 'query' | 'objective' | 'workspace';
type LiteratureReviewStage = 'review' | 'summary';
type DesktopOpenPathResult = { ok: boolean; error?: string };
type PdfViewerState = {
  findingId: string;
  title: string;
  url: string;
  annotatedPath?: string | null;
} | null;
type ManualObjectiveForm = {
  title: string;
  subtitle: string;
  definition: string;
  signals: string;
  facet_questions: string;
  exemplar_answer: string;
};

function stableFindingKey(finding: ResearchFinding) {
  const ids = finding.source_ids || {};
  const sourceKey = ids.doi || ids.pmid || ids.pmcid || ids.pdf_url || finding.citation || finding.id;
  return sourceKey.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '').slice(0, 80) || `finding_${Date.now()}`;
}

function uniqueFindingId(finding: ResearchFinding, existingIds: Set<string>, index: number) {
  const base = stableFindingKey(finding) || `finding_${index + 1}`;
  let candidate = `finding_${base}`;
  let suffix = 2;
  while (existingIds.has(candidate)) {
    candidate = `finding_${base}_${suffix}`;
    suffix += 1;
  }
  existingIds.add(candidate);
  return candidate;
}


const emptyManualObjective: ManualObjectiveForm = {
  title: '',
  subtitle: '',
  definition: '',
  signals: '',
  facet_questions: '',
  exemplar_answer: '',
};

declare global {
  interface Window {
    desktopApp?: {
      openPath?: (targetPath: string) => Promise<DesktopOpenPathResult>;
    };
  }
}

function compactStatus(status: StatusState | null) {
  if (!status) return null;
  const message = status.message || '';
  if (/search_literature returned/i.test(message)) {
    return { ...status, message: 'Literature library updated.' };
  }
  if (/Fetching literature with/i.test(message)) {
    return { ...status, message: 'Searching literature...' };
  }
  if (/Fetched \d+ new literature/i.test(message)) {
    return { ...status, message: 'Literature evidence refreshed.' };
  }
  return status;
}

function InlineWorkspaceStatus({ status }: { status: StatusState | null }) {
  const visibleStatus = compactStatus(status);
  if (!visibleStatus) return null;
  return (
    <div
      className={classNames(
        'rounded-2xl border px-4 py-3 text-sm shadow-sm',
        visibleStatus.type === 'success' && 'border-emerald-200 bg-emerald-50 text-emerald-900',
        visibleStatus.type === 'error' && 'border-rose-200 bg-rose-50 text-rose-900',
        visibleStatus.type === 'info' && 'border-sky-200 bg-sky-50 text-sky-900'
      )}
    >
      {visibleStatus.message}
    </div>
  );
}

function BiotechProjectWorkspaceContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const routeProjectIdRaw = searchParams.get('projectId') || '';
  const routePersonaIdRaw = searchParams.get('personaId') || '';
  const routeQueryIdRaw = searchParams.get('queryId') || '';
  const parsedRouteProjectId = Number(routeProjectIdRaw);
  const parsedRoutePersonaId = Number(routePersonaIdRaw);
  const parsedRouteQueryId = Number(routeQueryIdRaw);
  const routeProjectId = routeProjectIdRaw && Number.isFinite(parsedRouteProjectId) ? parsedRouteProjectId : '';
  const routePersonaId = routePersonaIdRaw && Number.isFinite(parsedRoutePersonaId) ? parsedRoutePersonaId : '';
  const routeQueryId = routeQueryIdRaw && Number.isFinite(parsedRouteQueryId) ? parsedRouteQueryId : '';

  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<number | ''>('');
  const [selectedPersonaId, setSelectedPersonaId] = useState<number | ''>('');
  const [activeFlowStep, setActiveFlowStep] = useState<FlowStep>('query');
  const [focusQuestion, setFocusQuestion] = useState('');
  const [objectiveClusters, setObjectiveClusters] = useState<ObjectiveCluster[]>([]);
  const [selectedObjectiveId, setSelectedObjectiveId] = useState('');
  const [globalQuestions, setGlobalQuestions] = useState<string[]>([]);
  const [objectiveAnswers, setObjectiveAnswers] = useState<Record<string, string>>({});
  const [globalQuestionAnswers, setGlobalQuestionAnswers] = useState<Record<string, string>>({});
  const [clarifyingAnswers, setClarifyingAnswers] = useState<Record<string, string>>({});
  const [reasoningNotes, setReasoningNotes] = useState('');
  const [researchWorkTemplate, setResearchWorkTemplate] = useState<ResearchWorkTemplate>(createEmptyResearchWorkTemplate());
  const [agenticPlan, setAgenticPlan] = useState<AgenticPlan | null>(null);
  const [executionRun, setExecutionRun] = useState<ProjectExecutionRun | null>(null);
  const [executionEvents, setExecutionEvents] = useState<ProjectExecutionEvent[]>([]);
  const [selectedPlanStepId, setSelectedPlanStepId] = useState('');
  const [loadingProjects, setLoadingProjects] = useState(true);
  const [creatingProject, setCreatingProject] = useState(false);
  const [deletingProjectId, setDeletingProjectId] = useState<number | null>(null);
  const [loadingObjectiveClusters, setLoadingObjectiveClusters] = useState(false);
  const [fetchingLiterature, setFetchingLiterature] = useState(false);
  const [synthesizingGaps, setSynthesizingGaps] = useState(false);
  const [runningValidationId, setRunningValidationId] = useState<string | null>(null);
  const [literatureObjectiveLens, setLiteratureObjectiveLens] = useState<string | null>(null);
  const [literatureProcessingSummary, setLiteratureProcessingSummary] = useState<string | null>(null);
  const [literatureElicitationQuestions, setLiteratureElicitationQuestions] = useState<string[]>([]);
  const [literatureElicitationAnswers, setLiteratureElicitationAnswers] = useState<Record<string, string>>({});
  const [literatureReviewStage, setLiteratureReviewStage] = useState<LiteratureReviewStage>('review');
  const [preparingPdfFindingId, setPreparingPdfFindingId] = useState<string | null>(null);
  const [buildingPaperOntologyId, setBuildingPaperOntologyId] = useState<string | null>(null);
  const [pdfAnnotationFindingId, setPdfAnnotationFindingId] = useState<string | null>(null);
  const [pdfAnnotationStatus, setPdfAnnotationStatus] = useState<string | null>(null);
  const [pdfViewer, setPdfViewer] = useState<PdfViewerState>(null);
  const [memoryDrawerOpen, setMemoryDrawerOpen] = useState(false);
  const [projectQueries, setProjectQueries] = useState<ProjectQuerySession[]>([]);
  const [activeQueryId, setActiveQueryId] = useState<number | ''>('');
  const [hydratedQueryKey, setHydratedQueryKey] = useState('');
  const [queriesLoadedProjectId, setQueriesLoadedProjectId] = useState<number | null>(null);
  const querySavesInFlight = useRef(new Set<string>());
  const [newQueryText, setNewQueryText] = useState('');
  const [showNewQueryForm, setShowNewQueryForm] = useState(false);
  const [creatingQuery, setCreatingQuery] = useState(false);
  const [showManualObjectiveForm, setShowManualObjectiveForm] = useState(false);
  const [manualObjective, setManualObjective] = useState<ManualObjectiveForm>(emptyManualObjective);
  const [loadingWorkspace, setLoadingWorkspace] = useState(false);
  const [objectivePickerCollapsed, setObjectivePickerCollapsed] = useState(false);
  const [workspaceReadyForSave, setWorkspaceReadyForSave] = useState(false);
  const [researchBoard, setResearchBoard] = useState<ResearchBoard | null>(null);
  const [tacitState, setTacitState] = useState<TacitMemoryItem[]>([]);
  const [tacitElicitationQuestions, setTacitElicitationQuestions] = useState<TacitElicitationQuestion[]>([]);
  const [tacitElicitationAnswers, setTacitElicitationAnswers] = useState<Record<string, string>>({});
  const [handoffSummary, setHandoffSummary] = useState('');
  const [memoryStatus, setMemoryStatus] = useState('not saved yet');
  const [adaptiveElicitationSession, setAdaptiveElicitationSession] = useState<AdaptiveElicitationSession | null>(null);
  const [ontologyPreview, setOntologyPreview] = useState<OntologyPreviewResponse | null>(null);
  const [ontologyStatus, setOntologyStatus] = useState('not mapped yet');
  const [activeOntologyTrace, setActiveOntologyTrace] = useState<OntologyUsageTrace | null>(null);
  const [loadingOntology, setLoadingOntology] = useState(false);
  const [exportingDiagnostics, setExportingDiagnostics] = useState(false);
  const [status, setStatus] = useState<StatusState | null>(null);
  const querySectionRef = useRef<HTMLDivElement | null>(null);
  const objectiveSectionRef = useRef<HTMLDivElement | null>(null);
  const draftSectionRef = useRef<HTMLDivElement | null>(null);
  const researchDialogRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (!memoryDrawerOpen) return;
    const previousFocus = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    researchDialogRef.current?.querySelector<HTMLButtonElement>('button')?.focus();
    const trapFocus = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { setMemoryDrawerOpen(false); return; }
      if (event.key !== 'Tab') return;
      const controls = Array.from(researchDialogRef.current?.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], input:not(:disabled), textarea:not(:disabled), select:not(:disabled), summary, [tabindex="0"]') || []).filter(el => el.getClientRects().length > 0);
      const first = controls[0], last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    };
    document.addEventListener('keydown', trapFocus);
    return () => { document.body.style.overflow = previousOverflow; document.removeEventListener('keydown', trapFocus); previousFocus?.focus(); };
  }, [memoryDrawerOpen]);
  const [form, setForm] = useState<ProjectFormState>({
    name: '',
    end_product: '',
    target_host: 'Saccharomyces cerevisiae',
    project_goal: '',
    raw_material_focus: '',
    notes: '',
  });

  const selectedProject =
    selectedProjectId === '' ? null : projects.find((project) => project.id === Number(selectedProjectId)) || null;
  const selectedPersona =
    selectedProject && selectedPersonaId !== ''
      ? selectedProject.personas.find((persona) => persona.persona_id === Number(selectedPersonaId)) || null
      : null;

  useEffect(() => {
    setActiveOntologyTrace(null);
  }, [selectedProject?.id]);
  const selectedObjective = objectiveClusters.find((objective) => objective.id === selectedObjectiveId) || null;
  const pdfViewerFinding = pdfViewer
    ? researchWorkTemplate.literature_findings.find((finding) => finding.id === pdfViewer.findingId) || null
    : null;
  const activeProjectQuery =
    activeQueryId === '' ? null : projectQueries.find((query) => query.id === Number(activeQueryId)) || null;
  const workingQuestionText = focusQuestion.trim() || selectedProject?.project_goal || '';
  const selectedObjectiveLens = selectedObjective
    ? [selectedObjective.title, selectedObjective.definition, ...selectedObjective.signals].join(' ')
    : '';
  const activeObjectiveFrame = selectedObjective ? inferObjectiveFrame(selectedObjectiveLens) : null;
  const currentModeTitle = selectedObjective ? selectedObjective.title : 'Neutral workspace';
  const modeVisualKey = selectedObjective ? getModeVisualKey(selectedObjective.title) : 'general';

  const workspaceMemoryKey = useMemo(() => {
    const parts = [
      selectedProject?.scope_id || (selectedProject ? `project-${selectedProject.id}` : 'no-project'),
      activeQueryId === '' ? 'no-query' : `query-${activeQueryId}`,
      selectedPersonaId === '' ? 'no-persona' : `persona-${selectedPersonaId}`,
    ];
    return parts.join('__').toLowerCase().replace(/[^a-z0-9_-]+/g, '-');
  }, [selectedProject?.id, selectedProject?.scope_id, activeQueryId, selectedPersonaId]);
  const activeAdaptiveElicitationSession =
    adaptiveElicitationSession?.workspace_key === workspaceMemoryKey ? adaptiveElicitationSession : null;
  const boardWorkspaceKey = workspaceMemoryKey.replace(/__(?:persona-\d+|no-persona)$/, '__research-board');
  const preparationContext = useRef('');
  const preparationRunning = useRef(false);
  preparationContext.current = `${boardWorkspaceKey}:${focusQuestion}:${selectedPersonaId}`;
  useEffect(() => {
    let cancelled = false;
    setResearchBoard(null);
    if (selectedProject) {
      fetchResearchBoard(boardWorkspaceKey).then((result) => { if (!cancelled) setResearchBoard(result.board); }).catch(() => {});
    }
    return () => { cancelled = true; };
  }, [boardWorkspaceKey, selectedProject?.id]);
  const confirmedBoardRules = useMemo(() => (researchBoard?.grounding_version || 0) >= 2 && researchBoard?.workspace_key === boardWorkspaceKey
    && researchBoard.query === focusQuestion.replace(/\s+/g, ' ').trim()
    ? researchBoard.rules.filter((rule) => rule.status === 'confirmed' && rule.decision_key === researchBoard.decision_key) : [],
    [researchBoard, boardWorkspaceKey, focusQuestion]);
  const boardRuleAnswers = useMemo(() => Object.fromEntries(confirmedBoardRules.map((rule) =>
    [`Confirmed decision rule ${rule.id}`, `${rule.statement} Scope: ${rule.scope}. Action effect: ${rule.effect}.`])), [confirmedBoardRules]);
  const explicitWorkspaceState = useMemo<Record<string, unknown>>(
    () => ({
      selected_project: selectedProject,
      persona_id: selectedPersonaId === '' ? null : Number(selectedPersonaId),
      persona: selectedPersona?.name || null,
      query: focusQuestion,
      selected_objective: selectedObjective,
      clarifying_answers: { ...clarifyingAnswers, ...boardRuleAnswers },
      confirmed_research_rules: confirmedBoardRules,
      objective_answers: objectiveAnswers,
      global_question_answers: globalQuestionAnswers,
      reasoning_notes: reasoningNotes,
      research_work_template: researchWorkTemplate,
      literature_processing: {
        objective_lens: literatureObjectiveLens,
        processing_summary: literatureProcessingSummary,
        elicitation_questions: literatureElicitationQuestions,
        elicitation_answers: literatureElicitationAnswers,
        review_stage: literatureReviewStage,
      },
      tacit_elicitation_questions: tacitElicitationQuestions,
      tacit_elicitation_answers: tacitElicitationAnswers,
      adaptive_elicitation_session: activeAdaptiveElicitationSession,
      agentic_plan: agenticPlan,
      selected_plan_step_id: selectedPlanStepId,
      execution_run: executionRun,
    }),
    [
      selectedProject,
      selectedPersonaId,
      selectedPersona?.name,
      focusQuestion,
      selectedObjective,
      clarifyingAnswers,
      objectiveAnswers,
      globalQuestionAnswers,
      reasoningNotes,
      researchWorkTemplate,
      literatureObjectiveLens,
      literatureProcessingSummary,
      literatureElicitationQuestions,
      literatureElicitationAnswers,
      literatureReviewStage,
      boardRuleAnswers,
      confirmedBoardRules,
      tacitElicitationQuestions,
      tacitElicitationAnswers,
      activeAdaptiveElicitationSession,
      agenticPlan,
      selectedPlanStepId,
      executionRun,
    ]
  );
  const workspaceDigest = useMemo(() => {
    const finalizedLiteratureReview = literatureReviewStage !== 'review' && researchWorkTemplate.synthesis_memo.trim();
    const findingNotes = finalizedLiteratureReview
      ? ''
      : researchWorkTemplate.literature_findings
      .slice(0, 6)
      .map((finding, index) => {
        const knowns = (finding.knowns || []).slice(0, 2).join('; ');
        const unknowns = (finding.unknowns || []).slice(0, 2).join('; ');
        const annotations = (finding.annotation_insights || []).slice(0, 2).join('; ');
        const judgments = (finding.judgment_calls || []).slice(0, 2).map((item) => item.stance).filter(Boolean).join('; ');
        return `${index + 1}. ${finding.citation || 'Untitled source'}${knowns ? `\nKnown: ${knowns}` : ''}${unknowns ? `\nOpen: ${unknowns}` : ''}${annotations ? `\nSystem annotations: ${annotations}` : ''}${judgments ? `\nUser judgments: ${judgments}` : ''}${finding.relevance ? `\nNotes: ${finding.relevance.slice(0, 400)}` : ''}`;
      })
      .join('\n\n');
    const userInputs = [
      ...Object.entries(clarifyingAnswers),
      ...Object.entries(boardRuleAnswers),
      ...Object.entries(objectiveAnswers),
      ...Object.entries(globalQuestionAnswers),
      ...Object.entries(literatureElicitationAnswers),
    ]
      .filter(([, value]) => String(value || '').trim())
      .map(([question, answer]) => `- ${question}: ${answer}`)
      .join('\n');
    return [
      `Project: ${selectedProject?.name || 'No project selected'}`,
      `Goal: ${selectedProject?.project_goal || 'Not set'}`,
      `Collaborator: ${selectedPersona?.name || 'Not selected'}`,
      `Objective: ${selectedObjective?.title || 'Not selected'}`,
      `Working question: ${focusQuestion || researchWorkTemplate.initial_query || 'Not set'}`,
      literatureProcessingSummary ? `Literature processing: ${literatureProcessingSummary}` : '',
      finalizedLiteratureReview ? `Final literature review:\n${researchWorkTemplate.synthesis_memo}` : '',
      findingNotes ? `Literature insights:\n${findingNotes}` : '',
      userInputs ? `User inputs and tacit judgments:\n${userInputs}` : '',
      reasoningNotes ? `Reasoning notes:\n${reasoningNotes}` : '',
      handoffSummary ? `Handoff summary:\n${handoffSummary}` : '',
    ]
      .filter(Boolean)
      .join('\n\n');
  }, [
    researchWorkTemplate,
    clarifyingAnswers,
    boardRuleAnswers,
    objectiveAnswers,
    globalQuestionAnswers,
    literatureElicitationAnswers,
    literatureReviewStage,
    selectedProject,
    selectedPersona?.name,
    selectedObjective?.title,
    focusQuestion,
    literatureProcessingSummary,
    reasoningNotes,
    handoffSummary,
  ]);
  const modeStudioTone: Record<string, string> = {
    general: 'border-slate-200/90 bg-white/78',
    evidence: 'border-sky-200/80 bg-[linear-gradient(135deg,rgba(239,246,255,0.78),rgba(255,255,255,0.74))]',
    data: 'border-indigo-200/80 bg-[linear-gradient(135deg,rgba(238,242,255,0.8),rgba(255,255,255,0.74))]',
    experiment: 'border-emerald-200/80 bg-[linear-gradient(135deg,rgba(236,253,245,0.82),rgba(255,251,235,0.72))]',
    process: 'border-cyan-200/80 bg-[linear-gradient(135deg,rgba(236,254,255,0.8),rgba(255,255,255,0.74))]',
    economics: 'border-amber-200/80 bg-[linear-gradient(135deg,rgba(255,251,235,0.82),rgba(255,255,255,0.74))]',
    sourcing: 'border-lime-200/80 bg-[linear-gradient(135deg,rgba(247,254,231,0.82),rgba(255,251,235,0.72))]',
    recovery: 'border-fuchsia-200/80 bg-[linear-gradient(135deg,rgba(250,245,255,0.82),rgba(255,255,255,0.74))]',
  };
  const modePageTone: Record<string, string> = {
    general: 'bg-emerald-50/20',
    evidence: 'bg-sky-50/50',
    data: 'bg-indigo-50/45',
    experiment: 'bg-emerald-50/50',
    process: 'bg-cyan-50/50',
    economics: 'bg-amber-50/45',
    sourcing: 'bg-lime-50/45',
    recovery: 'bg-fuchsia-50/45',
  };
  const scrollToSection = (target: React.RefObject<HTMLDivElement | null>) => {
    window.requestAnimationFrame(() => {
      target.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  };
  const resetQueryDependentState = (nextQuery = '') => {
    setFocusQuestion(nextQuery);
    setSelectedPersonaId(workspacePersonaId(selectedProject?.personas || []));
    setObjectiveClusters([]);
    setSelectedObjectiveId('');
    setGlobalQuestions([]);
    setObjectiveAnswers({});
    setGlobalQuestionAnswers({});
    setClarifyingAnswers({});
    setReasoningNotes('');
    setResearchWorkTemplate(createEmptyResearchWorkTemplate(nextQuery));
    setAgenticPlan(null);
    setSelectedPlanStepId('');
    setLiteratureObjectiveLens(null);
    setLiteratureProcessingSummary(null);
    setLiteratureElicitationQuestions([]);
    setLiteratureElicitationAnswers({});
    setLiteratureReviewStage('review');
    setActiveFlowStep('query');
  };
  const makeQueryTitle = (query: string, fallback: string) => {
    const trimmed = query.trim();
    return trimmed ? trimmed.slice(0, 72) : fallback;
  };
  const queryTextFromSession = (query: ProjectQuerySession) => {
    const template = query.state?.research_work_template as Partial<ResearchWorkTemplate> | undefined;
    const templateQuery = typeof template?.initial_query === 'string' ? template.initial_query.trim() : '';
    const titleQuery = query.title && query.title !== 'Untitled query' ? query.title.trim() : '';
    return query.query.trim() || templateQuery || titleQuery;
  };
  const workTemplateFromSession = (query: ProjectQuerySession, restoredQuery: string) => {
    const template = query.state?.research_work_template as ResearchWorkTemplate | undefined;
    return normalizeResearchWorkTemplate(template, restoredQuery);
  };
  const currentQueryState = (): Record<string, unknown> => ({
    selected_persona_id: selectedPersonaId === '' ? null : Number(selectedPersonaId),
    active_flow_step: activeFlowStep,
    objective_clusters: objectiveClusters,
    selected_objective_id: selectedObjectiveId,
    global_questions: globalQuestions,
    objective_answers: objectiveAnswers,
    global_question_answers: globalQuestionAnswers,
    clarifying_answers: clarifyingAnswers,
    reasoning_notes: reasoningNotes,
    research_work_template: researchWorkTemplate,
    agentic_plan: agenticPlan,
    selected_plan_step_id: selectedPlanStepId,
    literature_objective_lens: literatureObjectiveLens,
    literature_processing_summary: literatureProcessingSummary,
    literature_elicitation_questions: literatureElicitationQuestions,
    literature_elicitation_answers: literatureElicitationAnswers,
    literature_review_stage: literatureReviewStage,
  });
  const restoreQueryState = (query: ProjectQuerySession) => {
    const state = query.state || {};
    const personaId = typeof state.selected_persona_id === 'number' ? state.selected_persona_id : '';
    const restoredQuery = queryTextFromSession(query);
    setFocusQuestion(restoredQuery);
    setSelectedPersonaId(workspacePersonaId(selectedProject?.personas || [], personaId));
    setActiveFlowStep(state.active_flow_step === 'objective' || state.active_flow_step === 'workspace' ? state.active_flow_step : 'query');
    setObjectiveClusters((state.objective_clusters as ObjectiveCluster[]) || []);
    setSelectedObjectiveId(typeof state.selected_objective_id === 'string' ? state.selected_objective_id : '');
    setGlobalQuestions((state.global_questions as string[]) || []);
    setObjectiveAnswers((state.objective_answers as Record<string, string>) || {});
    setGlobalQuestionAnswers((state.global_question_answers as Record<string, string>) || {});
    setClarifyingAnswers((state.clarifying_answers as Record<string, string>) || {});
    setReasoningNotes(typeof state.reasoning_notes === 'string' ? state.reasoning_notes : '');
    setResearchWorkTemplate(workTemplateFromSession(query, restoredQuery));
    setAgenticPlan((state.agentic_plan as AgenticPlan | null) || null);
    setSelectedPlanStepId(typeof state.selected_plan_step_id === 'string' ? state.selected_plan_step_id : '');
    setLiteratureObjectiveLens(typeof state.literature_objective_lens === 'string' ? state.literature_objective_lens : null);
    setLiteratureProcessingSummary(typeof state.literature_processing_summary === 'string' ? state.literature_processing_summary : null);
    setLiteratureElicitationQuestions((state.literature_elicitation_questions as string[]) || []);
    setLiteratureElicitationAnswers((state.literature_elicitation_answers as Record<string, string>) || {});
    setLiteratureReviewStage(state.literature_review_stage === 'summary' ? 'summary' : 'review');
    setObjectivePickerCollapsed(Boolean(state.selected_objective_id));
  };

  const loadProjects = async (preferredProjectId?: number) => {
    setLoadingProjects(true);
    try {
      const data = await fetchProjects();
      const rows = data.projects || [];
      setProjects(rows);
      setSelectedProjectId((current) => {
        if (preferredProjectId && rows.some((project) => project.id === preferredProjectId)) {
          return preferredProjectId;
        }
        if (routeProjectId !== '' && rows.some((project) => project.id === Number(routeProjectId))) {
          return Number(routeProjectId);
        }
        if (current !== '' && rows.some((project) => project.id === Number(current))) {
          return current;
        }
        return '';
      });
    } catch (error) {
      setProjects([]);
      setSelectedProjectId('');
      setStatus({ type: 'error', message: error instanceof Error ? error.message : 'Failed to load projects' });
    } finally {
      setLoadingProjects(false);
    }
  };

  useEffect(() => {
    loadProjects().catch(() => {});
  }, [routeProjectId]);

  useEffect(() => {
    if (routeProjectId === '') {
      setSelectedProjectId('');
      return;
    }
    setSelectedProjectId(routeProjectId);
  }, [routeProjectId]);

  useEffect(() => {
    if (!selectedProject) {
      setSelectedPersonaId('');
      setProjectQueries([]);
      setActiveQueryId('');
      setHydratedQueryKey('');
      return;
    }

    setSelectedPersonaId((current) => {
      if (routePersonaId !== '' && selectedProject.personas.some((persona) => persona.persona_id === Number(routePersonaId))) {
        return Number(routePersonaId);
      }
      if (current !== '' && selectedProject.personas.some((persona) => persona.persona_id === Number(current))) {
        return current;
      }
      return workspacePersonaId(selectedProject.personas);
    });
  }, [selectedProject, routePersonaId]);

  useEffect(() => {
    let cancelled = false;
    const loadQueries = async () => {
      if (!selectedProject) {
        return;
      }
      setHydratedQueryKey('');
      setQueriesLoadedProjectId(null);
      try {
        const response = await fetchProjectQueries(selectedProject.id);
        if (cancelled) return;
        const rows = response.queries || [];
        setProjectQueries(rows);
        setQueriesLoadedProjectId(selectedProject.id);
        if (rows.length > 0) {
          const preferred = routeQueryId !== '' ? rows.find((item) => item.id === Number(routeQueryId)) : null;
          const next = preferred || rows[0];
          setActiveQueryId(next.id);
          restoreQueryState(next);
          setHydratedQueryKey(`${selectedProject.id}:${next.id}`);
        } else {
          setActiveQueryId('');
          setHydratedQueryKey('');
          resetQueryDependentState('');
          setActiveFlowStep('query');
          setShowNewQueryForm(true);
        }
      } catch (error) {
        if (!cancelled) {
          setStatus({ type: 'error', message: error instanceof Error ? error.message : 'Failed to load project queries' });
        }
      }
    };
    loadQueries().catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [selectedProject?.id, routeQueryId]);

  useEffect(() => {
    if (
      !selectedProject
      || activeQueryId === ''
      || hydratedQueryKey !== `${selectedProject.id}:${activeQueryId}`
    ) {
      return;
    }
    const storedQuery = projectQueries.find((item) => item.id === Number(activeQueryId));
    if (storedQuery?.query.trim() && !focusQuestion.trim()) {
      return;
    }
    const payload = {
      title: makeQueryTitle(focusQuestion, 'Untitled query'),
      query: focusQuestion,
      state: currentQueryState(),
    };
    const saveKey = `${selectedProject.id}:${activeQueryId}`;
    if (!queryNeedsSave(storedQuery, payload) || querySavesInFlight.current.has(saveKey)) return;
    const timer = window.setTimeout(async () => {
      if (querySavesInFlight.current.has(saveKey)) return;
      querySavesInFlight.current.add(saveKey);
      try {
        const saved = await updateProjectQuery(selectedProject.id, activeQueryId, payload);
        setProjectQueries((current) => current.map((item) => (item.id === saved.id ? saved : item)));
      } catch {
        // Workspace-level autosave still protects the active draft; query session save can retry on the next edit.
      } finally {
        querySavesInFlight.current.delete(saveKey);
      }
    }, 900);
    return () => window.clearTimeout(timer);
  }, [
    selectedProject?.id,
    activeQueryId,
    hydratedQueryKey,
    projectQueries,
    focusQuestion,
    selectedPersonaId,
    activeFlowStep,
    JSON.stringify(objectiveClusters),
    selectedObjectiveId,
    JSON.stringify(globalQuestions),
    JSON.stringify(objectiveAnswers),
    JSON.stringify(globalQuestionAnswers),
    JSON.stringify(clarifyingAnswers),
    reasoningNotes,
    JSON.stringify(researchWorkTemplate),
    JSON.stringify(agenticPlan),
    selectedPlanStepId,
    literatureObjectiveLens,
    literatureProcessingSummary,
    JSON.stringify(literatureElicitationQuestions),
    JSON.stringify(literatureElicitationAnswers),
    literatureReviewStage,
  ]);

  useEffect(() => {
    if (!selectedPersona) {
      }
  }, [selectedPersona?.persona_id]);

  useEffect(() => {
    if (!selectedProject || selectedPersonaId === '') {
      return;
    }

    const currentProjectId = searchParams.get('projectId') || '';
    const currentPersonaId = searchParams.get('personaId') || '';
    const nextProjectId = String(selectedProject.id);
    const nextPersonaId = String(selectedPersonaId);

    if (currentProjectId === nextProjectId && currentPersonaId === nextPersonaId) {
      return;
    }

    const params = new URLSearchParams(searchParams.toString());
    params.set('projectId', nextProjectId);
    params.set('personaId', nextPersonaId);
    router.replace(`/?${params.toString()}`, { scroll: false });
  }, [router, searchParams, selectedProject?.id, selectedPersonaId]);

  useEffect(() => {
    setHydratedQueryKey('');
    setWorkspaceReadyForSave(false);
    setExecutionRun(null);
    setExecutionEvents([]);
    setTacitState([]);
    setAdaptiveElicitationSession(null);
    setHandoffSummary('');
    setMemoryStatus('loading memory...');
  }, [selectedProjectId]);

  useEffect(() => {
    let cancelled = false;

    const loadWorkspace = async () => {
      if (!selectedProject || !selectedPersona || selectedPersonaId === '' || activeQueryId !== ''
        || queriesLoadedProjectId !== selectedProject.id || projectQueries.length > 0) {
        return;
      }

      setLoadingWorkspace(true);
      try {
        const response = await fetchWorkspaceState(selectedProject.id, Number(selectedPersonaId));
        if (cancelled) return;

        if (response.state) {
          const nextFocusQuestion = response.state.focus_question || defaultFocusQuestion(selectedProject, selectedPersona);
          setFocusQuestion(nextFocusQuestion);
          setClarifyingAnswers(response.state.clarifying_answers || {});
          setReasoningNotes(response.state.reasoning_notes || '');
          setResearchWorkTemplate(normalizeResearchWorkTemplate(response.state.work_template, nextFocusQuestion));
          setAgenticPlan(response.state.plan || null);
          setSelectedPlanStepId(response.state.selected_step_id || response.state.plan?.steps[0]?.id || '');
        } else {
          const nextFocusQuestion = defaultFocusQuestion(selectedProject, selectedPersona);
          setFocusQuestion(nextFocusQuestion);
          setClarifyingAnswers({});
          setReasoningNotes('');
          setResearchWorkTemplate(createEmptyResearchWorkTemplate(nextFocusQuestion));
          setAgenticPlan(null);
          setSelectedPlanStepId('');
        }
      } catch (error) {
        if (cancelled) return;
        const nextFocusQuestion = defaultFocusQuestion(selectedProject, selectedPersona);
        setFocusQuestion(nextFocusQuestion);
        setClarifyingAnswers({});
        setReasoningNotes('');
        setResearchWorkTemplate(createEmptyResearchWorkTemplate(nextFocusQuestion));
        setAgenticPlan(null);
        setSelectedPlanStepId('');
        setStatus({ type: 'error', message: error instanceof Error ? error.message : 'Failed to load saved workspace' });
      } finally {
        if (!cancelled) {
          setLoadingWorkspace(false);
          setWorkspaceReadyForSave(true);
        }
      }
    };

    loadWorkspace().catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [selectedProject?.id, selectedPersona?.persona_id, selectedPersonaId, activeQueryId, queriesLoadedProjectId, projectQueries.length]);

  useEffect(() => {
    let cancelled = false;

    const loadExecutionRun = async () => {
      if (!selectedProject || !selectedPersona || selectedPersonaId === '') {
        return;
      }
      try {
        const response = await fetchLatestExecutionRun(selectedProject.id, Number(selectedPersonaId));
        if (cancelled) return;
        setExecutionRun(response.run || null);
        setExecutionEvents(response.events || []);
      } catch {
        if (!cancelled) {
          setExecutionRun(null);
          setExecutionEvents([]);
        }
      }
    };

    loadExecutionRun().catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [selectedProject?.id, selectedPersona?.persona_id, selectedPersonaId]);

  useEffect(() => {
    if (!workspaceReadyForSave || loadingWorkspace || !selectedProject || !selectedPersona || selectedPersonaId === '' || activeQueryId !== '') {
      return;
    }

    const timer = window.setTimeout(async () => {
      try {
        await saveWorkspaceState(selectedProject.id, Number(selectedPersonaId), {
          focus_question: focusQuestion,
          clarifying_answers: clarifyingAnswers,
          reasoning_notes: reasoningNotes,
          work_template: researchWorkTemplate,
          plan: agenticPlan,
          selected_step_id: selectedPlanStepId || undefined,
        });
      } catch {
        // Autosave retries on the next workspace change.
      }
    }, 900);

    return () => {
      window.clearTimeout(timer);
    };
  }, [
    workspaceReadyForSave,
    loadingWorkspace,
    selectedProject?.id,
    selectedPersona?.persona_id,
    selectedPersonaId,
    activeQueryId,
    focusQuestion,
    JSON.stringify(clarifyingAnswers),
    reasoningNotes,
    JSON.stringify(researchWorkTemplate),
    JSON.stringify(agenticPlan),
    selectedPlanStepId,
  ]);

  useEffect(() => {
    if (!selectedProject || selectedPersonaId === '') {
      return;
    }
    let cancelled = false;
    const loadMemory = async () => {
      try {
        const response = await fetchWorkspaceMemory(workspaceMemoryKey);
        if (cancelled) return;
        if (response.memory) {
          setTacitState(response.memory.tacit_state || []);
          setTacitElicitationQuestions(((response.memory.explicit_state?.tacit_elicitation_questions as TacitElicitationQuestion[]) || []));
          setTacitElicitationAnswers(((response.memory.explicit_state?.tacit_elicitation_answers as Record<string, string>) || {}));
          setAdaptiveElicitationSession(
            (response.memory.explicit_state?.adaptive_elicitation_session as AdaptiveElicitationSession | null) || null
          );
          setHandoffSummary(response.memory.handoff_summary || '');
          setMemoryStatus(`loaded memory${response.memory.updated_at ? ` from ${new Date(response.memory.updated_at).toLocaleString()}` : ''}`);
        } else {
          setTacitState([]);
          setTacitElicitationQuestions([]);
          setTacitElicitationAnswers({});
          setAdaptiveElicitationSession(null);
          setHandoffSummary('');
          setMemoryStatus('new memory record');
        }
      } catch {
        if (!cancelled) {
          setMemoryStatus('memory load unavailable');
        }
      }
    };
    loadMemory().catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [selectedProject?.id, selectedPersonaId, workspaceMemoryKey]);

  useEffect(() => {
    if (!selectedProject || selectedPersonaId === '') {
      return;
    }
    const timer = window.setTimeout(async () => {
      try {
        const response = await saveWorkspaceMemory(workspaceMemoryKey, {
          scope: selectedProject.scope_id || `project-${selectedProject.id}`,
          explicit_state: explicitWorkspaceState,
          tacit_state: tacitState,
          handoff_summary: handoffSummary,
        });
        const updatedAt = response.memory?.updated_at;
        setMemoryStatus(`saved${updatedAt ? ` at ${new Date(updatedAt).toLocaleTimeString()}` : ''}`);
      } catch {
        setMemoryStatus('save failed; memory changes are local');
      }
    }, 1100);
    return () => {
      window.clearTimeout(timer);
    };
  }, [
    selectedProject?.id,
    selectedProject?.scope_id,
    selectedPersonaId,
    workspaceMemoryKey,
    JSON.stringify(explicitWorkspaceState),
    JSON.stringify(tacitState),
    handoffSummary,
  ]);

  useEffect(() => {
    if (!memoryDrawerOpen || !selectedProject || selectedPersonaId === '') {
      return;
    }
    let cancelled = false;
    const loadOntology = async () => {
      setLoadingOntology(true);
      setOntologyStatus('loading stored ontology...');
      try {
        const response = await fetchStoredOntology(selectedProject.id);
        if (cancelled) return;
        setOntologyPreview(response);
        setOntologyStatus(response.nodes.length > 0 ? `loaded ${response.nodes.length} entities and ${response.edges.length} relations` : 'no stored ontology yet');
      } catch (error) {
        if (!cancelled) {
          setOntologyStatus(error instanceof Error ? error.message : 'ontology load failed');
        }
      } finally {
        if (!cancelled) {
          setLoadingOntology(false);
        }
      }
    };
    loadOntology().catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [memoryDrawerOpen, selectedProject?.id, selectedPersonaId]);

  useEffect(() => {
    if (!selectedProject || !executionRun || !['queued', 'running'].includes(executionRun.status)) {
      return;
    }

    let cancelled = false;
    let pending = false;
    const controller = new AbortController();
    const timer = window.setInterval(async () => {
      if (pending) return;
      pending = true;
      try {
        const response = await fetchExecutionRun(selectedProject.id, executionRun.id, controller.signal);
        if (cancelled) return;
        setExecutionRun(response.run || null);
        setExecutionEvents(response.events || []);
        if (response.run?.final_work_template) {
          setResearchWorkTemplate(response.run.final_work_template);
        }
        if (response.run?.final_plan) {
          setAgenticPlan(response.run.final_plan);
          setSelectedPlanStepId(response.run.final_plan.steps[0]?.id || '');
        }
        if (response.run?.status === 'completed') {
          setStatus({ type: 'success', message: 'Agentic execution completed and the workspace was refreshed.' });
        } else if (response.run?.status === 'failed') {
          setStatus({ type: 'error', message: response.run.error_message || 'Agentic execution failed.' });
        }
      } catch {
        // Keep the existing UI state if polling fails briefly.
      } finally {
        pending = false;
      }
    }, 2000);

    return () => {
      cancelled = true;
      controller.abort();
      window.clearInterval(timer);
    };
  }, [selectedProject?.id, executionRun?.id, executionRun?.status]);

  const handleCreateProject = async () => {
    if (!form.name.trim() || !form.end_product.trim()) {
      setStatus({ type: 'error', message: 'Project name and end product are required.' });
      return;
    }

    setCreatingProject(true);
    setStatus({ type: 'info', message: 'Creating project...' });
    try {
      const response = await createProject(form);
      await loadProjects(response.project.id);
      router.push(`/?projectId=${response.project.id}`);
      setSelectedProjectId(response.project.id);
      setSelectedPersonaId('');
      setActiveFlowStep('query');
      setFocusQuestion('');
      setShowNewQueryForm(true);
      setReasoningNotes('');
      setStatus({
        type: 'success',
        message: `Created ${response.project.name}.`,
      });
    } catch (error) {
      setStatus({ type: 'error', message: error instanceof Error ? error.message : 'Failed to create project' });
    } finally {
      setCreatingProject(false);
    }
  };

  const handleOpenProject = (projectId: number) => {
    router.push(`/?projectId=${projectId}`);
    setSelectedProjectId(projectId);
  };

  const handleCreateProjectQuery = async () => {
    if (!selectedProject) {
      return;
    }
    const query = newQueryText.trim();
    if (!query) {
      setStatus({ type: 'error', message: 'Write the query before creating the investigation.' });
      return;
    }
    setCreatingQuery(true);
    try {
      const created = await createProjectQuery(selectedProject.id, {
        title: makeQueryTitle(query, `Investigation ${projectQueries.length + 1}`),
        query,
        state: {},
      });
      setProjectQueries((current) => [created, ...current]);
      setActiveQueryId(created.id);
      restoreQueryState(created);
      setHydratedQueryKey(`${selectedProject.id}:${created.id}`);
      router.replace(`/?projectId=${selectedProject.id}&queryId=${created.id}`, { scroll: false });
      setNewQueryText('');
      setShowNewQueryForm(false);
      setStatus({ type: 'success', message: 'Created a new investigation.' });
    } catch (error) {
      setStatus({ type: 'error', message: error instanceof Error ? error.message : 'Failed to create query' });
    } finally {
      setCreatingQuery(false);
    }
  };

  const handleSelectProjectQuery = (queryId: number) => {
    const next = projectQueries.find((item) => item.id === queryId);
    if (!next) return;
    const nextPersonaId = typeof next.state?.selected_persona_id === 'number' ? next.state.selected_persona_id : '';
    setActiveQueryId(next.id);
    restoreQueryState(next);
    setHydratedQueryKey(`${selectedProject?.id}:${next.id}`);
    logProjectEvent('project_query_selected', {
      project_id: selectedProject?.id,
      query_id: next.id,
      query: next.query,
      persona_id: nextPersonaId || undefined,
    }).catch(() => {});
    router.replace(`/?projectId=${selectedProject?.id}${nextPersonaId ? `&personaId=${nextPersonaId}` : ''}&queryId=${next.id}`, { scroll: false });
    setStatus({ type: 'info', message: 'Investigation opened.' });
  };

  const splitManualLines = (value: string) =>
    value
      .split('\n')
      .map((item) => item.trim())
      .filter(Boolean);

  const handleManualObjectiveChange = (field: keyof ManualObjectiveForm, value: string) => {
    setManualObjective((current) => ({ ...current, [field]: value }));
  };

  const handleCreateManualObjective = () => {
    if (!manualObjective.title.trim() || !manualObjective.definition.trim()) {
      setStatus({ type: 'error', message: 'Add at least a title and definition for the objective.' });
      return;
    }
    const next: ObjectiveCluster = {
      id: `manual_${manualObjective.title.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '').slice(0, 48) || Date.now()}`,
      title: manualObjective.title.trim(),
      subtitle: manualObjective.subtitle.trim() || 'User-defined objective mode',
      definition: manualObjective.definition.trim(),
      signals: splitManualLines(manualObjective.signals),
      facet_questions: splitManualLines(manualObjective.facet_questions),
      exemplar_answer: manualObjective.exemplar_answer.trim() || 'Use this objective lens to structure the next workspace output.',
    };
    setObjectiveClusters((current) => [next, ...current.filter((item) => item.id !== next.id)]);
    setSelectedObjectiveId(next.id);
    setObjectivePickerCollapsed(true);
    setShowManualObjectiveForm(false);
    setManualObjective(emptyManualObjective);
    setActiveFlowStep('workspace');
    logProjectEvent('project_objective_selected', {
      project_id: selectedProject?.id,
      query_id: activeQueryId === '' ? undefined : activeQueryId,
      persona_id: selectedPersonaId === '' ? undefined : selectedPersonaId,
      objective_id: next.id,
      objective_title: next.title,
      query: focusQuestion,
    }).catch(() => {});
    scrollToSection(draftSectionRef);
    setStatus({ type: 'success', message: `Created and selected objective mode: ${next.title}.` });
  };

  const handleDeleteProject = async (project: Project) => {
    const confirmed = window.confirm(`Delete "${project.name}" and its saved project workspace?`);
    if (!confirmed) {
      return;
    }

    setDeletingProjectId(project.id);
    setStatus({ type: 'info', message: `Deleting ${project.name}...` });
    try {
      await deleteProject(project.id);
      if (selectedProjectId === project.id) {
        router.push('/');
        setSelectedProjectId('');
        setSelectedPersonaId('');
      }
      await loadProjects();
      setStatus({ type: 'success', message: `Deleted ${project.name}.` });
    } catch (error) {
      setStatus({ type: 'error', message: error instanceof Error ? error.message : 'Failed to delete project' });
    } finally {
      setDeletingProjectId(null);
    }
  };

  const handleReturnToLanding = () => {
    router.push('/');
    setSelectedProjectId('');
    setSelectedPersonaId('');
    setActiveQueryId('');
    setSelectedObjectiveId('');
    setActiveFlowStep('query');
    setStatus(null);
  };

  const handleClusterObjectives = async () => {
    const queryText = focusQuestion.trim() || selectedProject?.project_goal?.trim() || '';
    if (!queryText) {
      setStatus({ type: 'error', message: 'Add a working question before clustering objective angles.' });
      return;
    }
    if (!selectedPersona) {
      setStatus({ type: 'error', message: 'The project has no workspace profile. Reopen the project or check its setup.' });
      setActiveFlowStep('query');
      return;
    }

    setLoadingObjectiveClusters(true);
    setStatus({ type: 'info', message: 'Clustering objective angles for this project question...' });
    try {
      const response = await clusterObjectives({
        query: queryText,
        context: [
          selectedProject?.project_goal ? `Project goal: ${selectedProject.project_goal}` : '',
          selectedProject?.end_product ? `End product: ${selectedProject.end_product}` : '',
          selectedProject?.target_host ? `Target host: ${selectedProject.target_host}` : '',
          selectedProject?.raw_material_focus ? `Cost or sourcing context: ${selectedProject.raw_material_focus}` : '',
          selectedProject?.notes ? `Project context: ${selectedProject.notes}` : '',
        ]
          .filter(Boolean)
          .join('\n'),
        k: 4,
        persona_id: selectedPersona?.persona_id,
      });
      setObjectiveClusters(response.objectives || []);
      setGlobalQuestions(response.global_questions || []);
      setSelectedObjectiveId('');
      setObjectiveAnswers({});
      setGlobalQuestionAnswers({});
      setObjectivePickerCollapsed(false);
      setActiveFlowStep('objective');
      scrollToSection(objectiveSectionRef);
      setStatus({
        type: 'success',
        message: response.objectives?.length
          ? 'Objective clusters generated. Pick the mode that should govern the next workspace.'
          : 'No objective clusters were returned.',
      });
    } catch (error) {
      setStatus({ type: 'error', message: error instanceof Error ? error.message : 'Failed to cluster objectives' });
    } finally {
      setLoadingObjectiveClusters(false);
    }
  };

  const handleSelectObjective = (objectiveId: string) => {
    setSelectedObjectiveId(objectiveId);
    setObjectivePickerCollapsed(true);
    setActiveFlowStep('workspace');
    const objective = objectiveClusters.find((item) => item.id === objectiveId);
    logProjectEvent('project_objective_selected', {
      project_id: selectedProject?.id,
      query_id: activeQueryId === '' ? undefined : activeQueryId,
      persona_id: selectedPersonaId === '' ? undefined : selectedPersonaId,
      objective_id: objectiveId,
      objective_title: objective?.title,
      query: focusQuestion,
    }).catch(() => {});
    scrollToSection(draftSectionRef);
  };

  const handleRefineQuery = () => {
    const currentQuery = focusQuestion.trim() || researchWorkTemplate.initial_query.trim() || selectedProject?.project_goal?.trim() || '';
    if (activeQueryId === '') {
      setNewQueryText(currentQuery);
      setShowNewQueryForm(true);
      setStatus({ type: 'info', message: 'Use the project query panel to create the first investigation query.' });
      return;
    }
    setShowNewQueryForm(false);
    setActiveFlowStep('query');
    setStatus({ type: 'info', message: 'Edit the working query for this investigation.' });
    scrollToSection(querySectionRef);
  };

  const handleChooseAnotherObjective = () => {
    setActiveFlowStep('objective');
    setObjectivePickerCollapsed(false);
    scrollToSection(objectiveSectionRef);
  };

  const handleOpenWorkspaceStage = (stage: LiteratureReviewStage) => {
    setLiteratureReviewStage(stage);
    setActiveFlowStep(selectedObjective ? 'workspace' : 'objective');
    scrollToSection(selectedObjective ? draftSectionRef : objectiveSectionRef);
  };

  const handleFetchLiterature = async () => {
    const requestContext = preparationContext.current;
    if (!selectedProject || !selectedPersona || selectedPersonaId === '') {
      setStatus({ type: 'error', message: 'Open a project before fetching literature.' });
      return;
    }
    const queryText = researchWorkTemplate.initial_query.trim() || focusQuestion.trim() || selectedProject.project_goal.trim();
    if (!queryText) {
      setStatus({ type: 'error', message: 'Add an initial query or working question before fetching literature.' });
      return;
    }

    setFetchingLiterature(true);
    setStatus({ type: 'info', message: 'Fetching literature with PubMed, Semantic Scholar, OpenAlex, and Crossref...' });
    try {
      const response = await fetchProjectLiterature(selectedProject.id, {
        persona_id: Number(selectedPersonaId),
        query: queryText,
        objective_id: selectedObjective?.id,
        objective_title: selectedObjective?.title,
        objective_definition: selectedObjective?.definition,
        objective_signals: selectedObjective?.signals,
        project_goal: selectedProject.project_goal,
        project_end_product: selectedProject.end_product,
        project_target_host: selectedProject.target_host,
        clarifying_answers: clarifyingAnswers,
        objective_answers: objectiveAnswers,
        global_question_answers: globalQuestionAnswers,
        reasoning_notes: reasoningNotes,
        work_template: researchWorkTemplate,
        max_results: 5,
        existing_citations: researchWorkTemplate.literature_findings.map((item) => item.citation).filter(Boolean),
      });
      const existing = new Set(researchWorkTemplate.literature_findings.map((item) => item.citation.trim().toLowerCase()).filter(Boolean));
      if (preparationContext.current !== requestContext) return;
      const existingIds = new Set(researchWorkTemplate.literature_findings.map((item) => item.id));
      const newFindings = (response.findings || [])
        .filter((item) => !existing.has(item.citation.trim().toLowerCase()))
        .map((item, index) => ({ ...item, id: uniqueFindingId(item, existingIds, index) }));
      const nextWorkTemplate = {
        ...researchWorkTemplate,
        initial_query: researchWorkTemplate.initial_query.trim() || queryText,
        literature_findings: [...researchWorkTemplate.literature_findings, ...newFindings],
      };
      setResearchWorkTemplate(nextWorkTemplate);
      setLiteratureObjectiveLens(response.objective_lens || selectedObjective?.title || null);
      setLiteratureProcessingSummary(response.processing_summary || null);
      setLiteratureElicitationQuestions(response.elicitation_questions || []);
      setLiteratureElicitationAnswers({});
      setLiteratureReviewStage('review');
      setActiveOntologyTrace(response.ontology_trace || null);
      const trace = response.tool_trace;
      logProjectEvent('project_literature_fetched', {
        project_id: selectedProject.id,
        query_id: activeQueryId === '' ? undefined : activeQueryId,
        persona_id: Number(selectedPersonaId),
        objective_id: selectedObjective?.id,
        objective_title: selectedObjective?.title,
        tool_query: trace.query,
        result_count: trace.result_count,
        added_count: newFindings.length,
      }).catch(() => {});
      if (newFindings.length > 0) {
        syncProjectOntology(selectedProject.id, {
          persona_id: Number(selectedPersonaId),
          query: queryText,
          objective_id: selectedObjective?.id,
          objective_title: selectedObjective?.title,
          objective_definition: selectedObjective?.definition,
          project_goal: selectedProject.project_goal,
          project_end_product: selectedProject.end_product,
          project_target_host: selectedProject.target_host,
          explicit_state: explicitWorkspaceState,
          tacit_state: tacitState,
          work_template: nextWorkTemplate,
          plan: agenticPlan,
        })
          .then((ontology) => {
            setOntologyPreview(ontology);
            setOntologyStatus(ontology.sync_message || `synced ${ontology.nodes.length} ontology entities`);
          })
          .catch(() => {});
      }
      setStatus({ type: 'success', message: `Literature library updated. Added ${newFindings.length} new source${newFindings.length === 1 ? '' : 's'}.` });
      return nextWorkTemplate;
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to fetch literature';
      setStatus({ type: 'error', message });
    } finally {
      setFetchingLiterature(false);
    }
  };

  const handlePreparePaperPdf = async (finding: ResearchFinding, background = false) => {
    const requestContext = preparationContext.current;
    if (preparationRunning.current && !background) return;
    if (!selectedProject || !selectedPersona || selectedPersonaId === '') {
      setStatus({ type: 'error', message: 'Open a project before preparing an annotated PDF.' });
      return;
    }
    const queryText = researchWorkTemplate.initial_query.trim() || focusQuestion.trim() || selectedProject.project_goal.trim();
    if (!queryText) {
      setStatus({ type: 'error', message: 'Add an initial query or working question before annotating a PDF.' });
      return;
    }

    if (preparingPdfFindingId && !background) return;
    const contextKey = JSON.stringify([4, selectedProject.id, finding.id, finding.citation, finding.source_ids,
      queryText, selectedObjective?.id, selectedObjective?.title, selectedObjective?.definition,
      selectedObjective?.signals, selectedProject.project_goal, selectedProject.end_product, selectedProject.target_host]);
    setPdfAnnotationFindingId(finding.id);
    setPreparingPdfFindingId(finding.id);
    const saved = finding.pdf_reader;
    const savedFileExists = saved?.context_key === contextKey
      && saved.url.startsWith(`/api/projects/${selectedProject.id}/literature/pdf/`)
      && Boolean(saved.modified)
      && await fetch(`${API_BASE}${saved.url}`, { method: 'HEAD', signal: AbortSignal.timeout(10000) })
        .then((r) => r.ok && r.headers.get('last-modified') === saved.modified).catch(() => false);
    if (preparationContext.current !== requestContext) return;
    if (saved && savedFileExists) {
      if (!background) setPdfViewer({ findingId: finding.id, title: finding.citation || 'Annotated literature PDF',
        url: `${API_BASE}${saved.url}`, annotatedPath: saved.path,
        });
      setPdfAnnotationStatus(background ? 'Reused saved annotations.' : 'Opened saved annotations. No download or generation was requested.');
      setPreparingPdfFindingId(null);
      return finding;
    }
    setPreparingPdfFindingId(finding.id);
    setPdfAnnotationStatus('Opening paper: checking saved files and annotations. Missing or outdated annotations will be prepared; this may take a few minutes.');
    try {
      const response = await preparePaperPdf(selectedProject.id, {
        persona_id: Number(selectedPersonaId),
        finding,
        query: queryText,
        project_goal: selectedProject.project_goal,
        project_end_product: selectedProject.end_product,
        project_target_host: selectedProject.target_host,
        persona_name: selectedPersona.name,
        persona_focus: selectedPersona.focus_area,
        objective_id: selectedObjective?.id,
        objective_title: selectedObjective?.title,
        objective_definition: selectedObjective?.definition,
        objective_signals: selectedObjective?.signals,
        max_annotations: 8,
      });

      if (response.status !== 'success') {
        const message = response.message || 'No downloadable open-access PDF was found for this paper.';
        setPdfAnnotationStatus(message);
        return;
      }

      const savedModified = response.annotated_pdf_url
        ? await fetch(`${API_BASE}${response.annotated_pdf_url}`, { method: 'HEAD', signal: AbortSignal.timeout(10000) })
          .then((r) => r.ok ? r.headers.get('last-modified') || undefined : undefined).catch(() => undefined)
        : undefined;

      if (preparationContext.current !== requestContext) return;
      const preparedFinding: ResearchFinding = {
        ...finding,
        labels: Array.from(new Set([...finding.labels, 'pdf annotated'])),
        pdf_reader: response.annotated_pdf_url ? { context_key: contextKey, url: response.annotated_pdf_url, modified: savedModified, path: response.annotated_pdf_path || undefined } : undefined,
        annotation_insights: response.insights, generated_questions: response.research_questions,
        annotations: response.annotations, structured_notes: response.structured_notes,
      };

      setResearchWorkTemplate((current) => ({
        ...current,
        literature_findings: current.literature_findings.map((item) =>
          item.id === finding.id
            ? {
                ...item,
                labels: item.labels.includes('pdf annotated') ? item.labels : [...item.labels, 'pdf annotated'],
                pdf_reader: response.annotated_pdf_url ? { context_key: contextKey, url: response.annotated_pdf_url, modified: savedModified, path: response.annotated_pdf_path || undefined } : undefined,
                annotation_insights: response.insights,
                generated_questions: response.research_questions,
                annotations: response.annotations,
                structured_notes: response.structured_notes,
                unknowns: Array.from(new Set([
                  ...(item.unknowns || []).filter((value) => (
                    !(item.generated_questions || []).includes(value)
                    && !/^Page \d+: (?:What project-relevant uncertainty|Which intervention should|What experiment would|Which follow-up study)/.test(value)
                  )),
                  ...(response.research_questions || []),
                ])),
              }
            : item
        ),
      }));

      if (response.annotated_pdf_url && !background) {
        setPdfViewer({
          findingId: finding.id,
          title: finding.citation || response.paper_id || 'Annotated literature PDF',
          url: `${API_BASE}${response.annotated_pdf_url}`,
          annotatedPath: response.annotated_pdf_path,
        });
      }

      const message = background ? response.message : `${response.message} ${response.visual_annotations ? 'Opened in the in-app PDF reader.' : 'PDF reader opened, but visual highlights were unavailable.'}`;
      setPdfAnnotationStatus(message);
      logProjectEvent('paper_pdf_annotated', {
        project_id: selectedProject.id,
        query_id: activeQueryId === '' ? undefined : activeQueryId,
        persona_id: Number(selectedPersonaId),
        objective_id: selectedObjective?.id,
        objective_title: selectedObjective?.title,
        paper_id: response.paper_id,
        citation: finding.citation,
        annotations: response.annotations.length,
      }).catch(() => {});
      return preparedFinding;
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to prepare annotated PDF';
      setPdfAnnotationStatus(message);
    } finally {
      setPreparingPdfFindingId(null);
    }
  };

  const handlePrepareEvidenceSources = async (progress: (message: string) => void) => {
    if (!selectedProject || !selectedPersona || selectedPersonaId === '') throw new Error('Open a project before preparing evidence.');
    if (preparationRunning.current || fetchingLiterature || preparingPdfFindingId) throw new Error('A literature request is already running. Wait for it to finish.');
    preparationRunning.current = true;
    try {
    const requestContext = preparationContext.current;
    let template = researchWorkTemplate;
    if (!template.literature_findings.length) {
      progress('Finding and screening literature…');
      const fetched = await handleFetchLiterature();
      if (!fetched) throw new Error('Literature search did not finish. Check the project search and retry.');
      template = fetched;
    }
    const findings = [...template.literature_findings];
    const notices: string[] = [];
    // Keep local inference serial and bound the first preparation batch.
    const candidates = findings.filter(f => !/not relevant|irrelevant/i.test(f.relevance || '')).slice(0, 5);
    if (!candidates.length) throw new Error('No relevant records are available. Refine the literature query first.');
    for (const [index, finding] of candidates.entries()) {
      if (preparationContext.current !== requestContext) throw new Error('The project or question changed. Preparation stopped.');
      progress(`Preparing paper ${index + 1} of ${candidates.length} · checking saved annotations first`);
      const prepared = await handlePreparePaperPdf(finding, true);
      if (prepared) findings[findings.findIndex(f => f.id === finding.id)] = prepared;
      else notices.push(`Could not prepare ${finding.citation || 'a paper'}. Review its access and annotation status in the evidence library.`);
    }
    if (preparationContext.current !== requestContext) throw new Error('The project or question changed. Preparation stopped.');
    if (template.literature_findings.length > candidates.length) notices.push('This run prepared up to five relevant papers. Other library records remain available for individual review.');
    return { state: { ...explicitWorkspaceState, research_work_template: { ...template, literature_findings: findings } }, notices };
    } finally { preparationRunning.current = false; }
  };

  const handleBuildPaperOntology = async (finding: ResearchFinding) => {
    if (!selectedProject || !selectedPersona || selectedPersonaId === '') {
      setStatus({ type: 'error', message: 'Open a project before building a paper ontology.' });
      return;
    }
    const queryText = researchWorkTemplate.initial_query.trim() || focusQuestion.trim() || selectedProject.project_goal.trim();
    setBuildingPaperOntologyId(finding.id);
    setOntologyStatus('building paper ontology...');
    setStatus({ type: 'info', message: 'Building a paper-scoped ontology and syncing it into the project graph...' });
    try {
      const response = await buildPaperOntology(selectedProject.id, {
        persona_id: Number(selectedPersonaId),
        finding,
        query: queryText,
        objective_id: selectedObjective?.id,
        objective_title: selectedObjective?.title,
        objective_definition: selectedObjective?.definition,
        project_goal: selectedProject.project_goal,
        project_end_product: selectedProject.end_product,
        project_target_host: selectedProject.target_host,
        persist: true,
      });
      setOntologyPreview(response);
      setOntologyStatus(response.sync_message || `built paper ontology with ${response.nodes.length} entities`);
      logProjectEvent('paper_ontology_requested', {
        project_id: selectedProject.id,
        query_id: activeQueryId === '' ? undefined : activeQueryId,
        persona_id: Number(selectedPersonaId),
        objective_id: selectedObjective?.id,
        finding_id: finding.id,
        citation: finding.citation,
        node_count: response.nodes.length,
        edge_count: response.edges.length,
      }).catch(() => {});
      setStatus({ type: 'success', message: response.sync_message || 'Paper ontology synced into the project graph.' });
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to build paper ontology';
      setOntologyStatus(message);
      setStatus({ type: 'error', message });
    } finally {
      setBuildingPaperOntologyId(null);
    }
  };

  const handleSynthesizeLiteratureGaps = async () => {
    if (!selectedProject || !selectedPersona || selectedPersonaId === '') {
      setStatus({ type: 'error', message: 'Open a project before synthesizing gaps.' });
      return;
    }
    const queryText = researchWorkTemplate.initial_query.trim() || focusQuestion.trim() || selectedProject.project_goal.trim();
    setSynthesizingGaps(true);
    setStatus({ type: 'info', message: 'Synthesizing editable literature gap clusters...' });
    try {
      const response = await synthesizeLiteratureGaps(selectedProject.id, {
        persona_id: Number(selectedPersonaId),
        query: queryText,
        project_goal: selectedProject.project_goal,
        project_end_product: selectedProject.end_product,
        project_target_host: selectedProject.target_host,
        objective_id: selectedObjective?.id,
        objective_title: selectedObjective?.title,
        objective_definition: selectedObjective?.definition,
        objective_signals: selectedObjective?.signals,
        work_template: researchWorkTemplate,
        max_gaps: 6,
      });
      setResearchWorkTemplate((current) => ({
        ...current,
        common_gaps: response.gaps,
        synthesis_memo: response.cross_paper_synthesis?.summary || response.synthesis_summary || current.synthesis_memo,
      }));
      logProjectEvent('project_literature_gaps_synthesized', {
        project_id: selectedProject.id,
        query_id: activeQueryId === '' ? undefined : activeQueryId,
        persona_id: Number(selectedPersonaId),
        objective_id: selectedObjective?.id,
        gap_count: response.gaps.length,
        consensus_patterns: response.cross_paper_synthesis?.consensus_patterns || [],
        transferability_assumptions: response.cross_paper_synthesis?.transferability_assumptions || [],
      }).catch(() => {});
      setStatus({ type: 'success', message: response.synthesis_summary || `Synthesized ${response.gaps.length} literature gap clusters.` });
    } catch (error) {
      setStatus({ type: 'error', message: error instanceof Error ? error.message : 'Failed to synthesize literature gaps' });
    } finally {
      setSynthesizingGaps(false);
    }
  };

  const handleRunValidationTrack = async (findingId: string, trackId: string) => {
    if (!selectedProject || !selectedPersona || selectedPersonaId === '') {
      setStatus({ type: 'error', message: 'Open a project before running validation.' });
      return;
    }
    const finding = researchWorkTemplate.literature_findings.find((item) => item.id === findingId);
    const track = finding?.validation_tracks?.find((item) => item.id === trackId);
    if (!finding || !track) return;
    setRunningValidationId(trackId);
    setStatus({ type: 'info', message: 'Running validation path...' });
    try {
      const response = await runValidationTrack(selectedProject.id, {
        persona_id: Number(selectedPersonaId),
        track,
        query: researchWorkTemplate.initial_query || focusQuestion,
        project_goal: selectedProject.project_goal,
        objective_title: selectedObjective?.title,
      });
      setResearchWorkTemplate((current) => ({
        ...current,
        literature_findings: current.literature_findings.map((item) =>
          item.id === findingId
            ? {
                ...item,
                validation_tracks: (item.validation_tracks || []).map((candidate) =>
                  candidate.id === trackId
                    ? { ...candidate, execution_result: { ...response.result, status: response.status, message: response.message } }
                    : candidate
                ),
              }
            : item
        ),
      }));
      setStatus({ type: response.status === 'error' ? 'error' : 'success', message: response.message });
    } catch (error) {
      setStatus({ type: 'error', message: error instanceof Error ? error.message : 'Failed to run validation' });
    } finally {
      setRunningValidationId(null);
    }
  };

  const handleLiteratureElicitationAnswerChange = (question: string, value: string) => {
    setLiteratureElicitationAnswers((current) => ({
      ...current,
      [question]: value,
    }));
  };

  const handleCaptureLiteratureTacitAnswer = (question: string) => {
    const answer = (literatureElicitationAnswers[question] || '').trim();
    if (!answer) {
      return;
    }

    const stableId = `tacit_${question.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '').slice(0, 48)}`;
    const nextJudgment: JudgmentCall = {
      id: stableId,
      stance: answer,
      rationale: `Response to literature-processing prompt: ${question}`,
      implication: 'Use this tacit judgment when prioritizing gaps, boundary conditions, and experiment-plan proposals.',
    };
    setResearchWorkTemplate((current) => {
      const existing = current.judgment_calls.some((item) => item.id === stableId);
      return {
        ...current,
        judgment_calls: existing
          ? current.judgment_calls.map((item) => (item.id === stableId ? nextJudgment : item))
          : [...current.judgment_calls, nextJudgment],
      };
    });
    setStatus({ type: 'success', message: 'Captured your literature judgment in the work template.' });
  };

  const handleCompleteLiteratureReview = (summary: string) => {
    setResearchWorkTemplate((current) => ({
      ...current,
      synthesis_memo: summary,
    }));
    setLiteratureReviewStage('summary');
    setStatus({
      type: 'success',
      message: 'Compiled the literature review summary. Review and edit the evidence synthesis here.',
    });
  };

  const updatePdfViewerFinding = (patch: Partial<ResearchFinding>) => {
    if (!pdfViewer) {
      return;
    }
    setResearchWorkTemplate((current) => ({
      ...current,
      literature_findings: current.literature_findings.map((finding) =>
        finding.id === pdfViewer.findingId ? { ...finding, ...patch } : finding
      ),
    }));
  };

  const handleRefreshOntology = async () => {
    if (!selectedProject || selectedPersonaId === '') {
      setOntologyStatus('Open a project workspace first.');
      return;
    }
    setLoadingOntology(true);
    setOntologyStatus('syncing workbench context into ontology...');
    try {
      const response = await syncProjectOntology(selectedProject.id, {
        persona_id: Number(selectedPersonaId),
        query: focusQuestion || researchWorkTemplate.initial_query || selectedProject.project_goal,
        objective_id: selectedObjective?.id,
        objective_title: selectedObjective?.title,
        objective_definition: selectedObjective?.definition,
        project_goal: selectedProject.project_goal,
        project_end_product: selectedProject.end_product,
        project_target_host: selectedProject.target_host,
        explicit_state: explicitWorkspaceState,
        tacit_state: tacitState,
        work_template: researchWorkTemplate,
        plan: agenticPlan,
      });
      setOntologyPreview(response);
      setOntologyStatus(response.sync_message || `synced ${response.nodes.length} entities and ${response.edges.length} relations`);
    } catch (error) {
      setOntologyStatus(error instanceof Error ? error.message : 'ontology sync failed');
    } finally {
      setLoadingOntology(false);
    }
  };

  const handleReviewOntologyNode = async (nodeId: string, nextStatus: 'confirmed' | 'rejected') => {
    if (!selectedProject) {
      return;
    }
    setOntologyStatus('saving ontology review...');
    try {
      const response = await reviewProjectOntologyItem(selectedProject.id, {
        target_type: 'node',
        target_id: nodeId,
        status: nextStatus,
      });
      setOntologyPreview(response);
      setOntologyStatus(response.sync_message || `ontology node ${nextStatus}`);
    } catch (error) {
      setOntologyStatus(error instanceof Error ? error.message : 'ontology review failed');
    }
  };

  const handleFormChange = (field: keyof ProjectFormState, value: string) => {
    setForm((current) => ({ ...current, [field]: value }));
  };

  const handleCopyWorkspaceDigest = async () => {
    try {
      await navigator.clipboard.writeText(workspaceDigest);
      setStatus({ type: 'success', message: 'Copied workspace digest to clipboard.' });
    } catch {
      setStatus({ type: 'error', message: 'Could not copy the workspace digest. Select the text manually instead.' });
    }
  };

  const handleOpenPdfInSystemViewer = async () => {
    if (!pdfViewer?.annotatedPath || !window.desktopApp?.openPath) {
      setStatus({ type: 'info', message: 'System PDF viewer is only available in the desktop app after annotation creates a local file.' });
      return;
    }
    const opened = await window.desktopApp.openPath(pdfViewer.annotatedPath);
    setStatus({
      type: opened.ok ? 'success' : 'error',
      message: opened.ok ? 'Opened annotated PDF in the system viewer.' : opened.error || 'Could not open the system PDF viewer.',
    });
  };

  const handleExportDiagnostics = async () => {
    if (!selectedProject) return;
    const issueNote =
      window.prompt(
        [
          'Optional: describe what went wrong or what looked low quality.',
          'Examples: bad literature query, irrelevant search results, weak annotations, missing evidence, confusing draft.',
        ].join('\n')
      ) || '';

    setExportingDiagnostics(true);
    setStatus({ type: 'info', message: 'Preparing diagnostics bundle...' });
    try {
      await logProjectEvent('diagnostics_context_snapshot', {
        project_id: selectedProject.id,
        project_name: selectedProject.name,
        persona_id: selectedPersonaId || null,
        persona_name: selectedPersona?.name || null,
        objective_id: selectedObjectiveId || null,
        objective_title: selectedObjective?.title || null,
        active_query_id: activeQueryId || null,
        focus_question: focusQuestion,
        literature_query: researchWorkTemplate.initial_query,
        literature_review_stage: literatureReviewStage,
        literature_findings: researchWorkTemplate.literature_findings.length,
        annotation_insights: researchWorkTemplate.literature_findings.reduce(
          (count, finding) => count + (finding.annotation_insights || []).length,
          0
        ),
        issue_note: issueNote.trim() || null,
        status_message: status?.message || null,
      }).catch(() => {});

      if (issueNote.trim()) {
        await logProjectEvent('diagnostics_issue_reported', {
          project_id: selectedProject.id,
          project_name: selectedProject.name,
          persona_id: selectedPersonaId || null,
          objective_id: selectedObjectiveId || null,
          focus_question: focusQuestion,
          literature_query: researchWorkTemplate.initial_query,
          issue_note: issueNote.trim(),
        }).catch(() => {});
      }

      const url = diagnosticsExportUrl({ project_id: selectedProject.id, include_pdfs: true });
      const link = document.createElement('a');
      link.href = url;
      link.download = '';
      document.body.appendChild(link);
      link.click();
      link.remove();
      setStatus({ type: 'success', message: 'Diagnostics download started. Share that zip when reporting the trial issue.' });
    } catch (error) {
      setStatus({ type: 'error', message: error instanceof Error ? error.message : 'Failed to export diagnostics' });
    } finally {
      setExportingDiagnostics(false);
    }
  };

  return (
    <div className={classNames('relative min-h-screen overflow-hidden p-0 text-slate-950 transition-colors duration-700', modePageTone[modeVisualKey] || modePageTone.general)}>
      <ModeBackdrop modeKey={modeVisualKey} />
      <div className="relative z-10 flex min-h-screen w-full flex-col gap-3 p-3">
        <WorkspaceHeader
          selectedProject={Boolean(selectedProject)}
          onReturnToLanding={handleReturnToLanding}
          onOpenMemory={selectedProject ? () => setMemoryDrawerOpen(true) : undefined}
          onExportDiagnostics={selectedProject ? handleExportDiagnostics : undefined}
          exportingDiagnostics={exportingDiagnostics}
          journeyHref={selectedProject ? `/journey?projectId=${selectedProject.id}` : undefined}
          memoryItemCount={tacitState.length}
          status={null}
        />

        {!selectedProject ? (
          <ProjectLandingShell
            form={form}
            onFormChange={handleFormChange}
            onCreateProject={handleCreateProject}
            creatingProject={creatingProject}
            loadingProjects={loadingProjects}
            projects={projects}
            selectedProjectId={selectedProjectId}
            onOpenProject={handleOpenProject}
            onDeleteProject={handleDeleteProject}
            deletingProjectId={deletingProjectId}
            onRefreshProjects={() => {
              loadProjects().catch(() => {});
            }}
          />
        ) : (
          <main className="grid min-h-0 flex-1 items-start gap-3 xl:grid-cols-[320px_minmax(0,1fr)]">
            <WorkflowStateSidebar
              selectedProject={selectedProject}
              focusQuestion={focusQuestion}
              selectedObjective={selectedObjective}
              researchWorkTemplate={researchWorkTemplate}
              literatureReviewStage={literatureReviewStage}
              onEditQuestion={handleRefineQuery}
              onChangeObjective={handleChooseAnotherObjective}
              onOpenLiteratureReview={() => handleOpenWorkspaceStage('review')}
              onOpenLiteratureSummary={() => handleOpenWorkspaceStage('summary')}
            />

            <div className="min-w-0 space-y-5">
              <ProjectOverview selectedProject={selectedProject} workingQuestion={focusQuestion} />

              <section className="rounded-[1.75rem] border border-slate-200 bg-white/90 p-4 shadow-sm backdrop-blur">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                  <div>
                    <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-500">Project investigations</div>
                    <div className="mt-1 text-lg font-semibold text-slate-950">Investigations</div>
                  </div>
                  <button
                    onClick={() => setShowNewQueryForm((current) => !current)}
                    className="rounded-2xl bg-slate-950 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800"
                  >
                    {showNewQueryForm ? 'Hide query form' : 'New query'}
                  </button>
                </div>
                <div className="mt-4 flex gap-2 overflow-x-auto pb-1">
                  {projectQueries.map((query, index) => {
                    const active = query.id === activeQueryId;
                    return (
                      <button
                        key={query.id}
                        onClick={() => handleSelectProjectQuery(query.id)}
                        className={classNames(
                          'min-w-[220px] rounded-2xl border px-3 py-2 text-left transition',
                          active ? 'border-slate-950 bg-slate-950 text-white' : 'border-slate-200 bg-slate-50 text-slate-800 hover:bg-white'
                        )}
                      >
                        <div className={classNames('text-[10px] font-semibold uppercase tracking-wide', active ? 'text-slate-300' : 'text-slate-500')}>
                          Query {index + 1}
                        </div>
                        <div className="mt-1 line-clamp-2 text-sm font-semibold">
                          {query.title && query.title !== 'Untitled query' ? query.title : queryTextFromSession(query) || 'Untitled query'}
                        </div>
                        <div className={classNames('mt-1 text-[11px]', active ? 'text-slate-300' : 'text-slate-500')}>
                          {new Date(query.updated_at).toLocaleString()}
                        </div>
                      </button>
                    );
                  })}
                </div>
                {(showNewQueryForm || projectQueries.length === 0) && (
                  <div className="mt-3 rounded-[1.4rem] border border-dashed border-slate-300 bg-white p-4">
                    <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-600">Create another query</div>
                    <textarea
                      value={newQueryText}
                      onChange={(event) => setNewQueryText(event.target.value)}
                      rows={4}
                      className="mt-3 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900"
                      placeholder="New investigation query"
                    />
                    <div className="mt-3 flex justify-end">
                      <button
                        onClick={handleCreateProjectQuery}
                        disabled={!newQueryText.trim() || creatingQuery}
                        className="rounded-2xl bg-slate-950 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {creatingQuery ? 'Creating...' : 'Create query and continue'}
                      </button>
                    </div>
                  </div>
                )}
              </section>

              <InlineWorkspaceStatus status={status} />

              {activeQueryId !== '' && (activeFlowStep === 'collaborator' || activeFlowStep === 'query') && (
                <div ref={querySectionRef} className="scroll-mt-28">
                  <QueryAlignmentSection focusQuestion={focusQuestion} onFocusQuestionChange={setFocusQuestion}
                    onSubmitQuery={handleClusterObjectives} submittingQuery={loadingObjectiveClusters} />
                </div>
              )}

              {activeQueryId !== '' && (activeFlowStep === 'objective' || activeFlowStep === 'workspace') && (
                <section
                  ref={objectiveSectionRef}
                  className={classNames(
                    'scroll-mt-28 rounded-[2rem] border p-5 shadow-[0_40px_120px_-60px_rgba(15,23,42,0.36)] backdrop-blur-md transition-all duration-700',
                    modeStudioTone[modeVisualKey] || modeStudioTone.general
                  )}
                >
                  {activeFlowStep === 'objective' && (
                  <ObjectiveClusteringSection
                    objectiveClusters={objectiveClusters}
                    selectedObjective={selectedObjective}
                    selectedObjectiveId={selectedObjectiveId}
                    objectivePickerCollapsed={objectivePickerCollapsed}
                    onSelectObjective={handleSelectObjective}
                    onGenerateModes={handleClusterObjectives}
                    loadingObjectiveClusters={loadingObjectiveClusters}
                    canGenerateModes={Boolean(selectedPersona && workingQuestionText)}
                    objectiveAnswers={objectiveAnswers}
                    onObjectiveAnswerChange={(question, value) =>
                      setObjectiveAnswers((current) => ({
                        ...current,
                        [question]: value,
                      }))
                    }
                    globalQuestions={globalQuestions}
                    globalQuestionAnswers={globalQuestionAnswers}
                    onGlobalQuestionChange={(question, value) =>
                      setGlobalQuestionAnswers((current) => ({
                        ...current,
                        [question]: value,
                      }))
                    }
                    onSetObjectivePickerCollapsed={setObjectivePickerCollapsed}
                    showManualObjectiveForm={showManualObjectiveForm}
                    manualObjective={manualObjective}
                    onToggleManualObjectiveForm={() => setShowManualObjectiveForm((current) => !current)}
                    onManualObjectiveChange={handleManualObjectiveChange}
                    onCreateManualObjective={handleCreateManualObjective}
                  />
                  )}

                  {activeFlowStep === 'workspace' && (
                <div ref={draftSectionRef} className="scroll-mt-28">
                  <LiteratureSurveySection
                    selectedObjective={selectedObjective}
                    onChooseAnotherObjective={handleChooseAnotherObjective}
                    researchWorkTemplate={researchWorkTemplate}
                    onResearchWorkTemplateChange={setResearchWorkTemplate}
                    onFetchLiterature={handleFetchLiterature}
                    fetchingLiterature={fetchingLiterature}
                    onSynthesizeGaps={handleSynthesizeLiteratureGaps}
                    synthesizingGaps={synthesizingGaps}
                    onRunValidationTrack={handleRunValidationTrack}
                    runningValidationId={runningValidationId}
                    literatureObjectiveLens={literatureObjectiveLens}
                    literatureProcessingSummary={literatureProcessingSummary}
                    literatureElicitationQuestions={literatureElicitationQuestions}
                    onPreparePaperPdf={handlePreparePaperPdf}
                    onBuildPaperOntology={handleBuildPaperOntology}
                    preparingPdfFindingId={preparingPdfFindingId}
                    buildingPaperOntologyId={buildingPaperOntologyId}
                    pdfAnnotationStatus={pdfAnnotationStatus}
                    pdfAnnotationFindingId={pdfAnnotationFindingId}
                    reviewStage={literatureReviewStage}
                    onCompleteLiteratureReview={handleCompleteLiteratureReview}
                  />
                </div>
                  )}
                </section>
              )}
            </div>
          </main>
        )}
      </div>

      {pdfViewer && (
        <div role="dialog" aria-modal="true" aria-label="Annotated PDF reader" style={{ paddingTop: 48 }} className="fixed inset-0 z-50 bg-slate-950">
          <div className="flex h-full w-full flex-col overflow-hidden bg-white">
            <div className="flex flex-col gap-3 border-b border-slate-200 bg-slate-50 px-5 py-3 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-500">Annotated PDF Reader</div>
                <div className="mt-1 line-clamp-2 text-sm font-semibold text-slate-950">{pdfViewer.title}</div>
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  onClick={handleOpenPdfInSystemViewer}
                  className="rounded-2xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-900 hover:bg-slate-50"
                >
                  Open system viewer
                </button>
                <a
                  href={pdfViewer.url}
                  target="_blank"
                  rel="noreferrer"
                  className="rounded-2xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-900 hover:bg-slate-50"
                >
                  New tab
                </a>
                <button
                  onClick={() => setPdfViewer(null)}
                  className="rounded-2xl bg-slate-950 px-3 py-2 text-xs font-semibold text-white hover:bg-slate-800"
                >
                  Close
                </button>
              </div>
            </div>

            <div className="grid min-h-0 flex-1 gap-0 lg:grid-cols-[minmax(0,1fr)_460px]">
              <iframe title="Annotated PDF" src={pdfViewer.url} className="h-full min-h-0 w-full bg-slate-950" />
              {pdfViewerFinding && <PaperEvidencePanel key={pdfViewer.findingId} finding={pdfViewerFinding}
                onPage={page=>setPdfViewer(current=>current ? {...current,url:`${current.url.split('#')[0]}#page=${page}`} : null)}
                onNoteChange={note=>updatePdfViewerFinding({synthesis_memo:note})}
                onOpenBoard={()=>{setPdfViewer(null);setMemoryDrawerOpen(true);}}
              />}
            </div>
          </div>
        </div>
      )}

      {memoryDrawerOpen && selectedProject && (
        <div ref={researchDialogRef} role="dialog" aria-modal="true" aria-label="Research board and project memory" style={{ paddingTop: 48 }} className="fixed inset-0 z-40 bg-slate-50">
          <aside className="h-full w-full overflow-y-auto bg-slate-50 px-4 pb-8 sm:px-8 lg:px-12">
            <div className="sticky top-0 z-10 mb-5 flex items-center justify-between gap-4 border-b border-slate-200 bg-slate-50 py-4">
              <div>
                <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-amber-800">Project Context</div>
                <div className="mt-1 text-2xl font-semibold tracking-tight text-slate-950">Research board and project memory</div>
              </div>
              <button
                onClick={() => setMemoryDrawerOpen(false)}
                className="rounded-2xl bg-slate-950 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800"
              >
                Close
              </button>
            </div>

            <div className="mb-4"><ResearchBoardPanel workspaceKey={boardWorkspaceKey} explicitState={explicitWorkspaceState} onBoardChange={setResearchBoard} onPrepareSources={handlePrepareEvidenceSources} /></div>
            <details className="mb-4"><summary className="cursor-pointer text-sm text-slate-600">Workspace digest and export</summary>
            <div className="mb-4 rounded-[1.4rem] border border-slate-200 bg-slate-50 p-4">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-600">Workspace Digest</div>
                  <div className="mt-1 text-sm leading-6 text-slate-700">
                    Copy this as a handoff/export seed. It combines explicit selections, literature notes, and user-entered judgments.
                  </div>
                </div>
                <button
                  onClick={handleCopyWorkspaceDigest}
                  className="rounded-2xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-900 hover:bg-slate-50"
                >
                  Copy digest
                </button>
              </div>
              <textarea
                readOnly
                value={workspaceDigest}
                rows={10}
                className="mt-3 w-full rounded-2xl border border-slate-200 bg-white px-3 py-2 text-xs leading-5 text-slate-800"
              />
            </div>

            </details>
            {selectedPersona ? (
              <div className="space-y-4">
                <details className="rounded-2xl border border-slate-200 p-3"><summary className="cursor-pointer text-sm text-slate-600">Project knowledge map</summary>
                <OntologyPanel
                  preview={ontologyPreview}
                  loading={loadingOntology}
                  status={ontologyStatus}
                  activeTrace={activeOntologyTrace}
                  onRefresh={handleRefreshOntology}
                  onReviewNode={handleReviewOntologyNode}
                />
                </details>
              </div>
            ) : (
              <div className="rounded-2xl border border-dashed border-amber-300 bg-amber-50 p-4 text-sm leading-6 text-amber-950">
                Project knowledge is available after workspace setup.
              </div>
            )}
          </aside>
        </div>
      )}
    </div>
  );
}

export default function BiotechProjectWorkspace() {
  return (
    <Suspense fallback={<main className="min-h-screen bg-slate-950 p-8 text-white">Loading workspace...</main>}>
      <BiotechProjectWorkspaceContent />
    </Suspense>
  );
}
