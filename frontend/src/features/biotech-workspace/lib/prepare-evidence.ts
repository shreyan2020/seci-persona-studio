import type { ResearchBoard } from '../board-types';

/** Persist each stage before starting the next; never reuse a captured revision. */
export async function prepareBoardStages(options: {
  board: ResearchBoard | null;
  workspaceKey: string;
  state: Record<string, unknown>;
  isCurrent: () => boolean;
  mutate: (operation: 'compare' | 'start', payload: Record<string, unknown>) => Promise<{ board: ResearchBoard }>;
  saved: (board: ResearchBoard) => void;
  progress: (message: string) => void;
}) {
  let current = options.board;
  for (const operation of ['compare', 'start'] as const) {
    if (!options.isCurrent()) return false;
    options.progress(operation === 'compare' ? 'Comparing verified PDF passages…' : 'Preparing perspectives and decision options…');
    const result = await options.mutate(operation, {
      workspace_key: options.workspaceKey,
      expected_revision: current?.revision || 0,
      explicit_state: options.state,
    });
    if (!options.isCurrent()) return false;
    current = result.board;
    options.saved(current);
  }
  return true;
}
