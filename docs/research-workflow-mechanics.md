# Research workflow: evidence, synthesis, and investigator judgment

## Product decision

Use progressive disclosure with one task per surface. The reader supports checking a paper; the board supports comparing papers and making a decision. Do not ask the investigator the same class of question in both places.

| Surface | Responsibility | Visible interaction |
|---|---|---|
| Investigation | Define the question and research focus | Working question, objective selection |
| Evidence library | Find and manage candidate papers | Citation, relevance summary, useful matches, review action |
| PDF reader | Inspect the source | One extracted passage at a time, page navigation, optional reading note |
| Board: evidence | Compare reported conditions and outcomes | Passage-based table; click a cell to check its source |
| Board: perspectives | Inspect alternative interpretations | Three bounded role contributions, followed by a review |
| Board: overview | Resolve consequential local judgments | One pending question or draft lesson, then decision options |

The library shows a heading without identifier strings, one relevance caption, a paper summary, publisher/PubMed link, PDF attachment and reading notes. Editable citation/label/known/unknown/relevance forms are removed for existing papers. Historical judgments and validation records remain under Saved review notes when present. Existing summary text is retained, not retroactively validated. Structured paper notes remain machine-readable inputs. The reader shows highlighted excerpts in ascending page order, with reading notes shared with the library. The old generated selection reason is no longer displayed because it could invent relevance.

PDF attachment accepts readable, unencrypted PDFs up to 30 MB, stores them by content hash within the project, and uses the existing annotation path. An uploaded file is not automatically evidence: its excerpts still need source/topic/support checks.

## M1 — Information retrieval: anchored screening before ranking

Implementation: `backend/research_tools.py`, `search_literature`, `_literature_relevance_profile`, `_screen_literature_record`, `_literature_relevance_score`, `_llm_refine_literature_records`.

1. Inputs are the working question, project goal, explicit product/host and objective context.
2. Build anchored query candidates. A relaxed fallback may drop the host but must preserve the target product. Query the existing PubMed, Semantic Scholar, OpenAlex and Crossref adapters; merge duplicate records.
3. Screen title/abstract before ranking. Reject supplementary artifacts. If product tokens are known, require all product tokens. Otherwise require at least two specific topic tokens. Missing host or requested substrate is a transfer limitation, not proof of direct applicability.
4. Build lexical term weights from question (8), goal (7), objective title (5), definition (4), signals (3), and supplied context (2), with domain/specificity boosts. Normalize selected weights as `1 + 4*w/max(w)`.
5. Sum token hits weighted by title (3), abstract (1.35), and journal (0.35). Add phrase hits (5 in title, otherwise 2.5), explicit product/host matches and metadata-quality adjustments; penalize clinical mismatch, competing products and incomplete metadata. These are ranking heuristics, not probabilities or scientific confidence.
6. A bounded model reranker selects from eligible candidates and supplies a rationale. Invalid selections and explicit irrelevance are excluded. Empty selection remains empty; do not fill a result quota. The explicit offline/rerank-disabled mode uses the screened lexical ranking.

Output: candidate records, IDs, rationale and transfer scope. The compact Matches line is presentation-only and does not change ranking. Existing saved libraries are not automatically re-screened by Prepare evidence; this is a remaining limitation.

## M2 — Annotation: bounded passage selection with source identity

Implementation: `backend/research_tools.py`, `annotate_pdf_for_objective`; `frontend/.../PaperEvidencePanel.tsx`.

1. Reuse cached annotations when the existing source/context checks pass. Otherwise read the original PDF.
2. Stop candidate collection at the detected References section. Construct passage candidates from page text and rectangles; rank using investigation terms, section cues, numeric/outcome cues and length adjustments. Deduplicate normalized passage signatures.
3. Send at most 24 ranked candidates to the selector. Accept at most the requested number (normally 8, bounded to 1–20). A model rejection is not replaced by a keyword candidate. Keyword-only mode is an explicit environment setting.
4. Store each passage's original PDF SHA-256, page, exact snippet, stable passage ID and proposed selection reason. Highlight matching rectangles, with text-search fallback. A reason is an interpretation, not an additional source.
5. Retain structured paper extraction for downstream synthesis. Do not make a separate model call to generate passage elicitation prompts. New annotations use question/project/objective context, not the selected legacy persona lens.
6. Reader interaction: Previous/Next follows page order and requests the PDF page; source text stays visible and reading notes are optional. Actual PDF fragment navigation depends on the browser's PDF viewer. If explicit target-product tokens are absent before References, annotation makes no selection/notes model calls and returns the readable PDF with zero excerpts. Annotation cache contract version 3 invalidates earlier relevance explanations.

An extracted passage is not a reconstructed experiment. A cached legacy annotation is retained rather than silently rewritten.

## M3 — Comparison: source-bound cells, explicit human corrections

Implementation: `backend/evidence_comparison.py`, `build_comparison`, `accept_cells`, `guided_judgment`.

Extract a bounded set of host, intervention, comparator, substrate, cultivation, titer, yield, productivity and limitation cells from verified passages. A cell must be an exact source substring; numeric metrics must include the required numeric/unit pattern. Do not join separate passages into an invented experiment or normalize incompatible units implicitly.

Rows represent passages and are interleaved by paper. Missing means not extracted. Human review can confirm or reject a cell. Optional setup comparisons and remembered cases create recorded context, a measurement task or a draft action rule; they do not bypass rule confirmation. Rejecting a cell withdraws dependent rules.

## M4 — Agent discussion: independent proposals, then bounded critique

Implementation: `backend/research_board.py`, `verified_pdf_evidence`, `generate_board`, `accept_review`.

1. Recompute source hashes on the server. Require each quoted passage to occur on its claimed original page, before References. Reject unverifiable passages.
2. Reuse a valid canonical action catalog for the current decision; otherwise generate two or three evidence-linked alternatives. Action IDs are canonical, not free-form aliases.
3. Interleave evidence across papers and supply at most ten quoted passages, with quote length bounded in the prompt.
4. Run three concurrent role prompts under the shared model concurrency limit: strain engineering, measurement/evidence, process feasibility. Each receives the same context and catalog but none of the other roles' current-round posts.
5. Require nonempty text, valid evidence references and a catalog action ID. Then audit both action labels and perspective claims against their cited excerpts. Withhold items without explicit support-review approval, and remove perspectives whose actions were rejected. Failure yields a partial round, not stock replacement text.
6. A reviewer sees supported posts and proposes source-linked challenges, resolution tasks, and at most two eligible investigator questions. Audit challenges and question justifications before accepting them. There is no majority vote and no consensus confidence score.

Reading notes are included separately as researcher accounts, bounded to eight notes of 1,200 characters. They cannot create source references or confirmed constraints. Role prompts share a model; they are perspectives, not independent empirical replications. Citation validation checks provenance, not entailment. The additional support audit also uses the model and remains fallible.

### Grounding contract version 2

Before comparison or recommendation, group verified excerpts by original-document hash. For an explicit target product, require its normalized tokens in original-PDF first-page context or verified excerpts. Client citations, labels and generated relevance captions cannot establish this match. This conservative filter can miss synonyms and transfer evidence; a lexical match is not proof of scientific relevance.

Before the support model runs, reject recognized multi-paper assertions citing fewer than two distinct source hashes and recognized assertions of local laboratory experience/capability when no researcher accounts exist. These pattern checks catch known failure classes, not all paraphrases. The model audit checks remaining organism/product/intervention/outcome claims and must explicitly approve each whole item with a reason. Missing, duplicate, malformed or failed audit results withhold the item. Repeated excerpts across roles are allowed; they do not increase source independence.

Legacy boards without this version remain stored but are hidden as actionable recommendations; mutation routes and confirmed-rule context reject them until regeneration. Regeneration starts a new checked board rather than carrying forward unchecked actions/rules. If no relevant evidence or supported perspective exists, the system requests relevant sources instead of producing an experiment recommendation.

The real investigation-4 check on 2026-09-19 found five verified excerpts from one TAT-fusion/mammalian-cell paper in the frontend-launched PDF store, and zero excerpts eligible for the itaconic-acid target. Its former multi-paper claim was unsupported. No saved project records were deleted during this check.

## M5 — Question asking: eligibility gate and a small review queue

Implementation: `accept_review`, `answer_board`, `ResearchBoardPanel.tsx`.

Accept a proposed question only when it has: (a) an unresolved flag; (b) ownership classified as preference, local constraint or experience; (c) an ownership rationale and reason retrieval cannot settle it; (d) valid action IDs; (e) valid source posts; and (f) evidence references connected to those posts. Measurement/optimization justifications are routed to experiments. Other gaps can be routed to literature, workspace inspection or comparison.

Deduplicate by decision ID and sorted affected action IDs; suppress a question already covered by confirmed rules. This coarse deduplication can conflate different constraints on the same action and needs future evaluation.

The implemented question is deliberately an action-exclusion question: what local constraint or experience would rule out these options? It is not yet a repertory grid or a general adaptive interview. The UI shows the first pending item in accepted order; draft lessons take priority. There is no calibrated value-of-information ranking. Asking fewer questions here is a presentation/gating policy, not a demonstrated optimal interview policy.

Keep/exclude answers create a draft. Unsure/decide-later creates no rule. A free-form account can propose a rule only with an exact user quote and catalog action IDs. The user reviews its statement, scope and effect before application.

## M6 — Decision memory: confirmed, scoped, reversible rules

Implementation: `apply_rules`, `review_rule`, `BoardRepository`.

Only confirmed rules for the current decision affect action eligibility. Confirming an exclusion removes its action IDs from the eligible set; revocation recomputes eligibility. Changing the research question changes decision scope. SQLite revisions implement optimistic concurrency: stale writes are rejected instead of overwriting a newer review.

This filters proposed actions; it neither proves that an option works nor executes an experiment. A scientific unknown remains a measurement task.

## Collaborators and retired code

The research board replaces manual collaborator selection for obtaining multiple perspectives. The old selection also provided annotation weighting and persistence identity, so it was not previously a cosmetic control.

Normal workflow now removes the picker, manual collaborator creation, and persona starter questionnaires. A saved valid persona ID is retained; an unassigned query uses a stable literature/evidence/benchmark profile, falling back to the lowest existing persona ID. This is a compatibility mechanism, not an extra decision for the investigator. Existing server APIs/storage still use these IDs; a complete persona-schema deletion requires a separate data migration. Other legacy objective/synthesis APIs may still consume that profile.

Removed implementation: duplicated PDF question handlers and editing forms, unused collaborator-grid component, legacy numerical elicitation and inferred-memory panels and their workspace action handlers, and the passage-question model generator/helpers. Backend experimental harnesses and persisted historical fields remain for compatibility and reproducible evaluation; they are not active user-facing mechanisms.

## Validation and remaining limits

Test source verification, no annotation quota filling, absence of per-passage interviews, context separation, exact action IDs, unknown/deferred answers, confirmation/revocation, stale revisions and stable persona fallback. Type-check and inspect the reader and query flow.

The combined mechanism is source-grounded comparison plus perspective critique plus selective human constraints. Its usefulness must be evaluated against the same papers and decision task with simpler baselines. Measure source errors, inappropriate questions, missed local constraints, decision changes, completion time and investigator effort. Do not claim novelty, lower cognitive load or scientific validity from implementation tests alone.
