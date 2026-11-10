# Experiment-centered research board

The comparison layer uses two separate operations:

1. **Extract atomic facts.** Every condition, intervention, comparator, outcome, or limitation retains one verified PDF passage as its source. Exact-span validation establishes provenance only.
2. **Link experiment records.** Facts from different passages may be joined only within one paper and only when the same explicit strain identifier, named condition, figure reference, or table reference appears as a link anchor on every fact. Facts that fail this rule remain unresolved.

The deterministic validator also refuses to merge different carbon sources, different cultivation settings, or genetic and process interventions into one record. “Fed-batch” is a cultivation setting unless the passage explicitly reports a changed feeding treatment. A reported comparator is displayed as the baseline, but its presence is not treated as proof that the intervention caused the outcome.

## Terminology alignment

The records use a deliberately small vocabulary layer:

- OBI `investigation`, `assay`, and `planned process` concepts organize experimental roles.
- BFO `material entity` identifies hosts and chemical materials at a broad level.
- ChEBI identifiers normalize only exact, deterministic chemical matches currently supported by the application (`CHEBI:17234` glucose and `CHEBI:17754` glycerol).

Ontology tags improve naming and retrieval; they do not validate an extracted fact or an experiment link. New chemical mappings should be added only after identifier verification and tests.

## Discussion and elicitation

Agent perspectives receive the experiment records and must identify the comparison supporting an argument, along with transfer limits. Investigator questions are reserved for documented local requirements whose answer could change action eligibility. Missing paper facts route to retrieval, and unknown effects route to an experiment rather than a preference question.
