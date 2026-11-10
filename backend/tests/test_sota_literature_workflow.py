import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research_tools import _literature_relevance_profile
from sota_literature_workflow import (
    WorkflowError,
    WorkflowTraceLogger,
    _candidate_payload,
    _dedupe_records,
    _parse_embeddings_payload,
    _record_grounded_knowns,
)


class SotaLiteratureWorkflowTests(unittest.TestCase):
    def test_knowns_cannot_borrow_quantitative_claims_from_another_candidate(self):
        record = {
            "title": "De novo production of naringenin in engineered Saccharomyces cerevisiae",
            "abstract": "The baseline produced 5.4 μM naringenin and the optimized strain exceeded 400 μM.",
        }

        knowns = _record_grounded_knowns(
            record,
            ["CRISPR interference increased naringenin to 421.6 mg/L."],
        )

        self.assertFalse(any("421.6" in claim or "CRISPR" in claim for claim in knowns))
        self.assertTrue(any("5.4" in claim and "400" in claim for claim in knowns))

    def test_candidate_payload_prioritizes_exact_product_host_over_recent_background(self):
        profile = _literature_relevance_profile(
            "naringenin from glucose in Saccharomyces cerevisiae genetic intervention titer"
        )
        records = [
            {
                "title": "The Therapeutic Potential of Naringenin: A Review of Clinical Trials",
                "abstract": "Clinical review with background on naringenin.",
                "year": "2024",
                "cited_by_count": 500,
            },
            {
                "title": "De novo production of naringenin in engineered Saccharomyces cerevisiae",
                "abstract": "Naringenin was produced from glucose after pathway engineering with quantitative titers.",
                "year": "2012",
                "cited_by_count": 10,
            },
        ]

        candidates, _ = _candidate_payload(records, relevance_profile=profile)

        self.assertTrue(candidates[0]["title"].startswith("De novo production"))
        self.assertGreater(
            candidates[0]["deterministic_relevance"],
            candidates[1]["deterministic_relevance"],
        )

    def test_dedupe_records_merges_sources_by_doi(self):
        records = [
            {
                "doi": "10.1000/example",
                "title": "Short abstract paper",
                "abstract": "short",
                "sources": ["openalex"],
            },
            {
                "doi": "https://doi.org/10.1000/example",
                "title": "Short abstract paper",
                "abstract": "this abstract is longer and should be kept",
                "sources": ["semantic_scholar"],
            },
        ]

        deduped = _dedupe_records(records)

        self.assertEqual(len(deduped), 1)
        self.assertEqual(deduped[0]["sources"], ["openalex", "semantic_scholar"])
        self.assertEqual(deduped[0]["abstract"], "this abstract is longer and should be kept")

    def test_trace_logger_writes_jsonl_and_keeps_trace(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "workflow.jsonl")
            old_value = os.environ.get("SOTA_WORKFLOW_LOG_PATH")
            os.environ["SOTA_WORKFLOW_LOG_PATH"] = log_path
            try:
                logger = WorkflowTraceLogger(run_id="test_run")
                index = logger.start("capability_check", inputs={"query": "example"})
                event = logger.end(index, status="missing_capability", message="example missing", errors=["missing embedding backend"])

                self.assertEqual(event.run_id, "test_run")
                self.assertEqual(event.stage, "capability_check")
                self.assertEqual(event.status, "missing_capability")
                self.assertTrue(os.path.exists(log_path))
                with open(log_path, encoding="utf-8") as handle:
                    self.assertIn('"stage": "capability_check"', handle.read())
            finally:
                if old_value is None:
                    os.environ.pop("SOTA_WORKFLOW_LOG_PATH", None)
                else:
                    os.environ["SOTA_WORKFLOW_LOG_PATH"] = old_value

    def test_workflow_error_exposes_failed_stage_and_trace(self):
        logger = WorkflowTraceLogger(run_id="test_failure")
        index = logger.start("llm_query_decomposition")

        with self.assertRaises(WorkflowError) as context:
            logger.fail(index, "llm_query_decomposition", "LLM failed", RuntimeError("connection refused"))

        self.assertEqual(context.exception.stage, "llm_query_decomposition")
        self.assertEqual(context.exception.trace[-1].status, "error")
        self.assertIn("connection refused", str(context.exception))

    def test_parse_embeddings_payload_accepts_openai_style_data(self):
        embeddings = _parse_embeddings_payload(
            {
                "data": [
                    {"embedding": [1, 2, 3]},
                    {"embedding": [0.5, 0.25, 0.125]},
                ]
            }
        )

        self.assertEqual(embeddings, [[1.0, 2.0, 3.0], [0.5, 0.25, 0.125]])


if __name__ == "__main__":
    unittest.main()
