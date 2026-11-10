'use client';

import { useEffect, useMemo, useState } from 'react';
import { API_BASE } from '@/features/biotech-workspace/lib/api-base';

type ReportStatus = 'draft' | 'queued' | 'running' | 'success' | 'failed';

interface ReportMeta {
  id: number;
  title: string;
  objective_id?: string | null;
  persona_id?: number | null;
  status: ReportStatus;
  qmd_path: string;
  last_output_html_path?: string | null;
  last_output_pdf_path?: string | null;
  last_render_at?: string | null;
  last_manifest_path?: string | null;
  last_log_path?: string | null;
  error_message?: string | null;
  created_at: string;
  updated_at: string;
}

interface PersonaItem {
  id: number;
  name: string;
  scope: string;
  last_summary: string;
}

async function fetchReport(id: string, signal?: AbortSignal): Promise<ReportMeta> {
  const res = await fetch(`${API_BASE}/api/reports/${id}`, { cache: 'no-store', signal });
  if (!res.ok) throw new Error('Failed to load report');
  return res.json();
}

async function fetchQmd(id: string): Promise<string> {
  const res = await fetch(`${API_BASE}/api/reports/${id}/qmd`, { cache: 'no-store' });
  if (!res.ok) throw new Error('Failed to load qmd');
  const data = await res.json();
  return data.qmd || '';
}

async function fetchPersonas(): Promise<PersonaItem[]> {
  const res = await fetch(`${API_BASE}/api/personas`, { cache: 'no-store' });
  if (!res.ok) return [];
  const data = await res.json();
  return data.personas || [];
}

export default function ReportEditorPage({ params }: { params: { id: string } }) {
  const reportId = params.id;
  const [meta, setMeta] = useState<ReportMeta | null>(null);
  const [qmd, setQmd] = useState('');
  const [logs, setLogs] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [rendering, setRendering] = useState(false);
  const [personas, setPersonas] = useState<PersonaItem[]>([]);
  const [personaId, setPersonaId] = useState<number | ''>('');
  const [objectiveId, setObjectiveId] = useState('');

  const htmlPreviewUrl = useMemo(() => `${API_BASE}/api/reports/${reportId}/output/html`, [reportId]);

  const load = async () => {
    setLoading(true);
    try {
      const [report, text, personaList] = await Promise.all([
        fetchReport(reportId),
        fetchQmd(reportId),
        fetchPersonas(),
      ]);
      setMeta(report);
      setQmd(text);
      setPersonas(personaList);
      setPersonaId(report.persona_id ?? '');
      setObjectiveId(report.objective_id || '');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [reportId]);

  useEffect(() => {
    if (!meta || !['queued', 'running'].includes(meta.status)) return;
    let cancelled = false;
    let pending = false;
    const controller = new AbortController();
    const timer = setInterval(async () => {
      if (pending) return;
      pending = true;
      try {
        const next = await fetchReport(reportId, controller.signal);
        if (!cancelled) setMeta(next);
      } catch {
        // no-op
      } finally {
        pending = false;
      }
    }, 2500);
    return () => { cancelled = true; controller.abort(); clearInterval(timer); };
  }, [meta?.status, reportId]);

  const saveQmd = async () => {
    setSaving(true);
    try {
      const res = await fetch(`${API_BASE}/api/reports/${reportId}/qmd`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ qmd }),
      });
      if (!res.ok) throw new Error('Save failed');
      const report = await fetchReport(reportId);
      setMeta(report);
    } finally {
      setSaving(false);
    }
  };

  const render = async (formats: Array<'html' | 'pdf'>) => {
    setRendering(true);
    try {
      const res = await fetch(`${API_BASE}/api/reports/${reportId}/render`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          params: objectiveId ? { objective_id: objectiveId } : {},
          formats,
          cache_ok: true,
          persona_id: personaId === '' ? null : Number(personaId),
        }),
      });
      if (!res.ok) throw new Error('Render enqueue failed');
      const report = await fetchReport(reportId);
      setMeta(report);
    } finally {
      setRendering(false);
    }
  };

  const loadLogs = async () => {
    const res = await fetch(`${API_BASE}/api/reports/${reportId}/logs`, { cache: 'no-store' });
    if (!res.ok) return;
    const data = await res.json();
    setLogs(data.content || '');
  };

  if (loading) {
    return <div className="p-6 text-sm text-neutral-600">Loading report...</div>;
  }

  if (!meta) {
    return <div className="p-6 text-sm text-red-600">Report not found.</div>;
  }

  return (
    <div className="min-h-screen bg-neutral-50 p-6">
      <div className="mx-auto max-w-7xl space-y-4">
        <div className="rounded-2xl border border-neutral-200 bg-white p-4 shadow-sm">
          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={saveQmd}
              disabled={saving}
              className="rounded-xl bg-neutral-900 px-3 py-2 text-sm font-semibold text-white disabled:opacity-60"
            >
              {saving ? 'Saving...' : 'Save'}
            </button>
            <button
              onClick={() => render(['html'])}
              disabled={rendering}
              className="rounded-xl border border-neutral-200 bg-white px-3 py-2 text-sm font-semibold text-neutral-900"
            >
              Render HTML
            </button>
            <button
              onClick={() => render(['html', 'pdf'])}
              disabled={rendering}
              className="rounded-xl border border-neutral-200 bg-white px-3 py-2 text-sm font-semibold text-neutral-900"
            >
              Render HTML+PDF
            </button>
            <button
              onClick={loadLogs}
              className="rounded-xl border border-neutral-200 bg-white px-3 py-2 text-sm font-semibold text-neutral-900"
            >
              View logs
            </button>
            <a
              href={`${API_BASE}/api/reports/${reportId}/output/pdf`}
              className="rounded-xl border border-neutral-200 bg-white px-3 py-2 text-sm font-semibold text-neutral-900"
            >
              Download PDF
            </a>
            <span className="ml-auto rounded-full border border-neutral-200 bg-neutral-50 px-3 py-1 text-xs text-neutral-700">
              Status: {meta.status}
            </span>
          </div>

          <div className="mt-3 grid gap-2 md:grid-cols-2">
            <label className="text-sm text-neutral-700">
              Persona
              <select
                value={personaId}
                onChange={(e) => setPersonaId(e.target.value === '' ? '' : Number(e.target.value))}
                className="mt-1 w-full rounded-xl border border-neutral-200 bg-white px-3 py-2 text-sm"
              >
                <option value="">None</option>
                {personas.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} ({p.scope})
                  </option>
                ))}
              </select>
            </label>
            <label className="text-sm text-neutral-700">
              Objective
              <input
                value={objectiveId}
                onChange={(e) => setObjectiveId(e.target.value)}
                className="mt-1 w-full rounded-xl border border-neutral-200 bg-white px-3 py-2 text-sm"
                placeholder="objective cluster id"
              />
            </label>
          </div>

          <div className="mt-2 text-xs text-neutral-500">
            Last render: {meta.last_render_at || 'never'}
            {meta.error_message ? ` · Error: ${meta.error_message}` : ''}
          </div>
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-2xl border border-neutral-200 bg-white p-4 shadow-sm">
            <div className="mb-2 text-sm font-semibold text-neutral-900">QMD Editor</div>
            <textarea
              value={qmd}
              onChange={(e) => setQmd(e.target.value)}
              rows={30}
              className="w-full rounded-xl border border-neutral-200 bg-white p-3 font-mono text-xs text-neutral-900"
            />
            {logs ? (
              <pre className="mt-3 max-h-56 overflow-auto rounded-xl border border-neutral-200 bg-neutral-50 p-3 text-xs text-neutral-800">
                {logs}
              </pre>
            ) : null}
          </div>

          <div className="rounded-2xl border border-neutral-200 bg-white p-4 shadow-sm">
            <div className="mb-2 text-sm font-semibold text-neutral-900">Preview</div>
            <iframe
              title="report-preview"
              src={htmlPreviewUrl}
              className="h-[760px] w-full rounded-xl border border-neutral-200"
            />
          </div>
        </div>
      </div>
    </div>
  );
}
