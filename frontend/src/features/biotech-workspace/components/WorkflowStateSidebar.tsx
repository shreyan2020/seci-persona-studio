import type { ObjectiveCluster, Project, ResearchWorkTemplate } from '@/features/biotech-workspace/types';
import { classNames } from '@/features/biotech-workspace/lib/utils';

interface WorkflowStateSidebarProps {
  selectedProject: Project;
  focusQuestion: string;
  selectedObjective: ObjectiveCluster | null;
  researchWorkTemplate: ResearchWorkTemplate;
  literatureReviewStage: 'review' | 'summary';
  onEditQuestion: () => void;
  onChangeObjective: () => void;
  onOpenLiteratureReview: () => void;
  onOpenLiteratureSummary: () => void;
}

function SidebarRow({
  label,
  value,
  detail,
  actionLabel,
  onAction,
  active,
  current = false,
}: {
  label: string;
  value: string;
  detail?: string;
  actionLabel: string;
  onAction: () => void;
  active: boolean;
  current?: boolean;
}) {
  return (
    <div className={classNames('border-t border-slate-200 px-4 py-4', current ? 'bg-emerald-50/70' : active ? 'bg-white' : 'bg-slate-50/70')}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-500">
            {label}
            {current ? <span className="ml-2 rounded-full bg-emerald-100 px-1.5 py-0.5 text-[9px] text-emerald-800">Current</span> : null}
          </div>
          <div className="mt-1 line-clamp-2 text-sm font-semibold leading-5 text-slate-950">{value}</div>
        </div>
        <button
          onClick={onAction}
          className="shrink-0 rounded-xl border border-slate-200 bg-white px-2 py-1 text-[11px] font-semibold text-slate-700 transition hover:bg-slate-50"
        >
          {actionLabel}
        </button>
      </div>
      {detail && <div className="mt-2 line-clamp-3 text-xs leading-5 text-slate-600">{detail}</div>}
    </div>
  );
}

export function WorkflowStateSidebar({
  selectedProject,
  focusQuestion,
  selectedObjective,
  researchWorkTemplate,
  literatureReviewStage,
  onEditQuestion,
  onChangeObjective,
  onOpenLiteratureReview,
  onOpenLiteratureSummary,
}: WorkflowStateSidebarProps) {
  return (
    <aside className="rounded-none border border-slate-200 bg-white/95 shadow-[18px_0_70px_-55px_rgba(15,23,42,0.65)] backdrop-blur xl:sticky xl:top-3 xl:max-h-[calc(100vh-1.5rem)] xl:overflow-y-auto">
      <div className="border-b border-slate-200 p-4">
        <div className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">Project Console</div>
        <div className="mt-2 text-lg font-semibold text-slate-950">{selectedProject.name}</div>
      </div>

      <SidebarRow
        label="Question"
        value={focusQuestion.trim() || selectedProject.project_goal || 'No working question yet'}
        actionLabel="Edit"
        onAction={onEditQuestion}
        active={Boolean(focusQuestion.trim())}
      />

      <SidebarRow
        label="Objective Mode"
        value={selectedObjective?.title || 'Not selected'}
        detail={selectedObjective?.subtitle}
        actionLabel={selectedObjective ? 'Change' : 'Open'}
        onAction={onChangeObjective}
        active={Boolean(selectedObjective)}
      />

      <SidebarRow
        label="Literature Sources"
        value={`${researchWorkTemplate.literature_findings.length} source${researchWorkTemplate.literature_findings.length === 1 ? '' : 's'} reviewed`}
        actionLabel="Open"
        onAction={onOpenLiteratureReview}
        active={researchWorkTemplate.literature_findings.length > 0}
        current={literatureReviewStage === 'review'}
      />

      <SidebarRow
        label="Literature Summary"
        value={
          researchWorkTemplate.synthesis_memo
            ? 'Final summary reviewed'
            : 'No final summary yet'
        }
        detail={
          researchWorkTemplate.synthesis_memo ||
          'Not finalized yet.'
        }
        actionLabel="Open"
        onAction={onOpenLiteratureSummary}
        active={Boolean(researchWorkTemplate.synthesis_memo)}
        current={literatureReviewStage === 'summary'}
      />

    </aside>
  );
}
