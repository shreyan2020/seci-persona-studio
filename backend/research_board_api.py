"""Server-owned board state; mutations use optimistic revisions."""
from evidence_grounding import GROUNDING_VERSION, relevant_evidence
from pathlib import Path
from typing import Any, Literal
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from paper_storage import paper_evidence_root
from comparison_models import Dimension
from evidence_comparison import build_comparison, guided_judgment, DIMENSIONS
from research_tools import search_literature
from research_board import (BoardConflict, BoardRepository, ResearchBoard, answer_board,
                           generate_board, review_rule, verified_pdf_evidence, key, clean)


class StartBoardRequest(BaseModel):
    workspace_key: str = Field(min_length=1, max_length=300)
    explicit_state: dict[str, Any]
    expected_revision: int = Field(default=0, ge=0)


class BoardAnswerRequest(BaseModel):
    workspace_key: str
    expected_revision: int
    question_id: str
    answer_type: Literal["allow", "avoid", "experience", "unsure"]
    text: str = Field(default="", max_length=4000)


class RuleReviewRequest(BaseModel):
    workspace_key: str
    expected_revision: int
    rule_id: str
    operation: Literal["confirm", "reject", "revoke"]
    statement: str | None = Field(default=None, max_length=1400)


class CommentRequest(BaseModel):
    workspace_key: str
    expected_revision: int
    reply_to: str
    text: str = Field(min_length=1, max_length=4000)


class ComparisonChoiceRequest(BaseModel):
    workspace_key: str
    expected_revision: int
    row_id: str
    dimension: Dimension
    review: Literal['confirmed', 'rejected'] | None = None
    relation: Literal['same','different','unavailable','unknown'] = 'unknown'
    basis: Literal['setup','past_case','uncertain'] = 'uncertain'
    cue: str = ''
    response: str = ''
    exception: str = ''
    consequence: Literal['context','measure','allow','avoid'] = 'context'
    action_ids: list[str] = Field(default_factory=list, max_length=10)
    detail: str = Field(default='', max_length=4000)


class GapSourcesRequest(BaseModel):
    workspace_key: str
    expected_revision: int
    dimension: Dimension


def board_router(db, ollama, pdf_root: Path | None = None) -> APIRouter:
    router = APIRouter(prefix="/api/research-board", tags=["research-board"])
    root = pdf_root if pdf_root is not None else paper_evidence_root()

    def repository():
        return BoardRepository(db.db_path)

    def current(request):
        board = repository().get(request.workspace_key)
        if board is None:
            raise HTTPException(404, "Research board not found")
        if board.grounding_version != GROUNDING_VERSION:
            raise HTTPException(409, "Refresh the evidence before using this research board.")
        if board.revision != request.expected_revision:
            raise HTTPException(409, "The board changed. Reload it before continuing.")
        return board

    async def generate(prompt, **kwargs):
        return await ollama.generate_json(prompt, num_ctx=8192, **kwargs)

    @router.get("")
    async def get_board(workspace_key: str):
        return {"board": repository().get(workspace_key)}

    @router.get('/knowledge')
    async def get_knowledge(workspace_key: str):
        from board_knowledge import board_knowledge
        board = repository().get(workspace_key)
        if board is None:
            raise HTTPException(404, 'Research board not found')
        return {**board_knowledge(board), 'revision':board.revision, 'workspace_key':board.workspace_key}

    @router.post("/start")
    async def start(request: StartBoardRequest):
        previous = repository().get(request.workspace_key)
        if (previous.revision if previous else 0) != request.expected_revision:
            raise HTTPException(409, "The board changed. Reload it before starting another round.")
        try:
            if not clean(request.explicit_state.get("query")):
                raise ValueError("Add a working research question before gathering perspectives.")
            evidence = verified_pdf_evidence(request.explicit_state, root)
            if not evidence:
                findings = (request.explicit_state.get("research_work_template") or {}).get("literature_findings") or []
                has_annotations = any(isinstance(f, dict) and f.get("annotations") for f in findings)
                if has_annotations:
                    raise ValueError("Annotations are saved, but none could be verified against the original PDFs in this server's paper storage. Check that the reader and board use the same PAPER_EVIDENCE_ROOT and that the original files are present. Older annotations may need regeneration to add source fingerprints.")
                raise ValueError("No saved passage annotations were supplied for this working question. Review a paper first, then gather perspectives.")
            board = await generate_board(workspace_key=request.workspace_key, state=request.explicit_state,
                evidence=evidence, generate=generate, previous=previous, model=ollama.model)
            board.model = ollama.model
            return {"board": repository().save(board, request.expected_revision)}
        except BoardConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.post("/answer")
    async def answer(request: BoardAnswerRequest):
        try:
            board = await answer_board(current(request), request.question_id, request.answer_type, request.text, generate)
            return {"board": repository().save(board, request.expected_revision)}
        except BoardConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(503, "The account could not be interpreted. Your answer has not been turned into a rule; retry or choose an explicit action.") from exc

    @router.post('/compare')
    async def compare(request: StartBoardRequest):
        old = repository().get(request.workspace_key)
        if (old.revision if old else 0) != request.expected_revision:
            raise HTTPException(409, 'The board changed. Reload before building the comparison.')
        query = clean(request.explicit_state.get('query'), 1800)
        if not query:
            raise HTTPException(422, 'Add a working question first.')
        evidence = relevant_evidence(request.explicit_state, verified_pdf_evidence(request.explicit_state, root))
        if not evidence:
            raise HTTPException(422, 'No verifiable PDF passages are available for comparison. Review a relevant paper first.')
        decision = key('decision', [request.workspace_key, query.lower()])
        board = old.model_copy(deep=True) if old and old.grounding_version == GROUNDING_VERSION and old.decision_key == decision else ResearchBoard(workspace_key=request.workspace_key,decision_key=decision,query=query,round=0)
        board.grounding_version = GROUNDING_VERSION
        board.evidence = evidence
        project = request.explicit_state.get('selected_project') or {}
        board.comparison_project = {k: clean(project.get(k)) for k in ['end_product','target_host','project_goal']}
        board = await build_comparison(board, evidence, generate)
        board.model = ollama.model
        try:
            return {'board': repository().save(board, request.expected_revision)}
        except BoardConflict as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.post('/compare-choice')
    async def compare_choice(request: ComparisonChoiceRequest):
        board = current(request).model_copy(deep=True)
        try:
            if request.review:
                fact = next((f for f in board.experiment_facts if f.id == request.row_id and f.dimension == request.dimension), None)
                row = next((r for r in board.comparison_rows if r.id == request.row_id), None)
                cell = fact or (row.cells.get(request.dimension) if row else None)
                if cell is None:
                    raise ValueError('Unknown source detail.')
                cell.review = request.review
                if request.review == 'rejected':
                    linked = {key('comparison_question', j.id) for j in board.comparison_judgments if j.row_id == request.row_id and j.dimension == request.dimension}
                    for rule in list(board.rules):
                        if rule.question_id in linked and rule.status in {'draft','confirmed'}:
                            board = review_rule(board, rule.id, 'reject' if rule.status == 'draft' else 'revoke')
                    if fact:
                        for record in board.experiment_records:
                            record.fact_ids = [fid for fid in record.fact_ids if fid != fact.id]
                            record.evidence_refs = list(dict.fromkeys(
                                f.evidence_id for f in board.experiment_facts if f.id in record.fact_ids and f.review != 'rejected'))
                            if record.link_status == 'linked' and len(record.evidence_refs) < 2:
                                record.link_status = 'single_passage'
                                record.link_anchors = []
                        board.experiment_records = [record for record in board.experiment_records if record.fact_ids]
                    board.comparison_warnings.append('Extraction rejected. Any draft or confirmed rules based on this detail were withdrawn; historical choices remain in the record.')
            else:
                board = guided_judgment(board, **request.model_dump(exclude={'workspace_key','expected_revision','review'}))
            return {'board': repository().save(board, request.expected_revision)}
        except BoardConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.post('/gap-sources')
    async def gap_sources(request: GapSourcesRequest):
        board = current(request).model_copy(deep=True)
        project = board.comparison_project
        # Only public topic fields leave the app; recalled cases and local
        # judgments are never placed into external provider search strings.
        query = ' '.join([project.get('end_product',''),project.get('target_host',''),DIMENSIONS[request.dimension]])
        if not project.get('end_product'):
            raise HTTPException(422, 'Build the comparison with a project end product before searching.')
        try:
            result = await search_literature(query,max_results=3,search_focus=DIMENSIONS[request.dimension],end_product=project.get('end_product',''),target_host=project.get('target_host',''),project_goal='')
            board.comparison_sources = [{'title':r.get('title',''), 'doi':r.get('doi',''), 'pmid':r.get('pmid',''),
                'scope':(r.get('relevance_screening') or {}).get('scope',''), 'reason':(r.get('relevance_screening') or {}).get('reason',''),
                'sources':r.get('sources',[]), 'dimension':request.dimension} for r in result.get('results',[])]
            board.comparison_warnings = [result.get('screening_summary','')] + [f'{name}: source unavailable.' for name in result.get('errors',{})]
            return {'board':repository().save(board,request.expected_revision)}
        except BoardConflict as exc:
            raise HTTPException(409,str(exc)) from exc

    @router.post("/rule")
    async def rule(request: RuleReviewRequest):
        try:
            board = review_rule(current(request), request.rule_id, request.operation, request.statement)
            return {"board": repository().save(board, request.expected_revision)}
        except BoardConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.post("/comment")
    async def comment(request: CommentRequest):
        from research_board import BoardPost
        board = current(request)
        target = next((p for p in board.posts if p.id == request.reply_to), None)
        if target is None or not clean(request.text):
            raise HTTPException(422, "Choose a post and enter a reply")
        board.posts.append(BoardPost(id=key("comment", [board.revision, request.reply_to, request.text]),
            role="Researcher", kind="user", round=board.round, text=clean(request.text, 4000),
            reply_to=target.id, evidence_refs=target.evidence_refs))
        try:
            return {"board": repository().save(board, request.expected_revision)}
        except BoardConflict as exc:
            raise HTTPException(409, str(exc)) from exc

    return router
