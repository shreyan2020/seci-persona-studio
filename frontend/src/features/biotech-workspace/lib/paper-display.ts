import type { ResearchFinding, PaperAnnotation } from '../types';

export function comparisonValue(dimension: string, value: string): string {
  // Keep the full genotype in the source-detail view, not the scan-friendly grid.
  if (dimension === 'host' && value.includes(' (')) return value.slice(0, value.indexOf(' ('));
  return value;
}

export function paperHeading(finding: Pick<ResearchFinding, 'citation'>): string {
  return finding.citation.replace(/\s*(?:DOI|PMID|PMCID)\s*:\s*\S+/gi, '').trim().replace(/\.+$/, '') || 'Untitled paper';
}

export function paperLink(finding: ResearchFinding): string | undefined {
  const doi = finding.source_ids?.doi || finding.citation.match(/\bDOI:\s*(10\.\d{4,9}\/\S+)/i)?.[1];
  if (doi) return `https://doi.org/${encodeURI(doi.replace(/^https?:\/\/doi\.org\//i, '').replace(/[.,;]+$/, ''))}`;
  const pmid = finding.source_ids?.pmid || finding.citation.match(/\bPMID:\s*(\d+)/i)?.[1];
  if (pmid && /^\d+$/.test(pmid)) return `https://pubmed.ncbi.nlm.nih.gov/${pmid}/`;
  const url = finding.citation.match(/https?:\/\/[^\s]+/i)?.[0];
  return url;
}

export function orderedHighlights(annotations: PaperAnnotation[] = []): PaperAnnotation[] {
  return [...annotations].sort((a, b) => a.page - b.page);
}
