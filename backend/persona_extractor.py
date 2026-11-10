import json
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

from models import PersonaPayload
from database import db
from ollama_client import ollama

PERSONA_ROOT = Path(os.getenv("PERSONA_ROOT", "data/personas"))
MAX_TRANSCRIPT_CHARS = int(os.getenv("MAX_TRANSCRIPT_CHARS", "120000"))
CHUNK_SIZE = int(os.getenv("PERSONA_CHUNK_SIZE", "10000"))


def _schema_hint() -> str:
    return (
        "{"
        '"persona_id":"string",'
        '"scope_id":"string",'
        '"role":"string|unknown",'
        '"domain_expertise":{"biotech":"novice|intermediate|expert|unknown","stats":"novice|intermediate|expert|unknown","coding":"novice|intermediate|expert|unknown"},'
        '"goals":["string"],'
        '"constraints":{"time_sensitivity":"low|medium|high|unknown","compliance_posture":"strict|moderate|flexible|unknown","risk_tolerance":"low|medium|high|unknown"},'
        '"preferences":{"output_format":"steps|table|narrative|mixed|unknown","citation_need":"low|medium|high|unknown","verbosity":"low|medium|high|unknown"},'
        '"decision_style":"exploratory|confirmatory|production|unknown",'
        '"trust_profile":{"default_reliance":"low|medium|high|unknown","verification_habits":["string"]},'
        '"taboo_or_redlines":["string"],'
        '"key_quotes":[{"quote":"string","interview_id":1}],'
        '"evidence":{"support":[{"claim":"string","interview_id":1,"span_hint":"string"}]}'
        "}"
    )


def _compose_transcripts(interviews: List[Dict[str, Any]], max_chars: int) -> str:
    parts: List[str] = []
    used = 0
    print(f"DEBUG: Composing transcripts with max {max_chars} chars from {len(interviews)} interviews")
    for item in interviews:
        text = item.get("transcript_text") or ""
        if not text and item.get("transcript_path"):
            path = Path(item["transcript_path"])
            if path.exists() and path.is_file():
                text = path.read_text(encoding="utf-8", errors="replace")
        block = f"[interview_id={item['id']}]\n{text}\n"
        if used + len(block) > max_chars:
            remaining = max_chars - used
            if remaining <= 0:
                break
            block = block[:remaining]
        parts.append(block)
        used += len(block)
    return "\n".join(parts)


def _chunk_text(text: str, chunk_size: int) -> List[str]:
    if len(text) <= chunk_size:
        return [text]
    chunks = []
    idx = 0
    while idx < len(text):
        chunks.append(text[idx : idx + chunk_size])
        idx += chunk_size
    return chunks


async def _extract_fragment(scope_id: str, persona_name: str, chunk: str, chunk_index: int) -> Dict[str, Any]:
    prompt = (
        "SYSTEM:\n"
        "You extract a user persona from interview transcripts. "
        "Output MUST be valid JSON matching the schema. Use only evidence from transcripts; if unknown, use 'unknown'.\n\n"
        "USER:\n"
        f"Schema: {_schema_hint()}\n"
        f"persona_id should be an internal slug and scope_id should be '{scope_id}'.\n"
        f"Persona name: {persona_name}\n"
        f"Transcript chunk index: {chunk_index}\n"
        "Transcripts:\n"
        f"{chunk}\n\n"
        "Return JSON only."
    )
    return await ollama.generate_json_cached(
        cache=db,
        task_type="persona_fragment_extraction",
        prompt=prompt,
        cache_version=1,
        cache_inputs={"scope_id": scope_id, "chunk_index": chunk_index},
        max_retries=2,
        temperature=0.7,
        top_p=0.9,
    )


async def _merge_fragments(scope_id: str, persona_name: str, fragments: List[Dict[str, Any]]) -> Dict[str, Any]:
    prompt = (
        "SYSTEM:\n"
        "Merge persona JSON fragments into one final persona JSON that matches schema exactly. "
        "Preserve evidence provenance via interview_id.\n\n"
        "USER:\n"
        f"Schema: {_schema_hint()}\n"
        f"scope_id must be '{scope_id}'.\n"
        f"Persona name: {persona_name}\n"
        "Fragments:\n"
        f"{json.dumps(fragments)}\n\n"
        "Return JSON only."
    )
    return await ollama.generate_json_cached(
        cache=db,
        task_type="persona_fragment_merge",
        prompt=prompt,
        cache_version=1,
        cache_inputs={"scope_id": scope_id, "fragment_count": len(fragments)},
        max_retries=2,
        temperature=0.7,
        top_p=0.9,
    )


def build_persona_summary(persona: PersonaPayload) -> str:
    goals = "; ".join(persona.goals[:3]) if persona.goals else "unknown goals"
    redlines = "; ".join(persona.taboo_or_redlines[:2]) if persona.taboo_or_redlines else "none"
    habits = "; ".join(persona.trust_profile.verification_habits[:2]) if persona.trust_profile.verification_habits else "none"
    workflow_stage = persona.workflow_stage or "general"
    workflow_focus = "; ".join(persona.workflow_focus[:3]) if persona.workflow_focus else "general workflow support"
    project_goal = ""
    if isinstance(persona.project_context, dict):
        project_goal = str(persona.project_context.get("project_goal") or "").strip()
    summary = (
        f"Role: {persona.role}. "
        f"Workflow stage: {workflow_stage}. "
        f"Expertise biotech/stats/coding: {persona.domain_expertise.biotech}/{persona.domain_expertise.stats}/{persona.domain_expertise.coding}. "
        f"Decision style: {persona.decision_style}. "
        f"Constraints: time={persona.constraints.time_sensitivity}, compliance={persona.constraints.compliance_posture}, risk={persona.constraints.risk_tolerance}. "
        f"Preferences: format={persona.preferences.output_format}, citations={persona.preferences.citation_need}, verbosity={persona.preferences.verbosity}. "
        f"Workflow focus: {workflow_focus}. "
        f"Goals: {goals}. "
        f"Verification habits: {habits}. "
        f"Redlines: {redlines}."
    )
    if project_goal:
        summary += f" Program goal: {project_goal}."
    return summary[:1200]


async def extract_persona_from_interviews(
    scope_id: str,
    persona_name: str,
    interviews: List[Dict[str, Any]],
) -> Tuple[Dict[str, Any], str, List[Dict[str, Any]]]:
    transcript_text = _compose_transcripts(interviews, MAX_TRANSCRIPT_CHARS)
    if not transcript_text.strip():
        raise ValueError("No interview transcript text available for extraction")

    chunks = _chunk_text(transcript_text, CHUNK_SIZE)
    fragments: List[Dict[str, Any]] = []
    for idx, chunk in enumerate(chunks):
        fragment = await _extract_fragment(scope_id, persona_name, chunk, idx)
        fragments.append(fragment)

    if len(fragments) == 1:
        merged = fragments[0]
    else:
        merged = await _merge_fragments(scope_id, persona_name, fragments)

    payload = PersonaPayload.model_validate(merged)
    summary = build_persona_summary(payload)
    return payload.model_dump(), summary, fragments


def save_persona_snapshot(persona_id: int, payload: Dict[str, Any], fragments: List[Dict[str, Any]]):
    PERSONA_ROOT.mkdir(parents=True, exist_ok=True)
    snapshot_path = PERSONA_ROOT / f"{persona_id}.json"
    snapshot_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    fragment_dir = PERSONA_ROOT / "fragments" / str(persona_id)
    fragment_dir.mkdir(parents=True, exist_ok=True)
    for idx, fragment in enumerate(fragments):
        (fragment_dir / f"fragment_{idx}.json").write_text(json.dumps(fragment, indent=2), encoding="utf-8")


def _merge_unique_strings(existing: List[str], incoming: List[str], max_items: int = 50) -> List[str]:
    out: List[str] = []
    seen = set()
    for item in [*existing, *incoming]:
        normalized = (item or "").strip()
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(normalized)
        if len(out) >= max_items:
            break
    return out


def _pick_enum(existing: str, incoming: str, ordered: List[str]) -> str:
    existing = existing or "unknown"
    incoming = incoming or "unknown"
    if existing == "unknown" and incoming != "unknown":
        return incoming
    if incoming == "unknown":
        return existing
    if existing not in ordered or incoming not in ordered:
        return existing
    return ordered[max(ordered.index(existing), ordered.index(incoming))]


def merge_persona_payloads(existing_payload: Dict[str, Any], incoming_payload: Dict[str, Any]) -> Dict[str, Any]:
    existing = PersonaPayload.model_validate(existing_payload)
    incoming = PersonaPayload.model_validate(incoming_payload)

    merged = {
        "persona_id": existing.persona_id or incoming.persona_id,
        "scope_id": existing.scope_id or incoming.scope_id,
        "role": existing.role if existing.role and existing.role != "unknown" else incoming.role,
        "domain_expertise": {
            "biotech": _pick_enum(existing.domain_expertise.biotech or "unknown", incoming.domain_expertise.biotech or "unknown", ["unknown", "novice", "intermediate", "expert"]),
            "stats": _pick_enum(existing.domain_expertise.stats or "unknown", incoming.domain_expertise.stats or "unknown", ["unknown", "novice", "intermediate", "expert"]),
            "coding": _pick_enum(existing.domain_expertise.coding or "unknown", incoming.domain_expertise.coding or "unknown", ["unknown", "novice", "intermediate", "expert"]),
        },
        "goals": _merge_unique_strings(existing.goals, incoming.goals, max_items=20),
        "constraints": {
            "time_sensitivity": _pick_enum(existing.constraints.time_sensitivity or "unknown", incoming.constraints.time_sensitivity or "unknown", ["unknown", "low", "medium", "high"]),
            "compliance_posture": _pick_enum(existing.constraints.compliance_posture or "unknown", incoming.constraints.compliance_posture or "unknown", ["unknown", "flexible", "moderate", "strict"]),
            "risk_tolerance": _pick_enum(existing.constraints.risk_tolerance or "unknown", incoming.constraints.risk_tolerance or "unknown", ["unknown", "low", "medium", "high"]),
        },
        "preferences": {
            "output_format": existing.preferences.output_format if existing.preferences.output_format and existing.preferences.output_format != "unknown" else incoming.preferences.output_format,
            "citation_need": _pick_enum(existing.preferences.citation_need or "unknown", incoming.preferences.citation_need or "unknown", ["unknown", "low", "medium", "high"]),
            "verbosity": _pick_enum(existing.preferences.verbosity or "unknown", incoming.preferences.verbosity or "unknown", ["unknown", "low", "medium", "high"]),
        },
        "decision_style": existing.decision_style if existing.decision_style and existing.decision_style != "unknown" else incoming.decision_style,
        "trust_profile": {
            "default_reliance": _pick_enum(existing.trust_profile.default_reliance or "unknown", incoming.trust_profile.default_reliance or "unknown", ["unknown", "low", "medium", "high"]),
            "verification_habits": _merge_unique_strings(existing.trust_profile.verification_habits, incoming.trust_profile.verification_habits, max_items=20),
        },
        "taboo_or_redlines": _merge_unique_strings(existing.taboo_or_redlines, incoming.taboo_or_redlines, max_items=20),
        "key_quotes": [],
        "evidence": {"support": []},
        "workflow_stage": existing.workflow_stage if existing.workflow_stage and existing.workflow_stage != "general" else incoming.workflow_stage,
        "workflow_focus": _merge_unique_strings(existing.workflow_focus, incoming.workflow_focus, max_items=12),
        "project_context": {
            **(incoming.project_context or {}),
            **(existing.project_context or {}),
        },
    }

    quote_seen = set()
    for quote in [*existing.key_quotes, *incoming.key_quotes]:
        key = (quote.quote.strip().lower(), quote.interview_id)
        if key in quote_seen:
            continue
        quote_seen.add(key)
        merged["key_quotes"].append({"quote": quote.quote, "interview_id": quote.interview_id})
        if len(merged["key_quotes"]) >= 5:
            break

    existing_support = existing.evidence.get("support", [])
    incoming_support = incoming.evidence.get("support", [])
    support_seen = set()
    for support in [*existing_support, *incoming_support]:
        claim = support.claim.strip() if hasattr(support, "claim") else str(support.get("claim", "")).strip()
        interview_id = support.interview_id if hasattr(support, "interview_id") else int(support.get("interview_id", 0))
        span_hint = support.span_hint if hasattr(support, "span_hint") else support.get("span_hint")
        key = (claim.lower(), interview_id, (span_hint or "").strip().lower())
        if not claim or key in support_seen:
            continue
        support_seen.add(key)
        merged["evidence"]["support"].append({
            "claim": claim,
            "interview_id": interview_id,
            "span_hint": span_hint,
        })
        if len(merged["evidence"]["support"]) >= 15:
            break

    validated = PersonaPayload.model_validate(merged)
    return validated.model_dump()
