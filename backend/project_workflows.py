from __future__ import annotations

import os
from copy import deepcopy
from typing import Any, Dict, Iterable, List

from database import db
from models import PersonaPayload
from ollama_client import ollama
from persona_extractor import build_persona_summary


_FALLBACK_WORKFLOW_PERSONAS: List[Dict[str, Any]] = [
    {
        "name": "Feedstock and Sourcing Strategist",
        "workflow_stage": "feedstock",
        "focus_area": "Raw material strategy and low-cost carbon input selection",
        "starter_questions": [
            "Which carbon sources and co-feeds can lower cost without hurting downstream biology?",
            "What regional sourcing risks or by-product opportunities should we account for first?",
        ],
        "role": "process_strategy_lead",
        "workflow_focus": [
            "Cost-efficient carbon sources",
            "By-product valorization options",
            "Upstream sourcing risk",
        ],
        "goals": [
            "Map the cheapest feasible feedstock options for {end_product}",
            "Identify procurement risks before strain work scales up",
            "Align sourcing choices with fermentation performance constraints",
        ],
    },
    {
        "name": "Strain Design Lead",
        "workflow_stage": "strain_engineering",
        "focus_area": "Pathway design, host engineering, and bottleneck prioritization",
        "starter_questions": [
            "Which pathway bottlenecks are most likely to cap {end_product} titers in {target_host}?",
            "What genetic interventions should be prioritized before optimizing fermentation conditions?",
        ],
        "role": "metabolic_engineer",
        "workflow_focus": [
            "Pathway bottleneck ranking",
            "Enzyme and host engineering",
            "Experimental design",
        ],
        "goals": [
            "Design a host strain roadmap for {end_product} in {target_host}",
            "Sequence edits from highest-leverage bottlenecks to lower-leverage polish work",
            "Preserve experimental learnings in a reusable hypothesis queue",
        ],
    },
    {
        "name": "Fermentation Process Engineer",
        "workflow_stage": "upstream_process",
        "focus_area": "Bioreactor strategy, media design, and operating envelope definition",
        "starter_questions": [
            "What fermentation levers matter most after the first viable strain exists?",
            "Which process variables should be screened early for {end_product} in {target_host}?",
        ],
        "role": "bioprocess_engineer",
        "workflow_focus": [
            "Media and feed strategy",
            "Critical process parameters",
            "Scale-up readiness",
        ],
        "goals": [
            "Translate strain hypotheses into a scalable fermentation plan",
            "Identify the minimum viable DOE to improve titer, rate, and yield",
            "Flag operating risks before pilot-scale decisions",
        ],
    },
    {
        "name": "Downstream Recovery Lead",
        "workflow_stage": "downstream_processing",
        "focus_area": "Product recovery, purification tradeoffs, and formulation readiness",
        "starter_questions": [
            "Where will the hardest separation or purification pain points likely show up?",
            "How should recovery strategy influence upstream process decisions early?",
        ],
        "role": "downstream_process_lead",
        "workflow_focus": [
            "Separation bottlenecks",
            "Purity-cost tradeoffs",
            "Integration with upstream decisions",
        ],
        "goals": [
            "Anticipate recovery constraints for {end_product} before they become expensive surprises",
            "Choose purification routes that match product purity requirements",
            "Connect downstream burden back to upstream design choices",
        ],
    },
    {
        "name": "Literature and Benchmark Analyst",
        "workflow_stage": "analytics",
        "focus_area": "Literature synthesis, benchmark mapping, and open-question framing",
        "starter_questions": [
            "What are the most successful reported strategies and benchmark examples for {end_product} production?",
            "Which open questions, improvement levers, or recurring bottlenecks show up across recent work?",
        ],
        "role": "scientific_intelligence_analyst",
        "workflow_focus": [
            "Literature synthesis",
            "Benchmark examples",
            "Open question mapping",
        ],
        "goals": [
            "Summarize the strongest published strategies and examples for {end_product}",
            "Distill recurring bottlenecks and unresolved questions from the literature",
            "Turn evidence synthesis into the next set of editable project decisions",
        ],
    },
    {
        "name": "Techno-Economic Analyst",
        "workflow_stage": "economics",
        "focus_area": "Program economics, milestone gating, and commercial feasibility",
        "starter_questions": [
            "What assumptions dominate the economics of {end_product} production first?",
            "Which milestones should gate further investment in this program?",
        ],
        "role": "techno_economic_analyst",
        "workflow_focus": [
            "Cost drivers",
            "Scenario and sensitivity analysis",
            "Investment gating decisions",
        ],
        "goals": [
            "Translate technical choices into cost and margin implications",
            "Make milestone gates explicit for the program team",
            "Expose which assumptions most change commercial viability",
        ],
    },
]

_WORKFLOW_STAGES = {
    "feedstock",
    "strain_engineering",
    "upstream_process",
    "downstream_processing",
    "economics",
    "regulatory_quality",
    "analytics",
    "general",
}
_LEVELS = {"novice", "intermediate", "expert", "unknown"}
_SENSITIVITY = {"low", "medium", "high", "unknown"}
_COMPLIANCE = {"flexible", "moderate", "strict", "unknown"}
_FORMATS = {"steps", "table", "narrative", "mixed", "unknown"}
_DECISIONS = {"exploratory", "confirmatory", "production", "unknown"}
_RELIANCE = {"low", "medium", "high", "unknown"}


def _slugify(value: str) -> str:
    return "-".join(part for part in "".join(ch.lower() if ch.isalnum() else "-" for ch in value).split("-") if part) or "item"


def _pick_enum(value: Any, allowed: set[str], default: str) -> str:
    candidate = str(value or "").strip().lower()
    return candidate if candidate in allowed else default


def _clean_strings(values: Iterable[Any], limit: int) -> List[str]:
    out: List[str] = []
    seen = set()
    for value in values:
        text = str(value or "").strip()
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


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _project_context(
    project_name: str,
    end_product: str,
    target_host: str,
    project_goal: str,
    raw_material_focus: str,
    notes: str,
) -> Dict[str, Any]:
    return {
        "project_name": project_name,
        "end_product": end_product,
        "target_host": target_host,
        "project_goal": project_goal,
        "raw_material_focus": raw_material_focus,
        "notes": notes,
    }


def _materialize_persona(
    raw: Dict[str, Any],
    *,
    index: int,
    project_slug: str,
    scope_id: str,
    context: Dict[str, Any],
    default_name: str,
    default_stage: str,
    dynamic_generation: bool,
) -> Dict[str, Any]:
    name = str(raw.get("name") or default_name).strip() or default_name
    workflow_stage = _pick_enum(raw.get("workflow_stage"), _WORKFLOW_STAGES, default_stage)
    focus_area = str(raw.get("focus_area") or "").strip() or f"Advance the {workflow_stage.replace('_', ' ')} workstream."
    starter_questions = _clean_strings(raw.get("starter_questions") or [], 3)
    workflow_focus = _clean_strings(raw.get("workflow_focus") or [], 4) or [focus_area]
    goals = _clean_strings(raw.get("goals") or [], 4) or [focus_area]
    taboo = _clean_strings(raw.get("taboo_or_redlines") or [], 4)
    habits = _clean_strings(((raw.get("trust_profile") or {}).get("verification_habits") or []), 4)

    payload = {
        "persona_id": f"{project_slug}-{index:02d}-{_slugify(name)}",
        "scope_id": scope_id,
        "role": str(raw.get("role") or "workflow_partner").strip() or "workflow_partner",
        "domain_expertise": {
            "biotech": _pick_enum((raw.get("domain_expertise") or {}).get("biotech"), _LEVELS, "intermediate"),
            "stats": _pick_enum((raw.get("domain_expertise") or {}).get("stats"), _LEVELS, "intermediate"),
            "coding": _pick_enum((raw.get("domain_expertise") or {}).get("coding"), _LEVELS, "unknown"),
        },
        "goals": goals,
        "constraints": {
            "time_sensitivity": _pick_enum((raw.get("constraints") or {}).get("time_sensitivity"), _SENSITIVITY, "medium"),
            "compliance_posture": _pick_enum((raw.get("constraints") or {}).get("compliance_posture"), _COMPLIANCE, "moderate"),
            "risk_tolerance": _pick_enum((raw.get("constraints") or {}).get("risk_tolerance"), _SENSITIVITY, "medium"),
        },
        "preferences": {
            "output_format": _pick_enum((raw.get("preferences") or {}).get("output_format"), _FORMATS, "mixed"),
            "citation_need": _pick_enum((raw.get("preferences") or {}).get("citation_need"), _SENSITIVITY, "medium"),
            "verbosity": _pick_enum((raw.get("preferences") or {}).get("verbosity"), _SENSITIVITY, "medium"),
        },
        "decision_style": _pick_enum(raw.get("decision_style"), _DECISIONS, "production"),
        "trust_profile": {
            "default_reliance": _pick_enum((raw.get("trust_profile") or {}).get("default_reliance"), _RELIANCE, "medium"),
            "verification_habits": habits,
        },
        "taboo_or_redlines": taboo,
        "key_quotes": [],
        "evidence": {"support": []},
        "workflow_stage": workflow_stage,
        "workflow_focus": workflow_focus,
        "project_context": {
            **context,
            "focus_area": focus_area,
            "starter_questions": starter_questions,
            "dynamic_generation": dynamic_generation,
        },
    }

    validated = PersonaPayload.model_validate(payload)
    return {
        "name": name,
        "identity_key": f"project-workflow:{scope_id}:{index:02d}:{_slugify(name)}",
        "payload": validated.model_dump(),
        "summary": build_persona_summary(validated),
    }


def _fallback_personas(
    *,
    project_name: str,
    scope_id: str,
    end_product: str,
    target_host: str,
    project_goal: str,
    raw_material_focus: str,
    notes: str,
) -> List[Dict[str, Any]]:
    context = _project_context(project_name, end_product, target_host, project_goal, raw_material_focus, notes)
    project_slug = _slugify(project_name)
    personas: List[Dict[str, Any]] = []

    for index, spec in enumerate(_FALLBACK_WORKFLOW_PERSONAS, start=1):
        raw = deepcopy(spec)
        raw["goals"] = [
            goal.format(end_product=end_product, target_host=target_host)
            for goal in raw.get("goals", [])
        ]
        raw["starter_questions"] = [
            question.format(end_product=end_product, target_host=target_host)
            for question in raw.get("starter_questions", [])
        ]
        personas.append(
            _materialize_persona(
                raw,
                index=index,
                project_slug=project_slug,
                scope_id=scope_id,
                context=context,
                default_name=spec["name"],
                default_stage=spec["workflow_stage"],
                dynamic_generation=False,
            )
        )

    return personas


async def build_project_personas(
    *,
    project_name: str,
    scope_id: str,
    end_product: str,
    target_host: str,
    project_goal: str,
    raw_material_focus: str,
    notes: str,
) -> List[Dict[str, Any]]:
    context = _project_context(project_name, end_product, target_host, project_goal, raw_material_focus, notes)
    project_slug = _slugify(project_name)
    persona_model = os.getenv("OLLAMA_PERSONA_MODEL") or os.getenv("OLLAMA_SOTA_MODEL") or ollama.model
    cache_inputs = {
        "version": 1,
        "model": persona_model,
        "project_name": project_name.strip(),
        "end_product": end_product.strip(),
        "target_host": target_host.strip(),
        "project_goal": project_goal.strip(),
        "raw_material_focus": raw_material_focus.strip(),
        "notes": notes.strip(),
    }
    cache_key = db.llm_cache_key("project_personas", cache_inputs)

    cached = db.get_llm_cache(cache_key)
    raw_personas = (cached or {}).get("payload", {}).get("personas") if cached else None
    if isinstance(raw_personas, list):
        personas: List[Dict[str, Any]] = []
        for index, raw in enumerate(raw_personas[:6], start=1):
            if not isinstance(raw, dict):
                continue
            personas.append(
                _materialize_persona(
                    raw,
                    index=index,
                    project_slug=project_slug,
                    scope_id=scope_id,
                    context=context,
                    default_name=f"{project_name} Workflow Persona {index}",
                    default_stage="general",
                    dynamic_generation=True,
                )
            )
        if len(personas) >= 4:
            return personas

    if os.getenv("OLLAMA_PROJECT_PERSONAS_ENABLED", "1") == "0":
        return _fallback_personas(
            project_name=project_name,
            scope_id=scope_id,
            end_product=end_product,
            target_host=target_host,
            project_goal=project_goal,
            raw_material_focus=raw_material_focus,
            notes=notes,
        )

    try:
        response = await ollama.generate_json(
            ollama.get_project_persona_generation_prompt(
                project={
                    "name": project_name,
                    "end_product": end_product,
                    "target_host": target_host,
                    "project_goal": project_goal,
                    "raw_material_focus": raw_material_focus,
                    "notes": notes,
                }
            ),
            max_retries=0,
            temperature=0.2,
            top_p=0.9,
            model=persona_model,
            timeout_seconds=_env_float("OLLAMA_PROJECT_PERSONA_TIMEOUT_SECONDS", 20.0),
        )
        raw_personas = response.get("personas") if isinstance(response, dict) else None
        if isinstance(raw_personas, list):
            personas: List[Dict[str, Any]] = []
            for index, raw in enumerate(raw_personas[:6], start=1):
                if not isinstance(raw, dict):
                    continue
                personas.append(
                    _materialize_persona(
                        raw,
                        index=index,
                        project_slug=project_slug,
                        scope_id=scope_id,
                        context=context,
                        default_name=f"{project_name} Workflow Persona {index}",
                        default_stage="general",
                        dynamic_generation=True,
                    )
                )
            if len(personas) >= 4:
                db.upsert_llm_cache(
                    cache_key=cache_key,
                    task_type="project_personas",
                    model=persona_model,
                    payload={"personas": raw_personas[:6]},
                    metadata={"source": "ollama"},
                )
                return personas
    except Exception:
        pass

    return _fallback_personas(
        project_name=project_name,
        scope_id=scope_id,
        end_product=end_product,
        target_host=target_host,
        project_goal=project_goal,
        raw_material_focus=raw_material_focus,
        notes=notes,
    )
