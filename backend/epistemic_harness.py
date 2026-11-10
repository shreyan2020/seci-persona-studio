from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections import Counter
from typing import Any, Awaitable, Callable, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


GapType = Literal[
    "retrieval",
    "workspace",
    "logical",
    "ontology",
    "conflict",
    "empirical",
    "tacit",
    "hypothesis_space",
]
ResolutionAction = Literal[
    "search_literature",
    "inspect_workspace",
    "derive",
    "align_constructs",
    "compare_evidence",
    "run_experiment",
    "ask_user",
    "discover_hypothesis",
    "stop",
]
GenerateJSON = Callable[..., Awaitable[Dict[str, Any]]]


class LiteratureChunk(BaseModel):
    page: Optional[int] = None
    source_sha256: Optional[str] = None
    provenance: Literal["pdf_passage", "user_note", "generated_note"] = "user_note"
    id: str
    text: str
    kind: Literal["evidence", "analyst_gap", "annotation", "context"] = "evidence"


class LiteratureSource(BaseModel):
    id: str
    citation: str
    chunks: List[LiteratureChunk] = Field(default_factory=list)
    source_ids: Dict[str, str] = Field(default_factory=dict)


class EvidenceClaim(BaseModel):
    id: str
    source_id: str
    proposition: str
    claim_type: Literal[
        "definition",
        "mechanism",
        "empirical_effect",
        "measurement",
        "method",
        "boundary_condition",
        "limitation",
        "other",
    ] = "other"
    status: Literal["supported", "inferred", "contested"] = "supported"
    chunk_ids: List[str] = Field(default_factory=list)
    scope: Dict[str, str] = Field(default_factory=dict)
    evidence_strength: float = Field(default=0.5, ge=0.0, le=1.0)
    extraction_confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class PaperGap(BaseModel):
    id: str
    statement: str
    related_claim_ids: List[str] = Field(default_factory=list)
    missing_premises: List[str] = Field(default_factory=list)
    provisional_type: GapType = "logical"


class PaperWorldModel(BaseModel):
    source_id: str
    citation: str
    claims: List[EvidenceClaim] = Field(default_factory=list)
    gaps: List[PaperGap] = Field(default_factory=list)
    rejected_claims: List[Dict[str, str]] = Field(default_factory=list)


class ClaimRelation(BaseModel):
    source_claim_id: str
    target_claim_id: str
    relation: Literal[
        "supports",
        "contradicts",
        "qualifies",
        "replicates",
        "same_construct",
        "potentially_transfers_to",
    ]
    rationale: str = ""


class EpistemicGap(BaseModel):
    id: str
    statement: str
    gap_type: GapType
    related_claim_ids: List[str] = Field(default_factory=list)
    missing_premises: List[str] = Field(default_factory=list)
    affected_decisions: List[str] = Field(default_factory=list)
    candidate_actions: List[ResolutionAction] = Field(default_factory=list)
    recommended_action: ResolutionAction
    routing_rationale: str
    decision_relevance: float = Field(default=0.5, ge=0.0, le=1.0)
    user_answerability: float = Field(default=0.0, ge=0.0, le=1.0)


class EpistemicHarnessResult(BaseModel):
    world_summary: str = ""
    paper_models: List[PaperWorldModel] = Field(default_factory=list)
    claim_relations: List[ClaimRelation] = Field(default_factory=list)
    gaps: List[EpistemicGap] = Field(default_factory=list)
    elicitation_payload: Dict[str, Any] = Field(default_factory=dict)

    def trace(self) -> Dict[str, Any]:
        routing = Counter(gap.recommended_action for gap in self.gaps)
        return {
            "world_summary": self.world_summary,
            "sources_processed": len(self.paper_models),
            "accepted_claims": sum(len(model.claims) for model in self.paper_models),
            "rejected_claims": sum(len(model.rejected_claims) for model in self.paper_models),
            "gap_count": len(self.gaps),
            "routing_counts": dict(sorted(routing.items())),
            "paper_models": [model.model_dump() for model in self.paper_models],
            "claim_relations": [relation.model_dump() for relation in self.claim_relations],
            "gaps": [gap.model_dump() for gap in self.gaps],
        }


def _slug(value: Any, fallback: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")[:72]
    return cleaned or fallback


def _trim(value: Any, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def extract_literature_sources(explicit_state: Dict[str, Any], max_sources: int = 5) -> List[LiteratureSource]:
    template = explicit_state.get("research_work_template")
    if not isinstance(template, dict):
        return []
    findings = template.get("literature_findings")
    if not isinstance(findings, list):
        return []

    sources: List[LiteratureSource] = []
    for source_index, raw in enumerate(findings[:max_sources]):
        if not isinstance(raw, dict):
            continue
        source_id = _slug(raw.get("id"), f"source_{source_index + 1}")
        citation = _trim(raw.get("citation"), 500) or f"Source {source_index + 1}"
        chunks: List[LiteratureChunk] = []

        def add_chunks(values: Any, kind: Literal["evidence", "analyst_gap", "annotation", "context"]) -> None:
            if not isinstance(values, list):
                return
            for item in values[:10]:
                text = _trim(item, 1800)
                if text:
                    chunks.append(
                        LiteratureChunk(
                            id=f"{source_id}_chunk_{len(chunks) + 1}",
                            text=text,
                            kind=kind,
                        )
                    )

        for item in (raw.get("annotations") or [])[:20]:
            if not isinstance(item, dict) or item.get("evidence_kind") != "pdf_passage":
                continue
            if not item.get("passage_id") or not item.get("source_sha256") or not item.get("page"):
                continue
            text = _trim(item.get("snippet"), 1800)
            if text:
                chunks.append(LiteratureChunk(id=str(item["passage_id"]), text=text,
                    page=int(item["page"]), source_sha256=str(item["source_sha256"]),
                    provenance="pdf_passage", kind="evidence"))
        add_chunks(raw.get("knowns"), "evidence")
        add_chunks(raw.get("annotation_insights"), "annotation")
        notes = raw.get("structured_notes") or {}
        if isinstance(notes, dict):
            for field in ("limitations", "transferability_notes"):
                add_chunks(notes.get(field), "annotation")
        add_chunks(raw.get("unknowns"), "analyst_gap")
        synthesis_memo = _trim(raw.get("synthesis_memo"), 1800)
        if synthesis_memo:
            chunks.append(
                LiteratureChunk(
                    id=f"{source_id}_chunk_{len(chunks) + 1}",
                    text=synthesis_memo,
                    kind="context",
                )
            )
        if chunks:
            sources.append(
                LiteratureSource(
                    id=source_id,
                    citation=citation,
                    chunks=chunks,
                    source_ids={
                        str(key): _trim(value, 300)
                        for key, value in (raw.get("source_ids") or {}).items()
                        if _trim(value, 300)
                    },
                )
            )
    return sources


def build_paper_mapper_prompt(*, workspace_context: Dict[str, Any], source: LiteratureSource) -> str:
    return f"""
You are a provenance-constrained scientific evidence mapper. Build a micro-world for exactly one paper.

Workspace question and experiment context:
{json.dumps(workspace_context, ensure_ascii=False, default=str)[:7000]}

Paper:
{json.dumps(source.model_dump(), ensure_ascii=False, indent=2)}

Rules:
- Use only the supplied chunks. Do not use background knowledge to create paper claims.
- Every claim must cite one or more exact chunk ids from this paper.
- An analyst_gap chunk describes an uncertainty; it is not evidence that a proposition is true.
- Separate reported evidence from inference. Mark any project-level extrapolation as inferred.
- Preserve organism, intervention, measurement, and experimental-condition scope.
- Identify missing premises connecting the paper to the workspace decision.
- Do not write questions for the user in this stage.
- Return at most 4 atomic claims and 2 gaps. Keep every field concise.

Return JSON:
{{
  "claims": [
    {{
      "id": "short_snake_case_id",
      "proposition": "one atomic claim",
      "claim_type": "definition|mechanism|empirical_effect|measurement|method|boundary_condition|limitation|other",
      "status": "supported|inferred|contested",
      "chunk_ids": ["exact_chunk_id"],
      "scope": {{"organism": "", "intervention": "", "conditions": "", "outcome": ""}},
      "evidence_strength": 0.0,
      "extraction_confidence": 0.0
    }}
  ],
  "gaps": [
    {{
      "id": "short_snake_case_id",
      "statement": "specific unresolved logical or empirical gap",
      "related_claim_ids": ["claim_id"],
      "missing_premises": ["premise required to connect evidence to the decision"],
      "provisional_type": "retrieval|workspace|logical|ontology|conflict|empirical|tacit|hypothesis_space"
    }}
  ]
}}
""".strip()


def normalize_paper_model(source: LiteratureSource, raw: Dict[str, Any]) -> PaperWorldModel:
    valid_chunk_ids = {chunk.id for chunk in source.chunks if chunk.kind == "evidence"}
    claims: List[EvidenceClaim] = []
    rejected: List[Dict[str, str]] = []
    seen_claim_ids = set()
    for index, item in enumerate((raw.get("claims") or [])[:8]):
        if not isinstance(item, dict):
            continue
        claim_id = _slug(item.get("id"), f"claim_{index + 1}")
        claim_id = f"{source.id}__{claim_id}"
        proposition = _trim(item.get("proposition"), 1000)
        chunk_ids = [str(value) for value in (item.get("chunk_ids") or []) if str(value) in valid_chunk_ids]
        if not proposition or not chunk_ids:
            rejected.append(
                {
                    "claim_id": claim_id,
                    "reason": "missing proposition or valid source chunk provenance",
                }
            )
            continue
        if claim_id in seen_claim_ids:
            rejected.append({"claim_id": claim_id, "reason": "duplicate claim id"})
            continue
        seen_claim_ids.add(claim_id)
        try:
            claims.append(
                EvidenceClaim(
                    id=claim_id,
                    source_id=source.id,
                    proposition=proposition,
                    claim_type=item.get("claim_type") or "other",
                    status=item.get("status") or "supported",
                    chunk_ids=chunk_ids,
                    scope={str(key): _trim(value, 300) for key, value in (item.get("scope") or {}).items()},
                    evidence_strength=float(item.get("evidence_strength", 0.5)),
                    extraction_confidence=float(item.get("extraction_confidence", 0.5)),
                )
            )
        except (TypeError, ValueError):
            rejected.append({"claim_id": claim_id, "reason": "claim failed schema validation"})

    accepted_claim_ids = {claim.id for claim in claims}
    raw_to_full_claim_id = {
        claim.id.split("__", 1)[-1]: claim.id
        for claim in claims
    }
    gaps: List[PaperGap] = []
    for index, item in enumerate((raw.get("gaps") or [])[:6]):
        if not isinstance(item, dict) or not _trim(item.get("statement"), 1000):
            continue
        related = []
        for value in item.get("related_claim_ids") or []:
            candidate = str(value)
            full = candidate if candidate in accepted_claim_ids else raw_to_full_claim_id.get(_slug(candidate, ""))
            if full and full not in related:
                related.append(full)
        try:
            gaps.append(
                PaperGap(
                    id=f"{source.id}__{_slug(item.get('id'), f'gap_{index + 1}')}",
                    statement=_trim(item.get("statement"), 1000),
                    related_claim_ids=related,
                    missing_premises=[_trim(value, 600) for value in (item.get("missing_premises") or []) if _trim(value, 600)][:8],
                    provisional_type=item.get("provisional_type") or "logical",
                )
            )
        except (TypeError, ValueError):
            continue
    return PaperWorldModel(
        source_id=source.id,
        citation=source.citation,
        claims=claims,
        gaps=gaps,
        rejected_claims=rejected,
    )


def build_cross_paper_synthesis_prompt(
    *, workspace_context: Dict[str, Any], paper_models: List[PaperWorldModel]
) -> str:
    compact_models = [
        {
            "source_id": model.source_id,
            "citation": model.citation,
            "claims": [claim.model_dump(exclude_none=True) for claim in model.claims[:6]],
            "gaps": [gap.model_dump(exclude_none=True) for gap in model.gaps[:4]],
        }
        for model in paper_models
    ]
    return f"""
You are the cross-paper reasoner in an adaptive scientific elicitation harness.

Workspace context:
{json.dumps(workspace_context, ensure_ascii=False, default=str)[:7000]}

Provenance-checked paper micro-worlds:
{json.dumps(compact_models, ensure_ascii=False, separators=(',', ':'))[:16000]}

First align claims across papers without erasing disagreement. Then find missing premises between the evidence and concrete workspace decisions.

Gap routing rules:
- search_literature: likely answerable from more published evidence.
- inspect_workspace: likely present in project records, protocols, or existing data.
- derive or align_constructs: resolvable logically or terminologically.
- compare_evidence: sources disagree or operate under different scopes.
- run_experiment: the answer is an empirical unknown requiring new observations.
- ask_user: only tacit preferences, local constraints, unpublished knowledge, feasibility judgments, or decision thresholds the user is likely to know.
- discover_hypothesis: the current hypothesis space is probably incomplete.
- Never turn a retrieval, workspace, logical, or empirical gap into a user question merely because asking is easy.

Generate questions dynamically from the ask_user gaps. Do not use generic stock questions. Each question must name the relevant project-specific construct, intervention, outcome, or constraint. Every question must target exactly one belief variable and include a response likelihood for every hypothesis. Include an Other option when the hypothesis space may be incomplete.
Return at most 8 gaps, 4 belief variables, 4 decision actions, and 6 questions. Prefer one question per ask_user gap. Keep rationales to one sentence.

Return strict JSON:
{{
  "world_summary": "concise evidence-to-decision summary",
  "claim_relations": [
    {{"source_claim_id": "claim id", "target_claim_id": "claim id", "relation": "supports|contradicts|qualifies|replicates|same_construct|potentially_transfers_to", "rationale": "why"}}
  ],
  "gaps": [
    {{
      "id": "gap_id",
      "statement": "specific missing information",
      "gap_type": "retrieval|workspace|logical|ontology|conflict|empirical|tacit|hypothesis_space",
      "related_claim_ids": ["claim id"],
      "missing_premises": ["missing premise"],
      "affected_decisions": ["specific experiment or decision"],
      "candidate_actions": ["search_literature|inspect_workspace|derive|align_constructs|compare_evidence|run_experiment|ask_user|discover_hypothesis|stop"],
      "recommended_action": "one candidate action",
      "routing_rationale": "why this resolution source is appropriate",
      "decision_relevance": 0.0,
      "user_answerability": 0.0
    }}
  ],
  "belief_variables": [
    {{
      "id": "belief_id",
      "label": "project-specific uncertainty",
      "gap_id": "ask_user gap id",
      "hypotheses": [
        {{"id": "hypothesis_id", "proposition": "mutually exclusive possibility", "probability": 0.0, "evidence_refs": ["claim id"]}}
      ]
    }}
  ],
  "decision_actions": [
    {{"id": "action_id", "label": "feasible downstream action", "loss_by_hypothesis": {{"hypothesis_id": 0.0}}}}
  ],
  "candidate_questions": [
    {{
      "id": "question_id",
      "gap_id": "ask_user gap id",
      "target_variable_id": "belief_id",
      "question": "specific generated question",
      "why_it_matters": "which downstream decision could change",
      "evidence_refs": ["claim id"],
      "resolution_rationale": "why the user rather than search or experiment should resolve this",
      "alternative_resolution": "what the system could do if the user cannot answer",
      "answer_options": [{{"id": "option_id", "label": "specific answer", "allows_free_text": false}}],
      "predictions": [{{"hypothesis_id": "hypothesis_id", "option_probabilities": {{"option_id": 0.0}}}}],
      "decision_relevance": 0.0,
      "answerability": 0.0,
      "estimated_effort_seconds": 20
    }}
  ]
}}
""".strip()


def build_gap_routing_prompt(
    *, workspace_context: Dict[str, Any], paper_models: List[PaperWorldModel]
) -> str:
    compact_models = [
        {
            "source_id": model.source_id,
            "claims": [
                {
                    "id": claim.id,
                    "proposition": claim.proposition,
                    "status": claim.status,
                    "scope": claim.scope,
                }
                for claim in model.claims[:6]
            ],
            "gaps": [gap.model_dump(exclude_none=True) for gap in model.gaps[:4]],
        }
        for model in paper_models
    ]
    return f"""
You reconcile provenance-checked scientific micro-worlds and route evidence gaps. Return JSON only.

Workspace:
{json.dumps(workspace_context, ensure_ascii=False, default=str)[:5000]}

Paper micro-worlds:
{json.dumps(compact_models, ensure_ascii=False, separators=(',', ':'))[:14000]}

Create at most 2 claim relations and 4 non-duplicate gaps. Preserve conflicting scopes.
Route each gap to its best resolver:
- search_literature for published facts; inspect_workspace for existing local records;
- derive or align_constructs for logical/terminology work; compare_evidence for source conflict;
- run_experiment for unknown empirical effects; ask_user only for tacit constraints, unpublished local knowledge, feasibility judgments, or decision thresholds;
- discover_hypothesis when the model space is incomplete.
Do not convert an empirical or retrieval gap into ask_user.
If the workspace explicitly lists unresolved_user_owned_decisions, model each relevant item as a tacit gap routed to ask_user unless it has already been answered.

Return:
{{
  "world_summary": "two concise sentences",
  "claim_relations": [{{"source_claim_id":"id","target_claim_id":"id","relation":"supports|contradicts|qualifies|replicates|same_construct|potentially_transfers_to","rationale":"one sentence"}}],
  "gaps": [{{
    "id":"snake_case_id",
    "statement":"specific missing information",
    "gap_type":"retrieval|workspace|logical|ontology|conflict|empirical|tacit|hypothesis_space",
    "related_claim_ids":["claim id"],
    "missing_premises":["premise"],
    "affected_decisions":["decision"],
    "candidate_actions":["search_literature|inspect_workspace|derive|align_constructs|compare_evidence|run_experiment|ask_user|discover_hypothesis|stop"],
    "recommended_action":"one action",
    "routing_rationale":"one sentence",
    "decision_relevance":0.0,
    "user_answerability":0.0
  }}]
}}
""".strip()


def build_dynamic_question_prompt(
    *,
    workspace_context: Dict[str, Any],
    paper_models: List[PaperWorldModel],
    gap_analysis: Dict[str, Any],
) -> str:
    ask_gaps = [
        item
        for item in (gap_analysis.get("gaps") or [])
        if isinstance(item, dict) and item.get("recommended_action") == "ask_user"
    ][:2]
    claim_ids = {
        str(claim_id)
        for gap in ask_gaps
        for claim_id in (gap.get("related_claim_ids") or [])
    }
    claims = [
        {
            "id": claim.id,
            "proposition": claim.proposition,
            "scope": claim.scope,
        }
        for model in paper_models
        for claim in model.claims
        if claim.id in claim_ids
    ]
    return f"""
You generate decision-relevant questions from already-routed tacit scientific gaps. Return JSON only.

Workspace:
{json.dumps(workspace_context, ensure_ascii=False, default=str)[:4500]}

Ask-user gaps:
{json.dumps(ask_gaps, ensure_ascii=False, separators=(',', ':'))[:7000]}

Relevant evidence claims:
{json.dumps(claims, ensure_ascii=False, separators=(',', ':'))[:5000]}

For each useful gap, create one project-specific belief variable and at most one question. Return at most 2 variables, 3 actions, and 2 questions. The wording must be generated from the gap and name the relevant organism, intervention, outcome, assay, threshold, or constraint. Do not use stock questions. Hypotheses must be mutually exclusive. Include 2-3 answer options and a response-likelihood distribution for every hypothesis. Answer labels must be operational: use a numeric threshold or unit only when that exact number occurs in the supplied workspace or evidence; otherwise use a named policy or an Other/free-text threshold. Never invent a quantitative cutoff, and never use bare labels such as Low, Medium, High, Yes, or No. Include an Other option when the listed hypotheses may be incomplete. Decision actions must be downstream scientific choices from the workspace question, never "ask the user", "search", or another gap-resolution operation. Return at least two decision actions, and make their losses differ across hypotheses. Every action's loss_by_hypothesis must cover every hypothesis id. Keep all text concise.

Return:
{{
  "belief_variables":[{{"id":"belief_id","label":"specific uncertainty","gap_id":"exact ask-user gap id","hypotheses":[{{"id":"hypothesis_id","proposition":"possibility","probability":0.0,"evidence_refs":["claim id"]}}]}}],
  "decision_actions":[{{"id":"action_id","label":"feasible action","loss_by_hypothesis":{{"hypothesis_id":0.0}}}}],
  "candidate_questions":[{{
    "id":"question_id","gap_id":"exact ask-user gap id","target_variable_id":"belief_id",
    "question":"specific generated question","why_it_matters":"decision changed by the answer",
    "evidence_refs":["claim id"],"resolution_rationale":"why the user should answer",
    "alternative_resolution":"non-user resolution if they cannot answer",
    "answer_options":[{{"id":"option_id","label":"specific answer","allows_free_text":false}}],
    "predictions":[{{"hypothesis_id":"hypothesis_id","option_probabilities":{{"option_id":0.0}}}}],
    "decision_relevance":0.0,"answerability":0.0,"estimated_effort_seconds":20
  }}]
}}
""".strip()


def unsupported_question_numbers(question_payload: Dict[str, Any], grounding_text: str) -> List[str]:
    pattern = re.compile(r"(?<![A-Za-z0-9_])\d+(?:\.\d+)?%?")
    allowed = set(pattern.findall(grounding_text))
    generated_text: List[str] = []
    for variable in question_payload.get("belief_variables") or []:
        if not isinstance(variable, dict):
            continue
        generated_text.append(str(variable.get("label") or ""))
        generated_text.extend(
            str(item.get("proposition") or "")
            for item in (variable.get("hypotheses") or [])
            if isinstance(item, dict)
        )
    for question in question_payload.get("candidate_questions") or []:
        if not isinstance(question, dict):
            continue
        generated_text.append(str(question.get("question") or ""))
        generated_text.extend(
            str(item.get("label") or "")
            for item in (question.get("answer_options") or [])
            if isinstance(item, dict)
        )
    return sorted({token for token in pattern.findall("\n".join(generated_text)) if token not in allowed})


def build_quantitative_repair_prompt(
    *, question_payload: Dict[str, Any], unsupported_numbers: List[str]
) -> str:
    sanitized_payload = json.dumps(question_payload, ensure_ascii=False, separators=(",", ":"))[:12000]
    for token in unsupported_numbers:
        sanitized_payload = sanitized_payload.replace(token, "[UNSUPPORTED_CUTOFF]")
    return f"""
Repair this generated adaptive-elicitation JSON without changing its gap ids, variable ids, hypothesis ids, action ids, or scientific topic.

The payload contained {len(unsupported_numbers)} invented quantitative value(s). They have been replaced with [UNSUPPORTED_CUTOFF].

Replace unsupported numeric cutoffs in labels, propositions, questions, and answer options with complete non-numeric policies. For a tolerance question, contrast a strict policy such as "No reduction from the current baseline is acceptable" with a permissive policy such as "A trade-off is acceptable; specify the maximum". Only the option asking the user to specify a limit should have allows_free_text true. Do not emit the placeholder [UNSUPPORTED_CUTOFF], and do not introduce any new number. Keep the response-likelihood distributions and loss_by_hypothesis numeric probabilities/losses; those are model parameters and are allowed.

Return only the same three top-level keys: belief_variables, decision_actions, candidate_questions.

Payload:
{sanitized_payload}
""".strip()


def normalize_synthesis(
    *, raw: Dict[str, Any], paper_models: List[PaperWorldModel]
) -> EpistemicHarnessResult:
    claim_ids = {claim.id for model in paper_models for claim in model.claims}
    relations: List[ClaimRelation] = []
    for item in raw.get("claim_relations") or []:
        if not isinstance(item, dict):
            continue
        if item.get("source_claim_id") not in claim_ids or item.get("target_claim_id") not in claim_ids:
            continue
        if item.get("relation") == "replicates":
            owners = {claim.id: model.source_id for model in paper_models for claim in model.claims}
            if owners.get(item.get("source_claim_id")) == owners.get(item.get("target_claim_id")):
                continue
        try:
            relations.append(ClaimRelation.model_validate(item))
        except ValueError:
            continue

    gaps: List[EpistemicGap] = []
    for index, item in enumerate(raw.get("gaps") or []):
        if not isinstance(item, dict):
            continue
        candidate_actions = [value for value in (item.get("candidate_actions") or []) if value in ResolutionAction.__args__]
        recommended = item.get("recommended_action")
        if recommended not in ResolutionAction.__args__:
            continue
        if recommended not in candidate_actions:
            candidate_actions.append(recommended)
        action_gap_type = {
            "ask_user": "tacit",
            "run_experiment": "empirical",
            "search_literature": "retrieval",
            "inspect_workspace": "workspace",
            "align_constructs": "ontology",
            "compare_evidence": "conflict",
            "discover_hypothesis": "hypothesis_space",
            "derive": "logical",
        }.get(recommended)
        gap_type = action_gap_type or item.get("gap_type")
        if gap_type not in GapType.__args__:
            gap_type = "logical"
        try:
            gaps.append(
                EpistemicGap(
                    id=_slug(item.get("id"), f"gap_{index + 1}"),
                    statement=_trim(item.get("statement"), 1000),
                    gap_type=gap_type,
                    related_claim_ids=[value for value in (item.get("related_claim_ids") or []) if value in claim_ids],
                    missing_premises=[_trim(value, 600) for value in (item.get("missing_premises") or []) if _trim(value, 600)][:8],
                    affected_decisions=[_trim(value, 500) for value in (item.get("affected_decisions") or []) if _trim(value, 500)][:8],
                    candidate_actions=candidate_actions,
                    recommended_action=recommended,
                    routing_rationale=_trim(item.get("routing_rationale"), 1000),
                    decision_relevance=float(item.get("decision_relevance", 0.5)),
                    user_answerability=float(item.get("user_answerability", 0.0)),
                )
            )
        except (TypeError, ValueError):
            continue

    gaps_by_id = {gap.id: gap for gap in gaps}
    ask_gap_ids = [gap.id for gap in gaps if gap.recommended_action == "ask_user"]
    variables = []
    allowed_variable_ids = set()
    variable_to_gap: Dict[str, str] = {}
    for item in raw.get("belief_variables") or []:
        if not isinstance(item, dict):
            continue
        gap_id = _slug(item.get("gap_id"), "")
        if not gap_id and len(ask_gap_ids) == 1:
            gap_id = ask_gap_ids[0]
        gap = gaps_by_id.get(gap_id)
        if not gap or gap.recommended_action != "ask_user":
            continue
        variable_id = _slug(item.get("id"), "")
        hypotheses = item.get("hypotheses") or []
        if not variable_id or len(hypotheses) < 2:
            continue
        normalized_item = dict(item)
        normalized_item["id"] = variable_id
        normalized_item["gap_id"] = gap_id
        variables.append(normalized_item)
        allowed_variable_ids.add(variable_id)
        variable_to_gap[variable_id] = gap_id

    questions = []
    for item in raw.get("candidate_questions") or []:
        if not isinstance(item, dict):
            continue
        gap_id = _slug(item.get("gap_id"), "")
        target_id = _slug(item.get("target_variable_id"), "")
        if not gap_id:
            gap_id = variable_to_gap.get(target_id, "")
        gap = gaps_by_id.get(gap_id)
        if not gap or gap.recommended_action != "ask_user" or target_id not in allowed_variable_ids or variable_to_gap.get(target_id) != gap_id:
            continue
        normalized_item = dict(item)
        normalized_item["id"] = _slug(item.get("id"), f"question_{len(questions) + 1}")
        normalized_item["gap_id"] = gap_id
        normalized_item["target_variable_id"] = target_id
        normalized_item["gap_type"] = gap.gap_type
        normalized_item["evidence_refs"] = [value for value in (item.get("evidence_refs") or []) if value in claim_ids]
        questions.append(normalized_item)

    if not gaps:
        raise ValueError("Harness synthesis produced no valid routed gaps; absence of output is not a stop decision.")
    if not ask_gap_ids:
        return EpistemicHarnessResult(
            world_summary=_trim(raw.get("world_summary"), 2000),
            paper_models=paper_models, claim_relations=relations, gaps=gaps,
            elicitation_payload={
                "belief_variables": [], "decision_actions": [], "candidate_questions": [],
                "resolution_only": True,
            },
        )
    if not variables or not questions:
        diagnostic = {
            "ask_gap_ids": ask_gap_ids,
            "raw_variable_gap_ids": [item.get("gap_id") for item in (raw.get("belief_variables") or []) if isinstance(item, dict)],
            "raw_question_gap_ids": [item.get("gap_id") for item in (raw.get("candidate_questions") or []) if isinstance(item, dict)],
        }
        raise ValueError(
            "Harness synthesis produced no schema-valid ask-user gaps and dynamic questions: "
            + json.dumps(diagnostic, ensure_ascii=False)
        )

    hypothesis_ids = {
        _slug(hypothesis.get("id"), "")
        for variable in variables
        for hypothesis in (variable.get("hypotheses") or [])
        if isinstance(hypothesis, dict) and _slug(hypothesis.get("id"), "")
    }
    forbidden_action_terms = ("ask user", "ask the user", "question user", "search literature", "inspect workspace")
    actions = []
    for item in raw.get("decision_actions") or []:
        if not isinstance(item, dict):
            continue
        label = _trim(item.get("label"), 500)
        losses = item.get("loss_by_hypothesis")
        if any(term in label.lower() for term in forbidden_action_terms):
            continue
        if not isinstance(losses, dict) or not hypothesis_ids.issubset({_slug(key, "") for key in losses}):
            continue
        try:
            relevant_losses = [float(losses[key]) for key in losses if _slug(key, "") in hypothesis_ids]
        except (TypeError, ValueError):
            continue
        if len({round(value, 8) for value in relevant_losses}) < 2:
            continue
        actions.append(item)
    if len(actions) < 2:
        actions = []
    return EpistemicHarnessResult(
        world_summary=_trim(raw.get("world_summary"), 2000),
        paper_models=paper_models,
        claim_relations=relations,
        gaps=gaps,
        elicitation_payload={
            "belief_variables": variables,
            "decision_actions": actions,
            "candidate_questions": questions,
        },
    )


async def run_epistemic_gap_harness(
    *,
    workspace_context: Dict[str, Any],
    sources: List[LiteratureSource],
    generate_json: GenerateJSON,
    max_concurrency: int = 2,
) -> EpistemicHarnessResult:
    if not sources:
        raise ValueError("The epistemic harness requires at least one literature source with evidence chunks.")
    semaphore = asyncio.Semaphore(max(1, min(max_concurrency, 4)))

    async def map_source(source: LiteratureSource) -> PaperWorldModel:
        async with semaphore:
            raw = await generate_json(
                build_paper_mapper_prompt(workspace_context=workspace_context, source=source),
                max_retries=0,
                temperature=0.1,
                top_p=0.85,
                timeout_seconds=120,
                num_predict=600,
            )
        return normalize_paper_model(source, raw)

    paper_models = await asyncio.gather(*(map_source(source) for source in sources))
    if not any(model.claims for model in paper_models):
        raise ValueError("All generated paper claims failed provenance validation.")
    gap_analysis = await generate_json(
        build_gap_routing_prompt(
            workspace_context=workspace_context,
            paper_models=paper_models,
        ),
        max_retries=0,
        temperature=0.1,
        top_p=0.85,
        timeout_seconds=300,
        num_predict=1300,
    )
    # Normalize routing before spending a model call on questions. Invalid output
    # remains an error; valid non-user routes are a successful resolution plan.
    if not any(
        isinstance(gap, dict) and gap.get("recommended_action") == "ask_user"
        for gap in (gap_analysis.get("gaps") or [])
    ):
        return normalize_synthesis(raw=gap_analysis, paper_models=paper_models)
    question_payload = await generate_json(
        build_dynamic_question_prompt(
            workspace_context=workspace_context,
            paper_models=paper_models,
            gap_analysis=gap_analysis,
        ),
        max_retries=0,
        temperature=0.15,
        top_p=0.85,
        timeout_seconds=300,
        num_predict=1600,
    )
    grounding_text = json.dumps(workspace_context, ensure_ascii=False, default=str) + "\n" + "\n".join(
        chunk.text for source in sources for chunk in source.chunks
    )
    unsupported_numbers = unsupported_question_numbers(question_payload, grounding_text)
    if unsupported_numbers:
        question_payload = await generate_json(
            build_quantitative_repair_prompt(
                question_payload=question_payload,
                unsupported_numbers=unsupported_numbers,
            ),
            max_retries=0,
            temperature=0.05,
            top_p=0.8,
            timeout_seconds=240,
            num_predict=1300,
        )
        remaining_unsupported = unsupported_question_numbers(question_payload, grounding_text)
        if remaining_unsupported:
            raise ValueError(
                "Question generation retained unsupported quantitative values: "
                + ", ".join(remaining_unsupported)
            )
        if "[UNSUPPORTED_CUTOFF]" in json.dumps(question_payload, ensure_ascii=False):
            raise ValueError("Question repair leaked an unsupported-cutoff placeholder.")
    raw_synthesis = {**gap_analysis, **question_payload}
    return normalize_synthesis(raw=raw_synthesis, paper_models=paper_models)


def harness_run_id(result: EpistemicHarnessResult) -> str:
    payload = json.dumps(result.trace(), sort_keys=True, ensure_ascii=False)
    return "harness_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
