# Real-PDF audit of tacit knowledge elicitation

## Verdict

The system is a functioning prototype, not an empty skeleton. It reads real PDFs, generates substantive notes, proposes gaps, computes question scores, updates beliefs, and retains session state. However, this audit does **not** support treating it as a reliable tacit-knowledge elicitor. The weakest parts are evidence integrity, identifying genuinely user-owned gaps, meaningful answer alternatives, and reusing what was learned.

The code's mathematical operations are more developed than its checks on the meaning and source of their inputs. The most revealing result was a selected question with two poorly distinguished answers, perfect assumed response likelihoods, and different resulting research actions.

No production behavior was changed during this audit. Three runnable audit scripts and inspectable evidence were added. Existing tests passed; the observed quality failures below remain open.

## Question and real documents

**For glucose-derived naringenin production in Saccharomyces cerevisiae, should the first strain-engineering experiment increase aromatic precursor supply or balance the downstream naringenin pathway? What transfers across papers, what requires measurement in the project strain, and what local judgments are needed?**

The two original PDFs already existed in the workspace:

| Paper | Why it belongs in the case |
| --- | --- |
| Koopman et al. (2012), *De novo production of the flavonoid naringenin in engineered Saccharomyces cerevisiae*, [DOI](https://doi.org/10.1186/1475-2859-11-155), 15 pages | Direct evidence about the naringenin pathway, precursor changes, pathway balancing and cultivation conditions. |
| Liu et al. (2019), *Rewiring carbon metabolism in yeast for high level production of aromatic chemicals*, [DOI](https://doi.org/10.1038/s41467-019-12961-5), 13 pages | Evidence about aromatic precursor production and carbon redistribution. Its p-coumaric acid outcome is not a naringenin outcome. |

An adequate analysis must preserve that outcome distinction. A precursor-production result does not directly establish improved naringenin production in another strain. The papers also describe growth and cultivation conditions that make a local growth-versus-product trade-off relevant, but they cannot set that preference for a researcher.

PDF bytes, hashes, titles, page counts and model identity are recorded in [manifest.json](../artifacts/real_pdf_elicitation_audit/manifest.json). Original and annotated pages were rendered and visually inspected, including the problematic bibliography page. This verifies document identity and visible annotation behavior, not the scientific correctness of every generated note.

## What was actually executed

The installed local model was `qwen2.5:latest`, 7.6B Q4_K_M, digest `845dbda0ea48ed749caafd9e6037047aa19acfcfd82e704d7ca97d631a0b697e`. The runtime reported a 4,096-token context. No frontier-model comparison was run.

1. Both PDFs passed through the existing `annotate_pdf_for_objective` function in standard mode. This included live model selection of passages and live structured-note generation.
2. The audit mirrored the frontend's PDF annotation update into a PDF-only workspace: generated insights, annotations and questions were preserved, with no invented pre-existing `knowns`.
3. That state passed through `extract_literature_sources`, `run_epistemic_gap_harness` and `create_session` with the normal selection thresholds.
4. The separate `infer_workspace_memory` function was exercised with the same state.
5. A diagnostic bypass used direct PDF snippets and an explicitly described, fictional unresolved growth preference. It tested whether removing the generated-summary handoff would be sufficient.
6. Because neither harness run proposed a user question, a final isolated test supplied the preference gap to `build_dynamic_question_prompt`, then used the existing normalization, scoring and answer-update functions. This tests question generation and updating, **not autonomous gap discovery**.

There were 12 recorded live model calls across these stages, totaling approximately 241 seconds of measured model-request time. This is not end-to-end user time or a performance benchmark. The first PDF/harness run used seven calls, approximately 127 seconds.

The actual web routes, browser interaction, literature search/download, and human answering were not exercised. Standard PDF parsing worked through PyMuPDF. The optional strict scientific-parser path was checked and failed because GROBID/Docling was not configured; its errors are saved. The original audit driver's memory invocation omitted a required workspace key; that driver error was recorded, corrected, and the memory function was subsequently run successfully. It is not counted as a product failure.

## Observed results

| Check | Observation | Assessment |
| --- | --- | --- |
| Real PDF processing | 28 pages, 16 visual annotations, structured notes from both papers | Working functionality |
| Passage relevance | Two selected snippets came from Liu's bibliography; one concerned Taxol precursors in E. coli | Failed relevance/source boundary |
| Passage elicitation | All 16 prompts used the fixed transferability template | Basic scaffold in the tested default configuration |
| Stable prompt identity | Liu had eight prompts but only five distinct IDs | Reproducible collision defect |
| Evidence handoff | Harness received 20 annotation chunks and four generated-gap chunks, zero raw evidence chunks | Source detail is lost in this PDF-only UI path |
| Claim validation | Four accepted claims; two cited only generated-gap chunks | Failed provenance-type check |
| Cross-paper reasoning | Four gaps, all routed to `inspect_workspace`; zero user questions | Did not demonstrate useful integrated resolution |
| Workspace memory | One item repeated the already-explicit target host; ten questions returned | No newly demonstrated tacit knowledge |
| Direct-PDF diagnostic | Better resolver variety but still zero user questions; supplied preference not captured | Removing the summary handoff alone was insufficient in this run |
| Isolated supplied-gap test | Generated one question and selected it with positive VOI | Mechanics work; semantic validity failed |
| Answer reuse | Adaptive answer history removed by context compaction | Rebuild can lose what was learned |

The baseline's zero user questions is not itself proof of failure: choosing not to interrupt can be correct. The concern is the poor gap content and source handling behind that result. The positive control is one model sample, not a sensitivity estimate.

### The most revealing question

With the growth-tolerance gap supplied by the evaluator, the model asked:

> What is the acceptable growth reduction for increased naringenin production?

Its two principal alternatives were:

- “Higher naringenin production is preferred over slower growth”
- “Slower growth is preferred for higher naringenin production”

These are not clear opposing growth-versus-production policies. Both favor higher production; neither clearly states that preserving growth is mandatory. Nevertheless, the system accepted them as perfectly diagnostic alternatives, assigned equal priors and perfect `1/0` likelihoods, and calculated `EVSI=0.1`, cost `0.02`, and net value `0.08`.

In controlled branch probes, the first option selected “Increase aromatic precursor supply”; the second selected “Balance the downstream naringenin pathway.” Both left a posterior of approximately 0.999999 on their corresponding hypothesis and ended elicitation. The difference follows the generated loss table, not a verified difference between two defensible user preferences.

The “Other” branch was also probed with fictional text: “I cannot specify a trade-off without reviewing a previous failed strain.” The engine inserted that sentence as a new hypothesis with hardcoded probability 0.7, rebuilt its decision actions, and generated a discriminator. It did not retrieve the earlier failure or elicit the concrete experience. This is hypothesis insertion, not evidence that tacit reasoning was understood.

See [supplied_gap_session.json](../artifacts/real_pdf_elicitation_audit/supplied_gap_session.json) and [supplied_gap_answer_branches.json](../artifacts/real_pdf_elicitation_audit/supplied_gap_answer_branches.json). Every answer here is a synthetic software probe, never a real user response.

## Why these failures occur

**Evidence filtering is undone by annotation top-up.** `research_tools.py` fills the selected list back up to the requested count from keyword-ranked candidates. The model selected one passage for Koopman and three for Liu; the module returned eight each. The first bibliography passage was selected by the model itself, while the second was added afterward. Both model relevance and deterministic filtering need attention.

**Prompt identity is based on a truncated template prefix.** `_passage_prompt_id` includes the page and question, then truncates the slug before the distinguishing terms. Different passages on the same page can therefore share IDs. The frontend constructs passage-memory IDs from these IDs, so separate judgments can collide.

**Structured notes are flattened and truncated before the harness.** `_structured_notes_to_insights` prioritizes claims and methods, with a ten-item cap. The source extractor caps annotation insights again. In this case, limitations and transferability notes did not survive as typed chunks, and the original `annotations` objects were not used as raw source evidence.

**The validator checks existence of chunk IDs, not evidential support.** `normalize_paper_model` permits an `analyst_gap` chunk to support a claim, despite the mapper prompt prohibiting it. A controlled adversarial probe attached a plainly unsupported universal production claim to a valid gap ID; it was accepted. This does not validate entailment or truth. A relation labeled `replicates` was also accepted between claims from the same paper, with no check for independent replication.

**The three elicitation paths do not share a common acceptance policy.** Passage prompts default to templates unless `ENABLE_PDF_PASSAGE_PROMPTS_LLM=1`. Workspace memory appends fallback questions even after successful generation. Adaptive elicitation has routing and scoring, but no implemented decision-switch certificate that verifies distinct answer meanings and justified action consequences. The optional LLM passage-prompt configuration was not evaluated here.

**Learning is not consistently fed back.** The frontend includes `adaptive_elicitation_session` in saved explicit state, but `_compact_explicit_state_for_prompt` excludes it. A direct probe confirmed that prior adaptive answers disappear at that boundary. Other answer paths use `clarifying_answers`, so this finding should not be generalized to every kind of saved judgment.

Source locations: `research_tools.py:2179`, `research_tools.py:2230`, `research_tools.py:2407`, `epistemic_harness.py:146`, `epistemic_harness.py:251`, `main.py:3729`, `main.py:4142`, `adaptive_elicitation.py:1056`. Evaluated file hashes are in [code_fingerprints.json](../artifacts/real_pdf_elicitation_audit/code_fingerprints.json).

## What to improve first

1. **Repair the evidence contract.** Pass typed, page-linked PDF passages through to the harness. Keep generated questions separate from evidence. Exclude bibliography entries as primary findings and preserve limitations alongside claims. Hash passage identity rather than truncating a template.
2. **Make questions earn acceptance.** Require an unresolved user-owned premise, clear opposing answers, and explicit answer-to-action consequences grounded in project constraints. A logical/schema check alone cannot establish semantic correctness; ambiguous alternatives need rejection or review. Keep generated VOI inputs diagnostic until calibrated.
3. **Complete the learning loop.** Carry confirmed answers into every subsequent run; distinguish “I don't know,” “this is a preference,” and “recall this experience.” For tacit knowledge, use a concrete previous case, failure cue, exception or contrast, then ask the user to confirm the resulting reusable rule and its limits.
4. **Retest the same case and a held-out case.** Check that references cannot become findings, distinct passages cannot share answer IDs, an already-answered preference is not re-asked, missing measurements are not sent to the user, and an abstention does not become a high-confidence decision hypothesis. Then compare to a single stronger model with the same evidence.

The right next build is this evidence-to-question-to-confirmed-rule loop. Adding more scores or personas would not address the failures observed here.

## Reproduction and evidence

From the repository root, choose a new empty artifact directory so earlier results remain intact:

```powershell
$env:ELICITATION_AUDIT_DIR = "$PWD/artifacts/real_pdf_elicitation_audit_next"
python backend/run_real_pdf_elicitation_audit.py
python backend/run_real_pdf_elicitation_probes.py
python backend/run_real_pdf_question_stage_probe.py
```

The existing two PDFs, Python dependencies and running local Ollama model are required. The final isolated probe expects the preceding direct-PDF diagnostic to have produced a valid harness result. Model generation is stochastic, so later outputs need not match this run.

The scripts invoke PDF annotation to create audit copies. The `DATABASE_PATH` override directs database initialization to the audit directory. No saved user project or persona was edited.

Read [audit_checks.json](../artifacts/real_pdf_elicitation_audit/audit_checks.json) for counts, [deterministic_probes.json](../artifacts/real_pdf_elicitation_audit/deterministic_probes.json) for counterexamples, and the adjacent `call_*`, `probe_*`, and `question_probe_*` files for model prompts, responses, settings and timings. All intermediate inputs and outputs remain available for review.

The 26 existing focused tests passed and all three audit scripts compiled. Those tests demonstrate software behavior under their fixtures; they do not contradict the semantic failures found with real documents. This audit establishes concrete defects and limitations for this case, not human validity, exhaustiveness, or performance across models.
