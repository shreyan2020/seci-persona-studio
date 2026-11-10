import Link from 'next/link';
import { LoadingSpinner } from '@/features/biotech-workspace/components/LoadingSpinner';
import type { Project, ProjectFormState } from '@/features/biotech-workspace/types';
import { classNames } from '@/features/biotech-workspace/lib/utils';

interface ProjectLandingShellProps {
  form: ProjectFormState;
  onFormChange: (field: keyof ProjectFormState, value: string) => void;
  onCreateProject: () => void;
  creatingProject: boolean;
  loadingProjects: boolean;
  projects: Project[];
  selectedProjectId: number | '';
  onOpenProject: (projectId: number) => void;
  onDeleteProject: (project: Project) => void;
  deletingProjectId: number | null;
  onRefreshProjects: () => void;
}

export function ProjectLandingShell({
  form,
  onFormChange,
  onCreateProject,
  creatingProject,
  loadingProjects,
  projects,
  selectedProjectId,
  onOpenProject,
  onDeleteProject,
  deletingProjectId,
  onRefreshProjects,
}: ProjectLandingShellProps) {
  return (
    <div className="grid gap-6 xl:grid-cols-[360px_minmax(0,1fr)]">
      <aside className="space-y-5">
        <section className="border border-cyan-200 bg-cyan-50 p-5">
          <h2 className="text-lg font-semibold text-slate-950">Explore a research example</h2>
          <p className="mt-2 text-sm leading-6 text-slate-700">Compare itaconic-acid experiments and follow three specialist perspectives on the evidence.</p>
          <Link href="/examples/itaconate" className="mt-4 inline-block rounded-xl bg-cyan-900 px-4 py-3 text-sm font-semibold text-white">Open example project</Link>
          <p className="mt-2 text-xs text-slate-600">Ready to browse. No setup or model server needed.</p>
        </section>
        <section className="rounded-none border border-slate-200 bg-white/90 p-5 shadow-sm backdrop-blur">
          <div className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">Create Project</div>
          <div className="mt-4 space-y-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-700">Project name</label>
              <input
                value={form.name}
                onChange={(e) => onFormChange('name', e.target.value)}
                className="w-full rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900"
                placeholder="Flavonoid program"
              />
            </div>

            <div>
              <label className="mb-1 block text-xs font-medium text-slate-700">End product</label>
              <textarea
                value={form.end_product}
                onChange={(e) => onFormChange('end_product', e.target.value)}
                rows={3}
                className="w-full rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900"
                placeholder="Engineer flavonoid production in yeast"
              />
            </div>

            <div>
              <label className="mb-1 block text-xs font-medium text-slate-700">Target host</label>
              <input
                value={form.target_host}
                onChange={(e) => onFormChange('target_host', e.target.value)}
                className="w-full rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900"
                placeholder="Saccharomyces cerevisiae"
              />
            </div>

            <div>
              <label className="mb-1 block text-xs font-medium text-slate-700">Program goal</label>
              <textarea
                value={form.project_goal}
                onChange={(e) => onFormChange('project_goal', e.target.value)}
                rows={4}
                className="w-full rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900"
                placeholder="Example: draft experiment plan for a project to engineer flavonoid production in yeast"
              />
            </div>

            <div>
              <label className="mb-1 block text-xs font-medium text-slate-700">Raw material or cost lens (optional)</label>
              <input
                value={form.raw_material_focus}
                onChange={(e) => onFormChange('raw_material_focus', e.target.value)}
                className="w-full rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900"
                placeholder="Only fill this if sourcing/cost is an explicit concern"
              />
            </div>

            <div>
              <label className="mb-1 block text-xs font-medium text-slate-700">Context and constraints (optional)</label>
              <textarea
                value={form.notes}
                onChange={(e) => onFormChange('notes', e.target.value)}
                rows={4}
                className="w-full rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900"
                placeholder="Examples: limited wet-lab budget, prefer literature-first reasoning, need decision-ready tradeoffs for the next team review"
              />
            </div>

            <button
              onClick={onCreateProject}
              disabled={creatingProject}
              className="w-full rounded-2xl bg-slate-950 px-4 py-3 text-sm font-semibold text-white shadow-sm hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {creatingProject ? 'Creating project...' : 'Create project'}
            </button>
          </div>
        </section>

        <section className="rounded-none border border-slate-200 bg-white/90 p-5 shadow-sm backdrop-blur">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">Program Library</div>
              <div className="mt-1 text-sm text-slate-600">Open an existing biotech project workspace.</div>
            </div>
            <button
              onClick={onRefreshProjects}
              className="rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-900 hover:bg-slate-50"
            >
              Refresh
            </button>
          </div>

          {loadingProjects ? (
            <LoadingSpinner />
          ) : projects.length === 0 ? (
            <div className="mt-4 rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-4 text-sm text-slate-600">
              No projects yet. Create one from the form above to spin up a saved, project-scoped collaborator set.
            </div>
          ) : (
            <div className="mt-4 space-y-2">
              {projects.map((project) => {
                const active = selectedProjectId === project.id;
                return (
                  <div
                    key={project.id}
                    className={classNames(
                      'rounded-2xl border p-3 transition',
                      active ? 'border-emerald-300 bg-emerald-50 shadow-sm' : 'border-slate-200 bg-white hover:bg-slate-50'
                    )}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <button onClick={() => onOpenProject(project.id)} className="min-w-0 flex-1 text-left">
                        <div className="text-sm font-semibold text-slate-950">{project.name}</div>
                        <div className="mt-1 text-xs text-slate-600">{project.end_product}</div>
                      </button>
                      <div className="flex shrink-0 flex-col items-end gap-2">

                        <button
                          onClick={() => onDeleteProject(project)}
                          disabled={deletingProjectId === project.id}
                          className="rounded-xl border border-rose-200 bg-white px-2 py-1 text-[11px] font-semibold text-rose-700 transition hover:bg-rose-50 disabled:cursor-not-allowed disabled:opacity-60"
                        >
                          {deletingProjectId === project.id ? 'Deleting...' : 'Delete'}
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>
      </aside>

      <main className="space-y-5">
        <section className="rounded-[1.75rem] border border-slate-200 bg-white/90 p-8 shadow-sm backdrop-blur">
          <div className="max-w-3xl">
            <div className="text-xs font-semibold uppercase tracking-[0.24em] text-emerald-700">Landing</div>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950 md:text-3xl">
              Start from an existing biotech project or spin up a new one
            </h2>
            <p className="mt-3 text-sm leading-6 text-slate-600 md:text-base">
              Define your question, inspect the evidence, and compare research options in a saved workspace.
            </p>
          </div>
          <div className="mt-6 grid gap-3 md:grid-cols-3">
            <div className="rounded-2xl border border-violet-200 bg-violet-50 p-4">
              <div className="text-[11px] font-semibold uppercase tracking-wide text-violet-800">1. Define The Program</div>
              <div className="mt-2 text-sm text-violet-950">
                Capture the end product, host, and goal without forcing every project into the same workflow template.
              </div>
            </div>
            <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4">
              <div className="text-[11px] font-semibold uppercase tracking-wide text-emerald-800">2. Refine The Question</div>
              <div className="mt-2 text-sm text-emerald-950">
                Use objective clustering to turn a vague prompt into distinct angles like literature synthesis, experiments, or process
                strategy.
              </div>
            </div>
            <div className="rounded-2xl border border-sky-200 bg-sky-50 p-4">
              <div className="text-[11px] font-semibold uppercase tracking-wide text-sky-800">3. Collaborate And Save</div>
              <div className="mt-2 text-sm text-sky-950">
                Compare evidence and agent perspectives in the research board, then review the decisions that need your input.
              </div>
            </div>
          </div>
        </section>

        <section className="rounded-[1.75rem] border border-dashed border-slate-300 bg-white/80 p-10 text-center text-sm text-slate-600 shadow-sm">
          Create or select a biotech project from the left to open the main workspace.
        </section>
      </main>
    </div>
  );
}
