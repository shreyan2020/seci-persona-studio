import { ResearchWorkTemplateSection } from '@/features/biotech-workspace/components/ResearchWorkTemplateSection';
import type { ObjectiveCluster, ResearchFinding, ResearchWorkTemplate } from '@/features/biotech-workspace/types';

interface LiteratureSurveySectionProps {
  selectedObjective: ObjectiveCluster | null;
  onChooseAnotherObjective: () => void;
  researchWorkTemplate: ResearchWorkTemplate;
  onResearchWorkTemplateChange: (next: ResearchWorkTemplate) => void;
  onFetchLiterature: () => void;
  fetchingLiterature: boolean;
  onSynthesizeGaps: () => void;
  synthesizingGaps: boolean;
  onRunValidationTrack: (findingId: string, trackId: string) => void;
  runningValidationId?: string | null;
  literatureObjectiveLens?: string | null;
  literatureProcessingSummary?: string | null;
  literatureElicitationQuestions?: string[];
  onPreparePaperPdf?: (finding: ResearchFinding) => void;
  onBuildPaperOntology?: (finding: ResearchFinding) => void;
  preparingPdfFindingId?: string | null;
  buildingPaperOntologyId?: string | null;
  pdfAnnotationStatus?: string | null;
  pdfAnnotationFindingId?: string | null;
  reviewStage: 'review' | 'summary';
  onCompleteLiteratureReview: (summary: string) => void;
}

export function LiteratureSurveySection({
  selectedObjective,
  onChooseAnotherObjective,
  researchWorkTemplate,
  onResearchWorkTemplateChange,
  onFetchLiterature,
  fetchingLiterature,
  onSynthesizeGaps,
  synthesizingGaps,
  onRunValidationTrack,
  runningValidationId,
  literatureObjectiveLens,
  literatureProcessingSummary,
  literatureElicitationQuestions,
  onPreparePaperPdf,
  onBuildPaperOntology,
  preparingPdfFindingId,
  buildingPaperOntologyId,
  pdfAnnotationStatus,
  pdfAnnotationFindingId,
  reviewStage,
  onCompleteLiteratureReview,
}: LiteratureSurveySectionProps) {
  if (!selectedObjective) {
    return (
      <section className="border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-600">
        Choose an objective mode to continue.
      </section>
    );
  }

  return (
    <section className="border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-col gap-3 border-b border-slate-200 pb-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="text-[11px] font-semibold uppercase text-slate-500">Literature survey</div>
          <h2 className="mt-1 text-xl font-semibold text-slate-950">{selectedObjective.title}</h2>
        </div>
        <button
          onClick={onChooseAnotherObjective}
          className="border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50"
        >
          Change objective
        </button>
      </div>

      <ResearchWorkTemplateSection
        workTemplate={researchWorkTemplate}
        onWorkTemplateChange={onResearchWorkTemplateChange}
        onFetchLiterature={onFetchLiterature}
        fetchingLiterature={fetchingLiterature}
        onSynthesizeGaps={onSynthesizeGaps}
        synthesizingGaps={synthesizingGaps}
        onRunValidationTrack={onRunValidationTrack}
        runningValidationId={runningValidationId}
        literatureObjectiveLens={literatureObjectiveLens}
        literatureProcessingSummary={literatureProcessingSummary}
        literatureElicitationQuestions={literatureElicitationQuestions}
        onPreparePaperPdf={onPreparePaperPdf}
        onBuildPaperOntology={onBuildPaperOntology}
        preparingPdfFindingId={preparingPdfFindingId}
        buildingPaperOntologyId={buildingPaperOntologyId}
        pdfAnnotationStatus={pdfAnnotationStatus}
        pdfAnnotationFindingId={pdfAnnotationFindingId}
        reviewStage={reviewStage}
        onCompleteReview={onCompleteLiteratureReview}
      />
    </section>
  );
}
