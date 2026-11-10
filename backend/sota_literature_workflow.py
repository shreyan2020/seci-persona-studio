from __future__ import annotations

import json
import math
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

from models import FetchProjectLiteratureRequest, ResearchFinding, WorkflowStageTrace
from ollama_client import ollama
from research_tools import (
    _literature_relevance_profile,
    _literature_relevance_score,
    _merge_record,
    _record_key,
    _unique_in_order,
    search_crossref,
    search_openalex,
    search_pubmed,
    search_semantic_scholar,
)


class WorkflowError(Exception):
    def __init__(self, stage: str, message: str, trace: List[WorkflowStageTrace]):
        super().__init__(message)
        self.stage = stage
        self.trace = trace


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _compact(value: Any, *, max_chars: int = 1800) -> Any:
    if isinstance(value, dict):
        return {str(key): _compact(item, max_chars=max_chars) for key, item in value.items()}
    if isinstance(value, list):
        return [_compact(item, max_chars=max_chars) for item in value[:40]]
    if isinstance(value, str):
        cleaned = re.sub(r"\s+", " ", value).strip()
        return cleaned[: max_chars - 3].rstrip() + "..." if len(cleaned) > max_chars else cleaned
    return value


class WorkflowTraceLogger:
    def __init__(self, run_id: Optional[str] = None):
        self.run_id = run_id or f"sota_lit_{uuid.uuid4().hex[:12]}"
        self.trace: List[WorkflowStageTrace] = []
        self.log_path = Path(os.getenv("SOTA_WORKFLOW_LOG_PATH", "data/workflow_logs/literature_workflow.jsonl"))

    def start(self, stage: str, *, inputs: Optional[Dict[str, Any]] = None) -> int:
        item = WorkflowStageTrace(
            run_id=self.run_id,
            stage=stage,
            started_at=_utc_now(),
            inputs=_compact(inputs or {}),
        )
        self.trace.append(item)
        return len(self.trace) - 1

    def end(
        self,
        index: int,
        *,
        status: str = "success",
        message: str = "",
        outputs: Optional[Dict[str, Any]] = None,
        errors: Optional[List[str]] = None,
    ) -> WorkflowStageTrace:
        item = self.trace[index]
        ended_at = _utc_now()
        started = datetime.fromisoformat(item.started_at) if item.started_at else datetime.now(timezone.utc)
        ended = datetime.fromisoformat(ended_at)
        updated = item.model_copy(
            update={
                "status": status,
                "message": message,
                "ended_at": ended_at,
                "duration_ms": round((ended - started).total_seconds() * 1000, 2),
                "outputs": _compact(outputs or {}),
                "errors": [str(error) for error in (errors or []) if str(error).strip()],
            }
        )
        self.trace[index] = updated
        self._write(updated)
        return updated

    def record(
        self,
        stage: str,
        *,
        status: str,
        message: str = "",
        inputs: Optional[Dict[str, Any]] = None,
        outputs: Optional[Dict[str, Any]] = None,
        errors: Optional[List[str]] = None,
    ) -> WorkflowStageTrace:
        index = self.start(stage, inputs=inputs)
        return self.end(index, status=status, message=message, outputs=outputs, errors=errors)

    def fail(self, index: int, stage: str, message: str, exc: Exception) -> None:
        self.end(index, status="error", message=message, errors=[str(exc)])
        raise WorkflowError(stage, f"{message}: {exc}", self.trace) from exc

    def _write(self, item: WorkflowStageTrace) -> None:
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(item.model_dump(), ensure_ascii=False) + "\n")
        except Exception:
            # Logging must never change workflow semantics. The trace is still returned.
            return


def _request_user_inputs(request: FetchProjectLiteratureRequest, project: Dict[str, Any]) -> List[str]:
    return [
        str(request.project_end_product or project.get("end_product") or ""),
        str(request.project_target_host or project.get("target_host") or ""),
        " ".join(f"{question}: {answer}" for question, answer in (request.clarifying_answers or {}).items() if str(answer).strip()),
        " ".join(f"{question}: {answer}" for question, answer in (request.objective_answers or {}).items() if str(answer).strip()),
        " ".join(f"{question}: {answer}" for question, answer in (request.global_question_answers or {}).items() if str(answer).strip()),
        str(request.reasoning_notes or ""),
        str(project.get("raw_material_focus") or ""),
        str(project.get("notes") or ""),
    ]


def _capability_report() -> Dict[str, Any]:
    return {
        "llm": {
            "provider": "ollama",
            "base_url": getattr(ollama, "base_url", ""),
            "model": getattr(ollama, "model", ""),
            "required": True,
        },
        "pdf_parsing": {
            "grobid_url": os.getenv("GROBID_URL", ""),
            "docling_url": os.getenv("DOCLING_URL", ""),
            "docling_enabled": os.getenv("DOCLING_ENABLED", "0") == "1",
            "required_for_literature_fetch": False,
        },
        "dense_retrieval": {
            "embedding_url": os.getenv("SOTA_EMBEDDING_URL", ""),
            "embedding_model": os.getenv("SOTA_EMBEDDING_MODEL", "") or os.getenv("OLLAMA_EMBEDDING_MODEL", ""),
            "sentence_transformers_model": os.getenv("SOTA_SENTENCE_TRANSFORMERS_MODEL", ""),
            "vector_search_url": os.getenv("SOTA_VECTOR_SEARCH_URL", ""),
            "required_for_literature_fetch": False,
        },
        "reranker": {
            "cross_encoder_url": os.getenv("SOTA_CROSS_ENCODER_URL", ""),
            "llm_reranker_enabled": True,
        },
        "citation_graph": {
            "semantic_scholar_api_key_present": bool(os.getenv("SEMANTIC_SCHOLAR_API_KEY")),
            "semantic_scholar_graph_api": True,
        },
    }


async def _decompose_query(
    *,
    logger: WorkflowTraceLogger,
    project: Dict[str, Any],
    persona: Dict[str, Any],
    request: FetchProjectLiteratureRequest,
    ontology_context: str,
    max_variants: int,
) -> Dict[str, Any]:
    stage = "llm_query_decomposition"
    index = logger.start(
        stage,
        inputs={
            "query": request.query,
            "project_goal": request.project_goal or project.get("project_goal"),
            "objective_title": request.objective_title,
            "variant_target": max_variants,
            "ontology_context_present": bool(ontology_context),
        },
    )
    prompt = f"""
You are formulating scholarly literature searches for a scientific project. Return strict JSON only.

Project goal: {request.project_goal or project.get("project_goal") or project.get("name") or ""}
End product: {request.project_end_product or project.get("end_product") or ""}
Target host/context: {request.project_target_host or project.get("target_host") or ""}
Collaborator/persona: {persona.get("name") or ""}
Objective title: {request.objective_title or ""}
Objective definition: {request.objective_definition or ""}
Objective signals: {json.dumps(request.objective_signals or [], ensure_ascii=False)}
User query: {request.query}
User/project answers: {json.dumps(_request_user_inputs(request, project), ensure_ascii=False)}
Ontology context from the project memory:
{ontology_context or "none"}

Decompose the query into search facets and generate {max_variants} database-ready query variants.
Use concrete domain terms, synonyms, organism/product names, method terms, and review/counterevidence variants.
Do not invent unsupported organisms, genes, products, or user constraints.

Return JSON:
{{
  "intent_summary": "final project goal being served by the search",
  "facets": {{
    "construct": ["domain construct terms"],
    "method": ["method or workflow terms"],
    "domain": ["organism, product, pathway, discipline terms"],
    "outcome": ["evaluation, benchmark, or decision terms"],
    "exclusion": ["terms or scopes to avoid"]
  }},
  "inclusion_criteria": ["criteria used to judge relevant papers"],
  "exclusion_criteria": ["criteria used to reject papers"],
  "query_variants": [
    {{"id": "q1", "type": "exact|broad|method|review|counterevidence|citation_seed|domain_transfer", "query": "search string", "purpose": "why this query exists"}}
  ]
}}
""".strip()
    try:
        payload = await ollama.generate_json(prompt, max_retries=1, temperature=0.15, top_p=0.9)
    except Exception as exc:
        logger.fail(index, stage, "LLM query decomposition failed", exc)

    variants = payload.get("query_variants") if isinstance(payload, dict) else None
    if not isinstance(variants, list):
        exc = ValueError("query_variants must be a list")
        logger.fail(index, stage, "LLM query decomposition returned invalid JSON shape", exc)
    cleaned = []
    seen_queries = set()
    for item in variants:
        if not isinstance(item, dict):
            continue
        query = " ".join(str(item.get("query") or "").split()).strip()
        if len(query) < 4 or query.lower() in seen_queries:
            continue
        seen_queries.add(query.lower())
        cleaned.append(
            {
                "id": str(item.get("id") or f"q{len(cleaned) + 1}").strip(),
                "type": str(item.get("type") or "broad").strip(),
                "query": query,
                "purpose": str(item.get("purpose") or "").strip(),
            }
        )
        if len(cleaned) >= max_variants:
            break
    if len(cleaned) < 3:
        exc = ValueError(f"expected at least 3 usable query variants, got {len(cleaned)}")
        logger.fail(index, stage, "LLM query decomposition did not produce enough usable variants", exc)

    payload["query_variants"] = cleaned
    logger.end(
        index,
        message=f"Generated {len(cleaned)} query variants for literature retrieval.",
        outputs={
            "intent_summary": payload.get("intent_summary"),
            "facets": payload.get("facets") or {},
            "query_variants": cleaned,
            "inclusion_criteria": payload.get("inclusion_criteria") or [],
            "exclusion_criteria": payload.get("exclusion_criteria") or [],
        },
    )
    return payload


def _dedupe_records(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_key: Dict[str, Dict[str, Any]] = {}
    for record in records:
        key = _record_key(record)
        if not key or key == "title:":
            continue
        by_key[key] = _merge_record(by_key[key], record) if key in by_key else record
    return list(by_key.values())


async def _retrieve_source(
    source: str,
    query: str,
    *,
    max_results: int,
    request: FetchProjectLiteratureRequest,
    project: Dict[str, Any],
) -> Dict[str, Any]:
    user_inputs = _request_user_inputs(request, project)
    if source == "pubmed":
        return await search_pubmed(
            query,
            max_results=max_results,
            project_goal=str(request.project_goal or project.get("project_goal") or ""),
            objective_title=request.objective_title or "",
            objective_definition=request.objective_definition or "",
            objective_signals=request.objective_signals or [],
            user_inputs=user_inputs,
        )
    if source == "semantic_scholar":
        return await search_semantic_scholar(query, max_results=max_results)
    if source == "openalex":
        return await search_openalex(query, max_results=max_results)
    if source == "crossref":
        return await search_crossref(query, max_results=max_results)
    raise ValueError(f"unsupported source: {source}")


async def _multi_source_retrieval(
    *,
    logger: WorkflowTraceLogger,
    request: FetchProjectLiteratureRequest,
    project: Dict[str, Any],
    variants: List[Dict[str, Any]],
    max_results: int,
) -> Tuple[List[Dict[str, Any]], Dict[str, int], List[Dict[str, Any]]]:
    stage = "multi_source_retrieval"
    index = logger.start(
        stage,
        inputs={
            "query_variant_count": len(variants),
            "sources": ["pubmed", "semantic_scholar", "openalex", "crossref"],
            "max_results_per_source_query": max_results,
        },
    )
    all_records: List[Dict[str, Any]] = []
    attempts: List[Dict[str, Any]] = []
    source_counts = {"pubmed": 0, "semantic_scholar": 0, "openalex": 0, "crossref": 0}
    errors: List[str] = []
    for variant in variants:
        query = str(variant.get("query") or "").strip()
        if not query:
            continue
        for source in source_counts:
            try:
                payload = await _retrieve_source(
                    source,
                    query,
                    max_results=max_results,
                    request=request,
                    project=project,
                )
                if payload.get("error"):
                    raise RuntimeError(str(payload.get("error")))
                records = payload.get("results") or []
                source_counts[source] += len(records)
                for attempt in payload.get("attempts") or [{"query": payload.get("search_query") or query, "result_count": len(records)}]:
                    attempts.append({"variant_id": variant.get("id"), "variant_type": variant.get("type"), "source": source, **attempt})
                for record in records:
                    record["sources"] = _unique_in_order([*(record.get("sources") or []), source])
                    record.setdefault("retrieval_queries", [])
                    record["retrieval_queries"].append({"variant_id": variant.get("id"), "type": variant.get("type"), "query": query, "source": source})
                    all_records.append(record)
            except Exception as exc:
                errors.append(f"{source}:{variant.get('id')}: {exc}")
                attempts.append({"variant_id": variant.get("id"), "variant_type": variant.get("type"), "source": source, "query": query, "result_count": 0, "error": str(exc)})

    records = _dedupe_records(all_records)
    if not records:
        logger.end(index, status="error", message="No literature records were retrieved from any source.", outputs={"source_counts": source_counts, "attempt_count": len(attempts)}, errors=errors)
        raise WorkflowError(stage, "No literature records were retrieved from any source.", logger.trace)
    status = "success_with_warnings" if errors else "success"
    logger.end(
        index,
        status=status,
        message=f"Retrieved {len(records)} unique records across source APIs.",
        outputs={"unique_records": len(records), "source_counts": source_counts, "attempts": attempts[:80]},
        errors=errors[:40],
    )
    return records, source_counts, attempts


async def _semantic_scholar_neighbors(paper_id: str, relation: str, limit: int) -> List[Dict[str, Any]]:
    fields = "paperId,title,abstract,year,authors,journal,externalIds,url,citationCount,openAccessPdf,isOpenAccess,publicationVenue"
    headers = {}
    api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
    if api_key:
        headers["x-api-key"] = api_key
    timeout = httpx.Timeout(30.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
        response = await client.get(
            f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}/{relation}",
            params={"limit": limit, "fields": fields},
        )
        response.raise_for_status()
    records = []
    paper_key = "citedPaper" if relation == "references" else "citingPaper"
    for item in (response.json() or {}).get("data", []) or []:
        paper = item.get(paper_key) or {}
        external = paper.get("externalIds") or {}
        doi = str(external.get("DOI") or "").strip().lower()
        pmid = str(external.get("PubMed") or "").strip()
        pmcid = str(external.get("PubMedCentral") or "").strip()
        title = str(paper.get("title") or "").strip()
        year = str(paper.get("year") or "").strip()
        venue = (paper.get("journal") or {}).get("name") or (paper.get("publicationVenue") or {}).get("name") or ""
        pdf_url = str((paper.get("openAccessPdf") or {}).get("url") or "").strip()
        citation = ". ".join(part for part in [title, venue, year, f"DOI: {doi}" if doi else "", f"PMID: {pmid}" if pmid else ""] if part)
        records.append(
            {
                "source": "semantic_scholar_graph",
                "sources": ["semantic_scholar_graph", f"semantic_scholar_{relation}"],
                "semantic_scholar_paper_id": str(paper.get("paperId") or "").strip(),
                "pmid": pmid,
                "pmcid": pmcid,
                "doi": doi,
                "pdf_url": pdf_url,
                "title": title,
                "journal": venue,
                "year": year,
                "authors": [str(author.get("name") or "").strip() for author in (paper.get("authors") or [])[:8] if str(author.get("name") or "").strip()],
                "abstract": str(paper.get("abstract") or "")[:5000],
                "citation": citation or title,
                "url": str(paper.get("url") or "").strip(),
                "cited_by_count": paper.get("citationCount"),
                "is_open_access": bool(paper.get("isOpenAccess")),
                "citation_graph_relation": relation,
                "citation_graph_seed": paper_id,
            }
        )
    return records


async def _citation_graph_expansion(
    *,
    logger: WorkflowTraceLogger,
    records: List[Dict[str, Any]],
    seed_limit: int = 3,
    neighbors_per_relation: int = 3,
) -> List[Dict[str, Any]]:
    stage = "citation_graph_expansion"
    seeds = [str(record.get("semantic_scholar_paper_id") or "").strip() for record in records if str(record.get("semantic_scholar_paper_id") or "").strip()]
    seeds = _unique_in_order(seeds)[:seed_limit]
    index = logger.start(stage, inputs={"seed_count": len(seeds), "seed_limit": seed_limit, "neighbors_per_relation": neighbors_per_relation})
    if not seeds:
        logger.end(
            index,
            status="skipped",
            message="No Semantic Scholar paper IDs were available for graph expansion.",
            outputs={"added_records": 0},
        )
        return records

    neighbor_records: List[Dict[str, Any]] = []
    errors: List[str] = []
    for seed in seeds:
        for relation in ["references", "citations"]:
            try:
                neighbor_records.extend(await _semantic_scholar_neighbors(seed, relation, neighbors_per_relation))
            except Exception as exc:
                errors.append(f"{seed}:{relation}: {exc}")

    expanded = _dedupe_records([*records, *neighbor_records])
    status = "success_with_warnings" if errors else "success"
    logger.end(
        index,
        status=status,
        message=f"Expanded retrieval with {max(0, len(expanded) - len(records))} citation-neighbor records.",
        outputs={"seed_count": len(seeds), "neighbor_records": len(neighbor_records), "expanded_unique_records": len(expanded)},
        errors=errors,
    )
    return expanded


def _embedding_configured() -> bool:
    return bool(
        os.getenv("SOTA_EMBEDDING_URL", "").strip()
        or os.getenv("SOTA_SENTENCE_TRANSFORMERS_MODEL", "").strip()
    )


def _parse_embeddings_payload(payload: Any) -> List[List[float]]:
    if isinstance(payload, dict) and isinstance(payload.get("embeddings"), list):
        raw = payload["embeddings"]
    elif isinstance(payload, dict) and isinstance(payload.get("data"), list):
        raw = [item.get("embedding") for item in payload["data"] if isinstance(item, dict)]
    elif isinstance(payload, list):
        raw = payload
    else:
        raise ValueError("Embedding service must return embeddings or OpenAI-style data[].embedding.")
    embeddings: List[List[float]] = []
    for item in raw:
        if not isinstance(item, list):
            raise ValueError("Embedding vector must be a list of numbers.")
        embeddings.append([float(value) for value in item])
    if not embeddings:
        raise ValueError("Embedding service returned no embeddings.")
    return embeddings


async def _embed_texts(texts: List[str]) -> List[List[float]]:
    embedding_url = os.getenv("SOTA_EMBEDDING_URL", "").strip()
    if embedding_url:
        embedding_model = os.getenv("SOTA_EMBEDDING_MODEL", "").strip() or os.getenv("OLLAMA_EMBEDDING_MODEL", "").strip()
        body: Dict[str, Any] = {"texts": texts, "input": texts}
        if embedding_model:
            body["model"] = embedding_model
        timeout = httpx.Timeout(120.0, connect=20.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(embedding_url, json=body)
            response.raise_for_status()
        embeddings = _parse_embeddings_payload(response.json())
        if len(embeddings) != len(texts):
            raise ValueError(f"Embedding service returned {len(embeddings)} embeddings for {len(texts)} texts.")
        return embeddings

    model_name = os.getenv("SOTA_SENTENCE_TRANSFORMERS_MODEL", "").strip()
    if model_name:
        try:
            from sentence_transformers import SentenceTransformer
        except Exception as exc:
            raise RuntimeError("SOTA_SENTENCE_TRANSFORMERS_MODEL is set but sentence-transformers is not installed.") from exc
        model = SentenceTransformer(model_name)
        vectors = model.encode(texts, normalize_embeddings=True)
        return [[float(value) for value in vector] for vector in vectors]

    raise RuntimeError("No embedding backend configured. Set SOTA_EMBEDDING_URL or SOTA_SENTENCE_TRANSFORMERS_MODEL.")


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _record_embedding_text(record: Dict[str, Any]) -> str:
    return " ".join(
        str(record.get(key) or "")
        for key in ["title", "abstract", "journal", "year", "citation"]
        if str(record.get(key) or "").strip()
    )[:5000]


async def _dense_embedding_rerank(
    *,
    logger: WorkflowTraceLogger,
    request: FetchProjectLiteratureRequest,
    decomposition: Dict[str, Any],
    records: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    stage = "dense_embedding_rerank"
    index = logger.start(
        stage,
        inputs={
            "record_count": len(records),
            "embedding_url_configured": bool(os.getenv("SOTA_EMBEDDING_URL", "").strip()),
            "sentence_transformers_model": os.getenv("SOTA_SENTENCE_TRANSFORMERS_MODEL", "").strip(),
        },
    )
    if not _embedding_configured():
        logger.end(
            index,
            status="missing_capability",
            message="Dense embedding rerank was skipped because no embedding backend is configured.",
            outputs={
                "required_configuration": ["SOTA_EMBEDDING_URL", "SOTA_SENTENCE_TRANSFORMERS_MODEL"],
                "records_carried_forward": len(records),
            },
            errors=["Configure an embedding backend to enable dense semantic scoring."],
        )
        return records

    query_text = " ".join(
        [
            request.query,
            str(decomposition.get("intent_summary") or ""),
            json.dumps(decomposition.get("facets") or {}, ensure_ascii=False),
            json.dumps(decomposition.get("inclusion_criteria") or [], ensure_ascii=False),
        ]
    )
    record_texts = [_record_embedding_text(record) for record in records]
    try:
        embeddings = await _embed_texts([query_text, *record_texts])
    except Exception as exc:
        logger.end(index, status="error", message="Dense embedding rerank failed.", errors=[str(exc)])
        raise WorkflowError(stage, f"Dense embedding rerank failed: {exc}", logger.trace) from exc

    query_embedding = embeddings[0]
    record_embeddings = embeddings[1:]
    reranked = []
    for record, embedding in zip(records, record_embeddings):
        item = dict(record)
        item["dense_similarity"] = round(_cosine(query_embedding, embedding), 6)
        reranked.append(item)
    reranked.sort(key=lambda item: -float(item.get("dense_similarity") or 0.0))
    logger.end(
        index,
        message="Applied dense semantic scores to retrieved literature candidates.",
        outputs={
            "record_count": len(reranked),
            "top_dense_matches": [
                {
                    "title": str(item.get("title") or "")[:220],
                    "dense_similarity": item.get("dense_similarity"),
                }
                for item in reranked[:8]
            ],
        },
    )
    return reranked


def _record_source_ids(record: Dict[str, Any]) -> Dict[str, str]:
    return {
        key: str(record.get(key) or "").strip()
        for key in ["pmid", "pmcid", "doi", "pdf_url", "semantic_scholar_paper_id"]
        if str(record.get(key) or "").strip()
    }


def _record_grounded_knowns(record: Dict[str, Any], proposed: Any, limit: int = 6) -> List[str]:
    source_text = " ".join(
        str(record.get(key) or "") for key in ("title", "abstract", "citation")
    )
    normalized_source = re.sub(r"\s+", " ", source_text).lower().replace(",", ".")
    grounded: List[str] = []
    for value in proposed if isinstance(proposed, list) else []:
        claim = re.sub(r"\s+", " ", str(value or "")).strip()
        if not claim:
            continue
        numbers = re.findall(r"\d+(?:[.,]\d+)?", claim)
        if any(number.replace(",", ".") not in normalized_source for number in numbers):
            continue
        technical = {
            token
            for token in re.findall(r"[a-z0-9-]+", claim.lower())
            if len(token) >= 5 and token not in {"which", "using", "production", "increase", "increased", "strain"}
        }
        overlap = sum(token in normalized_source for token in technical)
        if technical and overlap / len(technical) < 0.45:
            continue
        grounded.append(claim)

    if grounded:
        return _unique_in_order(grounded)[:limit]

    sentences = re.split(r"(?<=[.!?])\s+", str(record.get("abstract") or ""))
    relevant = [
        re.sub(r"\s+", " ", sentence).strip()[:700]
        for sentence in sentences
        if len(sentence.strip()) >= 45
        and re.search(r"naringenin|saccharomyces|glucose|titer|yield|engineer", sentence, re.IGNORECASE)
    ]
    if relevant:
        return _unique_in_order(relevant)[:limit]
    title = str(record.get("title") or "").strip()
    return [f"This record reports: {title}."] if title else []


def _record_grounded_labels(record: Dict[str, Any], proposed: Any) -> List[str]:
    source_text = " ".join(str(record.get(key) or "") for key in ("title", "abstract")).lower()
    labels = []
    for value in proposed if isinstance(proposed, list) else []:
        label = str(value or "").strip()
        tokens = [token for token in re.findall(r"[a-z0-9-]+", label.lower()) if len(token) >= 3]
        if label and tokens and all(token in source_text for token in tokens):
            labels.append(label)
    return _unique_in_order(labels)


def _candidate_payload(
    records: List[Dict[str, Any]],
    *,
    relevance_profile: Optional[Dict[str, Any]] = None,
    limit: int = 24,
) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    candidates = []
    by_id: Dict[str, Dict[str, Any]] = {}
    has_dense_scores = any(isinstance(record.get("dense_similarity"), (int, float)) for record in records)
    scored_records = []
    for record in records:
        item = dict(record)
        relevance = _literature_relevance_score(item, relevance_profile or {})
        item["deterministic_relevance"] = relevance["score"]
        item["matched_query_terms"] = relevance["matched_terms"]
        scored_records.append(item)
    sorted_records = sorted(
        scored_records,
        key=lambda item: (
            -float(item.get("dense_similarity") or 0.0) if has_dense_scores else 0.0,
            -float(item.get("deterministic_relevance") or 0.0),
            -int(item.get("cited_by_count") or 0),
            -(int(item.get("year") or 0) if str(item.get("year") or "").isdigit() else 0),
            0 if item.get("abstract") else 1,
        ),
    )
    for index, record in enumerate(sorted_records[:limit], start=1):
        candidate_id = f"cand_{index}"
        by_id[candidate_id] = record
        candidates.append(
            {
                "candidate_id": candidate_id,
                "title": str(record.get("title") or "")[:500],
                "citation": str(record.get("citation") or "")[:500],
                "journal": str(record.get("journal") or ""),
                "year": str(record.get("year") or ""),
                "sources": record.get("sources") or [],
                "source_ids": _record_source_ids(record),
                "cited_by_count": record.get("cited_by_count"),
                "dense_similarity": record.get("dense_similarity"),
                "deterministic_relevance": record.get("deterministic_relevance"),
                "matched_query_terms": record.get("matched_query_terms") or [],
                "abstract_excerpt": str(record.get("abstract") or "")[:1400],
                "retrieval_queries": record.get("retrieval_queries") or [],
                "citation_graph_relation": record.get("citation_graph_relation") or "",
            }
        )
    return candidates, by_id


async def _strict_llm_rerank_and_extract(
    *,
    logger: WorkflowTraceLogger,
    project: Dict[str, Any],
    persona: Dict[str, Any],
    request: FetchProjectLiteratureRequest,
    decomposition: Dict[str, Any],
    records: List[Dict[str, Any]],
    max_results: int,
) -> Dict[str, Any]:
    stage = "llm_rerank_and_evidence_extraction"
    relevance_profile = _literature_relevance_profile(
        request.query,
        project_goal=request.project_goal or project.get("project_goal") or "",
        objective_title=request.objective_title or "",
        objective_definition=request.objective_definition or "",
        objective_signals=request.objective_signals,
    )
    candidates, by_id = _candidate_payload(records, relevance_profile=relevance_profile)
    index = logger.start(stage, inputs={"candidate_count": len(candidates), "max_results": max_results})
    if not candidates:
        exc = ValueError("no candidates available for reranking")
        logger.fail(index, stage, "No candidates available for LLM reranking", exc)
    prompt = f"""
You are reranking scholarly papers and extracting evidence for a scientific literature workflow. Return strict JSON only.

Project goal: {request.project_goal or project.get("project_goal") or project.get("name") or ""}
End product: {request.project_end_product or project.get("end_product") or ""}
Target host/context: {request.project_target_host or project.get("target_host") or ""}
Collaborator/persona: {persona.get("name") or ""}
Objective: {request.objective_title or ""} -- {request.objective_definition or ""}
Initial user query: {request.query}

Intent summary:
{decomposition.get("intent_summary") or ""}

Facets:
{json.dumps(decomposition.get("facets") or {}, ensure_ascii=False)}

Inclusion criteria:
{json.dumps(decomposition.get("inclusion_criteria") or [], ensure_ascii=False)}

Exclusion criteria:
{json.dumps(decomposition.get("exclusion_criteria") or [], ensure_ascii=False)}

Candidates:
{json.dumps(candidates, ensure_ascii=False, indent=2)}

Select up to {max_results} papers. Use only the candidate metadata; do not invent paper findings.
Treat exact product, host, substrate, experimental intervention, and quantitative outcome matches as hard priorities.
Prefer direct experimental evidence over reviews or general methods. Exclude supplemental-file DOI records and clinical papers unless they uniquely answer the query.
Use deterministic_relevance and matched_query_terms as reproducible ranking evidence; only override them when the candidate metadata gives a specific reason.
For knowns, extract claims directly supported by title/abstract/citation metadata.
For unknowns, state what the paper metadata does not resolve for this project, especially transferability, feasibility, organism/product match, quantitative benchmark uncertainty, or missing experimental conditions.
Generate tacit information questions that ask the user for constraints, transferability judgments, feasibility limits, or priority calls needed after reading these papers.

Return JSON:
{{
  "objective_lens": "one sentence explaining how the objective conditions this review",
  "processing_summary": "2-4 sentences explaining how the search was decomposed, retrieved, reranked, and what remains uncertain",
  "elicitation_questions": ["question", "question", "question"],
  "selected": [
    {{
      "candidate_id": "cand_1",
      "score": 0.0,
      "evidence_role": "benchmark|method|review|gap|boundary_condition|background|counterevidence",
      "rationale": "why this paper belongs in the final evidence set",
      "labels": ["short labels"],
      "knowns": ["directly supported evidence claim"],
      "unknowns": ["project-specific uncertainty"],
      "relevance": "short relevance note"
    }}
  ]
}}
""".strip()
    try:
        payload = await ollama.generate_json(prompt, max_retries=1, temperature=0.1, top_p=0.85)
    except Exception as exc:
        logger.fail(index, stage, "LLM reranking and extraction failed", exc)

    selected = payload.get("selected") if isinstance(payload, dict) else None
    if not isinstance(selected, list):
        exc = ValueError("selected must be a list")
        logger.fail(index, stage, "LLM reranking returned invalid JSON shape", exc)

    findings: List[ResearchFinding] = []
    seen = set()
    for item in selected:
        if not isinstance(item, dict):
            continue
        candidate_id = str(item.get("candidate_id") or "").strip()
        if candidate_id not in by_id or candidate_id in seen:
            continue
        seen.add(candidate_id)
        record = by_id[candidate_id]
        score = float(record.get("deterministic_relevance") or 0.0)
        evidence_role = str(item.get("evidence_role") or "").strip()
        title_tokens = set(re.findall(r"[a-z0-9]+", str(record.get("title") or "").lower()))
        target_products = set(relevance_profile.get("target_product_terms") or [])
        target_hosts = set(relevance_profile.get("target_host_terms") or [])
        product_matches = not target_products or bool(target_products & title_tokens)
        host_matches = not target_hosts or target_hosts.issubset(title_tokens)
        context_mismatches = []
        if not product_matches:
            context_mismatches.append("target product")
        if not host_matches:
            context_mismatches.append("target host")
        if context_mismatches:
            evidence_role = "boundary_condition|transfer_evidence"
        labels = _record_grounded_labels(record, item.get("labels"))
        labels.extend(str(source).strip() for source in (record.get("sources") or []) if str(source).strip())
        if evidence_role:
            labels.append(f"evidence role: {evidence_role}")
        labels.append(f"deterministic relevance: {score:.2f}")
        source_ids = _record_source_ids(record)
        for key, value in source_ids.items():
            labels.append(f"{key.upper()}: {value}")
        knowns = _record_grounded_knowns(record, item.get("knowns"), limit=6)
        unknowns = [str(value).strip() for value in (item.get("unknowns") or []) if str(value).strip()][:6]
        relevance = str(item.get("relevance") or item.get("rationale") or "").strip()[:1200]
        if context_mismatches:
            mismatch_text = " and ".join(context_mismatches)
            unknowns.insert(0, f"Context mismatch: this paper does not match the requested {mismatch_text} in its title.")
            relevance = f"Transfer evidence only ({mismatch_text} mismatch). {relevance}".strip()
        if not knowns:
            exc = ValueError(f"{candidate_id} was selected without any knowns")
            logger.fail(index, stage, "LLM selected a candidate without extractive knowns", exc)
        findings.append(
            ResearchFinding(
                id=f"sota_lit_{len(findings) + 1}",
                citation=str(record.get("citation") or record.get("title") or f"Candidate {candidate_id}").strip(),
                labels=_unique_in_order(labels)[:12],
                knowns=knowns,
                unknowns=unknowns,
                relevance=relevance,
                source_ids=source_ids,
                synthesis_memo=str(item.get("rationale") or "").strip()[:1000],
            )
        )
        if len(findings) >= max_results:
            break

    if not findings:
        exc = ValueError("LLM did not select any valid candidates")
        logger.fail(index, stage, "LLM reranking did not produce a usable evidence set", exc)

    questions = [str(question).strip() for question in (payload.get("elicitation_questions") or []) if str(question).strip()]
    logger.end(
        index,
        message=f"Selected and extracted {len(findings)} final literature findings.",
        outputs={
            "selected_count": len(findings),
            "selected_citations": [finding.citation for finding in findings],
            "elicitation_question_count": len(questions),
        },
    )
    return {
        "findings": findings,
        "objective_lens": str(payload.get("objective_lens") or "").strip(),
        "processing_summary": str(payload.get("processing_summary") or "").strip(),
        "elicitation_questions": questions[:6],
    }


async def run_sota_literature_workflow(
    *,
    project_id: int,
    project: Dict[str, Any],
    persona: Dict[str, Any],
    request: FetchProjectLiteratureRequest,
    ontology_context: str = "",
    max_results: int = 5,
) -> Dict[str, Any]:
    logger = WorkflowTraceLogger()

    capabilities = _capability_report()
    logger.record(
        "capability_check",
        status="success_with_warnings"
        if not (capabilities["pdf_parsing"]["grobid_url"] or capabilities["pdf_parsing"]["docling_url"] or capabilities["pdf_parsing"]["docling_enabled"])
        or not (capabilities["dense_retrieval"]["embedding_url"] or capabilities["dense_retrieval"]["sentence_transformers_model"])
        else "success",
        message="Checked configured SOTA workflow capabilities.",
        inputs={"project_id": project_id},
        outputs=capabilities,
        errors=[
            "PDF layout parser not configured: set GROBID_URL, DOCLING_URL, or DOCLING_ENABLED=1 for strict PDF parsing stages."
            if not (capabilities["pdf_parsing"]["grobid_url"] or capabilities["pdf_parsing"]["docling_url"] or capabilities["pdf_parsing"]["docling_enabled"])
            else "",
            "Dense embedding retrieval not configured: set SOTA_EMBEDDING_URL or SOTA_SENTENCE_TRANSFORMERS_MODEL."
            if not (capabilities["dense_retrieval"]["embedding_url"] or capabilities["dense_retrieval"]["sentence_transformers_model"])
            else "",
        ],
    )

    variant_target = max(3, min(int(request.query_variant_count or 8), 20))
    decomposition = await _decompose_query(
        logger=logger,
        project=project,
        persona=persona,
        request=request,
        ontology_context=ontology_context,
        max_variants=variant_target,
    )

    records, source_counts, attempts = await _multi_source_retrieval(
        logger=logger,
        request=request,
        project=project,
        variants=decomposition.get("query_variants") or [],
        max_results=max(3, min(max_results, 8)),
    )

    dense_records = await _dense_embedding_rerank(
        logger=logger,
        request=request,
        decomposition=decomposition,
        records=records,
    )

    expanded_records = await _citation_graph_expansion(logger=logger, records=dense_records)

    extracted = await _strict_llm_rerank_and_extract(
        logger=logger,
        project=project,
        persona=persona,
        request=request,
        decomposition=decomposition,
        records=expanded_records,
        max_results=max_results,
    )

    return {
        "run_id": logger.run_id,
        "findings": extracted["findings"],
        "objective_lens": extracted.get("objective_lens") or decomposition.get("intent_summary") or "",
        "processing_summary": extracted.get("processing_summary") or "",
        "elicitation_questions": extracted.get("elicitation_questions") or [],
        "query_variants": decomposition.get("query_variants") or [],
        "source_counts": source_counts,
        "attempts": attempts,
        "record_count": len(expanded_records),
        "workflow_trace": logger.trace,
    }
