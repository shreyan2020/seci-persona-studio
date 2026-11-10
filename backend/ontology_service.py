import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from models import (
    AgenticPlan,
    BuildPaperOntologyRequest,
    BuildOntologyPreviewRequest,
    OntologyEdge,
    OntologyNode,
    OntologyPreviewResponse,
    OntologyQueryAugmentation,
    ResearchWorkTemplate,
    TacitMemoryItem,
)


STOPWORDS = {
    "about",
    "after",
    "also",
    "analysis",
    "and",
    "are",
    "based",
    "because",
    "before",
    "between",
    "both",
    "can",
    "claim",
    "data",
    "does",
    "during",
    "each",
    "from",
    "have",
    "into",
    "more",
    "most",
    "next",
    "not",
    "paper",
    "project",
    "result",
    "results",
    "should",
    "show",
    "study",
    "that",
    "the",
    "their",
    "then",
    "there",
    "these",
    "this",
    "through",
    "using",
    "with",
}

BIOTECH_TERMS = {
    "assay",
    "bioreactor",
    "biosynthesis",
    "cofactor",
    "construct",
    "downstream",
    "enzyme",
    "expression",
    "feedstock",
    "fermentation",
    "flux",
    "gene",
    "host",
    "media",
    "metabolic",
    "omics",
    "pathway",
    "precursor",
    "protein",
    "scale",
    "strain",
    "titer",
    "toxicity",
    "upstream",
    "yield",
}

ENTITY_TYPE_ALIASES = {
    "species": "species",
    "organism": "species",
    "host": "species",
    "chemical": "chemical",
    "compound": "chemical",
    "metabolite": "chemical",
    "product": "chemical",
    "precursor": "chemical",
    "gene": "gene_or_enzyme",
    "enzyme": "gene_or_enzyme",
    "protein": "gene_or_enzyme",
    "gene_or_enzyme": "gene_or_enzyme",
    "method": "method",
    "assay": "method",
    "measurement": "measurement",
    "metric": "measurement",
    "process_condition": "process_condition",
    "condition": "process_condition",
    "limitation": "limitation",
    "gap": "gap",
    "validation": "validation",
}

ALLOWED_EXTRACTED_RELATIONS = {
    "produces",
    "uses_host",
    "targets_product",
    "precursor_for",
    "catalyzes",
    "uses_method",
    "measured_by",
    "has_benchmark",
    "has_condition",
    "limited_by",
    "raises_gap",
    "tests",
    "improves",
    "increases",
    "decreases",
    "mentions",
}

KNOWN_BIOTECH_CHEMICALS = {
    "acetyl-coa",
    "caffeic acid",
    "cinnamic acid",
    "coumaric acid",
    "resveratrol",
    "naringenin",
    "p-coumaric acid",
    "p-coumaric",
    "coumaroyl-coa",
    "malonyl-coa",
    "p-ca",
    "phenylalanine",
    "sucrose",
    "tyrosine",
    "glucose",
    "flavonoid",
    "flavonoids",
    "quercetin",
    "kaempferol",
    "eriodictyol",
}

KNOWN_METHODS = {
    "hplc",
    "lc-ms",
    "lc ms",
    "gc-ms",
    "gc ms",
    "crispr",
    "rna-seq",
    "fed-batch",
    "batch fermentation",
    "fermentation",
    "assay",
    "biosensor",
    "directed evolution",
    "adaptive laboratory evolution",
}

KNOWN_PROCESS_CONDITIONS = {
    "fed-batch",
    "batch",
    "shake flask",
    "bioreactor",
    "fermentation",
    "oxygen",
    "media",
    "medium",
    "feed",
    "substrate",
}

NON_PRODUCT_CHEMICALS = {
    "acetyl-coa",
    "coumaroyl-coa",
    "flavonoid",
    "flavonoids",
    "glucose",
    "malonyl-coa",
    "phenylalanine",
    "sucrose",
    "tyrosine",
}

WEAK_CONCEPT_BIGRAM_TOKENS = {"produced", "reached", "reports", "reported", "supports"}

KNOWN_GENE_SYMBOLS = {
    "4CL",
    "ACC1",
    "ARO4",
    "ARO7",
    "CHI",
    "CHS",
    "FLS",
    "STS",
    "TAL",
    "TKL1",
    "ZWF1",
}

KNOWN_ENZYME_NAMES = {
    "4-coumarate coa ligase",
    "acetyl-coa carboxylase",
    "chalcone isomerase",
    "chalcone synthase",
    "flavonol synthase",
    "phenylalanine ammonia lyase",
    "stilbene synthase",
    "tyrosine ammonia lyase",
}

QUERY_TERM_BLOCKLIST = {
    "annotated",
    "annotation",
    "crossref",
    "literature",
    "openalex",
    "pdf",
    "pdf annotated",
    "pmcid",
    "pmid",
    "pubmed",
    "short label",
}

ONTOLOGY_GENERATION_VERSION = "ontology-v3-precision-grounded"


def _slug(value: str, prefix: str = "node") -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", (value or "").lower()).strip("_")
    return f"{prefix}_{cleaned[:72]}" if cleaned else f"{prefix}_unknown"


def _compact(value: Optional[str], limit: int = 220) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _stable_hash(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _stable_node_list(nodes: Iterable[OntologyNode]) -> List[OntologyNode]:
    return sorted(nodes, key=lambda node: (node.type, node.label.lower(), node.id))


def _stable_edge_list(edges: Iterable[OntologyEdge]) -> List[OntologyEdge]:
    return sorted(edges, key=lambda edge: (edge.relation, edge.source, edge.target, edge.id))


def _source_ref_from_ids(source_ids: Dict[str, Any]) -> List[str]:
    refs: List[str] = []
    for key in ("doi", "pmid", "pmcid", "pdf_url"):
        value = str(source_ids.get(key) or "").strip()
        if value:
            refs.append(f"{key}:{value}")
    return refs


def _tokens(text: str) -> List[str]:
    return [token.lower() for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", text or "")]


def _candidate_terms(texts: Iterable[str], limit: int = 18) -> List[str]:
    counts: Counter[str] = Counter()
    chemical_terms = {term.lower() for term in KNOWN_BIOTECH_CHEMICALS}
    for text in texts:
        toks = [token for token in _tokens(text) if token not in STOPWORDS and token not in QUERY_TERM_BLOCKLIST]
        for token in toks:
            if token in chemical_terms:
                counts[token] += 1
        for left, right in zip(toks, toks[1:]):
            if left in QUERY_TERM_BLOCKLIST or right in QUERY_TERM_BLOCKLIST:
                continue
            if left in WEAK_CONCEPT_BIGRAM_TOKENS or right in WEAK_CONCEPT_BIGRAM_TOKENS:
                continue
            if left in BIOTECH_TERMS or right in BIOTECH_TERMS or f"{left} {right}" in chemical_terms:
                counts[f"{left} {right}"] += 2
    return [term for term, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]]


def _normalize_entity_type(value: Any) -> str:
    key = re.sub(r"[^a-z0-9_]+", "_", str(value or "").lower()).strip("_")
    return ENTITY_TYPE_ALIASES.get(key, "concept")


def _normalize_relation(value: Any) -> str:
    relation = re.sub(r"[^a-z0-9_]+", "_", str(value or "").lower()).strip("_")
    return relation if relation in ALLOWED_EXTRACTED_RELATIONS else "mentions"


def _source_ref(source_refs: Optional[List[str]]) -> Optional[str]:
    return source_refs[0] if source_refs else None


def _finding_text_bundle(finding: Any) -> str:
    parts: List[str] = []
    for attr in ["citation", "relevance", "synthesis_memo"]:
        value = getattr(finding, attr, "")
        if value:
            parts.append(str(value))
    for attr in ["knowns", "unknowns", "annotation_insights", "generated_questions"]:
        parts.extend(str(item) for item in (getattr(finding, attr, None) or []) if str(item).strip())
    for judgment in getattr(finding, "judgment_calls", []) or []:
        if isinstance(judgment, dict):
            parts.extend(str(judgment.get(key) or "") for key in ["stance", "rationale", "implication"])
    for track in getattr(finding, "validation_tracks", []) or []:
        if isinstance(track, dict):
            parts.extend(str(track.get(key) or "") for key in ["target", "method", "success_signal"])
            parts.extend(str(item) for item in (track.get("questions") or []) if str(item).strip())
    return "\n".join(part for part in parts if part.strip())


def _measurement_mentions(text: str) -> List[str]:
    pattern = re.compile(
        r"\b\d+(?:\.\d+)?\s*(?:g/L|mg/L|ug/L|microg/L|mM|uM|μM|µM|fold|%|h|hours|days)\b",
        re.IGNORECASE,
    )
    return sorted(set(match.group(0) for match in pattern.finditer(text)), key=lambda item: text.lower().find(item.lower()))[:12]


def _species_mentions(text: str) -> List[str]:
    candidates = [
        "Saccharomyces cerevisiae",
        "Yarrowia lipolytica",
        "Escherichia coli",
        "E. coli",
        "Komagataella phaffii",
        "Pichia pastoris",
    ]
    lower = text.lower()
    found = [item for item in candidates if item.lower() in lower]
    return sorted(set(found), key=lambda item: lower.find(item.lower()) if item.lower() in lower else 999999)[:10]


def _chemical_mentions(text: str) -> List[str]:
    lower = text.lower()
    found = [item for item in KNOWN_BIOTECH_CHEMICALS if item in lower]
    return sorted(set(found), key=lambda item: lower.find(item.lower()) if item.lower() in lower else 999999)[:14]


def _method_mentions(text: str) -> List[str]:
    lower = text.lower()
    found = [item.upper() if item in {"hplc", "lc-ms", "gc-ms"} else item for item in KNOWN_METHODS if item in lower]
    return sorted(set(found), key=lambda item: lower.find(item.lower()))[:10]


def _process_condition_mentions(text: str) -> List[str]:
    lower = text.lower()
    found = [item for item in KNOWN_PROCESS_CONDITIONS if item in lower]
    return sorted(set(found), key=lambda item: lower.find(item.lower()))[:10]


def _gene_or_enzyme_mentions(text: str) -> List[str]:
    lower = text.lower()
    found = [name for name in KNOWN_ENZYME_NAMES if name in lower]
    found.extend(
        symbol
        for symbol in KNOWN_GENE_SYMBOLS
        if re.search(rf"(?<![A-Za-z0-9]){re.escape(symbol)}(?![A-Za-z0-9])", text, flags=re.IGNORECASE)
    )
    return sorted(set(found), key=lambda item: lower.find(item.lower()))[:12]


def fallback_paper_ontology_extraction(finding: Any) -> Dict[str, List[Dict[str, Any]]]:
    text = _finding_text_bundle(finding)
    entities: List[Dict[str, Any]] = []
    relations: List[Dict[str, Any]] = []

    def add_entity(label: str, entity_type: str, evidence: str = "") -> str:
        clean = _compact(label, 140)
        if not clean:
            return ""
        entity_id = _slug(f"{entity_type}_{clean}", "entity")
        if not any(item["id"] == entity_id for item in entities):
            entities.append(
                {
                    "id": entity_id,
                    "label": clean,
                    "type": entity_type,
                    "description": evidence or clean,
                    "evidence": [_compact(evidence or clean, 220)],
                    "confidence": 0.72,
                }
            )
        return entity_id

    species_ids = [add_entity(item, "species", "Detected as organism/host in paper evidence.") for item in _species_mentions(text)]
    chemical_ids = [add_entity(item, "chemical", "Detected as product, precursor, substrate, or metabolite in paper evidence.") for item in _chemical_mentions(text)]
    method_ids = [add_entity(item, "method", "Detected as method, assay, or tool in paper evidence.") for item in _method_mentions(text)]
    condition_ids = [add_entity(item, "process_condition", "Detected as process or cultivation condition.") for item in _process_condition_mentions(text)]
    measurement_ids = [add_entity(item, "measurement", "Detected quantitative benchmark or measurement.") for item in _measurement_mentions(text)]
    enzyme_ids = [add_entity(item, "gene_or_enzyme", "Detected gene, protein, or enzyme mention.") for item in _gene_or_enzyme_mentions(text)]

    relation_evidence = _compact(text, 260)
    product_chemical_ids = [
        entity_id
        for entity_id in chemical_ids
        if entity_id and not any(entity_id.endswith(f"_{_slug(name, 'chemical').removeprefix('chemical_')}") for name in NON_PRODUCT_CHEMICALS)
    ]
    for species_id in species_ids[:3]:
        for chemical_id in product_chemical_ids[:4]:
            relations.append({"source": species_id, "relation": "produces", "target": chemical_id, "evidence": [relation_evidence], "confidence": 0.62})
    for chemical_id in chemical_ids[:4]:
        for measurement_id in measurement_ids[:4]:
            relations.append({"source": chemical_id, "relation": "has_benchmark", "target": measurement_id, "evidence": [relation_evidence], "confidence": 0.7})
    for method_id in method_ids[:4]:
        for measurement_id in measurement_ids[:4]:
            relations.append({"source": measurement_id, "relation": "measured_by", "target": method_id, "evidence": [relation_evidence], "confidence": 0.68})
    for condition_id in condition_ids[:4]:
        for chemical_id in chemical_ids[:4]:
            relations.append({"source": chemical_id, "relation": "has_condition", "target": condition_id, "evidence": [relation_evidence], "confidence": 0.62})
    limitation_texts = [
        item
        for item in re.split(r"(?<=[.!?])\s+", text)
        if re.search(r"\b(however|limitation|limited|bottleneck|remain|uncertain|unknown|challenge|further)\b", item, re.IGNORECASE)
    ][:8]
    for index, limitation in enumerate(limitation_texts, start=1):
        limitation_id = add_entity(_compact(limitation, 110), "limitation", limitation)
        for chemical_id in chemical_ids[:2]:
            relations.append({"source": chemical_id, "relation": "limited_by", "target": limitation_id, "evidence": [_compact(limitation, 220)], "confidence": 0.68})

    return {"entities": entities[:40], "relations": relations[:80]}


async def llm_paper_ontology_extraction(
    finding: Any,
    *,
    project_goal: str = "",
    project_end_product: str = "",
    project_target_host: str = "",
    query: str = "",
    objective_title: str = "",
    objective_definition: str = "",
) -> Dict[str, List[Dict[str, Any]]]:
    if os.getenv("DISABLE_ONTOLOGY_LLM_EXTRACTION") == "1":
        return {"entities": [], "relations": []}
    try:
        from ollama_client import ollama
    except Exception:
        return {"entities": [], "relations": []}

    text_bundle = _finding_text_bundle(finding)[:14000]
    if not text_bundle.strip():
        return {"entities": [], "relations": []}

    prompt = f"""
You are extracting a typed ontology from one biotech paper for a scientist's project.

Use only the provided paper evidence. Do not invent genes, organisms, chemicals, measurements, or methods.
Prefer exact labels from the evidence. Include evidence snippets for every entity and relation.

Project goal: {project_goal or 'not provided'}
Target product: {project_end_product or 'not provided'}
Target host: {project_target_host or 'not provided'}
Query: {query or 'not provided'}
Objective: {' '.join(part for part in [objective_title, objective_definition] if part) or 'not provided'}

Allowed entity types:
- species
- chemical
- gene_or_enzyme
- method
- measurement
- process_condition
- limitation
- gap
- validation

Allowed relations:
{', '.join(sorted(ALLOWED_EXTRACTED_RELATIONS))}

Paper evidence:
{text_bundle}

Return JSON:
{{
  "entities": [
    {{
      "id": "short_stable_id",
      "label": "entity label",
      "type": "allowed entity type",
      "description": "what this entity means in the paper",
      "evidence": ["verbatim-ish short evidence snippet"],
      "confidence": 0.0
    }}
  ],
  "relations": [
    {{
      "source": "source entity id",
      "relation": "allowed relation",
      "target": "target entity id",
      "evidence": ["short evidence snippet"],
      "confidence": 0.0
    }}
  ]
}}
""".strip()
    try:
        payload = await ollama.generate_json(prompt, max_retries=1, temperature=0.1, top_p=0.85)
    except Exception:
        return {"entities": [], "relations": []}
    if not isinstance(payload, dict):
        return {"entities": [], "relations": []}
    entities = [item for item in (payload.get("entities") or []) if isinstance(item, dict)]
    relations = [item for item in (payload.get("relations") or []) if isinstance(item, dict)]
    return {"entities": entities[:40], "relations": relations[:80]}


class OntologyBuilder:
    def __init__(self, project_id: int):
        self.project_id = project_id
        self.nodes: Dict[str, OntologyNode] = {}
        self.edges: Dict[str, OntologyEdge] = {}

    def add_node(
        self,
        node_id: str,
        node_type: str,
        label: str,
        description: str = "",
        source_refs: Optional[List[str]] = None,
        attributes: Optional[Dict[str, Any]] = None,
        confidence: float = 0.7,
        status: str = "inferred",
    ) -> str:
        if not label:
            return node_id
        clean_description = _compact(description)
        clean_refs = sorted(set(source_refs or []))
        generation_attributes = {
            "generation_version": ONTOLOGY_GENERATION_VERSION,
            "generation_method": (attributes or {}).get("generation_method") or "deterministic_rules",
            "input_fingerprint": _stable_hash(
                {
                    "id": node_id,
                    "type": node_type,
                    "label": label,
                    "description": clean_description,
                    "source_refs": clean_refs,
                }
            ),
        }
        existing = self.nodes.get(node_id)
        if existing:
            refs = sorted(set(existing.source_refs + clean_refs))
            attrs = {**generation_attributes, **existing.attributes, **(attributes or {})}
            self.nodes[node_id] = existing.model_copy(update={"source_refs": refs, "attributes": attrs})
            return node_id
        attrs = {**generation_attributes, **(attributes or {})}
        self.nodes[node_id] = OntologyNode(
            id=node_id,
            type=node_type,
            label=label,
            description=clean_description,
            source_refs=clean_refs,
            attributes=attrs,
            confidence=confidence,
            status=status,
        )
        return node_id

    def add_edge(
        self,
        source: str,
        target: str,
        relation: str,
        evidence: Optional[List[str]] = None,
        confidence: float = 0.7,
    ) -> None:
        if not source or not target or source == target:
            return
        edge_id = _slug(f"{source}_{relation}_{target}", "edge")
        clean_evidence = sorted({_compact(item, 160) for item in (evidence or []) if item})
        existing = self.edges.get(edge_id)
        if existing:
            merged = sorted(set(existing.evidence + clean_evidence))
            self.edges[edge_id] = existing.model_copy(update={"evidence": merged, "confidence": max(existing.confidence, confidence)})
            return
        self.edges[edge_id] = OntologyEdge(
            id=edge_id,
            source=source,
            target=target,
            relation=relation,
            evidence=clean_evidence,
            confidence=confidence,
        )

    def concept(self, label: str, source_ref: Optional[str] = None) -> str:
        node_id = _slug(label, "concept")
        self.add_node(node_id, "concept", label, source_refs=[source_ref] if source_ref else [])
        return node_id


def _add_paper_claim(
    builder: OntologyBuilder,
    paper_id: str,
    text: str,
    claim_type: str,
    index: int,
    source_refs: Optional[List[str]] = None,
) -> str:
    clean = _compact(text, 260)
    if not clean:
        return ""
    claim_id = _slug(f"{paper_id}_{claim_type}_{index}_{clean[:48]}", "claim")
    builder.add_node(
        claim_id,
        "claim",
        clean,
        clean,
        source_refs=source_refs or [],
        attributes={
            "assertion_scope": "paper_says",
            "claim_type": claim_type,
            "paper_id": paper_id,
        },
        confidence=0.72 if claim_type in {"reported_claim", "annotation_insight"} else 0.62,
    )
    relation = "reports_claim" if claim_type == "reported_claim" else "raises_question" if claim_type == "open_question" else "contains_interpretation"
    builder.add_edge(paper_id, claim_id, relation, [clean], 0.72)
    for term in _candidate_terms([clean], 6):
        semantic_id = next(
            (
                node.id
                for node in builder.nodes.values()
                if node.label.strip().lower() == term.strip().lower()
                and node.type in {"chemical", "species", "gene_or_enzyme", "method", "measurement", "process_condition"}
            ),
            None,
        )
        builder.add_edge(
            claim_id,
            semantic_id or builder.concept(term, source_refs[0] if source_refs else None),
            "mentions_concept",
            [clean],
            0.65,
        )
    return claim_id


def _is_semantic_paper_label(label: str) -> bool:
    normalized = re.sub(r"\s+", " ", str(label or "")).strip().lower()
    if not normalized or normalized in QUERY_TERM_BLOCKLIST:
        return False
    if re.fullmatch(r"(?:19|20)\d{2}", normalized):
        return False
    if re.match(r"^(?:pmid|pmcid|doi|pdf_url|relevance score|deterministic relevance|matched terms|matched phrases|evidence role)\s*:", normalized):
        return False
    return normalized not in {"literature fetch", "objective-conditioned", "direct evidence", "partial relevance", "benchmark example"}


def _add_project_belief(
    builder: OntologyBuilder,
    root_id: str,
    label: str,
    description: str = "",
    evidence: Optional[List[str]] = None,
    source_refs: Optional[List[str]] = None,
    source_id: Optional[str] = None,
    source_paper_id: Optional[str] = None,
) -> str:
    clean_label = _compact(label, 220)
    if not clean_label:
        return ""
    belief_id = _slug(f"{source_id or source_paper_id or root_id}_{clean_label[:48]}", "belief")
    builder.add_node(
        belief_id,
        "project_belief",
        clean_label,
        description,
        source_refs=source_refs or [],
        attributes={
            "assertion_scope": "project_believes",
            "source_id": source_id,
            "source_paper_id": source_paper_id,
        },
        confidence=0.82,
    )
    builder.add_edge(root_id, belief_id, "holds_belief", evidence or [description], 0.82)
    if source_paper_id:
        builder.add_edge(belief_id, source_paper_id, "interprets_paper", evidence or [description], 0.78)
    return belief_id


def _add_extracted_paper_ontology(
    builder: OntologyBuilder,
    paper_id: str,
    extracted: Dict[str, Any],
    source_refs: Optional[List[str]] = None,
    extraction_source: str = "deterministic",
) -> None:
    entity_id_map: Dict[str, str] = {}
    for item in extracted.get("entities") or []:
        if not isinstance(item, dict):
            continue
        label = _compact(str(item.get("label") or ""), 160)
        if not label:
            continue
        entity_type = _normalize_entity_type(item.get("type"))
        raw_id = str(item.get("id") or _slug(f"{entity_type}_{label}", "entity"))
        node_id = _slug(f"{paper_id}_{entity_type}_{label}", "entity")
        evidence = item.get("evidence") if isinstance(item.get("evidence"), list) else []
        description = str(item.get("description") or (evidence[0] if evidence else label))
        confidence = item.get("confidence")
        builder.add_node(
            node_id,
            entity_type,
            label,
            description,
            source_refs=source_refs or [],
            attributes={
                "paper_id": paper_id,
                "ontology_scope": "paper_extracted_entity",
                "entity_type": entity_type,
                "extraction_source": extraction_source,
                "generation_method": f"{extraction_source}_paper_ontology_extraction",
                "evidence_fingerprint": _stable_hash(evidence or [description, label]),
                "evidence": [_compact(str(value), 220) for value in evidence[:5]],
            },
            confidence=max(0.35, min(float(confidence), 0.95)) if isinstance(confidence, (int, float)) else (0.82 if extraction_source == "llm" else 0.72),
        )
        entity_id_map[raw_id] = node_id
        entity_id_map[label.lower()] = node_id
        builder.add_edge(paper_id, node_id, "mentions", evidence[:2] or [description], 0.74)

    for item in extracted.get("relations") or []:
        if not isinstance(item, dict):
            continue
        source_raw = str(item.get("source") or item.get("source_id") or "").strip()
        target_raw = str(item.get("target") or item.get("target_id") or "").strip()
        source = entity_id_map.get(source_raw) or entity_id_map.get(source_raw.lower())
        target = entity_id_map.get(target_raw) or entity_id_map.get(target_raw.lower())
        if not source or not target:
            continue
        relation = _normalize_relation(item.get("relation"))
        evidence = item.get("evidence") if isinstance(item.get("evidence"), list) else []
        confidence = item.get("confidence")
        builder.add_edge(
            source,
            target,
            relation,
            [_compact(str(value), 220) for value in evidence[:4]],
            max(0.35, min(float(confidence), 0.95)) if isinstance(confidence, (int, float)) else (0.8 if extraction_source == "llm" else 0.64),
        )


def _add_project_context(builder: OntologyBuilder, request: BuildOntologyPreviewRequest) -> Tuple[str, Optional[str]]:
    project_label = request.project_end_product or request.project_goal or f"Project {builder.project_id}"
    project_id = builder.add_node(
        f"project_{builder.project_id}",
        "project",
        project_label,
        request.project_goal or "",
        attributes={"target_host": request.project_target_host, "end_product": request.project_end_product},
    )

    query_id = None
    if request.query:
        query_id = builder.add_node(_slug(request.query, "query"), "query", request.query, request.objective_definition or "")
        builder.add_edge(query_id, project_id, "asks_about", [request.query], 0.9)

    if request.persona_id:
        persona_id = builder.add_node(f"persona_{request.persona_id}", "persona", f"Persona {request.persona_id}")
        builder.add_edge(persona_id, project_id, "works_on", confidence=0.8)

    for label, relation in ((request.project_end_product, "targets_product"), (request.project_target_host, "uses_host")):
        if label:
            concept_id = builder.concept(label)
            builder.add_edge(project_id, concept_id, relation, [request.project_goal or ""], 0.8)

    if request.objective_title:
        objective_id = builder.add_node(
            request.objective_id or _slug(request.objective_title, "objective"),
            "objective",
            request.objective_title,
            request.objective_definition or "",
        )
        builder.add_edge(project_id, objective_id, "frames_decision", [request.objective_definition or ""], 0.8)
        if query_id:
            builder.add_edge(query_id, objective_id, "uses_lens", [request.objective_title], 0.8)

    return project_id, query_id


def _add_work_template(builder: OntologyBuilder, root_id: str, work_template: Optional[ResearchWorkTemplate]) -> None:
    if not work_template:
        return

    concept_edges: Set[Tuple[str, str]] = set()
    for index, finding in enumerate(work_template.literature_findings[:18], start=1):
        source_refs = _source_ref_from_ids(finding.source_ids or {})
        paper_id = builder.add_node(
            finding.id or f"paper_{index}",
            "paper",
            finding.citation or f"Paper {index}",
            finding.relevance or "; ".join((finding.knowns or [])[:2]),
            source_refs=source_refs,
            attributes={"labels": finding.labels, "source_ids": finding.source_ids},
        )
        builder.add_edge(paper_id, root_id, "supports_project", finding.knowns[:2] or [finding.relevance], 0.75)

        for claim_index, known in enumerate((finding.knowns or [])[:6], start=1):
            _add_paper_claim(builder, paper_id, known, "reported_claim", claim_index, source_refs)
        for claim_index, unknown in enumerate((finding.unknowns or [])[:6], start=1):
            _add_paper_claim(builder, paper_id, unknown, "open_question", claim_index, source_refs)
        for claim_index, insight in enumerate((finding.annotation_insights or [])[:6], start=1):
            _add_paper_claim(builder, paper_id, insight, "annotation_insight", claim_index, source_refs)

        semantic_labels = [label for label in (finding.labels or []) if _is_semantic_paper_label(label)]
        terms = list(
            dict.fromkeys(
                [*semantic_labels, *_candidate_terms([finding.relevance, *finding.knowns, *finding.unknowns], 10)]
            )
        )
        for term in terms[:12]:
            concept_id = builder.concept(term, source_refs[0] if source_refs else None)
            pair = (paper_id, concept_id)
            if pair not in concept_edges:
                builder.add_edge(paper_id, concept_id, "mentions", finding.knowns[:1] or finding.unknowns[:1], 0.7)
                concept_edges.add(pair)

        for judgment in finding.judgment_calls[:6]:
            stance = str(judgment.get("stance") or "").strip()
            if not stance:
                continue
            belief_id = _add_project_belief(
                builder,
                root_id,
                stance,
                str(judgment.get("rationale") or ""),
                [str(judgment.get("implication") or "")],
                source_refs,
                source_id=str(judgment.get("id") or ""),
                source_paper_id=paper_id,
            )
            if belief_id:
                builder.add_edge(belief_id, paper_id, "interprets_paper", [str(judgment.get("implication") or "")], 0.8)

        for track in finding.validation_tracks[:6]:
            target = str(track.get("target") or "").strip()
            if not target:
                continue
            validation_id = builder.add_node(
                track.get("id") or _slug(f"{finding.id}_{target}", "validation"),
                "validation",
                target,
                str(track.get("method") or ""),
            )
            builder.add_edge(validation_id, paper_id, "tests_claim_from", [str(track.get("success_signal") or "")], 0.75)

    for index, gap in enumerate(work_template.common_gaps[:10], start=1):
        gap_id = builder.add_node(gap.id or f"gap_{index}", "gap", gap.theme, gap.next_question)
        builder.add_edge(root_id, gap_id, "has_open_gap", gap.supporting_signals[:3], 0.75)
        for term in _candidate_terms([gap.theme, gap.next_question, *gap.supporting_signals], 5):
            builder.add_edge(gap_id, builder.concept(term), "needs_knowledge_about", gap.supporting_signals[:1], 0.65)

    for index, proposal in enumerate(work_template.proposal_candidates[:10], start=1):
        proposal_id = builder.add_node(proposal.id or f"proposal_{index}", "proposal", proposal.title, proposal.experiment_outline)
        builder.add_edge(proposal_id, root_id, "proposes_experiment_for", [proposal.why_now], 0.75)
        for readout in proposal.readouts[:8]:
            builder.add_edge(proposal_id, builder.concept(readout), "measured_by", [proposal.experiment_outline], 0.7)

    for judgment in work_template.judgment_calls[:10]:
        _add_project_belief(
            builder,
            root_id,
            judgment.stance,
            judgment.rationale,
            [judgment.implication],
            source_id=judgment.id,
        )


def _add_plan(builder: OntologyBuilder, root_id: str, plan: Optional[AgenticPlan]) -> None:
    if not plan:
        return
    plan_id = builder.add_node(_slug(plan.plan_title, "plan"), "plan", plan.plan_title, plan.strategy_summary)
    builder.add_edge(plan_id, root_id, "operationalizes", plan.success_criteria[:3], 0.8)
    for step in plan.steps[:12]:
        step_id = builder.add_node(step.id, "plan_step", step.title, step.description, attributes={"confidence": step.confidence})
        builder.add_edge(plan_id, step_id, "contains_step", [step.expected_outcome], 0.8)
        for fact in step.evidence_facts[:4]:
            builder.add_edge(step_id, builder.concept(fact), "depends_on_fact", [step.why_this_step], 0.7)


def _add_paper_subgraph(builder: OntologyBuilder, root_id: str, request: BuildPaperOntologyRequest) -> str:
    finding = request.finding
    source_refs = _source_ref_from_ids(finding.source_ids or {})
    paper_seed = source_refs[0] if source_refs else finding.citation or finding.id or "paper"
    paper_id = builder.add_node(
        finding.id or _slug(paper_seed, "paper"),
        "paper",
        finding.citation or "Untitled literature source",
        finding.relevance or "; ".join((finding.knowns or [])[:2]),
        source_refs=source_refs,
        attributes={
            "labels": finding.labels,
            "source_ids": finding.source_ids,
            "paper_scoped": True,
            "ontology_scope": "paper",
        },
        confidence=0.8,
    )
    builder.add_edge(paper_id, root_id, "supports_project", finding.knowns[:2] or [finding.relevance], 0.75)

    if request.objective_title:
        objective_id = request.objective_id or _slug(request.objective_title, "objective")
        builder.add_node(objective_id, "objective", request.objective_title, request.objective_definition or "", confidence=0.75)
        builder.add_edge(paper_id, objective_id, "read_through_lens", [request.objective_definition or request.objective_title], 0.75)

    _add_extracted_paper_ontology(
        builder,
        paper_id,
        fallback_paper_ontology_extraction(finding),
        source_refs,
        extraction_source="deterministic",
    )

    claim_texts = [(text, "reported_claim") for text in finding.knowns[:10]]
    claim_texts.extend((text, "open_question") for text in finding.unknowns[:10])
    claim_texts.extend((text, "annotation_insight") for text in (finding.annotation_insights or [])[:8])
    claim_texts.extend((text, "generated_research_question") for text in (finding.generated_questions or [])[:8])
    if finding.relevance:
        claim_texts.append((finding.relevance, "project_relevance"))

    for index, (text, claim_type) in enumerate(claim_texts, start=1):
        _add_paper_claim(builder, paper_id, text, claim_type, index, source_refs)

    for label in finding.labels[:10]:
        if not _is_semantic_paper_label(label):
            continue
        concept_id = builder.concept(label, source_refs[0] if source_refs else None)
        builder.add_edge(paper_id, concept_id, "tagged_with", [label], 0.7)

    for judgment in finding.judgment_calls[:8]:
        stance = str(judgment.get("stance") or "").strip()
        if not stance:
            continue
        _add_project_belief(
            builder,
            root_id,
            stance,
            str(judgment.get("rationale") or ""),
            [str(judgment.get("implication") or "")],
            source_refs=source_refs,
            source_id=str(judgment.get("id") or ""),
            source_paper_id=paper_id,
        )

    for track in finding.validation_tracks[:8]:
        target = str(track.get("target") or "").strip()
        if not target:
            continue
        validation_id = builder.add_node(
            track.get("id") or _slug(f"{paper_id}_{target}", "validation"),
            "validation",
            target,
            str(track.get("method") or ""),
            source_refs=source_refs,
            attributes={"paper_id": paper_id, "execution_result": track.get("execution_result") or {}},
            confidence=0.78,
        )
        builder.add_edge(validation_id, paper_id, "tests_claim_from", [str(track.get("success_signal") or "")], 0.78)
        for question in (track.get("questions") or [])[:5]:
            builder.add_edge(validation_id, builder.concept(str(question)), "asks_about", [str(question)], 0.65)

    return paper_id


def _add_tacit_memory(builder: OntologyBuilder, root_id: str, tacit_state: List[TacitMemoryItem]) -> List[str]:
    usable: List[str] = []
    for item in tacit_state[:12]:
        if item.status == "rejected":
            continue
        memory_id = builder.add_node(item.id, "tacit_memory", item.label, item.inference, attributes={"status": item.status})
        builder.add_edge(root_id, memory_id, "has_tacit_context", item.evidence[:3], max(0.45, item.confidence))
        usable.append(f"{item.label}: {item.inference}")
        for term in _candidate_terms([item.label, item.inference, *(item.evidence or [])], 4):
            builder.add_edge(memory_id, builder.concept(term), "makes_explicit", item.evidence[:1], max(0.45, item.confidence))
    return usable


def _query_augmentation(builder: OntologyBuilder, tacit_context: List[str]) -> OntologyQueryAugmentation:
    return _query_augmentation_from_items(list(builder.nodes.values()), list(builder.edges.values()), tacit_context)


def _is_query_expansion_label(label: str) -> bool:
    normalized = re.sub(r"\s+", " ", label.strip().lower())
    if len(normalized) < 3 or normalized in QUERY_TERM_BLOCKLIST:
        return False
    if re.fullmatch(r"(?:19|20)\d{2}", normalized):
        return False
    if re.match(r"^(?:pmid|pmcid|doi|pdf_url|relevance score|matched terms|matched phrases)\s*:", normalized):
        return False
    if any(token in WEAK_CONCEPT_BIGRAM_TOKENS for token in normalized.split()):
        return False
    return not any(token in QUERY_TERM_BLOCKLIST for token in normalized.split())


def _query_augmentation_from_items(
    nodes: List[OntologyNode],
    edges: List[OntologyEdge],
    tacit_context: Optional[List[str]] = None,
) -> OntologyQueryAugmentation:
    degree: Dict[str, int] = defaultdict(int)
    for edge in edges:
        if edge.status == "rejected":
            continue
        degree[edge.source] += 1
        degree[edge.target] += 1

    expansion_nodes = [
        node
        for node in nodes
        if node.status != "rejected"
        and node.type in {"concept", "chemical", "species", "gene_or_enzyme", "method", "process_condition"}
        and _is_query_expansion_label(node.label)
    ]
    expansion_nodes.sort(key=lambda node: (-degree[node.id], node.type, node.label.lower(), node.id))
    expanded_terms: List[str] = []
    seen_terms: Set[str] = set()
    for node in expansion_nodes:
        normalized = node.label.strip().lower()
        if normalized in seen_terms:
            continue
        seen_terms.add(normalized)
        expanded_terms.append(node.label)
        if len(expanded_terms) >= 18:
            break

    filters: Dict[str, List[str]] = {"pmid": [], "pmcid": [], "doi": []}
    for node in nodes:
        if node.status == "rejected":
            continue
        for ref in node.source_refs:
            key, _, value = ref.partition(":")
            if key in filters and value and value not in filters[key]:
                filters[key].append(value)

    lenses = [
        node.label
        for node in nodes
        if node.status != "rejected" and node.type in {"objective", "gap", "validation", "plan_step", "project_belief"}
    ][:10]

    routing: List[str] = []
    if any(node.status != "rejected" and node.type == "paper" for node in nodes):
        routing.append("literature")
    if any(node.status != "rejected" and node.type == "validation" for node in nodes):
        routing.append("experiment_validation")
    if any(node.status != "rejected" and node.type == "claim" for node in nodes):
        routing.append("paper_claims")
    if any(node.status != "rejected" and node.type == "project_belief" for node in nodes):
        routing.append("project_beliefs")
    tacit_context = tacit_context or [
        f"{node.label}: {node.description}"
        for node in nodes
        if node.status != "rejected" and node.type == "tacit_memory" and node.description
    ][:8]
    if tacit_context:
        routing.append("tacit_memory")
    if any(node.status != "rejected" and node.type == "plan_step" for node in nodes):
        routing.append("planning")

    return OntologyQueryAugmentation(
        expanded_terms=expanded_terms,
        filters={key: values[:12] for key, values in filters.items() if values},
        reasoning_lenses=lenses,
        tacit_context=tacit_context[:8],
        search_routing=routing or ["general_project_context"],
    )


def build_ontology_preview(project_id: int, request: BuildOntologyPreviewRequest) -> OntologyPreviewResponse:
    builder = OntologyBuilder(project_id)
    root_id, _ = _add_project_context(builder, request)
    _add_work_template(builder, root_id, request.work_template)
    _add_plan(builder, root_id, request.plan)
    tacit_context = _add_tacit_memory(builder, root_id, request.tacit_state)

    augmentation = _query_augmentation(builder, tacit_context)
    summary = (
        f"Ontology preview links {len(builder.nodes)} entities through {len(builder.edges)} relationships. "
        f"It can expand search with {len(augmentation.expanded_terms)} terms and route queries through "
        f"{', '.join(augmentation.search_routing)}."
    )
    return OntologyPreviewResponse(
        project_id=project_id,
        summary=summary,
        nodes=_stable_node_list(builder.nodes.values()),
        edges=_stable_edge_list(builder.edges.values()),
        query_augmentation=augmentation,
    )


def _build_paper_ontology_builder(project_id: int, request: BuildPaperOntologyRequest) -> Tuple[OntologyBuilder, str]:
    builder = OntologyBuilder(project_id)
    project_request = BuildOntologyPreviewRequest(
        persona_id=request.persona_id,
        query=request.query,
        objective_id=request.objective_id,
        objective_title=request.objective_title,
        objective_definition=request.objective_definition,
        project_goal=request.project_goal,
        project_end_product=request.project_end_product,
        project_target_host=request.project_target_host,
    )
    root_id, _ = _add_project_context(builder, project_request)
    paper_id = _add_paper_subgraph(builder, root_id, request)
    return builder, paper_id


def _paper_ontology_response(project_id: int, builder: OntologyBuilder, paper_id: str, *, sync_message: str = "") -> OntologyPreviewResponse:
    augmentation = _query_augmentation_from_items(list(builder.nodes.values()), list(builder.edges.values()))
    summary = (
        f"Paper ontology extracted {len(builder.nodes)} entities and {len(builder.edges)} relationships from "
        f"{builder.nodes.get(paper_id).label if builder.nodes.get(paper_id) else 'the selected paper'}."
    )
    return OntologyPreviewResponse(
        project_id=project_id,
        summary=summary,
        nodes=_stable_node_list(builder.nodes.values()),
        edges=_stable_edge_list(builder.edges.values()),
        query_augmentation=augmentation,
        persisted=False,
        sync_message=sync_message or summary,
    )


def build_paper_ontology(project_id: int, request: BuildPaperOntologyRequest) -> OntologyPreviewResponse:
    builder, paper_id = _build_paper_ontology_builder(project_id, request)
    return _paper_ontology_response(project_id, builder, paper_id)


async def build_paper_ontology_enriched(project_id: int, request: BuildPaperOntologyRequest) -> OntologyPreviewResponse:
    builder, paper_id = _build_paper_ontology_builder(project_id, request)
    source_refs = _source_ref_from_ids(request.finding.source_ids or {})
    extraction_mode = request.extraction_mode or "deterministic"
    if extraction_mode != "enriched":
        response = _paper_ontology_response(project_id, builder, paper_id)
        response.sync_message = (
            f"{response.summary} Used deterministic grounded extraction. "
            "Set extraction_mode='enriched' to add opt-in LLM suggestions."
        )
        return response

    extracted = await llm_paper_ontology_extraction(
        request.finding,
        project_goal=request.project_goal or "",
        project_end_product=request.project_end_product or "",
        project_target_host=request.project_target_host or "",
        query=request.query or "",
        objective_title=request.objective_title or "",
        objective_definition=request.objective_definition or "",
    )
    llm_entity_count = len(extracted.get("entities") or [])
    if llm_entity_count:
        _add_extracted_paper_ontology(builder, paper_id, extracted, source_refs, extraction_source="llm")
    response = _paper_ontology_response(project_id, builder, paper_id)
    response.sync_message = (
        f"{response.summary} Added {llm_entity_count} LLM-extracted typed entities on top of deterministic extraction."
        if llm_entity_count
        else f"{response.summary} Used deterministic typed extraction; LLM ontology extraction was unavailable or returned no entities."
    )
    return response


def ontology_response_from_graph(
    project_id: int,
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    *,
    persisted: bool,
    last_synced_at: Optional[str] = None,
    sync_message: str = "",
) -> OntologyPreviewResponse:
    validated_nodes = [OntologyNode.model_validate(node) for node in nodes]
    validated_edges = [OntologyEdge.model_validate(edge) for edge in edges]
    augmentation = _query_augmentation_from_items(validated_nodes, validated_edges)
    summary = (
        f"Stored ontology contains {len(validated_nodes)} entities and {len(validated_edges)} relationships. "
        f"It can expand search with {len(augmentation.expanded_terms)} terms and route queries through "
        f"{', '.join(augmentation.search_routing)}."
    )
    if last_synced_at:
        summary = f"{summary} Last synced: {last_synced_at}."
    return OntologyPreviewResponse(
        project_id=project_id,
        summary=summary,
        nodes=_stable_node_list(validated_nodes),
        edges=_stable_edge_list(validated_edges),
        query_augmentation=augmentation,
        persisted=persisted,
        sync_message=sync_message,
    )
