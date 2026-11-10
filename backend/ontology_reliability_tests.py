import asyncio
import unittest
from unittest.mock import patch

from models import BuildOntologyPreviewRequest, BuildPaperOntologyRequest, ResearchFinding, ResearchWorkTemplate
from ontology_service import build_ontology_preview, build_paper_ontology, build_paper_ontology_enriched


def _paper_request(extraction_mode: str = "deterministic") -> BuildPaperOntologyRequest:
    return BuildPaperOntologyRequest(
        persona_id=1,
        query="How should we improve resveratrol production in yeast?",
        objective_id="obj_experiments",
        objective_title="Experiment design",
        objective_definition="Ground next experiments in paper evidence.",
        project_goal="Improve resveratrol production in Saccharomyces cerevisiae.",
        project_end_product="resveratrol",
        project_target_host="Saccharomyces cerevisiae",
        extraction_mode=extraction_mode,
        finding=ResearchFinding(
            id="finding-1",
            citation="Example resveratrol yeast paper. PMID: 12345",
            labels=["pubmed", "literature fetch", "2019", "PMID: 12345", "resveratrol", "metabolic engineering"],
            knowns=[
                "Saccharomyces cerevisiae produced resveratrol using stilbene synthase.",
                "p-coumaric acid and malonyl-CoA precursor supply affected titer.",
                "The engineered strain reached 200 μM resveratrol.",
            ],
            unknowns=["Whether precursor supply or enzyme activity is limiting in our strain."],
            relevance="Direct yeast resveratrol production evidence with measurable titer.",
            source_ids={"pmid": "12345", "doi": "10.1000/example"},
            annotation_insights=["Page 4: HPLC measured resveratrol titer after pathway engineering."],
        ),
    )


def _graph_signature(response):
    return {
        "nodes": [node.model_dump() for node in response.nodes],
        "edges": [edge.model_dump() for edge in response.edges],
        "augmentation": response.query_augmentation.model_dump(),
    }


class OntologyReliabilityTests(unittest.TestCase):
    def test_work_template_does_not_promote_provider_or_identifier_labels(self):
        finding = _paper_request().finding
        finding.labels = [
            "pubmed",
            "openalex",
            "PMID: 23216753",
            "DOI: 10.1186/1475-2859-11-155",
            "naringenin",
        ]
        request = BuildOntologyPreviewRequest(
            query="naringenin in Saccharomyces cerevisiae",
            project_end_product="naringenin",
            project_target_host="Saccharomyces cerevisiae",
            work_template=ResearchWorkTemplate(literature_findings=[finding]),
        )

        preview = build_ontology_preview(1, request)
        labels = {node.label.lower() for node in preview.nodes}

        self.assertIn("naringenin", labels)
        self.assertNotIn("pubmed", labels)
        self.assertNotIn("openalex", labels)
        self.assertFalse(any(label.startswith("pmid:") or label.startswith("doi:") for label in labels))

    def test_same_context_produces_same_paper_ontology(self):
        first = build_paper_ontology(8, _paper_request())
        second = build_paper_ontology(8, _paper_request())

        self.assertEqual(_graph_signature(first), _graph_signature(second))

    def test_default_enriched_builder_does_not_call_llm(self):
        async def run():
            with patch("ontology_service.llm_paper_ontology_extraction") as mocked:
                response = await build_paper_ontology_enriched(8, _paper_request())
                mocked.assert_not_called()
                return response

        response = asyncio.run(run())
        self.assertIn("deterministic grounded extraction", response.sync_message)

    def test_deterministic_extraction_rejects_generic_capitalized_tokens(self):
        response = build_paper_ontology(8, _paper_request())
        enzyme_labels = {node.label.lower() for node in response.nodes if node.type == "gene_or_enzyme"}

        self.assertIn("stilbene synthase", enzyme_labels)
        self.assertTrue({"sts", "tal", "4cl"}.isdisjoint(enzyme_labels))
        self.assertTrue({"the", "this", "how", "page", "pmid", "hplc"}.isdisjoint(enzyme_labels))
        self.assertFalse(any(edge.relation == "catalyzes" for edge in response.edges))

    def test_query_augmentation_excludes_source_and_file_metadata(self):
        response = build_paper_ontology(8, _paper_request())
        expanded = {term.lower() for term in response.query_augmentation.expanded_terms}

        self.assertIn("resveratrol", expanded)
        self.assertTrue({"pubmed", "pmid", "openalex", "crossref", "pdf annotated"}.isdisjoint(expanded))
        self.assertFalse(
            any(
                node.label.lower() in {"pubmed", "literature fetch", "pmid: 12345", "2019", "pdf annotated"}
                for node in response.nodes
            )
        )

    def test_typed_measurements_and_production_relations_are_precise(self):
        response = build_paper_ontology(8, _paper_request())
        measurements = {node.label.lower() for node in response.nodes if node.type == "measurement"}
        labels_by_id = {node.id: node.label.lower() for node in response.nodes}
        produced_targets = {
            labels_by_id.get(edge.target, "")
            for edge in response.edges
            if edge.relation == "produces"
        }

        self.assertIn("200 μm", measurements)
        self.assertEqual(produced_targets, {"resveratrol"})


if __name__ == "__main__":
    unittest.main()
