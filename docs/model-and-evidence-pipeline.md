# Evidence access and model responsibilities

## Implemented

PDF resolution reuses the saved original first, resolves missing PMC identifiers via PubMed or Europe PMC (including DOI-only records), then enumerates the article's versions in NLM's public PMC Cloud bucket. It reads version metadata rather than assuming a version or guessing a filename, prefers published versions over manuscripts, converts official S3 URLs to HTTPS, and checks PDF magic bytes before saving. Existing direct-PDF and web download fallbacks remain. A failed download does not establish that a paper is closed access. The supplied PMC12177971 example was downloaded and opened successfully as a 16-page PDF on 2026-09-20.

Reference: https://pmc.ncbi.nlm.nih.gov/tools/pmcaws/ and https://pmc-oa-opendata.s3.amazonaws.com/README.txt . NLM is the source of this dataset. Downloads are saved snapshots, not automatically synchronized with later revisions.

The comparison table retains exact quoted spans. It shows a short strain label when the extracted value includes a parenthetical genotype; the original value remains in the source-detail view. New extraction requests ask for the strain identifier and intervention separately. Rows are ordered by page within each paper and interleaved across papers. This does not repair malformed PDF character extraction or certify genotype notation.

Claim-support review processes at most two proposed items per call and includes their complete stored quotations, replacing the earlier 900-character truncation. Structural failures, explicit unsupported judgments, incomplete review responses, and model errors produce distinct diagnostic messages. No failure permits a recommendation. This remains a fallible model-based review; a model's approval is not scientific validation. Old saved decisions still require regeneration; the UI now requests a refresh without describing internal schema versions.

Optional installed Ollama model tags:

| Setting | Responsibility |
| --- | --- |
| `OLLAMA_EXTRACTION_MODEL` | PDF notes, comparison fields, standard literature reranking |
| `OLLAMA_PERSPECTIVE_MODEL` | Board action candidates and specialist perspectives |
| `OLLAMA_REVIEW_MODEL` | Claim-support checks and discussion review |

Blank settings inherit `OLLAMA_MODEL`. This is selective routing, not a replacement of every legacy model call. No model weights are installed automatically. All routes share the existing client queue; multiple large models may incur weight-reload costs with one resident-model slot.

## Recommended next evaluation, not implemented

1. Retrieve paper passages by hybrid lexical and embedding search, with explicit product/host/condition scope. Preserve document identity, section/page, and exact spans. Retrieve neighboring method/result context before inferring absence or transferability.
2. Evaluate extraction against scientist-checked spans and units, including genotype notation. Measure false assignments across experimental conditions, not just valid JSON.
3. Evaluate support review against supported, contradicted, irrelevant, and insufficient-evidence claim pairs. Measure false acceptance and false rejection separately before selecting another reviewer model.
4. Let specialist perspectives propose alternatives from that evidence; use a reviewer to examine source support and meaningful disagreements. Repeated agreement is not independent evidence.

Nimble (https://github.com/bespokelabsai/nimble) currently produces flat enum/boolean decisions from text, with a 2,048-token prompt limit. It cannot extract arbitrary text spans or generate notes. It is a candidate for a separately evaluated relevance/section/claim classification stage, not a drop-in note extractor. Its choice probabilities are not calibrated correctness probabilities. No Nimble runtime or biomedical model has been installed or validated by this change.
