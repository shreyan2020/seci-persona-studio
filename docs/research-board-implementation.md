# Research board: implementation and algorithms

Implementation snapshot: 21 September 2026. This document describes the checked-in working-tree code, not a proposed architecture or a claim that every model output is reliable.

## 1. Purpose and interaction

The board connects published evidence to a researcher's next experimental decision:

1. Prepare PDFs and verify passages against the original files.
2. Extract experimental details and assemble conservative experiment records.
3. Compare conditions and outcomes across records.
4. Generate role-based perspectives and review their source support.
5. Ask for local information that papers cannot supply.
6. Save researcher context against a fact; apply decision rules only after confirmation.

The main interface has Overview, Evidence & comparison, and Perspectives & history. The comparison visualization is inside the board. Selecting a plotted titer or a condition opens a context form beneath that record. Source excerpts, additional experience controls and processing details are expandable.

## 2. Are the prompts dynamic or static?

There are two different meanings of “prompt” in this implementation.

| Surface | Fixed elements | Dynamic elements | Model call? |
| --- | --- | --- | --- |
| Inline fact question | `: does this fit your setup?` | Dimension label, selected value, paper/page/quote | No |
| Context text area | Label and example about pH/manual feeding | User-entered text | No |
| Comparison choices | Same, different, unavailable, unknown | Selected choice | No |
| Experience controls | Cue, response and exception menus | Shown when a past case is selected | No |
| Next-step controls | Context, measurement, keep/exclude rule | Keep/exclude choices suppressed for uncertainty; available actions come from the board | No |
| Fact extraction | Instruction and JSON schema | Supplied PDF passages | Yes |
| Agent perspectives | Three roles, instructions and output schema | Question, project fields, evidence, experiment records, recorded context and actions | Yes |
| Board review/questions | Review instructions and ownership constraints | Current posts, actions and evidence; generated question wording | Yes |
| Rule application | Deterministic state-transition rules | Researcher choice, confirmed rule and affected actions | No |

**The screenshot is a template-based form, not an individually generated elicitation question.** Its heading is effectively:

```ts
`${dimensions[fact.dimension]}: does this fit your setup?`
```

The placeholder `e.g. Our reactor controls pH, but feeding is manual.` is currently identical for every dimension, including carbon source. It is not evidence that the system understood the selected parameter.

Board-level questions are different: the review model proposes wording, which the server checks before accepting. If the proposed wording does not end in a question mark, the server uses a generic local-constraint/experience fallback attached to the affected actions.

Conditional display is implemented. Adaptive selection of the most informative question is not: there is no estimated information gain, EVSI calculation, learned intervention policy or optimized question budget in this board. The review prompt requests at most two questions; the acceptance function caps processing at four, and the overview normally displays one pending question at a time.

## 3. Main modules

Paths are relative to the repository root.

| Module | Responsibility |
| --- | --- |
| `backend/document_pipeline.py` | Local document parsing/classification and caches |
| `backend/research_tools.py` | Literature retrieval and passage relevance selection |
| `backend/research_board.py` | Evidence verification, role discussion, questions, rules, SQLite repository |
| `backend/evidence_grounding.py` | Product screening, structural checks and model-based claim support |
| `backend/evidence_comparison.py` | Fact extraction, experiment linking and structured researcher judgments |
| `backend/comparison_models.py` | Typed fact, record and judgment contracts |
| `backend/research_board_api.py` | Board API and optimistic revision checks |
| `backend/board_knowledge.py` | Current knowledge-graph projection |
| `backend/model_routing.py` | Optional task-specific model overrides |
| `frontend/src/features/biotech-workspace/components/ResearchBoardPanel.tsx` | Board navigation, preparation and discussion |
| `frontend/src/features/biotech-workspace/components/EvidenceComparisonPanel.tsx` | Inline source review and context entry |
| `frontend/src/features/biotech-workspace/components/EvidenceMap.tsx` | Experiment records, titer bars and selected-fact interaction |
| `frontend/src/features/biotech-workspace/lib/prepare-evidence.ts` | Sequential, separately persisted preparation stages |
| `frontend/src/features/biotech-workspace/lib/utils.ts` | Saved-template normalization, including missing collection defaults |

## 4. Document and evidence mechanics

### Parsing and candidate extraction

The local pipeline uses LiteParse and Ollama, with parsing and passage classification cached separately. PDF content, parser identity and model identity contribute to cache identity. Full-document parsing precedes bounded candidate selection; the system does not exhaustively classify every fact in every paper.

Selected blocks receive source-oriented labels such as methods, intervention, result, limitation, background and uncertain. Extracted spans must occur literally in their source blocks. Background-only and uncertain-only blocks do not become ordinary structured paper claims. Classification uses batches of three blocks in the current code.

See [local-document-pipeline.md](local-document-pipeline.md) for parser/worker/cache details.

### Server-side PDF verification

`verified_pdf_evidence`:

1. Reads at most eight findings and twenty annotations per finding.
2. Retains annotations marked `pdf_passage` and groups requests by SHA-256 fingerprint.
3. Streams original-file hashes, opens each matching PDF once and reads requested pages.
4. Stops at a page containing a standalone References heading.
5. Checks whether the normalized quote occurs in native text on the stated page.
6. Creates stable identifiers from source hash, page and quote; deduplicates and restores annotation order.

Quotation verification establishes location and provenance, not scientific entailment. OCR-only text can fail the native-text check. The verifier scans the configured original-PDF store; it is not itself a project authorization boundary. The References heuristic may miss or prematurely exclude content.

### Relevance screening

`relevant_evidence` tokenizes the target product and requires its informative tokens to occur in a document's collected quotations plus first-page native text. It uses set containment at document level, not embedding similarity or an entailment model. A topic match admits a source to later review; it does not prove each passage supports the decision. Client-written titles and summaries do not establish relevance.

## 5. Experimental fact extraction and linking

### Pass A: atomic extraction

The comparison stage groups passages by document, uses up to six documents and eight passages per document, and processes two passages per model call. Short aliases (`e1`, `e2`) are mapped back to stable evidence IDs. Extraction calls are currently sequential.

Dimensions: host, intervention, comparator, carbon source, cultivation, titer, yield, productivity and limitation. Each fact contains an exact value span, evidence ID, optional explicit anchors, intervention type, vocabulary terms and review state.

Deterministic acceptance requires:

- A supplied evidence ID and allowed dimension.
- A non-empty value occurring literally within that passage.
- A digit and recognized unit pattern for measurement dimensions.
- An allowed intervention type; only intervention facts may be genetic/process changes.
- Any linking anchor to occur literally in the same quote.

Stable fact IDs hash the evidence ID, dimension, value and intervention type. Identical facts retain their earlier review state after refresh. Changed spans are new facts.

The prompt distinguishes carbon feed from nitrogen/buffer/antifoam, and product titer from biomass, feed concentration or toxicity challenges. Those are model instructions, not a complete deterministic semantic validator. A literal substring can still be assigned the wrong scientific meaning.

### Pass B: experiment linking

A separate model call proposes groups of fact IDs. The validator rejects incompatible carbon-source/cultivation values and mixing genetic/process intervention types. Cross-passage groups must have:

- One source document.
- A common explicit strain, condition, figure or table anchor.
- That same anchor on every included fact.

Facts not accepted into a group remain individual unresolved records. They are not silently discarded or combined into synthetic experiments. A linking failure also leaves facts unresolved. The current linker uses one bounded response for the supplied facts, so large responses can truncate.

Anchor equality is a conservative grouping heuristic, not proof of experimental identity: one strain may be reused under different conditions. Conversely, strict string equality can split genuinely equivalent conditions.

### Visualization

Records display organism/carbon, intervention/baseline, cultivation and outcomes. Rejected facts are excluded. The titer plot recognizes g/L or g/liter strings, reads their leading numeric value and scales each bar as `100 × value / maximum_visible_value`. Paper filtering changes the visible comparison.

This is a descriptive plot, not a meta-analysis. It does not normalize media, strains, duration, volume or substrates, draw uncertainty intervals, or establish a causal ranking. It currently has no structured analyte field, so correct product assignment still depends on extraction/source review.

## 6. Agent discussion mechanics

Three fixed role prompts are used:

- **Strain engineering:** pathways, interventions and strain-specific transfer.
- **Process feasibility:** cultivation, growth trade-offs and local feasibility.
- **Measurement and evidence:** outcome definitions, comparability and missing measurements.

These are role-conditioned calls to an LLM, not independently trained domain experts. By default they share the configured Ollama model. Optional overrides are `OLLAMA_EXTRACTION_MODEL`, `OLLAMA_PERSPECTIVE_MODEL` and `OLLAMA_REVIEW_MODEL`.

Generation sequence:

1. Construct a decision key from workspace and normalized question.
2. Reuse compatible board state, increment the round and supersede pending questions.
3. Build a bounded context from project/question, current facts, researcher accounts and confirmed rules.
4. Interleave source passages so the first paper cannot occupy every evidence slot; include up to ten passages. Repeated first-page document context is omitted from generation prompts. Compact experiment records are capped at twelve.
5. If no action catalog exists, request two or three concrete alternatives and validate labels/references.
6. Launch the three first-perspective calls in an `asyncio.TaskGroup`. They do not see one another's current-round output. Client concurrency limits still constrain actual simultaneous inference.
7. Validate post structure and run source-support review over actions/posts.
8. Give surviving posts to the review model, which may add challenges, questions and resolution steps.
9. Check review outputs again, then apply confirmed decision rules.

This is a bounded generate–review cycle. It is not an iterative debate to consensus, a majority vote or a numerical aggregation of expert confidence. Disagreement is requested only when supported.

### Claim-support checks

A structural check rejects explicit multi-paper claims citing fewer than two distinct documents and some unsupported local-experience assertions. A separate model call then evaluates each item's cited quotations and available researcher accounts. Reviews run in batches of at most two items and must return an explicit Boolean plus a reason for each exact ID.

Malformed/unavailable review cannot authorize a claim. Unsupported actions/posts are removed. However, the reviewer is fallible and often shares the generating model: it can accept unsupported reasoning or reject valid uncertainty language. This is not an independent scientific verifier.

## 7. Tacit-knowledge elicitation and decision rules

### Fact-linked context: deterministic route

A confirmed source fact opens the inline form. The researcher chooses a relation (same/different/unavailable/unknown), a basis (setup/past case/uncertain), optionally supplies text, and selects a consequence.

A past case additionally records a cue, response and exception. This is a structured experience-recall scaffold; it is not repertory-grid triadic elicitation or automatic discovery of personal constructs.

The backend validates the selections and saves a `GuidedJudgment` against the fact ID/dimension, with the researcher's detail. A stable hash deduplicates identical submissions. It also appends a researcher post.

Consequences:

| Choice | Saved effect |
| --- | --- |
| Save context | Judgment and researcher post |
| Plan a measurement | Also records a `run_experiment` resolution step; does not execute an experiment |
| Keep/exclude | Creates an answered comparison question and a draft decision rule attached to selected actions |

Unknown/uncertain judgments cannot keep or exclude actions. Rules require a separate confirmation. Confirmed exclusions override eligibility; revocation recomputes action disposition. Rejecting a source fact withdraws associated draft/confirmed rules and removes it from current experiment records.

### Board-generated questions: model route

The reviewer can ask about an unresolved preference, local constraint or past experience with consequences for a specific action. Acceptance requires valid evidence, source posts, action IDs and an explanation of why retrieval cannot answer it. Questions justified as needing measurement are routed to experiments instead.

Question identity hashes the decision and action set. This suppresses repeated questions about the same choices, but can also collapse distinct constraints affecting identical actions. Confirmed rules suppress further questions about already resolved actions.

The generated board questions remain in Overview; the screenshot's inline form is a separate deterministic interaction. There is not yet a general algorithm mapping every generated question to a particular data-point widget.

## 8. Persistence, revisions and knowledge graph

SQLite stores the current board in `research_boards` and revision snapshots in `research_board_history`. Mutations carry `expected_revision`. A `BEGIN IMMEDIATE` transaction compares revisions, increments and writes both current state and history; conflicts return HTTP 409.

Preparation saves comparison before starting discussion. Thus a discussion failure need not erase a completed comparison. The UI prevents overlapping mutations and ignores responses for an obsolete workspace/question.

Primary API routes under `/api/research-board`:

- GET root: load board; GET `/knowledge`: graph projection.
- POST `/compare`: verify/extract/link evidence.
- POST `/start`: generate perspectives and review.
- POST `/compare-choice`: source review or local comparison.
- POST `/answer`, `/rule`, `/comment`: answer, review rule, reply.
- POST `/gap-sources`: literature candidates for a missing dimension.

The living knowledge map is computed from current board state and merged with stored project ontology. Nodes include papers, passages, experimental facts, experiment records, researcher context and confirmed decision rules. Edges record provenance, experiment membership and action effects. Rejected facts and unconfirmed/revoked rules are omitted from the corresponding current projection.

Vocabulary alignment is a small deterministic BFO/OBI/ChEBI mapping, not EDAM import or ontology reasoning. There is no automatic biochemical pathway reconstruction, entity-resolution engine, graph-learning process or model fine-tuning from researcher notes. “Living” means the projection changes with saved workspace state. Current origin/review fields do not fully encode who reviewed every fact; the walkthrough audit records that provenance separately.

## 9. Current walkthrough versus automatic capability

Project 1 contains two real downloaded papers and a source-audited set of six experiment records. Automatic selection/classification initially missed outcomes or assigned wrong dimensions. The displayed records were corrected by Codex against the PDFs.

The three displayed role perspectives and one challenge were edited/source-reviewed by Codex after Qwen drafts made unsupported cross-condition recommendations and invented local experience. They are persisted examples in the real board, not evidence that an untouched automatic run reliably produces those outputs. Regenerating can replace those examples with new model outputs.

Artifacts: `artifacts/itaconate-workflow/AUDIT.md`, `comparison-source-audited.json`, `perspectives-call-*.json`, `generated-perspectives.json` and `reviewed-perspectives.json`.

## 10. Known gaps and next implementation priorities

1. Replace the universal inline question/placeholder with dimension-specific templates. For example, a carbon-source selection should ask about substrate/feed formulation, rather than display a pH example.
2. Represent medium concentration separately from feed-stock concentration. In the screenshot, 600 g/L is a glucose feed concentration; the current broad carbon-source field does not model that distinction.
3. Add analyte, measurement basis, time window, vessel and experiment identity to typed facts before automated comparisons or ranking.
4. Make generated questions point to explicit fact/record IDs, so the same data-linked form can host them.
5. Improve bounded linking and schema-constrained generation; evaluate support-review precision and recall using real failures.
6. Record extraction/review actor and provenance as structured fields instead of relying on audit artifacts or a board model label.
7. Add semantic change detection for confirmed rules when evidence or scope changes. Current IDs and decision scoping are not a full truth-maintenance system.

Regression checks cover evidence linkage, review/confirmation requirements, concurrency cancellation, revision conflicts and context persistence. They verify software behavior, not scientific correctness. Real-paper semantic validation remains necessary.
