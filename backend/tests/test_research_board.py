import asyncio
import hashlib
import json
import os
import shutil
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from research_board import (BoardAction, BoardConflict, BoardEvidence, BoardPost, BoardRepository,
    ResearchBoard, accept_review, answer_board, confirmed_rule_context, generate_board,
    review_rule, verified_pdf_evidence)
from research_board_api import board_router
from epistemic_harness import LiteratureSource, LiteratureChunk, normalize_paper_model
from research_tools import annotate_pdf_for_objective


def example_board():
    return ResearchBoard(grounding_version=2, workspace_key="test", decision_key="decision", query="Choose an experiment",
        evidence=[BoardEvidence(id="e1", source_id="s1", citation="Controlled source", page=1,
            quote="Growth decreased under the studied conditions.", source_sha256="hash")],
        actions=[BoardAction(id="a1", label="Test precursor engineering", evidence_refs=["e1"]),
                 BoardAction(id="a2", label="Test pathway balance", evidence_refs=["e1"])],
        posts=[BoardPost(id="p1", round=1, role="Process", kind="perspective", text="Examine the growth trade-off.", evidence_refs=["e1"], action_ids=["a1"])])


def proposal(**overrides):
    return {"ownership": "preference", "unresolved": True, "ownership_rationale": "User owns the trade-off",
            "why_not_retrieve": "Papers cannot set local preferences", "action_ids": ["a1"],
            "evidence_refs": ["e1"], "source_post_ids": ["p1"], **overrides}


class BoardContractTests(unittest.TestCase):
    def ready(self):
        b = example_board()
        accept_review(b, {"questions": [proposal()]})
        return b

    def test_generated_gaps_cannot_support_claims(self):
        source = LiteratureSource(id="s", citation="fixture", chunks=[LiteratureChunk(id="gap", text="Unresolved", kind="analyst_gap")])
        model = normalize_paper_model(source, {"claims": [{"id": "fake", "proposition": "Production doubled", "chunk_ids": ["gap"]}]})
        self.assertFalse(model.claims)
        self.assertEqual(len(model.rejected_claims), 1)

    def test_questions_require_ownership_posts_and_evidence(self):
        for override in [{"ownership": "empirical"}, {"unresolved": False}, {"evidence_refs": ["fake"]}, {"source_post_ids": []}, {"action_ids": ["unknown"]}]:
            b = example_board()
            accept_review(b, {"questions": [proposal(**override)]})
            self.assertFalse(b.questions, override)
            self.assertTrue(b.rejected_proposals)

    def test_documented_local_requirement_question_is_preserved(self):
        b = example_board()
        question = "Can your lab reproduce the pH-control setup required by this option?"
        accept_review(b, {"questions": [proposal(ownership="local_constraint", question=question)]})
        self.assertEqual(b.questions[0].question, question)

    def test_opposite_action_effects_are_not_generated_prose(self):
        b = self.ready()
        q = b.questions[0]
        self.assertEqual(q.options[:2], ["Keep these actions eligible", "Exclude these actions"])
        for choice, disposition in [("allow", "eligible"), ("avoid", "excluded")]:
            draft = asyncio.run(answer_board(b, q.id, choice, "", AsyncMock()))
            self.assertEqual(draft.actions[0].disposition, "eligible")
            self.assertFalse(confirmed_rule_context(draft))
            confirmed = review_rule(draft, draft.rules[0].id, "confirm")
            self.assertEqual(confirmed.actions[0].disposition, disposition)
            self.assertEqual(confirmed.actions[1].disposition, "eligible")
            self.assertEqual(len(confirmed_rule_context(confirmed)), 1)

    def test_measurement_justification_routes_to_experiment(self):
        b = example_board()
        accept_review(b, {"questions": [proposal(why_not_retrieve="This requires further measurement in our strain.")]})
        self.assertFalse(b.questions)
        self.assertEqual(b.resolution_steps[0]["resolver"], "run_experiment")

    def test_non_catalog_alias_cannot_receive_a_rule(self):
        b = example_board()
        accept_review(b, {"questions": [proposal(action_ids=["Test precursor engineering"])]})
        self.assertFalse(b.questions)

    def test_uncertainty_does_not_create_a_preference(self):
        for choice, account in [("unsure", ""), ("experience", "I cannot specify a trade-off without looking up the failed strain.")]:
            b = self.ready(); generate = AsyncMock()
            result = asyncio.run(answer_board(b, b.questions[0].id, choice, account, generate))
            self.assertFalse(result.rules)
            self.assertEqual(result.questions[0].status, "deferred")
            generate.assert_not_awaited()

    def test_experience_rule_requires_exact_quote_and_confirmation(self):
        b = self.ready(); account = "We lost our previous strain during scale-up; avoid this route for now."
        invalid = AsyncMock(return_value={"abstain": False, "effect": "avoid", "statement": "Avoid this route", "user_quote": "Invented prior incident"})
        with self.assertRaises(ValueError):
            asyncio.run(answer_board(b, b.questions[0].id, "experience", account, invalid))
        valid = AsyncMock(return_value={"abstain": False, "effect": "avoid", "statement": "Avoid this route for now", "user_quote": "avoid this route for now"})
        result = asyncio.run(answer_board(b, b.questions[0].id, "experience", account, valid))
        self.assertEqual(result.rules[0].status, "draft")
        self.assertEqual(result.actions[0].disposition, "eligible")

    def test_confirmed_answer_is_not_asked_again_and_rule_can_be_revoked(self):
        b = self.ready()
        b = asyncio.run(answer_board(b, b.questions[0].id, "avoid", "", AsyncMock()))
        b = review_rule(b, b.rules[0].id, "confirm")
        accept_review(b, {"questions": [proposal()]})
        self.assertEqual(len(b.questions), 1)
        self.assertEqual(b.questions[0].status, "answered")
        b = review_rule(b, b.rules[0].id, "revoke")
        self.assertEqual(b.actions[0].disposition, "eligible")

    def test_rule_scope_does_not_transfer_to_another_decision(self):
        b = self.ready()
        b = asyncio.run(answer_board(b, b.questions[0].id, "avoid", "", AsyncMock()))
        b.decision_key = "changed"
        with self.assertRaises(ValueError): review_rule(b, b.rules[0].id, "confirm")

    def test_independent_perspectives_and_bounded_review(self):
        evidence = example_board().evidence
        prompts = []
        async def generate(prompt, **kwargs):
            if prompt.startswith("Audit claim support"):
                data = json.loads(prompt[prompt.index('{"items":'):])
                return {"checks":[{"id":item["id"],"supported":True,"reason":"Fixture support"} for item in data["items"]]}
            prompts.append(prompt)
            if len(prompts) == 1:
                return {"actions": [{"label": "Test precursor engineering", "evidence_refs": ["e1"]}, {"label": "Test pathway balance", "evidence_refs": ["e1"]}]}
            if len(prompts) <= 4:
                self.assertNotIn('"kind": "perspective"', prompt)
                return {"text": "One interpretation", "caveat": "Different strain", "evidence_refs": ["e1"], "action_id": __import__("research_board").key("action", "test precursor engineering")}
            return {"questions": [], "challenges": []}
        b = asyncio.run(generate_board(workspace_key="test", state={"query": "Choose an experiment",
            "research_work_template": {"literature_findings": [{"id": "f1", "citation": "Paper", "synthesis_memo": "Our previous culture stalled."}]}}, evidence=evidence, generate=generate))
        self.assertEqual(len(prompts), 5)
        self.assertEqual(len(b.posts), 3)
        self.assertEqual(len(b.actions), 2)
        self.assertFalse(b.questions)
        self.assertIn('researcher_reading_notes', prompts[-1])
        self.assertIn('Our previous culture stalled.', prompts[-1])
        self.assertFalse(b.rules)
        self.assertEqual([e.id for e in b.evidence], ['e1'])

    def test_repository_rejects_stale_updates(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = BoardRepository(str(Path(temp)/"test.sqlite"))
            b = repo.save(example_board(), 0)
            self.assertEqual(repo.get("test").revision, 1)
            with self.assertRaises(BoardConflict): repo.save(b, 0)

    def test_api_persists_confirmation_and_reports_conflict(self):
        with tempfile.TemporaryDirectory() as temp:
            db = SimpleNamespace(db_path=str(Path(temp)/"test.sqlite"))
            b = BoardRepository(db.db_path).save(self.ready(), 0)
            app = FastAPI(); app.include_router(board_router(db, SimpleNamespace(generate_json=AsyncMock(), model="test")))
            client = TestClient(app)
            response = client.post("/api/research-board/answer", json={"workspace_key":"test", "expected_revision":1,"question_id":b.questions[0].id,"answer_type":"avoid"})
            self.assertEqual(response.status_code, 200)
            draft = response.json()["board"]
            response = client.post("/api/research-board/rule", json={"workspace_key":"test","expected_revision":2,"rule_id":draft["rules"][0]["id"],"operation":"confirm"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(client.get("/api/research-board", params={"workspace_key":"test"}).json()["board"]["actions"][0]["disposition"], "excluded")
            stale = client.post("/api/research-board/rule", json={"workspace_key":"test","expected_revision":2,"rule_id":draft["rules"][0]["id"],"operation":"revoke"})
            self.assertEqual(stale.status_code, 409)


class PdfBoundaryTests(unittest.TestCase):
    def setUp(self):
        import fitz
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.pdf = self.root/"project"/"paper"/"original.pdf"
        self.pdf.parent.mkdir(parents=True)
        with fitz.open() as doc:
            doc.new_page().insert_text((50, 50), "Growth decreased under the studied conditions.")
            doc.new_page().insert_text((50, 50), "References\nOther Author. Unrelated production result.")
            doc.save(self.pdf)
        self.sha = hashlib.sha256(self.pdf.read_bytes()).hexdigest()

    def tearDown(self):
        self.temp.cleanup()

    def test_verification_parses_each_document_once_for_multiple_passages(self):
        import fitz
        rows = [{"page":1,"snippet":quote,"evidence_kind":"pdf_passage","source_sha256":self.sha}
                for quote in ["Growth decreased", "under the studied conditions."]]
        state = {"research_work_template":{"literature_findings":[{"citation":"Fixture","annotations":rows}]}}
        with patch("fitz.open", wraps=fitz.open) as opened:
            evidence = verified_pdf_evidence(state, self.root)
        self.assertEqual(len(evidence), 2)
        self.assertEqual(opened.call_count, 1)

    def test_annotation_closes_document_on_model_failure(self):
        import fitz
        document = fitz.open(self.pdf)
        with patch("fitz.open", return_value=document), patch("research_tools._llm_refine_annotation_candidates", AsyncMock(side_effect=RuntimeError("model failed"))):
            with self.assertRaisesRegex(RuntimeError, "model failed"):
                asyncio.run(annotate_pdf_for_objective(pdf_path=str(self.pdf), query="growth", output_path=str(self.root / "failed.pdf")))
        self.assertTrue(document.is_closed)

    def test_original_bytes_and_reference_boundary_are_checked(self):
        rows = [{"page":1,"snippet":"Growth decreased under the studied conditions.","evidence_kind":"pdf_passage","source_sha256":self.sha},
                {"page":2,"snippet":"Other Author. Unrelated production result.","evidence_kind":"pdf_passage","source_sha256":self.sha},
                {"page":1,"snippet":"A fabricated result.","evidence_kind":"pdf_passage","source_sha256":self.sha}]
        state = {"research_work_template":{"literature_findings":[{"id":"s","citation":"Fixture","annotations":rows}]}}
        evidence = verified_pdf_evidence(state, self.root)
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0].page, 1)
        rows[0]["source_sha256"] = "tampered"
        self.assertFalse(verified_pdf_evidence(state, self.root))

    def test_board_start_uses_writer_storage_from_launch_directory_or_override(self):
        from paper_storage import paper_evidence_root
        for configured in ["", str(self.root / "custom-evidence")]:
            with self.subTest(configured=configured), patch.dict(os.environ, {"PAPER_EVIDENCE_ROOT": configured}), patch("os.getcwd", return_value=str(self.root)):
                storage = paper_evidence_root()
                target = storage / "project" / "paper" / "original.pdf"
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(self.pdf, target)
                state = {"query": "Choose an experiment", "research_work_template": {"literature_findings": [{
                    "id": "paper", "citation": "Fixture", "annotations": [{"page": 1,
                    "snippet": "Growth decreased under the studied conditions.", "evidence_kind": "pdf_passage", "source_sha256": self.sha}]}]}}
                async def accepted(**kwargs):
                    self.assertEqual(len(kwargs["evidence"]), 1)
                    return ResearchBoard(workspace_key="storage-test", decision_key="test", query=state["query"], evidence=kwargs["evidence"])
                db = SimpleNamespace(db_path=str(self.root / ("override.sqlite" if configured else "default.sqlite")))
                app = FastAPI()
                app.include_router(board_router(db, SimpleNamespace(generate_json=AsyncMock(), model="fixture")))
                with patch("research_board_api.generate_board", side_effect=accepted):
                    response = TestClient(app).post("/api/research-board/start", json={"workspace_key": "storage-test", "explicit_state": state})
                self.assertEqual(response.status_code, 200, response.text)

    def test_board_distinguishes_missing_annotations_from_unverifiable_annotations(self):
        app = FastAPI()
        app.include_router(board_router(SimpleNamespace(db_path=str(self.root / "errors.sqlite")), SimpleNamespace(model="fixture"), pdf_root=self.root))
        client = TestClient(app)
        for annotations, message in [([], "No saved passage annotations"), ([{"page": 1, "snippet": "old passage"}], "Annotations are saved")]:
            response = client.post("/api/research-board/start", json={"workspace_key": "errors", "explicit_state": {
                "query": "Choose an experiment", "research_work_template": {"literature_findings": [{"annotations": annotations}]}}})
            self.assertEqual(response.status_code, 422)
            self.assertIn(message, response.json()["detail"])

    def test_no_quota_topup_or_bibliography_candidate(self):
        async def reject(*, candidates, **kwargs):
            self.assertTrue(all(c['page'] == 1 for c in candidates))
            return []
        with patch("research_tools._llm_refine_annotation_candidates", side_effect=reject), patch("research_tools._llm_structured_paper_notes", new=AsyncMock(return_value={})):
            result = asyncio.run(annotate_pdf_for_objective(pdf_path=self.pdf, query="Growth production", output_path=self.root/"annotated.pdf"))
        self.assertEqual(result["annotations"], [])

    def test_annotation_uses_investigation_context_without_an_interview_call(self):
        async def choose(*, contexts, **kwargs):
            self.assertEqual(contexts['persona'], '')
            self.assertEqual(contexts['persona_name'], '')
            return [{'page': 1, 'snippet': 'Growth decreased under the studied conditions.', 'reason': 'Growth trade-off', 'score': 2}]
        with patch('research_tools._llm_refine_annotation_candidates', side_effect=choose), patch('research_tools._llm_structured_paper_notes', new=AsyncMock(return_value={})) as notes:
            result = asyncio.run(annotate_pdf_for_objective(pdf_path=self.pdf, query='Growth', persona_name='Legacy role', persona_focus='Cost', output_path=self.root/'reader.pdf'))
        self.assertEqual(len(result['annotations']), 1)
        self.assertEqual(result['annotations'][0]['elicitation_prompts'], [])
        self.assertEqual(result['annotations'][0]['source_sha256'], self.sha)
        notes.assert_not_awaited()  # Source-only extraction replaces the project-conditioned notes call.





class BoardConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_roles_overlap_and_review_waits_for_all_roles(self):
        from research_board import ROLES, key
        started = 0
        completed = 0
        barrier = asyncio.Event()
        async def generate(prompt, **kwargs):
            nonlocal started, completed
            if prompt.startswith("Audit claim support"):
                data = json.loads(prompt[prompt.index('{"items":'):])
                return {"checks":[{"id":item["id"],"supported":True,"reason":"Fixture support"} for item in data["items"]]}
            if prompt.startswith("You contribute"):
                started += 1
                if started == 3:
                    barrier.set()
                await asyncio.wait_for(barrier.wait(), 1)
                self.assertNotIn('"kind": "perspective"', prompt)
                completed += 1
                return {"text":"Supported interpretation", "evidence_refs":["e1"], "action_id":key("action", "option one")}
            if prompt.startswith("Review a research board"):
                self.assertEqual(completed, 3)
                return {}
            return {"actions":[{"label":label,"evidence_refs":["e1"]} for label in ["Option one", "Option two"]]}
        board = await generate_board(workspace_key="test", state={"query":"Choose an experiment"}, evidence=example_board().evidence, generate=generate)
        self.assertEqual([p.role for p in board.posts], [role for role, _ in ROLES.values()])

    async def test_cancelled_board_joins_its_role_tasks(self):
        started = 0
        finished = 0
        barrier = asyncio.Event()
        async def generate(prompt, **kwargs):
            nonlocal started, finished
            if prompt.startswith("You contribute"):
                started += 1
                if started == 3:
                    barrier.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    finished += 1
            return {"actions":[{"label":label,"evidence_refs":["e1"]} for label in ["Option one", "Option two"]]}
        task = asyncio.create_task(generate_board(workspace_key="test", state={"query":"Choose an experiment"}, evidence=example_board().evidence, generate=generate))
        await asyncio.wait_for(barrier.wait(), 1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(finished, 3)


if __name__ == "__main__":
    unittest.main()
