import { useMemo, useState } from 'react';

import type { OntologyEdge, OntologyNode, OntologyPreviewResponse, OntologyUsageTrace } from '@/features/biotech-workspace/types';
import { classNames } from '@/features/biotech-workspace/lib/utils';

interface OntologyPanelProps {
  preview: OntologyPreviewResponse | null;
  loading: boolean;
  status: string;
  activeTrace?: OntologyUsageTrace | null;
  onRefresh: () => void;
  onReviewNode: (nodeId: string, status: 'confirmed' | 'rejected') => void;
}

const nodeTone: Record<string, string> = {
  project: 'border-slate-300 bg-slate-50 text-slate-800',
  paper: 'border-sky-200 bg-sky-50 text-sky-900',
  claim: 'border-blue-200 bg-blue-50 text-blue-900',
  concept: 'border-emerald-200 bg-emerald-50 text-emerald-900',
  gap: 'border-rose-200 bg-rose-50 text-rose-900',
  project_belief: 'border-teal-200 bg-teal-50 text-teal-900',
  validation: 'border-violet-200 bg-violet-50 text-violet-900',
  proposal: 'border-amber-200 bg-amber-50 text-amber-900',
  tacit_memory: 'border-orange-200 bg-orange-50 text-orange-900',
  plan_step: 'border-indigo-200 bg-indigo-50 text-indigo-900',
};

const statusTone: Record<string, string> = {
  confirmed: 'border-emerald-200 bg-emerald-50 text-emerald-800',
  rejected: 'border-rose-200 bg-rose-50 text-rose-800',
  edited: 'border-amber-200 bg-amber-50 text-amber-800',
  inferred: 'border-slate-200 bg-white text-slate-600',
};

const graphPalette: Record<string, { fill: string; stroke: string; text: string; line: string }> = {
  project: { fill: '#f8fafc', stroke: '#94a3b8', text: '#1e293b', line: '#94a3b8' },
  paper: { fill: '#f0f9ff', stroke: '#7dd3fc', text: '#0c4a6e', line: '#38bdf8' },
  claim: { fill: '#eff6ff', stroke: '#93c5fd', text: '#1e3a8a', line: '#60a5fa' },
  concept: { fill: '#ecfdf5', stroke: '#6ee7b7', text: '#065f46', line: '#34d399' },
  gap: { fill: '#fff1f2', stroke: '#fda4af', text: '#9f1239', line: '#fb7185' },
  project_belief: { fill: '#f0fdfa', stroke: '#5eead4', text: '#115e59', line: '#2dd4bf' },
  validation: { fill: '#f5f3ff', stroke: '#c4b5fd', text: '#4c1d95', line: '#a78bfa' },
  proposal: { fill: '#fffbeb', stroke: '#fcd34d', text: '#92400e', line: '#f59e0b' },
  tacit_memory: { fill: '#fff7ed', stroke: '#fdba74', text: '#9a3412', line: '#fb923c' },
  plan_step: { fill: '#eef2ff', stroke: '#a5b4fc', text: '#3730a3', line: '#818cf8' },
};

const defaultGraphTone = { fill: '#ffffff', stroke: '#cbd5e1', text: '#334155', line: '#94a3b8' };
const maxGraphNodes = 52;
const graphNodeWidth = 154;
const graphNodeHeight = 42;
const graphLaneGap = 34;
const graphNodeGap = 20;

function relationLabel(value: string) {
  return value.replace(/_/g, ' ');
}

function shortLabel(value: string, limit = 30) {
  const clean = value.replace(/\s+/g, ' ').trim();
  return clean.length <= limit ? clean : `${clean.slice(0, limit - 1).trim()}...`;
}

function categoryLabel(value: string) {
  return relationLabel(value || 'other');
}

function categoryOrder(type: string) {
  const order = [
    'project',
    'objective',
    'paper',
    'claim',
    'project_belief',
    'concept',
    'validation',
    'gap',
    'proposal',
    'plan_step',
    'tacit_memory',
  ];
  const index = order.indexOf(type);
  return index === -1 ? order.length : index;
}

function nodeImportance(node: OntologyNode, edges: OntologyEdge[]) {
  const degree = edges.reduce((count, edge) => count + (edge.source === node.id || edge.target === node.id ? 1 : 0), 0);
  const statusBoost = node.status === 'confirmed' || node.status === 'edited' ? 4 : node.status === 'rejected' ? -8 : 0;
  return degree * 2 + Math.round((node.confidence || 0) * 5) + statusBoost;
}

function buildGraphLayout(nodes: OntologyNode[], edges: OntologyEdge[], selectedType: string) {
  const visibleCandidates = nodes.filter((node) => node.status !== 'rejected' && (selectedType === 'all' || node.type === selectedType));
  const ranked = [...visibleCandidates]
    .sort((left, right) => nodeImportance(right, edges) - nodeImportance(left, edges) || left.type.localeCompare(right.type) || left.label.localeCompare(right.label))
    .slice(0, maxGraphNodes);
  const visibleIds = new Set(ranked.map((node) => node.id));
  const visibleEdges = edges
    .filter((edge) => edge.status !== 'rejected' && visibleIds.has(edge.source) && visibleIds.has(edge.target))
    .slice(0, 90);

  const groups = new Map<string, OntologyNode[]>();
  for (const node of ranked) {
    const existing = groups.get(node.type) || [];
    existing.push(node);
    groups.set(node.type, existing);
  }

  const categories = [...groups.keys()].sort((left, right) => categoryOrder(left) - categoryOrder(right) || left.localeCompare(right));
  const maxGroupSize = Math.max(1, ...categories.map((type) => groups.get(type)?.length || 0));
  const width = Math.max(760, categories.length * (graphNodeWidth + graphLaneGap) + 42);
  const height = Math.max(340, maxGroupSize * (graphNodeHeight + graphNodeGap) + 92);
  const positions = new Map<string, { x: number; y: number; node: OntologyNode }>();

  categories.forEach((type, typeIndex) => {
    const lane = groups.get(type) || [];
    const x = 24 + typeIndex * (graphNodeWidth + graphLaneGap);
    lane.forEach((node, nodeIndex) => {
      const y = 58 + nodeIndex * (graphNodeHeight + graphNodeGap);
      positions.set(node.id, { x, y, node });
    });
  });

  return { categories, groups, positions, visibleNodes: ranked, visibleEdges, width, height };
}

export function OntologyPanel({ preview, loading, status, activeTrace, onRefresh, onReviewNode }: OntologyPanelProps) {
  const [viewMode, setViewMode] = useState<'graph' | 'list'>('graph');
  const [selectedType, setSelectedType] = useState('all');
  const [traceHighlighted, setTraceHighlighted] = useState(false);
  const topNodes = preview?.nodes.slice(0, 18) || [];
  const topEdges = preview?.edges.slice(0, 10) || [];
  const augmentation = preview?.query_augmentation;
  const nodesById = useMemo(() => new Map((preview?.nodes || []).map((node) => [node.id, node])), [preview?.nodes]);
  const categoryCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const node of preview?.nodes || []) {
      if (node.status === 'rejected') continue;
      counts.set(node.type, (counts.get(node.type) || 0) + 1);
    }
    return [...counts.entries()].sort(([left], [right]) => categoryOrder(left) - categoryOrder(right) || left.localeCompare(right));
  }, [preview?.nodes]);
  const graphLayout = useMemo(() => buildGraphLayout(preview?.nodes || [], preview?.edges || [], selectedType), [preview?.edges, preview?.nodes, selectedType]);
  const highlightedNodeIds = useMemo(() => new Set(traceHighlighted ? activeTrace?.node_ids || [] : []), [activeTrace?.node_ids, traceHighlighted]);
  const highlightedEdgeIds = useMemo(() => new Set(traceHighlighted ? activeTrace?.edge_ids || [] : []), [activeTrace?.edge_ids, traceHighlighted]);
  const reviewCandidates = useMemo(
    () => (preview?.nodes || []).filter((node) => node.status === 'inferred' && ['concept', 'gap', 'validation', 'tacit_memory'].includes(node.type)).slice(0, 5),
    [preview?.nodes]
  );

  return (
    <section className="rounded-[1.4rem] border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-500">Ontology Layer</div>
          <div className="mt-1 text-lg font-semibold text-slate-950">Research entities, relations, and query expansion</div>
          <div className="mt-1 max-w-3xl text-sm leading-6 text-slate-700">
            The preview connects literature, experiment tracks, open gaps, plans, and tacit memory into a graph that can later steer search
            routing and answer synthesis.
          </div>
          <div className="mt-2 text-xs text-slate-500">{status}</div>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row lg:flex-col">
          <div className="grid grid-cols-2 overflow-hidden rounded-2xl border border-slate-200 bg-slate-50 p-1 text-xs font-semibold text-slate-600">
            {(['graph', 'list'] as const).map((mode) => (
              <button
                key={mode}
                onClick={() => setViewMode(mode)}
                className={classNames('rounded-xl px-3 py-2 capitalize transition', viewMode === mode ? 'bg-white text-slate-950 shadow-sm' : 'hover:bg-white/70')}
              >
                {mode}
              </button>
            ))}
          </div>
          {activeTrace && (
            <button
              onClick={() => {
                setViewMode('graph');
                setSelectedType('all');
                setTraceHighlighted((current) => !current);
              }}
              className={classNames(
                'rounded-2xl border px-4 py-3 text-sm font-semibold transition',
                traceHighlighted ? 'border-cyan-300 bg-cyan-50 text-cyan-950' : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50'
              )}
            >
              {traceHighlighted ? 'Clear trace' : 'Show ontology trace'}
            </button>
          )}
          <button
            onClick={onRefresh}
            disabled={loading}
            className="rounded-2xl bg-slate-950 px-4 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? 'Syncing...' : 'Sync ontology'}
          </button>
        </div>
      </div>

      {preview ? (
        <div className="mt-4 space-y-4">
          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-3 text-sm leading-6 text-slate-700">
            {preview.summary}
          </div>

          {activeTrace && (
            <div className="rounded-2xl border border-cyan-200 bg-cyan-50 p-3 text-sm leading-6 text-cyan-950">
              <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
                <div>
                  <div className="text-[11px] font-semibold uppercase tracking-wide text-cyan-800">{activeTrace.title || 'Ontology trace'}</div>
                  <div className="mt-1">{activeTrace.summary}</div>
                </div>
                <button
                  onClick={() => {
                    setViewMode('graph');
                    setSelectedType('all');
                    setTraceHighlighted(true);
                  }}
                  className="rounded-xl border border-cyan-300 bg-white px-3 py-2 text-xs font-semibold text-cyan-900 hover:bg-cyan-100"
                >
                  Highlight paths
                </button>
              </div>
            </div>
          )}

          <div className="rounded-2xl border border-slate-200 bg-white p-3">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-600">Entity Categories</div>
                <div className="mt-1 text-xs text-slate-500">Filter the graph by category, or keep all categories visible.</div>
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  onClick={() => setSelectedType('all')}
                  className={classNames(
                    'rounded-full border px-3 py-1.5 text-xs font-semibold transition',
                    selectedType === 'all' ? 'border-slate-950 bg-slate-950 text-white' : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50'
                  )}
                >
                  All {preview.nodes.filter((node) => node.status !== 'rejected').length}
                </button>
                {categoryCounts.map(([type, count]) => {
                  const tone = graphPalette[type] || defaultGraphTone;
                  return (
                    <button
                      key={type}
                      onClick={() => setSelectedType(type)}
                      className={classNames(
                        'rounded-full border px-3 py-1.5 text-xs font-semibold transition',
                        selectedType === type ? 'shadow-sm' : 'hover:bg-slate-50'
                      )}
                      style={{
                        borderColor: selectedType === type ? tone.stroke : '#e2e8f0',
                        backgroundColor: selectedType === type ? tone.fill : '#ffffff',
                        color: selectedType === type ? tone.text : '#475569',
                      }}
                    >
                      {categoryLabel(type)} {count}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          {viewMode === 'graph' && (
            <div className="rounded-2xl border border-slate-200 bg-white p-3">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-600">Ontology Graph</div>
                  <div className="mt-1 text-xs text-slate-500">
                    Showing {graphLayout.visibleNodes.length} entities and {graphLayout.visibleEdges.length} visible relations.
                  </div>
                </div>
                <div className="text-xs text-slate-500">{selectedType === 'all' ? 'Grouped by category' : categoryLabel(selectedType)}</div>
              </div>
              {graphLayout.visibleNodes.length > 0 ? (
                <div className="mt-3 overflow-auto rounded-2xl border border-slate-100 bg-slate-50">
                  <svg width={graphLayout.width} height={graphLayout.height} role="img" aria-label="Ontology entity relationship graph" className="block">
                    <defs>
                      <marker id="ontology-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
                        <path d="M 0 0 L 10 5 L 0 10 z" fill="#94a3b8" />
                      </marker>
                    </defs>
                    {graphLayout.categories.map((type) => {
                      const laneNodes = graphLayout.groups.get(type) || [];
                      const first = graphLayout.positions.get(laneNodes[0]?.id || '');
                      const tone = graphPalette[type] || defaultGraphTone;
                      if (!first) return null;
                      return (
                        <g key={`lane-${type}`}>
                          <text x={first.x} y={28} fill="#475569" fontSize="11" fontWeight="700" letterSpacing="0.06em">
                            {categoryLabel(type).toUpperCase()}
                          </text>
                          <line x1={first.x} y1={38} x2={first.x + graphNodeWidth} y2={38} stroke={tone.stroke} strokeWidth="2" strokeLinecap="round" />
                        </g>
                      );
                    })}
                    {graphLayout.visibleEdges.map((edge, index) => {
                      const source = graphLayout.positions.get(edge.source);
                      const target = graphLayout.positions.get(edge.target);
                      if (!source || !target) return null;
                      const sourceTone = graphPalette[source.node.type] || defaultGraphTone;
                      const isHighlighted = highlightedEdgeIds.has(edge.id);
                      const x1 = source.x + graphNodeWidth;
                      const y1 = source.y + graphNodeHeight / 2;
                      const x2 = target.x;
                      const y2 = target.y + graphNodeHeight / 2;
                      const midX = (x1 + x2) / 2;
                      const curveOffset = Math.min(80, Math.abs(x2 - x1) / 2);
                      const path =
                        x2 >= x1
                          ? `M ${x1} ${y1} C ${x1 + curveOffset} ${y1}, ${x2 - curveOffset} ${y2}, ${x2} ${y2}`
                          : `M ${source.x} ${y1} C ${source.x - 45} ${y1}, ${target.x + graphNodeWidth + 45} ${y2}, ${target.x + graphNodeWidth} ${y2}`;
                      const labelY = (y1 + y2) / 2 - 4 + (index % 3) * 7;
                      return (
                        <g key={edge.id}>
                          <path
                            d={path}
                            fill="none"
                            stroke={isHighlighted ? '#0891b2' : sourceTone.line}
                            strokeOpacity={isHighlighted ? 0.95 : traceHighlighted ? 0.18 : 0.42}
                            strokeWidth={isHighlighted ? 3 : 1.5}
                            markerEnd="url(#ontology-arrow)"
                          />
                          {(isHighlighted || index < 34) && (
                            <text x={midX} y={labelY} fill={isHighlighted ? '#0e7490' : '#64748b'} fontSize="9" fontWeight={isHighlighted ? 700 : 400} textAnchor="middle">
                              {shortLabel(relationLabel(edge.relation), 22)}
                            </text>
                          )}
                        </g>
                      );
                    })}
                    {graphLayout.visibleNodes.map((node) => {
                      const position = graphLayout.positions.get(node.id);
                      if (!position) return null;
                      const tone = graphPalette[node.type] || defaultGraphTone;
                      const isHighlighted = highlightedNodeIds.has(node.id);
                      const statusStroke = isHighlighted ? '#0891b2' : node.status === 'confirmed' ? '#059669' : node.status === 'edited' ? '#d97706' : tone.stroke;
                      return (
                        <g key={node.id}>
                          <title>{`${node.label}\n${categoryLabel(node.type)}\n${node.description || 'No description'}\nConfidence ${Math.round((node.confidence || 0) * 100)}%`}</title>
                          <rect
                            x={position.x}
                            y={position.y}
                            width={graphNodeWidth}
                            height={graphNodeHeight}
                            rx="8"
                            fill={tone.fill}
                            stroke={statusStroke}
                            strokeOpacity={traceHighlighted && !isHighlighted ? 0.35 : 1}
                            strokeWidth={isHighlighted ? 3 : node.status === 'confirmed' || node.status === 'edited' ? 2 : 1.4}
                          />
                          <text x={position.x + 10} y={position.y + 18} fill={tone.text} fontSize="11" fontWeight="700">
                            {shortLabel(node.label, 23)}
                          </text>
                          <text x={position.x + 10} y={position.y + 33} fill="#64748b" fontSize="9">
                            {node.status} · {Math.round((node.confidence || 0) * 100)}%
                          </text>
                        </g>
                      );
                    })}
                  </svg>
                </div>
              ) : (
                <div className="mt-3 rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
                  No visible entities for this category.
                </div>
              )}
            </div>
          )}

          <div className={classNames('grid gap-3 lg:grid-cols-[1fr_0.85fr]', viewMode === 'graph' ? 'hidden' : '')}>
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-3">
              <div className="flex items-center justify-between gap-3">
                <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-600">Graph Nodes</div>
                <div className="text-xs text-slate-500">{preview.nodes.length} entities</div>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                {topNodes.map((node) => (
                  <span
                    key={node.id}
                    title={node.description || node.label}
                    className={classNames(
                      'rounded-full border px-2.5 py-1 text-xs font-medium',
                      node.status === 'rejected' ? 'border-rose-200 bg-rose-50 text-rose-800 line-through' : nodeTone[node.type] || 'border-slate-200 bg-white text-slate-700'
                    )}
                  >
                    {node.label}
                  </span>
                ))}
              </div>
            </div>

            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-3">
              <div className="flex items-center justify-between gap-3">
                <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-600">Query Routing</div>
                <div className="text-xs text-slate-500">{preview.edges.length} relations</div>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                {(augmentation?.search_routing || []).map((route) => (
                  <span key={route} className="rounded-full border border-slate-200 bg-white px-2.5 py-1 text-xs font-medium text-slate-700">
                    {relationLabel(route)}
                  </span>
                ))}
              </div>
              <div className="mt-3 text-xs leading-5 text-slate-600">
                {(augmentation?.expanded_terms || []).slice(0, 12).join(', ') || 'No expansion terms yet.'}
              </div>
            </div>
          </div>

          {viewMode === 'list' && topEdges.length > 0 && (
            <div className="rounded-2xl border border-slate-200 bg-white p-3">
              <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-600">Relation Samples</div>
              <div className="mt-2 space-y-2">
                {topEdges.map((edge) => {
                  const source = nodesById.get(edge.source);
                  const target = nodesById.get(edge.target);
                  return (
                    <div key={edge.id} className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs leading-5 text-slate-700">
                      <span className="font-semibold text-slate-900">{source?.label || edge.source}</span>
                      {' -> '}
                      {relationLabel(edge.relation)}
                      {' -> '}
                      <span className="font-semibold text-slate-900">{target?.label || edge.target}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {reviewCandidates.length > 0 && (
            <div className="rounded-2xl border border-slate-200 bg-white p-3">
              <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-600">Review Queue</div>
              <div className="mt-2 space-y-2">
                {reviewCandidates.map((node) => (
                  <div key={node.id} className="flex flex-col gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <div className="text-sm font-semibold text-slate-900">{node.label}</div>
                      <div className="mt-0.5 flex flex-wrap gap-1">
                        <span className={classNames('rounded-full border px-2 py-0.5 text-[11px] font-medium', statusTone[node.status])}>{node.status}</span>
                        <span className="rounded-full border border-slate-200 bg-white px-2 py-0.5 text-[11px] text-slate-600">{node.type}</span>
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <button
                        onClick={() => onReviewNode(node.id, 'confirmed')}
                        className="rounded-xl border border-emerald-200 bg-white px-3 py-1.5 text-xs font-semibold text-emerald-800 hover:bg-emerald-50"
                      >
                        Confirm
                      </button>
                      <button
                        onClick={() => onReviewNode(node.id, 'rejected')}
                        className="rounded-xl border border-rose-200 bg-white px-3 py-1.5 text-xs font-semibold text-rose-800 hover:bg-rose-50"
                      >
                        Reject
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {(augmentation?.tacit_context.length || 0) > 0 && (
            <div className="rounded-2xl border border-orange-200 bg-orange-50 p-3">
              <div className="text-[11px] font-semibold uppercase tracking-wide text-orange-800">Tacit Knowledge Made Explicit</div>
              <div className="mt-2 space-y-1 text-sm leading-6 text-orange-950">
                {augmentation?.tacit_context.slice(0, 4).map((item) => <div key={item}>{item}</div>)}
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="mt-4 rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-4 text-sm leading-6 text-slate-600">
          No ontology preview yet. Refresh once there is a project, collaborator, and research context to map.
        </div>
      )}
    </section>
  );
}
