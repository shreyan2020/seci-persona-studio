'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { API_BASE } from '@/features/biotech-workspace/lib/api-base';

interface Report {
  id: number;
  title: string;
  objective_id?: string | null;
  status: string;
  updated_at: string;
}

export default function ReportsPage() {
  const [reports, setReports] = useState<Report[]>([]);
  const [title, setTitle] = useState('New DSM Report');
  const [objectiveId, setObjectiveId] = useState('');
  const [creating, setCreating] = useState(false);

  const load = async () => {
    const res = await fetch(`${API_BASE}/api/reports`, { cache: 'no-store' });
    if (!res.ok) return;
    const data = await res.json();
    setReports(data.reports || []);
  };

  useEffect(() => {
    load();
  }, []);

  const createReport = async () => {
    setCreating(true);
    try {
      const res = await fetch(`${API_BASE}/api/reports`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, objective_id: objectiveId || undefined }),
      });
      if (!res.ok) throw new Error('Create report failed');
      await load();
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="min-h-screen bg-neutral-50 p-6">
      <div className="mx-auto max-w-5xl space-y-4">
        <div className="rounded-2xl border border-neutral-200 bg-white p-4 shadow-sm">
          <div className="text-lg font-semibold text-neutral-900">Reports</div>
          <div className="mt-3 grid gap-2 md:grid-cols-3">
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="rounded-xl border border-neutral-200 px-3 py-2 text-sm"
              placeholder="report title"
            />
            <input
              value={objectiveId}
              onChange={(e) => setObjectiveId(e.target.value)}
              className="rounded-xl border border-neutral-200 px-3 py-2 text-sm"
              placeholder="objective id (optional)"
            />
            <button
              onClick={createReport}
              disabled={creating}
              className="rounded-xl bg-neutral-900 px-3 py-2 text-sm font-semibold text-white disabled:opacity-60"
            >
              {creating ? 'Creating...' : 'Create report'}
            </button>
          </div>
          <div className="mt-2 text-xs text-neutral-600">
            Also open <Link href="/personas" className="underline">Personas</Link>
          </div>
        </div>

        <div className="rounded-2xl border border-neutral-200 bg-white p-4 shadow-sm">
          <div className="mb-2 text-sm font-semibold text-neutral-900">Linked reports</div>
          <div className="space-y-2">
            {reports.map((report) => (
              <Link
                key={report.id}
                href={`/reports/${report.id}`}
                className="block rounded-xl border border-neutral-200 p-3 text-sm hover:bg-neutral-50"
              >
                <div className="font-semibold text-neutral-900">{report.title}</div>
                <div className="text-xs text-neutral-600">
                  id={report.id} · objective={report.objective_id || 'none'} · status={report.status}
                </div>
              </Link>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
