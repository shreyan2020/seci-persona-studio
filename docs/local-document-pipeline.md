# Local document processing

The annotation endpoint now uses LiteParse 2.14.6 and the existing Ollama client. No Jev or hosted OCR/inference provider is required.

## Mechanism

1. Hash the original PDF bytes. Parse all pages with LiteParse in a separate, hidden worker process, with OCR enabled, a 300-page limit and a 120-second deadline. Failed or incomplete parsing raises an error. Kill and join the worker on cancellation or timeout.
2. Cache the complete parser output under `PAPER_EVIDENCE_ROOT/.document-cache` (override with `DOCUMENT_CACHE_ROOT`). Identity includes source hash, parser version, OCR setting and pipeline contract. The original remains untouched. Atomic writes prevent partially written cache entries.
3. Derive stable passage IDs from source hash, physical page, block/row/window position and text. Preserve section headings, layout block types and bounding boxes. Table-row passages include the reported headers and cell separators. Large blocks are split into word-boundary windows; full parser output remains available in the cache.
4. Retrieve candidates using the existing project-term scorer and relevance selector. Source-only classification is lazy: classify at most the retrieved 24 blocks per annotation request, three per model call. The entire paper is parsed, but this is not an exhaustive whole-paper fact extraction job.
5. Classify with multiple labels: methods, intervention, result, limitation, background, uncertain. Extract up to two exact factual spans per block. Prompts contain source text, section and layout type, but no project goal, researcher preference or invented lab context. Cache each successful passage independently by source/parser/model identity. Another project retrieving that passage reuses it. Incomplete and failed classifications are not cached as empty successes.
6. Check that each returned fact is a literal substring of its source block. Build page-labelled notes from those spans, excluding background-only and uncertain-only blocks. No automatic transferability narrative is added. Strict preparation reports incomplete classification rather than claiming success.
7. Retain the existing project relevance stage, visual annotation and PDF provenance verification. Annotation metadata includes source block IDs and passage labels. The comparison module continues extracting and linking experimental facts from verified passages; classification labels do not authorize recommendations.

The scientific-parsing entry point defaults to the same cached LiteParse output when no alternate parser is configured. Candidate snippets must match normalized native PDF text before selection. Selection uses short model-facing IDs mapped back to stable source IDs, a 16,384-token context budget and the extraction-model override. Model failures and invalid selection responses raise retryable errors; an explicit empty selection remains a valid rejection.

Changing project context re-runs relevance selection but can reuse parsing and source classifications. Changing model tags, parser versions or source bytes invalidates their respective cache entries. Replace model weights under the same tag only with an updated `OLLAMA_MODEL_REVISION` to invalidate semantic cache entries.

## Limits and validation

Exact-span checks establish provenance, not scientific correctness. A classifier can still misidentify a cited background result as the present paper's result, or miss an intervention. The native-PDF verifier remains in place; OCR-only text may not pass that existing verification and is not silently treated as verified evidence. Complex table and genotype reconstruction still needs visual evaluation. Cache files contain source text and have no automatic retention policy in this change.

Tests cover stable coordinates/IDs, table headers, exact spans, background exclusion, per-model cache invalidation, cross-project reuse, incomplete classification, changed PDF bytes, and worker cancellation cleanup. A real 15-page research PDF was parsed into 327 blocks; a six-passage local Qwen probe returned classifications for all six. This is a compatibility probe, not a scientific accuracy benchmark. Docling is not installed or selected automatically; a controlled table-extraction comparison remains future evaluation.

Integration verification on 21 September 2026: 83 backend regression tests and the frontend TypeScript check passed. A real naringenin-paper annotation run using local Qwen returned three annotations, all three matching normalized original PDF page text, plus eight evidence claims, four method spans and seven quantitative spans. The default scientific-parser entry point also returned LiteParse sections successfully. These are parser/model integration checks, not a full browser workflow or expert assessment of the extracted facts.

Upstream parser documentation: https://github.com/run-llama/liteparse/tree/main/packages/python . Install the pinned dependency with `python -m pip install -r backend/requirements.txt` in the application's Python environment.
