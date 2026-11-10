"""A current projection of source facts and researcher context, without inferred biology."""
from models import OntologyNode, OntologyEdge
from research_board import key


def board_knowledge(board):
    nodes, edges = {}, []
    def node(id, type, label, refs=(), **attributes):
        nodes[id] = OntologyNode(id=id, type=type, label=label, source_refs=list(refs),
            attributes={"workspace_key":board.workspace_key, "board_revision":board.revision, **attributes})
    def edge(source, target, relation, refs=()):
        edges.append(OntologyEdge(id=key('kb_edge',[source,target,relation]),source=source,
            target=target,relation=relation,evidence=list(refs)))
    for evidence in board.evidence:
        node(evidence.source_id,'paper',evidence.citation,source_sha256=evidence.source_sha256)
        node(evidence.id,'source_passage',f'Page {evidence.page}',[evidence.source_id],
            quote=evidence.quote,page=evidence.page,origin='published_source')
        edge(evidence.source_id,evidence.id,'contains_passage')
    valid = {f.id for f in board.experiment_facts if f.review != 'rejected'}
    for fact in board.experiment_facts:
        if fact.id not in valid:
            continue
        node(fact.id,'experimental_fact',fact.value,[fact.evidence_id],dimension=fact.dimension,
            review=fact.review,origin='source_extraction',terms=[t.model_dump() for t in fact.ontology_terms])
        edge(fact.evidence_id,fact.id,'reports',[fact.evidence_id])
    for record in board.experiment_records:
        ids=[id for id in record.fact_ids if id in valid]
        if not ids: continue
        node(record.id,'experiment_record',record.title,record.evidence_refs,link_status=record.link_status)
        for id in ids: edge(record.id,id,'has_reported_detail',record.evidence_refs)
    for judgment in board.comparison_judgments:
        if judgment.row_id not in valid: continue
        node(judgment.id,'researcher_context',judgment.statement,[judgment.row_id],origin='researcher',basis=judgment.basis)
        edge(judgment.id,judgment.row_id,'compares_with_local_setup')
    for rule in board.rules:
        if rule.status != 'confirmed': continue
        node(rule.id,'decision_rule',rule.statement,origin='researcher_confirmed',scope=rule.scope)
        for aid in rule.action_ids:
            action=next((a for a in board.actions if a.id==aid),None)
            if action:
                node(aid,'proposed_action',action.label,action.evidence_refs,origin='model_proposal')
                edge(rule.id,aid,rule.effect)
    return {'nodes':[n.model_dump() for n in nodes.values()], 'edges':[e.model_dump() for e in edges]}
