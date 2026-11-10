# Research board and tacit elicitation

UI update, 8 September 2026: the board now occupies the full window, uses two columns for posts on wide screens, and has a sticky close/header area. Both the board and PDF reader reserve 48 CSS pixels above their controls for desktop window buttons. Paper activity is shown next to the relevant Review paper button. Saved reader metadata persists with the finding; reopening checks the research context and the local file's Last-Modified header before skipping preparation. Missing or changed files fall back to the existing preparation API, which now checks for a saved original PDF before attempting a download. Restart the backend to enable the added HEAD route. Older findings without reader metadata go through preparation once to populate it; compatible server annotations can still be reused.

Verification for this UI update: 19 focused backend tests and frontend type checking passed. The running browser showed the full-width board, 48-pixel clearance, and status beside the paper. An extension panel interrupted automation before the PDF reopening interaction completed, so native Electron placement and the complete live reopening sequence remain unverified.

Implemented and checked on 6 September 2026. This extends the real-PDF audit in `real-pdf-tacit-elicitation-audit.md`.

## What the component contributes

The useful contribution is an inspectable path from a paper passage, through a proposed action and an unresolved local judgment, to a researcher-confirmed rule with an observable action effect. A stronger language model can improve the proposed interpretations; it does not replace provenance, project memory, explicit confirmation, or reversible rule application. This implementation does not establish that multiple roles outperform a single model.

The board has three fixed backgrounds: strain engineering, measurement and evidence, and process feasibility. Each reads the same source material independently in the first round. A review call then posts challenges and proposes questions. These are different role prompts using the configured Ollama model, not independent human experts or independent scientific evidence. Agreement is never counted as confidence.

## Using it

1. Restart the backend and frontend with the updated source. Existing packaged desktop binaries are not rebuilt by this change.
2. Select a project and working research question. Prepare/annotate the relevant PDFs in the literature workflow. Older annotation caches are invalidated once because they lack the new provenance contract.
3. Open **Research Board / Memory**, then **Gather perspectives**. A single selected persona is not required; the board is shared across personas for that project/question workspace.
4. Inspect each proposed interpretation and its expandable source passages. Reply with missing context or a correction. Another round includes recent researcher replies and confirmed rules.
5. For a proposed question, keep the named actions eligible, exclude them, defer, or describe a concrete past case: what happened, which cue mattered, and when the lesson would not apply.
6. Review the draft lesson, its quoted account, listed action effect, and scope. Only **Confirm and apply** changes action eligibility. You can reject a draft or revoke a confirmed rule.

Rules are scoped to the current research decision. An exception in prose is preserved for review; the system does not automatically detect when real-world circumstances change. Revoke or revise the decision when an exception becomes relevant.

## Implementation boundaries

- Original PDF bytes are fingerprinted. Page and normalized passage text are verified against those bytes before admission to the board. Generated annotation commentary cannot substitute for a raw passage.
- Stable passage/question IDs prevent same-page collisions. Reference sections are excluded conservatively, including a mixed content page where the reference heading starts. Annotation count is no longer filled to a quota. Stock passage questions are disabled by default.
- A shared action catalog prevents each role from creating its own aliases. Questions must reference catalog IDs, source posts and valid evidence, and claim unresolved user ownership. Obvious measurement justifications are routed to an experiment. These checks are structural and partly heuristic; they do not prove that a question truly requires human judgment.
- The action catalog itself is model-proposed. Exact ID consistency does not prove conceptual distinctness of all action labels.
- An uncertain answer creates no preference or numerical belief. A past-case interpretation requires an exact quote and remains a draft. Confirmation is mandatory for rule effects.
- SQLite stores the board and revision history with optimistic concurrency checks. Stale edits return a conflict instead of overwriting newer work.
- Confirmed rules filter the board's actions deterministically and enter subsequent board, adaptive-elicitation and workspace-memory context. This is not a universal execution gate across every existing planning/tool API.
- Existing adaptive numeric scores remain in a collapsed diagnostic panel. The new board does not invent probabilities, utilities, or expert-vote weights.

## Observed real-PDF evaluation

Question: For glucose-derived naringenin in *S. cerevisiae*, should the first strain experiment increase aromatic precursor supply or balance the downstream naringenin pathway? Which findings transfer, which require measurement in our strain, and which local judgments remain?

Documents:

- Koopman et al. (2012), *De novo production of the flavonoid naringenin in engineered Saccharomyces cerevisiae*, DOI 10.1186/1475-2859-11-155.
- Liu et al. (2019), *Rewiring carbon metabolism in yeast for high level production of aromatic chemicals*, DOI 10.1038/s41467-019-12961-5.

The initial updated annotation run selected 16 verifiable passages across the two original PDFs, with no reference-section selections and no stock passage questions. The final board run reused those saved annotations and independently reverified the passages against the PDFs. Model: local `qwen2.5:latest`, resolved digest recorded in the manifest, 8,192-token context. Five board calls took approximately 47 seconds in total.

Final observed result: two accepted perspectives, two review challenges and one pending local-constraint question. One strain-engineering response omitted structured citations/action ID and was rejected; the board explicitly reported partial output. No replacement post was fabricated. Both documents were cited in the discussion, but the final user question linked to a post citing one document, so this is not evidence of successful multi-paper question synthesis.

The question asked what local constraint or past experience would rule out downstream naringenin pathway balancing. A controlled exclusion answer left eligibility unchanged while draft, then excluded that exact catalog action after confirmation and persisted through reload.

Browser checks used the actual board component and API in an isolated database. A clearly labeled synthetic past case about unavailable assays produced a quoted draft lesson via the live local model. Confirming excluded the named action, page reload preserved it, and revoking restored eligibility. A review reply was also saved and source passages displayed with page numbers. These are software checks, not observations of the user's lab or evidence of human elicitation validity.

Scientific limitations observed: the accepted discussion confused p-HCA precursor balancing with downstream naringenin pathway balancing. The review raised transfer concerns but repeated some of that conflation. Two roles also returned a placeholder caveat, shown as an explicit missing-limitation notice. Valid passage citations establish traceability, not entailment. The current role discussion must therefore be reviewed before scientific use.

## Verification and artifacts

44 focused backend tests passed across board contracts/API/persistence, provenance, Ollama context/caching, gap routing, and existing adaptive elicitation policies. Frontend TypeScript checking passed. Browser checks exercised the actual component in an isolated preview, not the complete production project-selection workflow.

Reproducible runner: `backend/run_research_board_demo.py`. It refuses to overwrite a nonempty output directory. Set `RESEARCH_BOARD_OUTPUT` to a new artifact directory; optionally set `RESEARCH_BOARD_REUSE` to the saved annotation directory. The default run annotates the existing original PDFs and uses the configured local model; it requires Ollama to be available.

- `artifacts/research_board_live/`: initial annotation/PDF outputs and initial board probe, retained as evidence of issues found.
- `artifacts/research_board_verified_live/`: corrected catalog run, exact prompts/responses/timings, model manifest, verified evidence, board before/after synthetic confirmation, and final isolated UI review state.

The next research validation should compare a single-model baseline with this board using the same papers and model budget, then have researchers assess source entailment, question answerability, newly elicited context, and resulting decision changes. No superiority claim is supported by this single case.
