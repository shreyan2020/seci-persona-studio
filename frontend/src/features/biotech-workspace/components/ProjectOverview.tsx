import type { Project } from '@/features/biotech-workspace/types';

interface ProjectOverviewProps {
  selectedProject: Project;
  workingQuestion?: string;
}

export function ProjectOverview({ selectedProject, workingQuestion }: ProjectOverviewProps) {
  return (
    <section className="rounded-[1.75rem] border border-slate-200 bg-white/90 p-6 shadow-sm backdrop-blur">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="max-w-3xl">
          <div className="text-xs font-semibold uppercase tracking-[0.24em] text-emerald-700">Step 1 / Project Brief</div>
          <h2 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">{selectedProject.name}</h2>

        </div>

        <div className="grid gap-2 sm:grid-cols-2">
          <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-3">
            <div className="text-[11px] font-semibold uppercase tracking-wide text-emerald-800">End Product</div>
            <div className="mt-1 text-sm font-semibold text-emerald-950">{selectedProject.end_product}</div>
          </div>
          <div className="rounded-2xl border border-sky-200 bg-sky-50 p-3">
            <div className="text-[11px] font-semibold uppercase tracking-wide text-sky-800">Host</div>
            <div className="mt-1 text-sm font-semibold text-sky-950">{selectedProject.target_host}</div>
          </div>
        </div>
      </div>

      <div className="mt-4 grid gap-3 lg:grid-cols-3">
        {selectedProject.project_goal.trim() !== workingQuestion?.trim() && <div className="rounded-2xl border border-violet-200 bg-violet-50 p-4">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-violet-800">Project Goal</div>
          <div className="mt-2 text-sm text-violet-950">{selectedProject.project_goal || 'No project goal captured yet.'}</div>
        </div>}
        <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-600">Optional Cost Or Sourcing Context</div>
          <div className="mt-2 text-sm text-slate-800">
            {selectedProject.raw_material_focus || 'Not set. Add this only if sourcing or cost should shape later decisions.'}
          </div>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-600">Program Context</div>
          <div className="mt-2 text-sm text-slate-800">{selectedProject.notes || 'No extra constraints captured yet.'}</div>
        </div>
      </div>
    </section>
  );
}
