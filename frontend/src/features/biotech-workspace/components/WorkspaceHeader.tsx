import Link from 'next/link';

import type { StatusState } from '@/features/biotech-workspace/types';

interface WorkspaceHeaderProps {
  selectedProject: boolean;
  onReturnToLanding: () => void;
  onOpenMemory?: () => void;
  onExportDiagnostics?: () => void;
  exportingDiagnostics?: boolean;
  journeyHref?: string;
  memoryItemCount?: number;
  status: StatusState | null;
}

export function WorkspaceHeader({
  selectedProject,
  onReturnToLanding,
  onOpenMemory,
  onExportDiagnostics,
  exportingDiagnostics = false,
  journeyHref,
  memoryItemCount = 0,
}: WorkspaceHeaderProps) {
  return (
    <section className="rounded-none border border-emerald-200/70 bg-white/90 p-6 shadow-[0_24px_70px_-45px_rgba(15,23,42,0.45)] backdrop-blur">
      <div className="flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between">
        <div className="max-w-3xl">
          <div className="inline-flex rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.28em] text-emerald-900">
            Biotech Program Workspace
          </div>
          <h1 className="mt-4 text-3xl font-semibold tracking-tight text-slate-950 md:text-4xl">Biotech project workspace</h1>
        </div>

        <div className="flex flex-wrap gap-2">
          {selectedProject && (
            <>
              {onOpenMemory && (
                <button
                  onClick={onOpenMemory}
                  className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-2 text-sm font-semibold text-amber-950 hover:bg-amber-100"
                >
                  Research Board / Memory{memoryItemCount > 0 ? ` (${memoryItemCount})` : ''}
                </button>
              )}
              {journeyHref && (
                <Link
                  href={journeyHref}
                  className="rounded-2xl border border-cyan-200 bg-cyan-50 px-4 py-2 text-sm font-semibold text-cyan-950 hover:bg-cyan-100"
                >
                  User Journey
                </Link>
              )}
              {onExportDiagnostics && (
                <button
                  onClick={onExportDiagnostics}
                  disabled={exportingDiagnostics}
                  className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-2 text-sm font-semibold text-rose-950 hover:bg-rose-100 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {exportingDiagnostics ? 'Exporting...' : 'Export Diagnostics'}
                </button>
              )}
              <button
                onClick={onReturnToLanding}
                className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm font-semibold text-emerald-900 hover:bg-emerald-100"
              >
                All Projects
              </button>
            </>
          )}
        </div>
      </div>
    </section>
  );
}
