export interface PlanRisk {
  risk: string;
  mitigation: string;
}

export interface PlanStep {
  id: string;
  title: string;
  description: string;
  why_this_step: string;
  objective_link: string;
  persona_link: string;
  evidence_facts: string[];
  examples: string[];
  dependencies: string[];
  source_refs: string[];
  gap_refs: string[];
  judgment_refs: string[];
  validation_refs: string[];
  expected_outcome: string;
  confidence: number;
}

export interface AgenticPlan {
  plan_title: string;
  strategy_summary: string;
  success_criteria: string[];
  assumptions: string[];
  risks: PlanRisk[];
  steps: PlanStep[];
}

export interface GeneratePlanResponse {
  plan: AgenticPlan;
}

export interface ObjectiveCluster {
  id: string;
  title: string;
  subtitle: string;
  definition: string;
  signals: string[];
  facet_questions: string[];
  exemplar_answer: string;
}

export interface ObjectiveClustersResponse {
  objectives: ObjectiveCluster[];
  global_questions: string[];
}

export interface ProjectPersona {
  persona_id: number;
  name: string;
  role: string;
  workflow_stage: string;
  focus_area: string;
  summary: string;
  goals: string[];
  workflow_focus: string[];
  starter_questions: string[];
  version: number;
}

export interface Project {
  id: number;
  scope_id: string;
  name: string;
  end_product: string;
  target_host: string;
  project_goal: string;
  raw_material_focus?: string | null;
  notes?: string | null;
  status: 'draft' | 'active' | 'archived';
  created_at: string;
  updated_at: string;
  personas: ProjectPersona[];
}

export interface ProjectsResponse {
  projects: Project[];
}

export interface CreateProjectResponse {
  project: Project;
  created_persona_ids: number[];
}

export interface CreateProjectCollaboratorResponse {
  project: Project;
  persona: ProjectPersona;
}

export interface ProjectQuerySession {
  id: number;
  project_id: number;
  title: string;
  query: string;
  state: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ProjectQuerySessionListResponse {
  queries: ProjectQuerySession[];
}

export interface ProjectJourneyEvent {
  id: number;
  event_type: string;
  title: string;
  detail: string;
  timestamp: string;
  query_id?: number | null;
  persona_id?: number | null;
  objective_id?: string | null;
  payload: Record<string, unknown>;
}

export interface ProjectJourneyPath {
  id: string;
  query_id: number;
  query_title: string;
  query: string;
  selected_persona_id?: number | null;
  selected_persona_name?: string | null;
  selected_objective_id?: string | null;
  selected_objective_title?: string | null;
  active_flow_step?: string | null;
  updated_at: string;
  literature_count: number;
  judgment_count: number;
  gap_count: number;
  proposal_count: number;
  plan_step_count: number;
  summary: string;
  next_action_hint: string;
  recent_events: ProjectJourneyEvent[];
}

export interface ProjectJourneySummary {
  total_queries: number;
  explored_collaborators: number;
  explored_objectives: number;
  literature_findings: number;
  judgment_calls: number;
  proposal_candidates: number;
  event_count: number;
}

export interface ProjectJourneyResponse {
  project: Project;
  summary: ProjectJourneySummary;
  paths: ProjectJourneyPath[];
  events: ProjectJourneyEvent[];
}

export interface ResearchFinding {
  pdf_reader?: { context_key: string; url: string; modified?: string; path?: string };
  structured_notes?: PaperStructuredNotes;
  id: string;
  citation: string;
  labels: string[];
  knowns: string[];
  unknowns: string[];
  relevance: string;
  source_ids?: Record<string, string>;
  annotation_insights?: string[];
  generated_questions?: string[];
  annotations?: PaperAnnotation[];
  judgment_calls?: JudgmentCall[];
  validation_tracks?: ValidationTrack[];
  synthesis_memo?: string;
}

export interface ResearchGap {
  id: string;
  theme: string;
  supporting_signals: string[];
  next_question: string;
  priority_note: string;
}

export interface CrossPaperSynthesis {
  summary: string;
  evidence_matrix: Record<string, unknown>[];
  consensus_patterns: string[];
  contradictions_or_tensions: string[];
  transferability_assumptions: string[];
  gap_rationale: string[];
  validation_priorities: string[];
}

export interface JudgmentCall {
  id: string;
  stance: string;
  rationale: string;
  implication: string;
}

export interface ValidationTrack {
  id: string;
  target: string;
  method: string;
  questions: string[];
  success_signal: string;
  execution_result?: Record<string, unknown>;
}

export interface ProposalCandidate {
  id: string;
  title: string;
  why_now: string;
  experiment_outline: string;
  readouts: string[];
  source_refs?: string[];
  gap_refs?: string[];
  judgment_refs?: string[];
  validation_refs?: string[];
}

export interface ResearchWorkTemplate {
  initial_query: string;
  literature_findings: ResearchFinding[];
  common_gaps: ResearchGap[];
  judgment_calls: JudgmentCall[];
  validation_tracks: ValidationTrack[];
  proposal_candidates: ProposalCandidate[];
  synthesis_memo: string;
}

export interface LiteratureToolTrace {
  tool_name: string;
  query: string;
  result_count: number;
  status: 'success' | 'error';
  error_message?: string | null;
}

export interface WorkflowStageTrace {
  run_id: string;
  stage: string;
  status: 'success' | 'success_with_warnings' | 'skipped' | 'missing_capability' | 'error';
  message: string;
  started_at?: string | null;
  ended_at?: string | null;
  duration_ms?: number | null;
  inputs: Record<string, unknown>;
  outputs: Record<string, unknown>;
  errors: string[];
}

export interface FetchProjectLiteratureResponse {
  findings: ResearchFinding[];
  tool_trace: LiteratureToolTrace;
  objective_lens?: string | null;
  processing_summary: string;
  elicitation_questions: string[];
  workflow_trace?: WorkflowStageTrace[];
  ontology_trace?: OntologyUsageTrace | null;
}

export interface SynthesizeLiteratureGapsResponse {
  gaps: ResearchGap[];
  synthesis_summary: string;
  cross_paper_synthesis: CrossPaperSynthesis;
}

export interface PaperAnnotation {
  passage_id?: string;
  source_sha256?: string;
  evidence_kind?: 'pdf_passage' | 'unverified';
  page: number;
  snippet: string;
  reason: string;
  matched_terms: string[];
  score: number;
  elicitation_prompts?: PaperPassageElicitationPrompt[];
}

export interface PaperPassageElicitationPrompt {
  id: string;
  category: 'transferability' | 'feasibility' | 'constraints' | 'evidence_trust' | 'validation' | 'handoff' | 'other';
  question: string;
  why_it_matters: string;
  evidence_refs: string[];
  priority: 'low' | 'medium' | 'high';
}

export interface PaperStructuredNotes {
  evidence_claims: string[];
  methods: string[];
  quantitative_benchmarks: string[];
  limitations: string[];
  transferability_notes: string[];
  research_gaps: string[];
}

export interface PreparePaperPdfResponse {
  status: 'success' | 'not_open_access' | 'error';
  message: string;
  paper_id?: string | null;
  pmid?: string | null;
  pmcid?: string | null;
  source_pdf_url?: string | null;
  original_pdf_path?: string | null;
  annotated_pdf_path?: string | null;
  annotated_pdf_url?: string | null;
  annotations: PaperAnnotation[];
  insights: string[];
  passage_insights: string[];
  structured_notes: PaperStructuredNotes;
  research_questions: string[];
  visual_annotations: boolean;
}

export interface TacitMemoryItem {
  id: string;
  label: string;
  inference: string;
  evidence: string[];
  confidence: number;
  status: 'inferred' | 'confirmed' | 'rejected' | 'edited';
  reviewer_note?: string | null;
}

export interface TacitElicitationQuestion {
  id: string;
  category: 'transferability' | 'feasibility' | 'constraints' | 'evidence_trust' | 'validation' | 'handoff';
  question: string;
  why_it_matters: string;
  evidence_refs: string[];
  suggested_owner?: string | null;
  priority: 'low' | 'medium' | 'high';
}

export interface BeliefHypothesis {
  id: string;
  proposition: string;
  probability: number;
  evidence_refs: string[];
}

export interface BeliefVariable {
  id: string;
  label: string;
  hypotheses: BeliefHypothesis[];
}

export interface ElicitationAnswerOption {
  id: string;
  label: string;
  allows_free_text: boolean;
}

export interface HypothesisAnswerPrediction {
  hypothesis_id: string;
  option_probabilities: Record<string, number>;
}

export interface QuestionLikelihoodModel {
  id: string;
  weight: number;
  predictions: HypothesisAnswerPrediction[];
}

export interface DecisionWorld {
  id: string;
  label: string;
  probability: number;
  hypothesis_assignments: Record<string, string>;
}

export interface DecisionAction {
  id: string;
  label: string;
  loss_by_world: Record<string, number>;
}

export interface AdaptiveElicitationQuestion {
  id: string;
  target_variable_id: string;
  question: string;
  why_it_matters: string;
  gap_id?: string | null;
  gap_type?: string | null;
  evidence_refs?: string[];
  resolution_rationale?: string;
  alternative_resolution?: string;
  answer_options: ElicitationAnswerOption[];
  predictions: HypothesisAnswerPrediction[];
  likelihood_models?: QuestionLikelihoodModel[];
  decision_relevance: number;
  answerability: number;
  estimated_effort_seconds: number;
  question_cost?: number;
  expected_information_gain: number;
  expected_geodesic_gain?: number;
  geometric_novelty?: number;
  target_normalized_uncertainty?: number;
  expected_bayes_risk_reduction?: number;
  robust_bayes_risk_reduction?: number;
  probability_of_action_change?: number;
  net_value?: number;
  selection_score: number;
  selection_rationale: string;
  status: 'candidate' | 'answered' | 'skipped';
}

export interface AdaptiveElicitationAnswer {
  question_id: string;
  option_id: string;
  option_label: string;
  free_text: string;
  entropy_before: number;
  entropy_after: number;
  information_gain: number;
  belief_shift?: number;
}

export interface AdaptiveElicitationSession {
  id: string;
  workspace_key: string;
  context_digest: string;
  belief_variables: BeliefVariable[];
  decision_worlds?: DecisionWorld[];
  decision_actions?: DecisionAction[];
  decision_model_source?: 'explicit' | 'derived';
  candidate_questions: AdaptiveElicitationQuestion[];
  current_question_id?: string | null;
  answer_history: AdaptiveElicitationAnswer[];
  initial_entropy: number;
  current_entropy: number;
  uncertainty_reduction: number;
  initial_normalized_uncertainty?: number;
  normalized_uncertainty?: number;
  initial_bayes_risk?: number;
  current_bayes_risk?: number;
  bayes_risk_reduction?: number;
  current_best_action_id?: string | null;
  status: 'active' | 'complete';
  selection_mode?: 'discrimination' | 'discovery' | 'complete';
  stopping_reason?: string | null;
  generation_source: 'harness' | 'model' | 'fallback';
  epistemic_trace?: {
    run_id?: string;
    world_summary?: string;
    sources_processed?: number;
    accepted_claims?: number;
    rejected_claims?: number;
    gap_count?: number;
    routing_counts?: Record<string, number>;
    gaps?: Array<{
      id: string;
      statement: string;
      gap_type: string;
      recommended_action: string;
      routing_rationale: string;
    }>;
  };
  max_questions: number;
  min_information_gain: number;
  min_geodesic_gain?: number;
  max_normalized_uncertainty_for_stop?: number;
  robust_quantile?: number;
  cost_per_second?: number;
  min_net_value?: number;
}

export interface AdaptiveElicitationResponse {
  session: AdaptiveElicitationSession;
}

export interface WorkspaceMemory {
  workspace_key: string;
  scope: string;
  explicit_state: Record<string, unknown>;
  tacit_state: TacitMemoryItem[];
  handoff_summary: string;
  updated_at?: string | null;
}

export interface WorkspaceMemoryResponse {
  memory?: WorkspaceMemory | null;
}

export interface InferWorkspaceMemoryResponse {
  tacit_state: TacitMemoryItem[];
  elicitation_questions: TacitElicitationQuestion[];
  handoff_summary: string;
}

export interface OntologyNode {
  id: string;
  type: string;
  label: string;
  description: string;
  source_refs: string[];
  attributes: Record<string, unknown>;
  confidence: number;
  status: 'inferred' | 'confirmed' | 'rejected' | 'edited';
}

export interface OntologyEdge {
  id: string;
  source: string;
  target: string;
  relation: string;
  evidence: string[];
  confidence: number;
  status: 'inferred' | 'confirmed' | 'rejected' | 'edited';
}

export interface OntologyQueryAugmentation {
  expanded_terms: string[];
  filters: Record<string, string[]>;
  reasoning_lenses: string[];
  tacit_context: string[];
  search_routing: string[];
}

export interface OntologyUsageTrace {
  id: string;
  purpose: string;
  title: string;
  summary: string;
  node_ids: string[];
  edge_ids: string[];
  expanded_terms: string[];
  reasoning_lenses: string[];
  tacit_context: string[];
  search_routing: string[];
}

export interface OntologyPreviewResponse {
  project_id: number;
  summary: string;
  nodes: OntologyNode[];
  edges: OntologyEdge[];
  query_augmentation: OntologyQueryAugmentation;
  persisted: boolean;
  sync_message: string;
}

export interface ProjectWorkspaceState {
  project_id: number;
  persona_id: number;
  focus_question?: string | null;
  clarifying_answers: Record<string, string>;
  reasoning_notes?: string | null;
  work_template?: ResearchWorkTemplate | null;
  plan?: AgenticPlan | null;
  selected_step_id?: string | null;
  updated_at?: string | null;
}

export interface ProjectWorkspaceResponse {
  state?: ProjectWorkspaceState | null;
}

export interface ProjectExecutionEvent {
  id: number;
  run_id: number;
  event_type: string;
  stage_key?: string | null;
  title: string;
  detail: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface ProjectExecutionRun {
  id: number;
  project_id: number;
  persona_id: number;
  run_kind: string;
  status: 'queued' | 'running' | 'completed' | 'failed';
  objective_id?: string | null;
  mode_label?: string | null;
  focus_question?: string | null;
  current_stage?: string | null;
  summary?: string | null;
  error_message?: string | null;
  created_at: string;
  updated_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  final_work_template?: ResearchWorkTemplate | null;
  final_plan?: AgenticPlan | null;
}

export interface ProjectExecutionRunResponse {
  run?: ProjectExecutionRun | null;
  events: ProjectExecutionEvent[];
}

export interface ProjectFormState {
  name: string;
  end_product: string;
  target_host: string;
  project_goal: string;
  raw_material_focus: string;
  notes: string;
}

export interface ObjectiveFrame {
  label: string;
  description: string;
  draftLabel: string;
  rawMaterialGuidance: string;
}

export interface StatusState {
  type: 'info' | 'success' | 'error';
  message: string;
}

export interface RankedPersona {
  persona: ProjectPersona;
  score: number;
}
