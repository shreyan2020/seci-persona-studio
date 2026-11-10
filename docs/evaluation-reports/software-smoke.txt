# Benchmark Suite: local_smoke

- Generated: 2026-05-16T11:48:51.726017+00:00
- Description: Fast smoke suite over tiny local fixtures for retrieval augmentation and ontology extraction metrics.
- Tasks: 2 total, 2 passed, 0 failed, 0 skipped

| Task | Type | Benchmark | Status | Primary Metrics | Report |
| --- | --- | --- | --- | --- | --- |
| beir_tiny_retrieval | retrieval_beir | beir_tiny | passed | baseline_ndcg_at_k=0.9536, baseline_recall_at_k=0.8333, ontology_ndcg_at_k=0.9936, ontology_recall_at_k=1.0000, ontology_ndcg_delta=0.0399, ontology_recall_delta=0.1667 | data\eval_runs\local_smoke\beir_tiny_retrieval\beir_tiny_retrieval_report.md |
| extraction_tiny | extraction_jsonl | extraction_tiny | passed | entity_f1=0.8571, entity_recall=1.0000, relation_f1=1.0000, relation_recall=1.0000 | data\eval_runs\local_smoke\extraction_tiny\extraction_tiny_report.md |
