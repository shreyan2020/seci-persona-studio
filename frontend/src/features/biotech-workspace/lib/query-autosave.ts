/** Compare persisted content, excluding response timestamps and object key order. */
function canonical(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).sort(([a], [b]) => a.localeCompare(b))
      .map(([key, item]) => [key, canonical(item)]));
  }
  return value;
}

type QueryContent = { title: string; query: string; state: Record<string, unknown> };

export function queryNeedsSave(stored: QueryContent | undefined, draft: QueryContent): boolean {
  if (!stored) return false; // Wait until this query has been loaded or created.
  return stored.title !== draft.title || stored.query !== draft.query
    || JSON.stringify(canonical(stored.state)) !== JSON.stringify(canonical(draft.state));
}
