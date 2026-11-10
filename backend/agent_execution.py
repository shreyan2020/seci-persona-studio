from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from database import db
from models import (
    AgenticPlan,
    JudgmentCall,
    PlanRisk,
    PlanStep,
    ProjectExecutionRun,
    ProposalCandidate,
    ResearchGap,
    ResearchFinding,
    ResearchWorkTemplate,
    StartProjectExecutionRequest,
    ValidationTrack,
)
from ollama_client import ollama
from research_tools import available_research_tools, collect_pdf_paths, get_research_tool_handlers, search_pubmed, read_local_pdf


class ScopeArtifact(BaseModel):
    summary: str = ""
    prioritized_targets: List[str] = Field(default_factory=list)
    leverage_points: List[str] = Field(default_factory=list)
    boundary_conditions: List[str] = Field(default_factory=list)
    open_dependencies: List[str] = Field(default_factory=list)


class EvidenceArtifact(BaseModel):
    summary: str = ""
    strongest_patterns: List[str] = Field(default_factory=list)
    unresolved_questions: List[str] = Field(default_factory=list)
    transferable_examples: List[str] = Field(default_factory=list)
    high_attention_topics: List[str] = Field(default_factory=list)


class ValidationArtifact(BaseModel):
    summary: str = ""
    validation_tracks: List[ValidationTrack] = Field(default_factory=list)
    recommended_readouts: List[str] = Field(default_factory=list)
    condition_generalization_checks: List[str] = Field(default_factory=list)
    ai_enzyme_improvement_objectives: List[str] = Field(default_factory=list)


class ProposalArtifact(BaseModel):
    summary: str = ""
    proposal_candidates: List[ProposalCandidate] = Field(default_factory=list)
    success_criteria: List[str] = Field(default_factory=list)
    next_decisions: List[str] = Field(default_factory=list)


class ToolEnrichmentArtifact(BaseModel):
    summary: str = ""
    literature_findings: List[ResearchFinding] = Field(default_factory=list)
    judgment_calls: List[JudgmentCall] = Field(default_factory=list)
    boundary_conditions: List[str] = Field(default_factory=list)
    tool_queries: List[str] = Field(default_factory=list)


def _clean_lines(values: List[Any], limit: int = 6) -> List[str]:
    out: List[str] = []
    seen = set()
    for value in values:
        text = " ".join(str(value or "").split()).strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def _work_template_summary(work_template: Optional[ResearchWorkTemplate]) -> str:
    if not work_template:
        return "none"
    sections: List[str] = []
    if work_template.initial_query.strip():
        sections.append(f"Initial query: {work_template.initial_query.strip()}")
    if work_template.literature_findings:
        findings = []
        for item in work_template.literature_findings[:5]:
            citation = item.citation.strip() or "uncited finding"
            knowns = "; ".join(_clean_lines(item.knowns, 3))
            unknowns = "; ".join(_clean_lines(item.unknowns, 3))
            findings.append(f"{citation}. Knowns: {knowns or 'none'}. Unknowns: {unknowns or 'none'}.")
        sections.append("Literature findings: " + " ".join(findings))
    if work_template.common_gaps:
        sections.append(
            "Common gaps: " + " | ".join(
                f"{gap.theme.strip() or 'gap'} -> {gap.next_question.strip() or 'open question'}"
                for gap in work_template.common_gaps[:5]
            )
        )
    if work_template.judgment_calls:
        sections.append(
            "Judgment calls: " + " | ".join(
                f"{item.stance.strip() or 'stance'}: {item.implication.strip() or item.rationale.strip() or 'no implication'}"
                for item in work_template.judgment_calls[:5]
            )
        )
    if work_template.validation_tracks:
        sections.append(
            "Validation tracks: " + " | ".join(
                f"{track.target.strip() or 'target'} via {track.method.strip() or 'method'}"
                for track in work_template.validation_tracks[:5]
            )
        )
    if work_template.proposal_candidates:
        sections.append(
            "Proposal seeds: " + " | ".join(
                f"{item.title.strip() or 'proposal'}: {item.why_now.strip() or item.experiment_outline.strip() or 'no note'}"
                for item in work_template.proposal_candidates[:5]
            )
        )
    if work_template.synthesis_memo.strip():
        sections.append(f"Synthesis memo: {work_template.synthesis_memo.strip()}")
    return "\n".join(sections) if sections else "none"


def _objective_context(request: StartProjectExecutionRequest) -> str:
    parts = [
        f"Objective id: {(request.objective_id or '').strip() or 'none'}",
        f"Objective title: {(request.objective_title or '').strip() or 'none'}",
        f"Objective definition: {(request.objective_definition or '').strip() or 'none'}",
        "Objective signals: " + (", ".join(_clean_lines(request.objective_signals, 8)) or "none"),
    ]
    return "\n".join(parts)


def _persona_summary(persona: dict) -> str:
    return str(persona.get("last_summary") or "No persona summary available.").strip()


def _persona_focus(persona: dict) -> str:
    persona_json = persona.get("persona_json") or {}
    workflow_focus = _clean_lines(persona_json.get("workflow_focus") or [], 6)
    goals = _clean_lines(persona_json.get("goals") or [], 6)
    stage = str(persona_json.get("workflow_stage") or "general").strip()
    role = str(persona_json.get("role") or "workflow_partner").strip()
    parts = [f"Role: {role}", f"Workflow stage: {stage}"]
    if workflow_focus:
        parts.append("Workflow focus: " + ", ".join(workflow_focus))
    if goals:
        parts.append("Goals: " + " | ".join(goals))
    return "\n".join(parts)


def _clarifying_answers_block(request: StartProjectExecutionRequest) -> str:
    answers = [
        f"- {question}: {answer}"
        for question, answer in (request.clarifying_answers or {}).items()
        if str(answer or "").strip()
    ]
    return "\n".join(answers) if answers else "none"


def _stage_prompt_prefix(project: dict, persona: dict, request: StartProjectExecutionRequest, work_template: ResearchWorkTemplate) -> str:
    return f"""Project:
- name: {project.get("name")}
- end_product: {project.get("end_product")}
- target_host: {project.get("target_host")}
- project_goal: {project.get("project_goal")}
- raw_material_focus: {project.get("raw_material_focus") or "none"}
- notes: {project.get("notes") or "none"}

Focus question:
{(request.focus_question or project.get("project_goal") or "").strip() or "none"}

Selected objective:
{_objective_context(request)}

Persona lens:
{_persona_summary(persona)}

Persona operating context:
{_persona_focus(persona)}

Clarifying answers:
{_clarifying_answers_block(request)}

User reasoning notes:
{(request.reasoning_notes or "").strip() or "none"}

Structured research work template:
{_work_template_summary(work_template)}
"""


def _fallback_scope(project: dict, request: StartProjectExecutionRequest, work_template: ResearchWorkTemplate) -> ScopeArtifact:
    targets = _clean_lines(
        [request.objective_title, project.get("project_goal"), request.focus_question]
        + [gap.theme for gap in work_template.common_gaps]
        + [track.target for track in work_template.validation_tracks],
        5,
    )
    leverage = _clean_lines(
        [item for finding in work_template.literature_findings for item in finding.knowns]
        + [item.theme for item in work_template.common_gaps],
        5,
    )
    boundaries = _clean_lines(
        [item.stance for item in work_template.judgment_calls]
        + [request.reasoning_notes or ""],
        5,
    )
    dependencies = _clean_lines(
        [item.next_question for item in work_template.common_gaps]
        + [question for track in work_template.validation_tracks for question in track.questions],
        5,
    )
    summary = (
        f"Center the run on {(request.focus_question or project.get('project_goal') or 'the active project question').strip()} "
        f"for {project.get('end_product') or 'the target product'} in {project.get('target_host') or 'the selected host'}."
    )
    return ScopeArtifact(
        summary=summary,
        prioritized_targets=targets or [project.get("project_goal") or "Clarify the active objective"],
        leverage_points=leverage or ["Turn the strongest literature signals into decision-useful next steps."],
        boundary_conditions=boundaries or ["Preserve explicit user exclusions and do not reopen deprioritized methods."],
        open_dependencies=dependencies or ["State the assumptions that still need explicit validation."],
    )


def _fallback_evidence(work_template: ResearchWorkTemplate) -> EvidenceArtifact:
    strongest_patterns = _clean_lines(
        [item for finding in work_template.literature_findings for item in finding.knowns]
        + [gap.theme for gap in work_template.common_gaps],
        6,
    )
    unresolved_questions = _clean_lines(
        [item for finding in work_template.literature_findings for item in finding.unknowns]
        + [gap.next_question for gap in work_template.common_gaps],
        6,
    )
    transferable_examples = _clean_lines(
        [finding.relevance for finding in work_template.literature_findings],
        5,
    )
    topics = _clean_lines(
        [gap.priority_note for gap in work_template.common_gaps]
        + [gap.theme for gap in work_template.common_gaps],
        5,
    )
    return EvidenceArtifact(
        summary="Preserve the strongest known strategy patterns while explicitly tracking the unresolved transfer and validation questions.",
        strongest_patterns=strongest_patterns or ["Precursor supply, enzyme choice, and process context repeatedly appear as leverage points."],
        unresolved_questions=unresolved_questions or ["Decide which apparently transferable findings need explicit validation in the target system."],
        transferable_examples=transferable_examples or ["Use neighboring compounds and related conditions as analog evidence, but flag generalization risk."],
        high_attention_topics=topics or ["High-citation or repeatedly mentioned topics should receive explicit attention in the final draft."],
    )


def _fallback_validation(work_template: ResearchWorkTemplate) -> ValidationArtifact:
    tracks = work_template.validation_tracks[:6]
    if not tracks:
        tracks = [
            ValidationTrack(
                id="validation_1",
                target="Key enzyme validation set",
                method="Compare enzyme variants under matched expression and assay conditions",
                questions=[
                    "Which objective matters most: higher activity, lower side activity, or improved expression in the host?",
                    "Which condition changes could break generalization from the literature examples?",
                ],
                success_signal="At least one variant improves the selected readout without creating a worse tradeoff elsewhere.",
            )
        ]
    readouts = _clean_lines(
        [track.success_signal for track in tracks]
        + [item for proposal in work_template.proposal_candidates for item in proposal.readouts],
        6,
    )
    return ValidationArtifact(
        summary="Define a validation package that makes transfer assumptions and enzyme-improvement goals observable before scaling the scope.",
        validation_tracks=tracks,
        recommended_readouts=readouts or ["Use readouts that separate activity gains from side-activity or expression artifacts."],
        condition_generalization_checks=[
            "Check whether the best-performing condition in the literature still holds under the target host and assay constraints."
        ],
        ai_enzyme_improvement_objectives=[
            "Rank whether the AI design goal is activity, selectivity, expression, or condition robustness before generating variants."
        ],
    )


def _fallback_proposals(project: dict, request: StartProjectExecutionRequest, work_template: ResearchWorkTemplate) -> ProposalArtifact:
    proposals = work_template.proposal_candidates[:6]
    if not proposals:
        proposals = [
            ProposalCandidate(
                id="proposal_1",
                title=f"Experiment plan for {(project.get('end_product') or 'target product')} transfer validation",
                why_now="The literature signals are promising but still require target-specific confirmation.",
                experiment_outline=(
                    "Select the most transferable benchmark strategy, define the minimum variant set, and compare performance under the target condition."
                ),
                readouts=[
                    "Primary production readout",
                    "Evidence of improved enzyme behavior",
                    "Generalization or failure-mode notes",
                ],
            )
        ]
    criteria = _clean_lines(
        [item.success_signal for item in work_template.validation_tracks]
        + [item for proposal in proposals for item in proposal.readouts],
        6,
    )
    next_decisions = _clean_lines(
        [gap.next_question for gap in work_template.common_gaps]
        + [item.implication for item in work_template.judgment_calls],
        6,
    )
    return ProposalArtifact(
        summary=(
            f"Turn the run into a concrete proposal set for {(request.focus_question or project.get('project_goal') or 'the active project question').strip()}."
        ),
        proposal_candidates=proposals,
        success_criteria=criteria or ["Each proposal should have a measurable success signal and a clear follow-on decision."],
        next_decisions=next_decisions or ["Choose which proposal should become the next lab-ready experiment plan."],
    )


async def _fallback_tool_enrichment(project: dict, request: StartProjectExecutionRequest, work_template: ResearchWorkTemplate) -> ToolEnrichmentArtifact:
    findings: List[ResearchFinding] = []
    tool_queries: List[str] = []

    primary_query = (
        work_template.initial_query.strip()
        or (request.focus_question or "").strip()
        or str(project.get("project_goal") or "").strip()
    )
    if primary_query:
        try:
            result = await search_pubmed(
                primary_query,
                max_results=5,
                project_goal=str(project.get("project_goal") or ""),
                objective_title=request.objective_title or "",
                objective_definition=request.objective_definition or "",
                objective_signals=request.objective_signals or [],
                user_inputs=[
                    request.focus_question or "",
                    request.reasoning_notes or "",
                    _clarifying_answers_block(request),
                    _work_template_summary(work_template),
                    str(project.get("end_product") or ""),
                    str(project.get("target_host") or ""),
                    str(project.get("notes") or ""),
                ],
            )
            tool_queries.append(str(result.get("search_query") or result.get("formulated_query") or primary_query))
            for index, item in enumerate((result.get("results") or [])[:5], start=1):
                findings.append(
                    ResearchFinding(
                        id=f"tool_finding_{index}",
                        citation=str(item.get("citation") or "").strip(),
                        labels=["pubmed", "tool-assisted evidence"],
                        knowns=_clean_lines([str(item.get("title") or "").strip()], 3),
                        unknowns=[],
                        relevance=str(item.get("abstract") or "").strip()[:500],
                    )
                )
        except Exception:
            pass

    judgments: List[JudgmentCall] = []
    boundary_lines = _clean_lines(
        [item.stance for item in work_template.judgment_calls] + [request.reasoning_notes or ""],
        5,
    )
    for index, line in enumerate(boundary_lines[:3], start=1):
        judgments.append(
            JudgmentCall(
                id=f"tool_judgment_{index}",
                stance=line,
                rationale="Recovered from the current workspace as a likely boundary or prioritization signal.",
                implication="Preserve this boundary when proposing citations, validation tracks, and experiments.",
            )
        )

    pdf_paths = collect_pdf_paths(request.notes or "", request.reasoning_notes or "")
    for path in pdf_paths[:2]:
        try:
            pdf_result = await read_local_pdf(path, max_pages=4)
            excerpt = str(pdf_result.get("text_excerpt") or "").strip()
            if excerpt:
                findings.append(
                    ResearchFinding(
                        id=f"tool_pdf_{len(findings) + 1}",
                        citation=f"Local PDF: {path}",
                        labels=["pdf", "tool-assisted evidence"],
                        knowns=_clean_lines([excerpt[:300]], 2),
                        unknowns=[],
                        relevance="Local PDF evidence ingested during execution.",
                    )
                )
        except Exception:
            pass

    return ToolEnrichmentArtifact(
        summary="Tool enrichment fallback searched PubMed directly and harvested existing boundary signals from the workspace.",
        literature_findings=findings[:5],
        judgment_calls=judgments[:4],
        boundary_conditions=_clean_lines([item.stance for item in judgments], 4),
        tool_queries=tool_queries,
    )


async def _run_json_stage(prompt: str, task_type: str) -> Dict[str, Any]:
    return await ollama.generate_json_cached(
        cache=db,
        task_type=task_type,
        prompt=prompt,
        cache_version=1,
        max_retries=2,
        temperature=0.2,
        top_p=0.9,
    )


async def _derive_tool_enrichment(project: dict, persona: dict, request: StartProjectExecutionRequest, work_template: ResearchWorkTemplate) -> ToolEnrichmentArtifact:
    tool_model = os.getenv("OLLAMA_TOOL_MODEL") or os.getenv("OLLAMA_SOTA_MODEL") or ollama.model
    system_prompt = """You are a biotech research assistant using tools.

Use tools when they can reduce manual cognitive load in the workspace, especially for:
- finding candidate citations or paper records
- extracting useful text from local PDFs explicitly referenced by the user
- surfacing likely boundary conditions or prioritization constraints

Use `search_pubmed` for literature discovery.
When calling `search_pubmed`, do not pass the user's full paragraph verbatim. Formulate a compact PubMed-style query from the project goal,
selected objective, objective signals, clarifying answers, reasoning notes, and work-template gaps. Prefer high-signal terms such as product,
host, pathway, enzyme, method, and benchmark terms.
Use `read_local_pdf` only when a PDF path is explicitly present in the workspace notes or reasoning.
If citations or boundaries are already strong and sufficient, you may decide not to call any tool.
"""
    user_prompt = f"""Fill the manual-heavy workspace fields as much as possible.

{_stage_prompt_prefix(project, persona, request, work_template)}

The goal is to reduce user effort in these fields:
- literature finding citations / source rows
- boundary conditions and judgment calls

If evidence is missing, use tools to gather it before finishing.
"""
    try:
        messages = await ollama.run_tool_loop(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            tools=available_research_tools(),
            tool_handlers=get_research_tool_handlers(),
            model=tool_model,
            max_rounds=4,
            temperature=0.1,
            top_p=0.9,
        )
        tool_context = ollama.collect_tool_messages(messages)
        if not tool_context.strip():
            return await _fallback_tool_enrichment(project, request, work_template)

        synthesis_prompt = f"""You are turning tool outputs into structured workspace suggestions.

{_stage_prompt_prefix(project, persona, request, work_template)}

Tool outputs:
{tool_context}

Task:
1. Propose literature finding rows using concrete citation strings.
2. Propose judgment calls or boundary conditions grounded in the user's notes and tool outputs.
3. Keep suggestions concise and decision-useful.
4. Do not invent claims unsupported by the workspace or tool outputs.

Return ONLY valid JSON:
{{
  "summary": "string",
  "literature_findings": [
    {{
      "id": "finding_1",
      "citation": "string",
      "labels": ["string"],
      "knowns": ["string"],
      "unknowns": ["string"],
      "relevance": "string"
    }}
  ],
  "judgment_calls": [
    {{
      "id": "judgment_1",
      "stance": "string",
      "rationale": "string",
      "implication": "string"
    }}
  ],
  "boundary_conditions": ["string"],
  "tool_queries": ["string"]
}}
"""
        payload = await _run_json_stage(synthesis_prompt, "execution_tool_synthesis")
        return ToolEnrichmentArtifact.model_validate(payload)
    except Exception:
        return await _fallback_tool_enrichment(project, request, work_template)


async def _derive_scope(project: dict, persona: dict, request: StartProjectExecutionRequest, work_template: ResearchWorkTemplate) -> ScopeArtifact:
    prompt = f"""You are a biotech execution coordinator. Build a scope brief that turns a workspace into an executable run.

{_stage_prompt_prefix(project, persona, request, work_template)}

Return ONLY valid JSON:
{{
  "summary": "string",
  "prioritized_targets": ["string"],
  "leverage_points": ["string"],
  "boundary_conditions": ["string"],
  "open_dependencies": ["string"]
}}
"""
    try:
        return ScopeArtifact.model_validate(await _run_json_stage(prompt, "execution_scope"))
    except Exception:
        return _fallback_scope(project, request, work_template)


async def _derive_evidence(project: dict, persona: dict, request: StartProjectExecutionRequest, work_template: ResearchWorkTemplate, scope: ScopeArtifact) -> EvidenceArtifact:
    prompt = f"""You are an evidence-and-gap analyst for a biotech planning workflow.

{_stage_prompt_prefix(project, persona, request, work_template)}

Scope brief:
- summary: {scope.summary}
- prioritized targets: {", ".join(scope.prioritized_targets) or "none"}
- leverage points: {", ".join(scope.leverage_points) or "none"}
- boundaries: {", ".join(scope.boundary_conditions) or "none"}

Task:
1. Distill the strongest recurring strategy patterns from the existing findings.
2. Extract unresolved questions that still block confident transfer to the user's target case.
3. Note transferable examples or analog cases that matter.
4. Highlight which topics deserve disproportionate attention because they recur, are high leverage, or are recently emphasized.

Return ONLY valid JSON:
{{
  "summary": "string",
  "strongest_patterns": ["string"],
  "unresolved_questions": ["string"],
  "transferable_examples": ["string"],
  "high_attention_topics": ["string"]
}}
"""
    try:
        return EvidenceArtifact.model_validate(await _run_json_stage(prompt, "execution_evidence"))
    except Exception:
        return _fallback_evidence(work_template)


async def _derive_validation(project: dict, persona: dict, request: StartProjectExecutionRequest, work_template: ResearchWorkTemplate, scope: ScopeArtifact, evidence: EvidenceArtifact) -> ValidationArtifact:
    prompt = f"""You are a biotech validation strategist. Convert the current evidence into concrete validation tracks.

{_stage_prompt_prefix(project, persona, request, work_template)}

Scope brief:
- summary: {scope.summary}
- prioritized targets: {", ".join(scope.prioritized_targets) or "none"}

Evidence brief:
- summary: {evidence.summary}
- strongest patterns: {", ".join(evidence.strongest_patterns) or "none"}
- unresolved questions: {", ".join(evidence.unresolved_questions) or "none"}
- transferable examples: {", ".join(evidence.transferable_examples) or "none"}

Task:
1. Propose validation tracks that test the most important transfer assumptions.
2. Include tracks for enzyme performance, condition transfer, or analog generalization when relevant.
3. Make the success signals measurable and decision-useful.
4. Recommend readouts that can distinguish better activity from better expression, lower side activity, or better condition robustness.

Return ONLY valid JSON:
{{
  "summary": "string",
  "validation_tracks": [
    {{
      "id": "validation_1",
      "target": "string",
      "method": "string",
      "questions": ["string"],
      "success_signal": "string"
    }}
  ],
  "recommended_readouts": ["string"],
  "condition_generalization_checks": ["string"],
  "ai_enzyme_improvement_objectives": ["string"]
}}
"""
    try:
        return ValidationArtifact.model_validate(await _run_json_stage(prompt, "execution_validation"))
    except Exception:
        return _fallback_validation(work_template)


async def _derive_proposals(project: dict, persona: dict, request: StartProjectExecutionRequest, work_template: ResearchWorkTemplate, scope: ScopeArtifact, evidence: EvidenceArtifact, validation: ValidationArtifact) -> ProposalArtifact:
    prompt = f"""You are a biotech proposal architect. Turn the workspace into concrete proposal candidates.

{_stage_prompt_prefix(project, persona, request, work_template)}

Scope brief:
- {scope.summary}

Evidence brief:
- strongest patterns: {", ".join(evidence.strongest_patterns) or "none"}
- unresolved questions: {", ".join(evidence.unresolved_questions) or "none"}

Validation brief:
- tracks: {" | ".join(f"{item.target} via {item.method}" for item in validation.validation_tracks) or "none"}
- readouts: {", ".join(validation.recommended_readouts) or "none"}
- generalization checks: {", ".join(validation.condition_generalization_checks) or "none"}

Task:
1. Generate proposal candidates that follow the user's boundaries and preserve the strongest transfer opportunities.
2. Each proposal should be experiment-oriented and grounded in the validation logic above.
3. Include why the proposal matters now, the basic outline, and the key readouts.
4. Return explicit success criteria and the next decisions these proposals should unlock.

Return ONLY valid JSON:
{{
  "summary": "string",
  "proposal_candidates": [
    {{
      "id": "proposal_1",
      "title": "string",
      "why_now": "string",
      "experiment_outline": "string",
      "readouts": ["string"]
    }}
  ],
  "success_criteria": ["string"],
  "next_decisions": ["string"]
}}
"""
    try:
        return ProposalArtifact.model_validate(await _run_json_stage(prompt, "execution_proposals"))
    except Exception:
        return _fallback_proposals(project, request, work_template)


def _merge_gaps(existing: List[ResearchGap], evidence: EvidenceArtifact) -> List[ResearchGap]:
    rows = list(existing)
    seen = {item.theme.strip().lower(): item for item in rows if item.theme.strip()}
    question_pool = evidence.unresolved_questions or ["State the remaining unresolved transfer question."]
    topic_pool = evidence.high_attention_topics or ["Transfer assumptions"]
    pattern_pool = evidence.strongest_patterns or ["Preserve the strongest recurring strategy patterns."]

    for index, topic in enumerate(topic_pool[:5], start=1):
        theme = topic.strip() or f"Gap {index}"
        key = theme.lower()
        if key in seen:
            continue
        next_question = question_pool[min(index - 1, len(question_pool) - 1)]
        rows.append(
            ResearchGap(
                id=f"gap_exec_{index}",
                theme=theme,
                supporting_signals=_clean_lines(pattern_pool, 4),
                next_question=next_question,
                priority_note="Execution emphasized this topic because it is high leverage or repeatedly signaled.",
            )
        )
        seen[key] = rows[-1]
    return rows[:6]


def _merge_validation_tracks(existing: List[ValidationTrack], validation: ValidationArtifact) -> List[ValidationTrack]:
    rows = list(existing)
    seen = {item.target.strip().lower(): item for item in rows if item.target.strip()}
    for item in validation.validation_tracks:
        key = item.target.strip().lower()
        if not key or key in seen:
            continue
        rows.append(item)
        seen[key] = item
    return rows[:6]


def _merge_proposals(existing: List[ProposalCandidate], proposals: ProposalArtifact) -> List[ProposalCandidate]:
    rows = list(existing)
    seen = {item.title.strip().lower(): item for item in rows if item.title.strip()}
    for item in proposals.proposal_candidates:
        key = item.title.strip().lower()
        if not key or key in seen:
            continue
        rows.append(item)
        seen[key] = item
    return rows[:6]


def _merge_literature_findings(existing: List[ResearchFinding], enrichment: ToolEnrichmentArtifact) -> List[ResearchFinding]:
    rows = list(existing)
    incoming = list(enrichment.literature_findings)

    for index, item in enumerate(rows):
        if not incoming:
            break
        if item.citation.strip():
            continue
        candidate = incoming.pop(0)
        rows[index] = ResearchFinding(
            id=item.id,
            citation=candidate.citation,
            labels=candidate.labels or item.labels,
            knowns=candidate.knowns or item.knowns,
            unknowns=candidate.unknowns or item.unknowns,
            relevance=candidate.relevance or item.relevance,
        )

    seen = {item.citation.strip().lower(): item for item in rows if item.citation.strip()}
    for item in incoming:
        key = item.citation.strip().lower()
        if not key or key in seen:
            continue
        rows.append(item)
        seen[key] = item
        if len(rows) >= 6:
            break

    return rows[:6]


def _merge_judgment_calls(existing: List[JudgmentCall], enrichment: ToolEnrichmentArtifact) -> List[JudgmentCall]:
    rows = list(existing)
    seen = {item.stance.strip().lower(): item for item in rows if item.stance.strip()}

    for stance in enrichment.boundary_conditions:
        key = stance.strip().lower()
        if not key or key in seen:
            continue
        rows.append(
            JudgmentCall(
                id=f"boundary_{len(rows) + 1}",
                stance=stance.strip(),
                rationale="Boundary condition proposed during tool-assisted execution.",
                implication="Preserve this constraint when selecting citations, validation work, and proposal scope.",
            )
        )
        seen[key] = rows[-1]
        if len(rows) >= 6:
            return rows[:6]

    for item in enrichment.judgment_calls:
        key = item.stance.strip().lower()
        if not key or key in seen:
            continue
        rows.append(item)
        seen[key] = item
        if len(rows) >= 6:
            break

    return rows[:6]


def _merge_work_template(
    work_template: ResearchWorkTemplate,
    request: StartProjectExecutionRequest,
    enrichment: ToolEnrichmentArtifact,
    scope: ScopeArtifact,
    evidence: EvidenceArtifact,
    validation: ValidationArtifact,
    proposals: ProposalArtifact,
) -> ResearchWorkTemplate:
    synthesis_parts = _clean_lines(
        [
            work_template.synthesis_memo,
            enrichment.summary,
            scope.summary,
            evidence.summary,
            validation.summary,
            proposals.summary,
            request.reasoning_notes or "",
        ],
        10,
    )
    return ResearchWorkTemplate(
        initial_query=work_template.initial_query.strip() or (request.focus_question or "").strip(),
        literature_findings=_merge_literature_findings(work_template.literature_findings, enrichment),
        common_gaps=_merge_gaps(work_template.common_gaps, evidence),
        judgment_calls=_merge_judgment_calls(work_template.judgment_calls, enrichment),
        validation_tracks=_merge_validation_tracks(work_template.validation_tracks, validation),
        proposal_candidates=_merge_proposals(work_template.proposal_candidates, proposals),
        synthesis_memo="\n\n".join(synthesis_parts),
    )


def _fallback_plan(project: dict, request: StartProjectExecutionRequest, scope: ScopeArtifact, evidence: EvidenceArtifact, validation: ValidationArtifact, proposals: ProposalArtifact) -> AgenticPlan:
    focus_question = (request.focus_question or project.get("project_goal") or "the active project question").strip()
    end_product = str(project.get("end_product") or "the target product").strip()
    target_host = str(project.get("target_host") or "the selected host").strip()

    steps = [
        PlanStep(
            id="step_scope",
            title="Lock the execution frame",
            description=f"Translate {focus_question} into a bounded experiment-planning scope for {end_product} in {target_host}.",
            why_this_step="The run should preserve explicit user boundaries before it widens into adjacent methods or claims.",
            objective_link=scope.summary,
            persona_link="Use the selected collaborator lens to decide which technical levers deserve priority.",
            evidence_facts=_clean_lines(scope.leverage_points + scope.boundary_conditions, 5),
            examples=_clean_lines(evidence.transferable_examples, 3),
            dependencies=[],
            expected_outcome="A bounded scope with visible leverage points and explicit exclusions.",
            confidence=0.72,
        ),
        PlanStep(
            id="step_evidence",
            title="Rank the strongest transferable evidence",
            description="Compare the recurring strategy patterns and identify which analog findings are most worth carrying forward.",
            why_this_step="The plan should be grounded in evidence patterns, not just intuitive similarity.",
            objective_link="Carry forward the highest-leverage known strategies while keeping transfer assumptions explicit.",
            persona_link="Match literature signals to the collaborator's workflow stage and project priorities.",
            evidence_facts=_clean_lines(evidence.strongest_patterns + evidence.high_attention_topics, 6),
            examples=_clean_lines(evidence.transferable_examples, 3),
            dependencies=["step_scope"],
            expected_outcome="A ranked evidence stack with visible unresolved transfer risks.",
            confidence=0.7,
        ),
        PlanStep(
            id="step_validation",
            title="Define the validation package",
            description="Specify how enzyme, condition, or analog-transfer claims will be tested before broader execution.",
            why_this_step="The user explicitly wants validation logic, not only literature summarization.",
            objective_link="Make the most important generalization assumptions experimentally observable.",
            persona_link="Use collaborator-specific readouts and methods to keep the package practical.",
            evidence_facts=_clean_lines(validation.recommended_readouts + validation.condition_generalization_checks, 6),
            examples=_clean_lines([item.target for item in validation.validation_tracks], 4),
            dependencies=["step_evidence"],
            expected_outcome="A minimal validation design with measurable success signals.",
            confidence=0.74,
        ),
        PlanStep(
            id="step_proposals",
            title="Draft proposal candidates",
            description="Turn the strongest evidence and validation logic into concrete proposal candidates and experiment outlines.",
            why_this_step="This is the point where the workflow becomes directly useful for project execution.",
            objective_link="Convert synthesis into editable experiment proposals instead of ending at analysis.",
            persona_link="Keep the proposals aligned with the collaborator's stage and decision style.",
            evidence_facts=_clean_lines(proposals.success_criteria + proposals.next_decisions, 6),
            examples=_clean_lines([item.title for item in proposals.proposal_candidates], 4),
            dependencies=["step_validation"],
            expected_outcome="A shortlist of proposals that can be discussed or selected for the next cycle.",
            confidence=0.76,
        ),
        PlanStep(
            id="step_gates",
            title="Set decision gates and follow-on branches",
            description="Define what results would justify advancing, revising, or stopping the proposed experiments.",
            why_this_step="The workflow should change the next decision, not only produce a polished narrative.",
            objective_link="Tie each proposal to a clear success threshold and next branch.",
            persona_link="Make the decision logic explicit so the collaborator can edit it before execution.",
            evidence_facts=_clean_lines(
                [item.success_signal for item in validation.validation_tracks] + proposals.success_criteria,
                6,
            ),
            examples=_clean_lines(proposals.next_decisions, 4),
            dependencies=["step_proposals"],
            expected_outcome="A decision-ready experiment plan with go/no-go logic.",
            confidence=0.73,
        ),
    ]

    return AgenticPlan(
        plan_title=f"Agentic execution draft for {end_product}",
        strategy_summary=(
            f"Use the existing literature findings, user judgments, and validation logic to turn {focus_question} into a bounded experiment plan."
        ),
        success_criteria=_clean_lines(proposals.success_criteria + validation.recommended_readouts, 6),
        assumptions=_clean_lines(scope.open_dependencies + evidence.unresolved_questions, 6),
        risks=[
            PlanRisk(
                risk="Transfer assumptions from similar compounds or conditions may fail in the target case.",
                mitigation="State each transfer assumption explicitly and include at least one validation track that can falsify it early.",
            ),
            PlanRisk(
                risk="A better-looking enzyme variant could reflect expression artifacts instead of genuinely better function.",
                mitigation="Use readouts that separate activity, side activity, and expression-level effects when possible.",
            ),
        ],
        steps=steps,
    )


async def _generate_final_plan(project: dict, persona: dict, request: StartProjectExecutionRequest, final_template: ResearchWorkTemplate, scope: ScopeArtifact, evidence: EvidenceArtifact, validation: ValidationArtifact, proposals: ProposalArtifact) -> AgenticPlan:
    augmented_reasoning = "\n".join(
        part
        for part in [
            request.reasoning_notes or "",
            f"Execution scope summary: {scope.summary}",
            "Prioritized targets: " + (", ".join(scope.prioritized_targets) or "none"),
            "Evidence patterns: " + (", ".join(evidence.strongest_patterns) or "none"),
            "Unresolved questions: " + (", ".join(evidence.unresolved_questions) or "none"),
            "Validation readouts: " + (", ".join(validation.recommended_readouts) or "none"),
            "Proposal candidates: " + (" | ".join(item.title for item in proposals.proposal_candidates) or "none"),
        ]
        if str(part or "").strip()
    )
    prompt = ollama.get_project_plan_prompt(
        project=project,
        persona_summary=_persona_summary(persona),
        focus_question=request.focus_question,
        notes=request.notes,
        clarifying_answers=request.clarifying_answers,
        reasoning_notes=augmented_reasoning,
        work_template_summary=_work_template_summary(final_template),
    )
    try:
        response_data = await ollama.generate_json_cached(
            cache=db,
            task_type="execution_final_plan",
            prompt=prompt,
            cache_version=1,
            max_retries=2,
            temperature=0.2,
            top_p=0.9,
        )
        raw_plan = response_data.get("plan") if isinstance(response_data, dict) else None
        if raw_plan is None:
            raw_plan = response_data
        return AgenticPlan.model_validate(raw_plan)
    except Exception:
        return _fallback_plan(project, request, scope, evidence, validation, proposals)


def _event_detail_from_payload(summary: str, bullets: List[str]) -> str:
    points = _clean_lines(bullets, 3)
    if not points:
        return summary
    return summary + " " + " ".join(f"- {item}" for item in points)


async def _record_stage(run_id: int, stage_key: str, title: str, detail: str, payload: Dict[str, Any]):
    db.append_project_execution_event(
        run_id=run_id,
        event_type="stage_completed",
        stage_key=stage_key,
        title=title,
        detail=detail,
        payload=payload,
    )


async def run_agentic_execution(
    *,
    run_id: int,
    project: dict,
    persona: dict,
    request: StartProjectExecutionRequest,
):
    work_template = request.work_template or ResearchWorkTemplate(
        initial_query=(request.focus_question or project.get("project_goal") or "").strip()
    )
    try:
        db.update_project_execution_run(run_id, status="running", current_stage="intake", set_started=True)
        db.append_project_execution_event(
            run_id=run_id,
            event_type="run_started",
            stage_key="intake",
            title="Execution started",
            detail="The agentic workflow is now processing the current workspace state.",
            payload={
                "focus_question": (request.focus_question or "").strip(),
                "objective_title": (request.objective_title or "").strip(),
            },
        )

        enrichment = await _derive_tool_enrichment(project, persona, request, work_template)
        db.update_project_execution_run(run_id, current_stage="tool_enrichment")
        await _record_stage(
            run_id,
            "tool_enrichment",
            "Prefilled citations and boundaries",
            _event_detail_from_payload(
                enrichment.summary or "Tool-assisted enrichment completed.",
                [item.citation for item in enrichment.literature_findings] + enrichment.boundary_conditions,
            ),
            enrichment.model_dump(),
        )
        work_template = ResearchWorkTemplate(
            initial_query=work_template.initial_query,
            literature_findings=_merge_literature_findings(work_template.literature_findings, enrichment),
            common_gaps=work_template.common_gaps,
            judgment_calls=_merge_judgment_calls(work_template.judgment_calls, enrichment),
            validation_tracks=work_template.validation_tracks,
            proposal_candidates=work_template.proposal_candidates,
            synthesis_memo="\n\n".join(
                part for part in [work_template.synthesis_memo.strip(), enrichment.summary.strip()] if part.strip()
            ),
        )

        scope = await _derive_scope(project, persona, request, work_template)
        db.update_project_execution_run(run_id, current_stage="scope")
        await _record_stage(
            run_id,
            "scope",
            "Framed execution scope",
            _event_detail_from_payload(scope.summary, scope.prioritized_targets + scope.boundary_conditions),
            scope.model_dump(),
        )

        evidence = await _derive_evidence(project, persona, request, work_template, scope)
        db.update_project_execution_run(run_id, current_stage="evidence")
        await _record_stage(
            run_id,
            "evidence",
            "Synthesized evidence and gaps",
            _event_detail_from_payload(evidence.summary, evidence.strongest_patterns + evidence.unresolved_questions),
            evidence.model_dump(),
        )

        validation = await _derive_validation(project, persona, request, work_template, scope, evidence)
        db.update_project_execution_run(run_id, current_stage="validation")
        await _record_stage(
            run_id,
            "validation",
            "Designed validation package",
            _event_detail_from_payload(validation.summary, validation.recommended_readouts + validation.condition_generalization_checks),
            validation.model_dump(),
        )

        proposals = await _derive_proposals(project, persona, request, work_template, scope, evidence, validation)
        db.update_project_execution_run(run_id, current_stage="proposals")
        await _record_stage(
            run_id,
            "proposals",
            "Drafted proposal candidates",
            _event_detail_from_payload(proposals.summary, [item.title for item in proposals.proposal_candidates] + proposals.next_decisions),
            proposals.model_dump(),
        )

        final_template = _merge_work_template(work_template, request, enrichment, scope, evidence, validation, proposals)
        final_plan = await _generate_final_plan(project, persona, request, final_template, scope, evidence, validation, proposals)

        db.upsert_project_workspace_state(
            project_id=int(project["id"]),
            persona_id=int(request.persona_id),
            focus_question=(request.focus_question or "").strip() or None,
            clarifying_answers=request.clarifying_answers,
            reasoning_notes=(request.reasoning_notes or "").strip() or None,
            work_template=final_template.model_dump(),
            plan=final_plan.model_dump(),
            selected_step_id=final_plan.steps[0].id if final_plan.steps else None,
        )

        summary = proposals.summary or final_plan.strategy_summary
        db.update_project_execution_run(
            run_id,
            status="completed",
            current_stage="completed",
            summary=summary,
            final_work_template=final_template.model_dump(),
            final_plan=final_plan.model_dump(),
            set_finished=True,
        )
        db.append_project_execution_event(
            run_id=run_id,
            event_type="run_completed",
            stage_key="completed",
            title="Execution completed",
            detail="The execution run updated the workspace with an enriched template and a refreshed plan.",
            payload={
                "summary": summary,
                "plan_title": final_plan.plan_title,
                "steps": len(final_plan.steps),
            },
        )
    except Exception as exc:
        db.update_project_execution_run(
            run_id,
            status="failed",
            current_stage="failed",
            error_message=str(exc),
            set_finished=True,
        )
        db.append_project_execution_event(
            run_id=run_id,
            event_type="run_failed",
            stage_key="failed",
            title="Execution failed",
            detail=str(exc),
            payload={"error": str(exc)},
        )


def to_execution_response(run: Optional[dict]) -> Optional[ProjectExecutionRun]:
    if not run:
        return None
    return ProjectExecutionRun(
        id=int(run["id"]),
        project_id=int(run["project_id"]),
        persona_id=int(run["persona_id"]),
        run_kind=str(run.get("run_kind") or "agentic_execution"),
        status=str(run.get("status") or "queued"),
        objective_id=run.get("objective_id"),
        mode_label=run.get("mode_label"),
        focus_question=run.get("focus_question"),
        current_stage=run.get("current_stage"),
        summary=run.get("summary"),
        error_message=run.get("error_message"),
        created_at=run["created_at"],
        updated_at=run["updated_at"],
        started_at=run.get("started_at"),
        finished_at=run.get("finished_at"),
        final_work_template=ResearchWorkTemplate.model_validate(run["final_work_template"]) if run.get("final_work_template") else None,
        final_plan=AgenticPlan.model_validate(run["final_plan"]) if run.get("final_plan") else None,
    )
