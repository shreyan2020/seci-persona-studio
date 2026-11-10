import type {
  ObjectiveCluster,
  ObjectiveFrame,
  Project,
  ProjectPersona,
  ResearchWorkTemplate,
} from '@/features/biotech-workspace/types';

export function classNames(...xs: Array<string | false | null | undefined>) {
  return xs.filter(Boolean).join(' ');
}

export function humanize(value: string) {
  return value.replace(/[_:-]+/g, ' ').replace(/\s+/g, ' ').trim();
}

export function defaultFocusQuestion(project: Project, persona?: ProjectPersona | null) {
  if (persona) {
    return '';
  }
  return '';
}

export function inferObjectiveFrame(objectiveText: string): ObjectiveFrame {
  const text = objectiveText.toLowerCase();

  if (/(literature|benchmark|examples|review|latest|papers|open questions|future|challenge)/.test(text)) {
    return {
      label: 'Evidence synthesis',
      description:
        'The draft should stay literature-first: benchmark reported strategies, compare examples, and turn open questions into next hypotheses.',
      draftLabel: 'Evidence Synthesis Draft',
      rawMaterialGuidance:
        'Only bring feedstock or raw materials in if the literature repeatedly flags precursor supply, carbon source, or sourcing cost as a real bottleneck.',
    };
  }

  if (/(data analysis|dataset|statistics|statistical|correlation|regression|omics|screening data|analy[sz]e data)/.test(text)) {
    return {
      label: 'Data analysis',
      description:
        'The draft should focus on interpreting datasets, comparing patterns, defining decision thresholds, and turning results into the next project choices.',
      draftLabel: 'Data Analysis Draft',
      rawMaterialGuidance:
        'Raw materials only matter here when feed, substrate, or sourcing variables are part of the dataset being interpreted.',
    };
  }

  if (/(experiment|strain|pathway|gene|construct|screen|assay|hypothesis)/.test(text)) {
    return {
      label: 'Experiment design',
      description:
        'The draft should prioritize hypotheses, constructs or edits, readouts, controls, and decision gates rather than full workflow coverage.',
      draftLabel: 'Experiment Plan Draft',
      rawMaterialGuidance:
        'Only include raw-material logic if substrate choice or precursor supply is part of the experimental hypothesis.',
    };
  }

  if (/(fermentation|media|bioreactor|culture|titer|yield|process|scale-up|doe)/.test(text)) {
    return {
      label: 'Process development',
      description: 'The draft should focus on operating conditions, DOE structure, and scale-up decision points.',
      draftLabel: 'Process Development Draft',
      rawMaterialGuidance:
        'Bring sourcing in only when feed composition, substrate quality, or cost materially changes process behavior.',
    };
  }

  if (/(purification|recovery|extraction|separation|downstream|isolation)/.test(text)) {
    return {
      label: 'Recovery strategy',
      description:
        'The draft should focus on extraction, separation, purity targets, and where upstream choices create downstream burden.',
      draftLabel: 'Recovery Strategy Draft',
      rawMaterialGuidance:
        'Only discuss raw materials if impurity profile or feed composition directly drives recovery complexity.',
    };
  }

  if (/(economics|tea|commercial|margin|cost|viability|scale)/.test(text)) {
    return {
      label: 'Economics and gating',
      description:
        'The draft should translate technical choices into cost drivers, milestone gates, and commercial feasibility questions.',
      draftLabel: 'Techno-Economic Draft',
      rawMaterialGuidance:
        'Raw materials should be a first-class topic here when they meaningfully affect COGS or scale assumptions.',
    };
  }

  if (/(feedstock|raw material|substrate|sourcing|supply|carbon source)/.test(text)) {
    return {
      label: 'Feedstock and sourcing',
      description:
        'The draft should focus on low-cost inputs, sourcing risk, and how feed choices constrain biology and process design.',
      draftLabel: 'Sourcing Strategy Draft',
      rawMaterialGuidance: 'Raw materials are central to this question and should be explicitly analyzed.',
    };
  }

  return {
    label: 'General project reasoning',
    description:
      'The draft can stay cross-functional, but it should still follow the working question instead of forcing every workflow stage.',
    draftLabel: 'Working Draft',
    rawMaterialGuidance:
      'Raw materials only need to enter when they change feasibility, economics, or the next scientific decision.',
  };
}

export function buildPlanningReasoningNotes(args: {
  reasoningNotes: string;
  selectedObjective: ObjectiveCluster | null;
  objectiveAnswers: Record<string, string>;
  globalQuestions: string[];
  globalQuestionAnswers: Record<string, string>;
}) {
  const sections: string[] = [];

  if (args.reasoningNotes.trim()) {
    sections.push(args.reasoningNotes.trim());
  }

  if (args.selectedObjective) {
    sections.push(
      [
        `Selected objective cluster: ${args.selectedObjective.title}`,
        args.selectedObjective.subtitle ? `Why this angle matters: ${args.selectedObjective.subtitle}` : '',
        args.selectedObjective.definition ? `Definition: ${args.selectedObjective.definition}` : '',
      ]
        .filter(Boolean)
        .join('\n')
    );
  }

  const answeredObjectiveQuestions = Object.entries(args.objectiveAnswers)
    .filter(([, answer]) => answer.trim())
    .map(([question, answer]) => `- ${question}: ${answer.trim()}`);
  if (answeredObjectiveQuestions.length > 0) {
    sections.push(`Objective refinement answers:\n${answeredObjectiveQuestions.join('\n')}`);
  }

  const answeredGlobalQuestions = args.globalQuestions
    .map((question) => ({ question, answer: args.globalQuestionAnswers[question] || '' }))
    .filter((item) => item.answer.trim())
    .map((item) => `- ${item.question}: ${item.answer.trim()}`);
  if (answeredGlobalQuestions.length > 0) {
    sections.push(`Cross-cutting considerations:\n${answeredGlobalQuestions.join('\n')}`);
  }

  return sections.filter(Boolean).join('\n\n');
}

export function createEmptyResearchWorkTemplate(initialQuery = ''): ResearchWorkTemplate {
  return {
    initial_query: initialQuery,
    literature_findings: [],
    common_gaps: [],
    judgment_calls: [],
    validation_tracks: [],
    proposal_candidates: [],
    synthesis_memo: '',
  };
}

export function normalizeResearchWorkTemplate(value: Partial<ResearchWorkTemplate> | null | undefined, initialQuery = ''): ResearchWorkTemplate {
  const result = { ...createEmptyResearchWorkTemplate(initialQuery), ...value };
  result.initial_query = typeof value?.initial_query === 'string' && value.initial_query.trim() ? value.initial_query : initialQuery;
  result.synthesis_memo = typeof value?.synthesis_memo === 'string' ? value.synthesis_memo : '';
  result.literature_findings = (Array.isArray(value?.literature_findings) ? value.literature_findings : []).filter(Boolean).map(f => ({
    ...f, citation: f.citation || '', relevance: f.relevance || '',
    labels: Array.isArray(f.labels) ? f.labels : [],
    knowns: Array.isArray(f.knowns) ? f.knowns : [],
    unknowns: Array.isArray(f.unknowns) ? f.unknowns : [],
    judgment_calls: Array.isArray(f.judgment_calls) ? f.judgment_calls : [],
    validation_tracks: Array.isArray(f.validation_tracks) ? f.validation_tracks : [],
  }));
  result.common_gaps = Array.isArray(value?.common_gaps) ? value.common_gaps : [];
  result.judgment_calls = Array.isArray(value?.judgment_calls) ? value.judgment_calls : [];
  result.validation_tracks = Array.isArray(value?.validation_tracks) ? value.validation_tracks : [];
  result.proposal_candidates = Array.isArray(value?.proposal_candidates) ? value.proposal_candidates : [];
  return result;
}

export function getModeVisualKey(modeLabel: string) {
  const label = modeLabel.toLowerCase();
  if (label.includes('evidence')) return 'evidence';
  if (label.includes('data analysis')) return 'data';
  if (label.includes('experiment')) return 'experiment';
  if (label.includes('process')) return 'process';
  if (label.includes('economics')) return 'economics';
  if (label.includes('feedstock') || label.includes('sourcing')) return 'sourcing';
  if (label.includes('recovery')) return 'recovery';
  return 'general';
}
