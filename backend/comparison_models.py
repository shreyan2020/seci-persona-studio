from typing import Literal
from pydantic import BaseModel, Field

Dimension = Literal['host', 'intervention', 'comparator', 'carbon_source', 'cultivation', 'titer', 'yield', 'productivity', 'limitation']
ExperimentCategory = Literal['pathway', 'cultivation', 'unresolved']
AnchorKind = Literal['strain', 'condition', 'figure', 'table']


class OntologyTerm(BaseModel):
    """A terminology alignment, never evidence that a relation is true."""
    namespace: Literal['OBI', 'ChEBI', 'BFO']
    term_id: str
    label: str


class LinkAnchor(BaseModel):
    kind: AnchorKind
    value: str


class ExperimentFact(BaseModel):
    """One exact-span fact that remains independently traceable to a passage."""
    id: str
    evidence_id: str
    dimension: Dimension
    value: str
    anchors: list[LinkAnchor] = Field(default_factory=list)
    intervention_type: Literal['genetic', 'process', 'none'] = 'none'
    ontology_terms: list[OntologyTerm] = Field(default_factory=list)
    review: Literal['unreviewed', 'confirmed', 'rejected'] = 'unreviewed'


class ExperimentRecord(BaseModel):
    """Facts linked only by an explicit, source-visible experiment anchor."""
    id: str
    title: str
    category: ExperimentCategory
    fact_ids: list[str]
    evidence_refs: list[str]
    link_anchors: list[LinkAnchor] = Field(default_factory=list)
    link_status: Literal['single_passage', 'linked', 'unresolved']
    important_differences: list[str] = Field(default_factory=list)

class EvidenceCell(BaseModel):
    value: str
    review: Literal['unreviewed', 'confirmed', 'rejected'] = 'unreviewed'

class EvidenceRow(BaseModel):
    """Legacy passage row retained for persisted-board compatibility."""
    id: str
    evidence_id: str
    cells: dict[Dimension, EvidenceCell] = Field(default_factory=dict)

class GuidedJudgment(BaseModel):
    id: str
    row_id: str
    dimension: Dimension
    relation: Literal['same', 'different', 'unavailable', 'unknown']
    basis: Literal['setup', 'past_case', 'uncertain']
    cue: str = ''
    response: str = ''
    exception: str = ''
    consequence: Literal['context', 'measure', 'allow', 'avoid'] = 'context'
    action_ids: list[str] = Field(default_factory=list)
    statement: str
    detail: str = ''
