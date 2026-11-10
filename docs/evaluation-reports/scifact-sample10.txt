# Benchmark Report: scifact_sample10

- Generated: 2026-05-16T12:17:20.647587+00:00
- Corpus documents: 5183
- Queries: 10
- Metric cutoff: @10

## Retrieval Metrics

| Mode | Precision | Recall | nDCG | MAP | MRR | Queries |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline | 0.0800 | 0.7500 | 0.6849 | 0.6583 | 0.6667 | 10 |
| ontology | 0.0800 | 0.7500 | 0.6849 | 0.6583 | 0.6667 | 10 |

## Ontology Lift

| Metric | Delta |
| --- | ---: |
| precision_at_k | +0.0000 |
| recall_at_k | +0.0000 |
| ndcg_at_k | +0.0000 |
| map | +0.0000 |
| mrr | +0.0000 |

## Notes

- `baseline` uses the benchmark query text only.
- `ontology` appends query-specific ontology expansion terms, reasoning lenses, and tacit context from the augmentation file.
- The JSON report includes per-query ontology audit records for stakeholder inspection.
