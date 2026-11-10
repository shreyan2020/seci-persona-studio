import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from main import _literature_record_to_research_finding, _synthesize_literature_processing
from models import FetchProjectLiteratureRequest, ResearchFinding
from research_tools import (
    _fallback_structured_paper_notes,
    _extract_research_questions_from_text,
    _literature_relevance_profile,
    _literature_relevance_score,
    _looks_like_reference_entry,
    formulate_pubmed_query,
)


QUERY = (
    "Which genetic interventions have experimentally improved de novo naringenin production "
    "from glucose in Saccharomyces cerevisiae, and what quantitative titer or yield evidence "
    "supports each intervention?"
)


class LiteratureReliabilityTests(unittest.IsolatedAsyncioTestCase):
    def test_high_keyword_score_does_not_prove_direct_evidence(self):
        finding = _literature_record_to_research_finding(
            {
                "title": "De novo production of naringenin in engineered Saccharomyces cerevisiae",
                "citation": "Example",
                "relevance_score": 120.0,
                "evidence_role": "background",
            },
            1,
        )

        self.assertNotIn("evidence role: direct evidence", finding.labels)
        self.assertIn("evidence role: background", finding.labels)

    def test_annotation_questions_skip_truncated_uncertainty_passages(self):
        complete = _extract_research_questions_from_text(
            "The mechanism responsible for extracellular naringenin export remains unknown.",
            page_label="Page 5",
        )
        truncated = _extract_research_questions_from_text(
            "The result remains uncertain while comparing the two strains", page_label="Page 6"
        )
        overlong = _extract_research_questions_from_text(
            "The mechanism remains unknown, " + "despite repeated measurements across strains " * 8 + ".",
            page_label="Page 6",
        )

        self.assertEqual(len(complete), 1)
        self.assertEqual(truncated, [])
        self.assertEqual(overlong, [])

    def test_query_preserves_product_host_and_carbon_source(self):
        query = formulate_pubmed_query(
            QUERY,
            project_goal="Experimentally validated naringenin production in Saccharomyces cerevisiae.",
            objective_title="Evidence synthesis",
            objective_definition="Compare quantitative genetic engineering benchmarks.",
            user_inputs=["Naringenin from glucose", "Saccharomyces cerevisiae"],
            max_terms=8,
        )

        self.assertIn("naringenin", query.split())
        self.assertIn("glucose", query.split())
        self.assertIn("saccharomyces", query.split())
        self.assertIn("cerevisiae", query.split())
        self.assertNotEqual(query, "naringenin yeast production synthesis")

    def test_direct_product_host_paper_outranks_analogue_and_supplement(self):
        profile = _literature_relevance_profile(
            QUERY,
            project_goal="Naringenin production in Saccharomyces cerevisiae",
            user_inputs=["Naringenin from glucose", "Saccharomyces cerevisiae"],
        )
        direct = _literature_relevance_score(
            {
                "title": "Engineering naringenin production in Saccharomyces cerevisiae",
                "abstract": "Naringenin was produced from glucose with a quantitative titer.",
                "year": "2024",
                "doi": "10.1/direct",
                "sources": ["pubmed"],
            },
            profile,
        )
        analogue = _literature_relevance_score(
            {
                "title": "De novo resveratrol production in Saccharomyces cerevisiae",
                "abstract": "A glucose-fed engineered yeast co-culture was evaluated.",
                "year": "2024",
                "doi": "10.1/analogue",
                "sources": ["pubmed"],
            },
            profile,
        )
        supplement = _literature_relevance_score(
            {
                "title": "Engineering naringenin production in Saccharomyces cerevisiae",
                "abstract": "",
                "year": "",
                "doi": "10.1021/example.s001",
                "sources": ["crossref"],
            },
            profile,
        )

        self.assertGreater(direct["score"], analogue["score"])
        self.assertGreater(direct["score"], supplement["score"])

    def test_reference_entries_are_rejected_from_annotations(self):
        self.assertTrue(
            _looks_like_reference_entry(
                "19. Trantas E, Panopoulos N: Metabolic engineering of flavonoids. Metab Eng 2009, 11:355-366."
            )
        )
        self.assertFalse(
            _looks_like_reference_entry(
                "Expression of a tyrosine ammonia lyase increased naringenin synthesis in the engineered strain."
            )
        )

    def test_fallback_notes_capture_micromolar_benchmarks_without_affiliation_noise(self):
        notes = _fallback_structured_paper_notes(
            analysis_context=(
                "The research group is part of the Centre for Genomics of Industrial Fermentation. "
                "The engineered strain produced 5.4 μM naringenin from glucose. "
                "Together these modifications resulted in a 40-fold increase to approximately 200 μM."
            ),
            selected=[],
            research_questions=[],
        )

        self.assertGreaterEqual(len(notes["quantitative_benchmarks"]), 2)
        self.assertFalse(any("research group" in item.lower() for item in notes["methods"]))

    def test_research_questions_focus_on_explicit_uncertainty(self):
        questions = _extract_research_questions_from_text(
            "The pathway was optimized by expressing three enzymes. "
            "However, the export mechanism has not yet been elucidated. "
            "Commercial production will require substantial further improvement of product yield."
        )

        self.assertEqual(len(questions), 2)
        self.assertTrue(any("What experiment would resolve" in item for item in questions))
        self.assertTrue(any("Which intervention should be prioritized" in item for item in questions))

    @patch("main.ollama.generate_json", new_callable=AsyncMock)
    async def test_synthesis_keeps_source_identity_and_all_records(self, generate_json):
        generate_json.return_value = {
            "objective_lens": "Direct host and product evidence.",
            "processing_summary": "Two records were assessed.",
            "elicitation_questions": ["Which result is reproducible?"],
            "findings": [
                {
                    "record_id": "record_2",
                    "citation": "Forged citation must be ignored",
                    "knowns": "A complete evidence sentence, not characters.",
                    "unknowns": ["Scale transfer remains unknown."],
                    "labels": "Direct evidence",
                    "relevance": "Directly relevant.",
                }
            ],
        }
        request = FetchProjectLiteratureRequest(persona_id=9, query=QUERY)
        fallback_findings = [
            ResearchFinding(
                id="lit_fetch_1",
                citation="Source paper one. 2024. PMID: 1",
                labels=["pubmed"],
                knowns=["Source title one"],
                source_ids={"pmid": "1"},
            ),
            ResearchFinding(
                id="lit_fetch_2",
                citation="Source paper two. 2023. DOI: 10.1/two",
                labels=["crossref"],
                knowns=["Source title two"],
                source_ids={"doi": "10.1/two"},
            ),
        ]
        records = [
            {"title": "Source title one", "citation": fallback_findings[0].citation},
            {"title": "Source title two", "citation": fallback_findings[1].citation},
        ]

        result = await _synthesize_literature_processing(
            {"project_goal": "Evidence audit", "target_host": "Saccharomyces cerevisiae"},
            {"name": "Literature analyst"},
            request,
            records,
            fallback_findings,
        )

        self.assertEqual(len(result["findings"]), 2)
        self.assertEqual(result["findings"][0].citation, fallback_findings[0].citation)
        self.assertEqual(result["findings"][1].citation, fallback_findings[1].citation)
        self.assertEqual(result["findings"][1].source_ids, {"doi": "10.1/two"})
        self.assertEqual(result["findings"][1].knowns, ["A complete evidence sentence, not characters."])
        self.assertEqual(result["findings"][1].labels, ["crossref", "Direct evidence"])


if __name__ == "__main__":
    unittest.main()
