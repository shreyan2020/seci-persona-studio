'use client';

import Link from 'next/link';
import { ResearchBoardPanel } from '@/features/biotech-workspace/components/ResearchBoardPanel';
import type { ResearchBoard } from '@/features/biotech-workspace/board-types';
import savedBoard from '@/examples/itaconate.json';

const board = savedBoard as ResearchBoard;
const keepSnapshot = () => {};

export default function ItaconateExample() {
  return <main className="mx-auto max-w-7xl space-y-6 p-5 sm:p-10">
    <header className="max-w-4xl space-y-4">
      <Link href="/" className="text-sm text-cyan-800 underline">Back to workspace</Link>
      <p className="text-xs font-semibold uppercase tracking-widest text-cyan-800">SECI Persona Studio · Example project</p>
      <h1 className="text-3xl font-semibold text-slate-950">Itaconic acid: pathway or cultivation?</h1>
      <p className="text-base leading-7 text-slate-700">{board.query}</p>
      <p className="text-sm leading-6 text-slate-600">Explore six experiment records, their source passages, and three specialist perspectives with a review challenge. Select a result to inspect its context, or open Perspectives &amp; history to follow the discussion.</p>
      <p className="text-sm leading-6 text-slate-600">This saved example uses source-reviewed comparisons and edited model perspectives. Browsing needs no backend or model server; editing and regeneration belong in a live project.</p>
      <div className="flex flex-wrap gap-4 text-sm text-cyan-800 underline">
        <a href="https://doi.org/10.1126/sciadv.adn0414" target="_blank" rel="noreferrer">Fu et al. (2024)</a>
        <a href="https://doi.org/10.1186/s13068-025-02668-9" target="_blank" rel="noreferrer">Ciliberti et al. (2025)</a>
      </div>
    </header>
    <ResearchBoardPanel previewBoard={board} workspaceKey={board.workspace_key} explicitState={{query: board.query}} onBoardChange={keepSnapshot} />
    <footer className="text-xs leading-5 text-slate-500">Source excerpts retain the papers’ wording and page references. Fu et al.: CC BY 4.0. Ciliberti et al.: CC BY-NC-ND 4.0. See the repository’s example provenance notes for attribution and review history.</footer>
  </main>;
}
