# Guided evidence comparison

Implemented 9 September 2026. Open **Research Board / Memory → Build evidence comparison** after reviewing relevant PDFs. A board discussion is not required to start.

## Interaction

The comparison separates conditions/interventions from controls/outcomes. Four passages are shown at a time, alternating source papers. Each cell is a proposed extraction with a visible review state. Missing cells read “Not extracted.” Values retain their source units; there is no cross-unit ranking or automatic conversion.

Selecting a detail reveals the original passage and page. **Matches the source** unlocks the local comparison; **Extraction is wrong** rejects the cell. Source confirmation means the extraction was checked, not that the reported experiment is correct or transferable.

The researcher then selects:

1. Same condition, different condition, unavailable here, or unknown.
2. Current setup, recalled past case, or uncertainty.
3. For a past case: a cue, the response taken, and when the lesson should be revisited.
4. Save context, request measurement, or draft an eligibility rule for specifically selected board actions.

The visible selection summary is saved as a researcher-authored structured account, not an inferred scientific claim. No language-model call is needed to save a choice. Unknown comparisons cannot generate eligibility rules. Draft rules require the existing confirmation step and can be revoked. Rejecting a source extraction also withdraws its dependent draft/confirmed rules. The account and rule history remain inspectable.

Saved comparisons enter subsequent board context. Existing free-form accounts remain optional for cases the predefined choices cannot express. The current choice vocabulary is a starter set, not a validated taxonomy of laboratory experience.

## External evidence

**Missing evidence? → Find supporting papers** uses the existing PubMed, Semantic Scholar, OpenAlex and Crossref integrations with the selected dimension and project product/host. External queries do not include recorded cases or local judgments. Fallback queries may broaden the dimension/host while preserving the product.

Returned records show provider attribution, DOI/PubMed links, and metadata screening scope. They remain candidates, separate from PDF-derived cells. They are not automatically imported as verified results; inspect the source and review its PDF through the literature workflow. Provider failures are reported. Topic matching does not establish that a candidate answers the selected gap.

## Provenance and scope

The existing PDF verifier checks original bytes, pages and passages before extraction. One model call per source extracts exact substrings from up to eight verified passages, for at most six sources. Unknown evidence IDs, nonmatching spans, and numerical outcomes without recognizable units are omitted. All accepted cells start unreviewed; identical refreshed extractions retain their review state.

Each row is one passage. It is deliberately not presented as a complete experiment record: the current implementation does not reliably identify experimental arms across figures, tables and methods or merge those arms across passages. Even within one passage, field interpretation and the association between conditions and results still require review. Repeated passages are not independent replications. This is a tested first step toward structured experiment comparison, not a validated experiment-extraction system.

Persistent typed fields live in the existing board payload and revision history; all mutations use optimistic revision checks. The new API routes are `/api/research-board/compare`, `/compare-choice` and `/gap-sources`. Confirmed rules retain their existing current-decision scope and do not universally gate every tool execution in the application.

## Verification

- 71 focused backend tests passed, including source-span validation, no cross-passage substitution, unknown-answer behavior, draft/confirm/revoke effects, source rejection invalidation, persistence, stale edits, and exclusion of private accounts from external search arguments.
- Frontend TypeScript checking and Python compilation passed.
- Live local `qwen2.5:latest` extraction used 16 reverified passages from the two existing real naringenin/precursor PDFs. Two calls returned six accepted rows and eleven exact-span cells. Unsupported cell proposals were discarded. Numerical cells include original concentration and yield units. The run did not validate semantic correctness or human cognitive load.
- A live request through the supporting-papers API returned three metadata candidates with one provider unavailable. The candidates included transfer/clinical-context material, reinforcing the need for source review before use; this is not evidence of perfect gap relevance. That API check used deterministic screened fallback, not a live model-reranking evaluation.
- Browser testing could not run because no browser was connected. Visual layout, complete in-app interaction and reduced cognitive load remain unverified.

Artifacts: `artifacts/evidence_comparison_live/board.json`, `call_1.json`, `call_2.json`, and `external_source_check.json`. The runnable extraction example is `backend/run_evidence_comparison_demo.py`; it refuses to overwrite the artifact directory. Test databases and accounts are isolated from project data.

Restart the backend and reload the frontend to use the new routes. No desktop installer was rebuilt.
