# Streamlined research overview

Open **Research Board / Memory** in a project. The default view shows evidence counts, a single pending judgment, and the available decision options. Evidence comparison and agent discussion have separate views. The knowledge map is collapsed; legacy diagnostics have been removed from this interface. See [research workflow mechanics](research-workflow-mechanics.md) for the reader, question policy, and compatibility details.

**Prepare evidence** uses the current library, searching with the existing relevance-screened retrieval service only when the library is empty. It checks up to five records not explicitly marked irrelevant, reuses matching saved PDFs, prepares missing annotations serially, then saves a comparison and a perspective round in order. This does not retrospectively re-screen all older library records. Paper failures are reported; successful stages remain saved if a later stage fails. Additional records can still be reviewed individually.

Only the first pending question is displayed. A draft lesson takes priority over another question. Deferral remains unresolved, and action eligibility changes only after explicit rule confirmation. Eligibility does not establish scientific validity. The existing backend continues to validate source provenance and question routing.

The full-screen panel traps keyboard focus, closes with Escape, restores the initiating focus and prevents background scrolling. Progress lives above the research views.

## Layout preview

In development, `/research-preview` renders the same component with clearly labeled synthetic cases. It demonstrates pending judgments, draft lessons, source inspection and discussion. It does not call mutation endpoints or alter project research. The route is unavailable in production.

## Verification

- `node --test tests/prepare-evidence.test.cjs` in `frontend`: revision propagation, failed-stage handling, stale-context protection and retained intermediate progress.
- `node node_modules/typescript/bin/tsc --noEmit` in `frontend`.
- `python -m unittest evidence_comparison_tests research_board_tests paper_pdf_reuse_tests` in `backend`.
- Browser inspection of the existing project's empty board and the populated synthetic preview, including desktop and narrow layouts, source selection, view switching and draft review.

A fresh live retrieval-to-model preparation batch was not run for this interface change. No claim of reduced researcher effort is made without a user evaluation.
