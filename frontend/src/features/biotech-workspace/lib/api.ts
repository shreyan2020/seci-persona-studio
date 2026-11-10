import type { ResearchBoard, BoardOperation } from '../board-types';
import type {
  CreateProjectResponse,
  FetchProjectLiteratureResponse,
  GeneratePlanResponse,
  ObjectiveClustersResponse,
  OntologyPreviewResponse,
  PreparePaperPdfResponse,
  ProjectExecutionRunResponse,
  ProjectFormState,
  ProjectJourneyResponse,
  ProjectQuerySession,
  ProjectQuerySessionListResponse,
  ResearchFinding,
  ResearchWorkTemplate,
  SynthesizeLiteratureGapsResponse,
  ValidationTrack,
  ProjectsResponse,
  TacitMemoryItem,
  ProjectWorkspaceResponse,
  WorkspaceMemoryResponse,
} from '@/features/biotech-workspace/types';
import { API_BASE } from './api-base';

export { API_BASE };

function formatApiError(payload: unknown, fallback: string): string {
  if (!payload || typeof payload !== 'object') return fallback;
  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (detail && typeof detail === 'object') {
    const message = (detail as { message?: unknown }).message;
    const trace = (detail as { workflow_trace?: Array<{ message?: string; errors?: string[] }> }).workflow_trace || [];
    const traceError = trace
      .flatMap((item) => item.errors || [])
      .find((item) => item.trim());
    if (typeof message === 'string' && message.trim()) {
      return traceError ? `${message} (${traceError})` : message;
    }
    if (traceError) return traceError;
  }
  const message = (payload as { message?: unknown }).message;
  return typeof message === 'string' && message.trim() ? message : fallback;
}

export async function fetchProjects(): Promise<ProjectsResponse> {
  const response = await fetch(`${API_BASE}/api/projects`, { cache: 'no-store' });
  if (!response.ok) throw new Error('Failed to load projects');
  return response.json();
}

export async function clusterObjectives(payload: {
  query: string;
  context?: string;
  k?: number;
  persona_id?: number;
}): Promise<ObjectiveClustersResponse> {
  const response = await fetch(`${API_BASE}/objectives`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to cluster objectives');
  }
  return response.json();
}

export async function createProject(payload: ProjectFormState): Promise<CreateProjectResponse> {
  const response = await fetch(`${API_BASE}/api/projects`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to create project');
  }
  return response.json();
}

export async function deleteProject(projectId: number): Promise<{ deleted: boolean; project_id: number }> {
  const response = await fetch(`${API_BASE}/api/projects/${projectId}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to delete project');
  }
  return response.json();
}

export async function generateProjectPlan(
  projectId: number,
  payload: {
    persona_id: number;
    focus_question?: string;
    notes?: string;
    clarifying_answers?: Record<string, string>;
    reasoning_notes?: string;
    work_template?: ResearchWorkTemplate | null;
  }
): Promise<GeneratePlanResponse> {
  const response = await fetch(`${API_BASE}/api/projects/${projectId}/plan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to generate project draft');
  }
  return response.json();
}

export async function fetchWorkspaceState(projectId: number, personaId: number): Promise<ProjectWorkspaceResponse> {
  const response = await fetch(`${API_BASE}/api/projects/${projectId}/workspace/${personaId}`, { cache: 'no-store' });
  if (!response.ok) throw new Error('Failed to load saved workspace');
  return response.json();
}

export async function fetchProjectLiterature(
  projectId: number,
  payload: {
    persona_id: number;
    query: string;
    objective_id?: string;
    objective_title?: string;
    objective_definition?: string;
    objective_signals?: string[];
    project_goal?: string;
    project_end_product?: string;
    project_target_host?: string;
    clarifying_answers?: Record<string, string>;
    objective_answers?: Record<string, string>;
    global_question_answers?: Record<string, string>;
    reasoning_notes?: string;
    work_template?: ResearchWorkTemplate | null;
    max_results?: number;
    existing_citations?: string[];
  }
): Promise<FetchProjectLiteratureResponse> {
  const response = await fetch(`${API_BASE}/api/projects/${projectId}/literature`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to fetch literature');
  }
  return response.json();
}

export async function synthesizeLiteratureGaps(
  projectId: number,
  payload: {
    persona_id: number;
    query: string;
    project_goal?: string;
    project_end_product?: string;
    project_target_host?: string;
    objective_id?: string;
    objective_title?: string;
    objective_definition?: string;
    objective_signals?: string[];
    work_template: ResearchWorkTemplate;
    max_gaps?: number;
  }
): Promise<SynthesizeLiteratureGapsResponse> {
  const response = await fetch(`${API_BASE}/api/projects/${projectId}/literature/gaps`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to synthesize literature gaps');
  }
  return response.json();
}

export async function runValidationTrack(
  projectId: number,
  payload: {
    persona_id: number;
    track: ValidationTrack;
    query?: string;
    project_goal?: string;
    objective_title?: string;
  }
): Promise<{ status: 'success' | 'unsupported' | 'error'; message: string; result: Record<string, unknown> }> {
  const response = await fetch(`${API_BASE}/api/projects/${projectId}/validation/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to run validation');
  }
  return response.json();
}

export async function fetchProjectQueries(projectId: number): Promise<ProjectQuerySessionListResponse> {
  const response = await fetch(`${API_BASE}/api/projects/${projectId}/queries`, { cache: 'no-store' });
  if (!response.ok) throw new Error('Failed to load project queries');
  return response.json();
}

export async function fetchProjectJourney(projectId: number): Promise<ProjectJourneyResponse> {
  const response = await fetch(`${API_BASE}/api/projects/${projectId}/journey`, { cache: 'no-store' });
  if (!response.ok) throw new Error('Failed to load project journey');
  return response.json();
}

export async function logProjectEvent(event_type: string, payload: Record<string, unknown>): Promise<{ status: string }> {
  const response = await fetch(`${API_BASE}/log_event`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ event_type, payload }),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to log project event');
  }
  return response.json();
}

export async function createProjectQuery(
  projectId: number,
  payload: { title?: string; query: string; state?: Record<string, unknown> }
): Promise<ProjectQuerySession> {
  const response = await fetch(`${API_BASE}/api/projects/${projectId}/queries`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to create project query');
  }
  return response.json();
}

export async function updateProjectQuery(
  projectId: number,
  queryId: number,
  payload: { title?: string; query?: string; state?: Record<string, unknown> }
): Promise<ProjectQuerySession> {
  const response = await fetch(`${API_BASE}/api/projects/${projectId}/queries/${queryId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to save project query');
  }
  return response.json();
}

export async function preparePaperPdf(
  projectId: number,
  payload: {
    persona_id: number;
    finding: ResearchFinding;
    query: string;
    project_goal?: string;
    project_end_product?: string;
    project_target_host?: string;
    persona_name?: string;
    persona_focus?: string;
    objective_id?: string;
    objective_title?: string;
    objective_definition?: string;
    objective_signals?: string[];
    max_annotations?: number;
  }
): Promise<PreparePaperPdfResponse> {
  const response = await fetch(`${API_BASE}/api/projects/${projectId}/literature/pdf`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(formatApiError(err, 'Failed to prepare annotated PDF'));
  }
  return response.json();
}

export async function fetchWorkspaceMemory(workspaceKey: string): Promise<WorkspaceMemoryResponse> {
  const response = await fetch(`${API_BASE}/api/workspace-memory/${encodeURIComponent(workspaceKey)}`, { cache: 'no-store' });
  if (!response.ok) throw new Error('Failed to load workspace memory');
  return response.json();
}

export async function saveWorkspaceMemory(
  workspaceKey: string,
  payload: {
    scope: string;
    explicit_state: Record<string, unknown>;
    tacit_state: TacitMemoryItem[];
    handoff_summary: string;
  }
): Promise<WorkspaceMemoryResponse> {
  const response = await fetch(`${API_BASE}/api/workspace-memory/${encodeURIComponent(workspaceKey)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to save workspace memory');
  }
  return response.json();
}

export function diagnosticsExportUrl(payload: { project_id?: number; include_pdfs?: boolean } = {}): string {
  const params = new URLSearchParams();
  if (payload.project_id) params.set('project_id', String(payload.project_id));
  if (payload.include_pdfs !== undefined) params.set('include_pdfs', String(payload.include_pdfs));
  const query = params.toString();
  return `${API_BASE}/api/diagnostics/export${query ? `?${query}` : ''}`;
}

export async function exportDiagnostics(payload: { project_id?: number; include_pdfs?: boolean } = {}): Promise<Blob> {
  const url = diagnosticsExportUrl(payload);
  const response = await fetch(url, { cache: 'no-store' });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to export diagnostics');
  }
  return response.blob();
}

export async function fetchOntologyPreview(
  projectId: number,
  payload: {
    persona_id?: number;
    query?: string;
    objective_id?: string;
    objective_title?: string;
    objective_definition?: string;
    project_goal?: string;
    project_end_product?: string;
    project_target_host?: string;
    explicit_state?: Record<string, unknown>;
    tacit_state?: TacitMemoryItem[];
    work_template?: ResearchWorkTemplate | null;
    plan?: GeneratePlanResponse['plan'] | null;
  }
): Promise<OntologyPreviewResponse> {
  const response = await fetch(`${API_BASE}/api/projects/${projectId}/ontology/preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to build ontology preview');
  }
  return response.json();
}

export async function fetchStoredOntology(projectId: number): Promise<OntologyPreviewResponse> {
  const response = await fetch(`${API_BASE}/api/projects/${projectId}/ontology`, { cache: 'no-store' });
  if (!response.ok) throw new Error('Failed to load project ontology');
  return response.json();
}

export async function syncProjectOntology(
  projectId: number,
  payload: {
    persona_id?: number;
    query?: string;
    objective_id?: string;
    objective_title?: string;
    objective_definition?: string;
    project_goal?: string;
    project_end_product?: string;
    project_target_host?: string;
    explicit_state?: Record<string, unknown>;
    tacit_state?: TacitMemoryItem[];
    work_template?: ResearchWorkTemplate | null;
    plan?: GeneratePlanResponse['plan'] | null;
  }
): Promise<OntologyPreviewResponse> {
  const response = await fetch(`${API_BASE}/api/projects/${projectId}/ontology/sync`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to sync project ontology');
  }
  return response.json();
}

export async function reviewProjectOntologyItem(
  projectId: number,
  payload: {
    target_type: 'node' | 'edge';
    target_id: string;
    status: 'inferred' | 'confirmed' | 'rejected' | 'edited';
    reviewer_note?: string;
  }
): Promise<OntologyPreviewResponse> {
  const response = await fetch(`${API_BASE}/api/projects/${projectId}/ontology/review`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to update ontology review state');
  }
  return response.json();
}

export async function buildPaperOntology(
  projectId: number,
  payload: {
    persona_id?: number;
    finding: ResearchFinding;
    query?: string;
    objective_id?: string;
    objective_title?: string;
    objective_definition?: string;
    project_goal?: string;
    project_end_product?: string;
    project_target_host?: string;
    persist?: boolean;
  }
): Promise<OntologyPreviewResponse> {
  const response = await fetch(`${API_BASE}/api/projects/${projectId}/literature/ontology`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to build paper ontology');
  }
  return response.json();
}

export async function fetchLatestExecutionRun(projectId: number, personaId: number): Promise<ProjectExecutionRunResponse> {
  const response = await fetch(`${API_BASE}/api/projects/${projectId}/execution-runs/latest?persona_id=${personaId}`, { cache: 'no-store' });
  if (!response.ok) throw new Error('Failed to load execution run');
  return response.json();
}

export async function fetchExecutionRun(projectId: number, runId: number, signal?: AbortSignal): Promise<ProjectExecutionRunResponse> {
  const response = await fetch(`${API_BASE}/api/projects/${projectId}/execution-runs/${runId}`, { cache: 'no-store', signal });
  if (!response.ok) throw new Error('Failed to load execution run');
  return response.json();
}

export async function startExecutionRun(
  projectId: number,
  payload: {
    persona_id: number;
    focus_question?: string;
    notes?: string;
    clarifying_answers?: Record<string, string>;
    reasoning_notes?: string;
    work_template?: ResearchWorkTemplate | null;
    objective_id?: string;
    objective_title?: string;
    objective_definition?: string;
    objective_signals?: string[];
  }
): Promise<ProjectExecutionRunResponse> {
  const response = await fetch(`${API_BASE}/api/projects/${projectId}/execution-runs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to start execution run');
  }
  return response.json();
}

export async function saveWorkspaceState(
  projectId: number,
  personaId: number,
  payload: {
    focus_question?: string;
    clarifying_answers?: Record<string, string>;
    reasoning_notes?: string;
    work_template?: ResearchWorkTemplate | null;
    plan?: GeneratePlanResponse['plan'] | null;
    selected_step_id?: string;
  }
): Promise<ProjectWorkspaceResponse> {
  const response = await fetch(`${API_BASE}/api/projects/${projectId}/workspace/${personaId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to save workspace');
  }
  return response.json();
}


export async function fetchResearchBoard(workspaceKey: string): Promise<{ board: ResearchBoard | null }> {
  const response = await fetch(`${API_BASE}/api/research-board?workspace_key=${encodeURIComponent(workspaceKey)}`, { cache: 'no-store' });
  if (!response.ok) throw new Error('Could not load the research board');
  return response.json();
}

export async function mutateResearchBoard(operation: BoardOperation, payload: Record<string, unknown>): Promise<{ board: ResearchBoard }> {
  const response = await fetch(`${API_BASE}/api/research-board/${operation}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(typeof error.detail === 'string' ? error.detail : 'The board could not be updated. Reload and try again.');
  }
  return response.json();
}
