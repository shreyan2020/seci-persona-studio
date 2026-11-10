# Literature relevance screening

The Itaconic Acid project (project 4, query 4) exposed an admission failure. PMID 19100310 describes TAT-fusion protein secretion and uptake in mammalian cells. Its abstract gives no itaconic-acid or Yarrowia connection. Calling it background for this project was unsupported.

Causes: generic terms contributed to ranking; product recognition depended on a short flavonoid-specific dictionary; PubMed fallback queries could drop the product; the reranker accepted negative rationales in its selected list; quota top-up reintroduced unselected records. A high keyword score was also being promoted to “direct evidence,” which it cannot establish.

Changes:

- The project route supplies explicit end-product and host fields. Search uses those anchors rather than relying on the old product dictionary. Common phrasing such as “Itaconic acid produced from glucose” becomes the complete product “itaconic acid.”
- PubMed fallbacks retain that product; relaxing the host is permitted only as a transfer search. All providers feed the same metadata screen.
- Candidate title/abstract must contain the target product tokens. Supplements are excluded in favor of their parent papers. Generic term matches cannot rescue a failed screen.
- Host/product matches and transfer candidates are labeled separately. A requested glucose, glycerol or xylose substrate absent from metadata triggers a transfer limitation. These are metadata checks, not entailment or experimental-quality judgments.
- The model selector must explicitly select relevant records and supply a positive rationale. Negative rationales are rejected; an empty selection stays empty. On model failure, fallback uses only screened candidates.
- Later synthesis also honors explicit irrelevance instead of converting it into a background explanation. Numeric ranking no longer assigns a “direct evidence” role.
- Screening counts appear in the processing summary. Exact exclusions are available in the search result diagnostics.

Validation: 34 focused tests passed. A live public-API run of `itaconic acid yarrowia lipolytica` collected 10 deduplicated candidates, rejected 3, and returned 5 in deterministic fallback mode. Semantic Scholar returned HTTP 429; the other providers responded. The resulting records concern itaconic-acid production in Yarrowia, including transport, metabolic engineering and scale-up. One waste-cooking-oil study motivated the additional substrate-transfer check. The live test did not evaluate model reranking quality or scientific entailment.

Artifacts: `artifacts/itaconic_search_screening_live.json` records the live search before the subsequent substrate refinement. `artifacts/itaconic_saved_record_screening.json` checks all five old citations without treating their generated summaries as evidence: four lack the target product in the saved title and one is a supplementary artifact. This is a title-only check, not a full abstract review of those four records.

Existing saved records are preserved; fetching again applies the new screening to incoming records. Restart the backend first. The strict product requirement intentionally favors precision for this project-focused workflow and can omit useful cross-product methods. Unlisted synonyms, abbreviations and complex product descriptions may still require query adjustment; no universal relevance guarantee is claimed.
