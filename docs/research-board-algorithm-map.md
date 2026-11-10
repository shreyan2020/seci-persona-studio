# Research board: current feature and algorithm map

This document describes the current implementation of the research-board subsystem: evidence preparation, experiment comparison, perspectives, conditional tacit elicitation, decision rules, persistence, and the UI/API orchestration around them.

It distinguishes three kinds of behavior:

- **Deterministic**: enforced by ordinary code and validation rules.
- **LLM-assisted**: proposed or classified by the configured Ollama model, then checked by code.
- **Hybrid**: an LLM proposes structured output and deterministic code accepts or rejects it.

Passing the tests verifies these software contracts. It does not establish that an LLM extraction is scientifically correct.

## System flow

```text
working question + project state
        |
        v
prepare/verify PDF passages
        |
        v
extract atomic facts --> conservatively link experiment records
        |                         |
        |                         v
        |                 researcher source review
        v
generate action catalog --> parallel role perspectives
        |                         |
        +------------+------------+
                     v
             fail-closed support audit
                     |
            surviving posts/actions?
              /                 \
            no                   yes
            |                     |
       partial board       review/challenges/questions
                                  |
                         researcher answer or comparison
                                  |
                             draft rule
                                  |
                         explicit confirm/reject
                                  |
                         action eligibility update
```

## Feature summary

| Feature | Current algorithmic pattern | Enforcement |
| --- | --- | --- |
| Board scoping | Canonical composite key | Deterministic |
| Preparation | Two-stage checkpointed pipeline | Deterministic |
| PDF provenance | SHA-256 content addressing + exact-span verification | Deterministic |
| Topic relevance | Conjunctive target-token filter at document level | Deterministic |
| Fact extraction | Schema-constrained LLM extraction | Hybrid |
| Ontology alignment | Small exact-match lookup | Deterministic |
| Experiment linking | LLM proposal + guarded record linkage | Hybrid |
| Transfer differences | Set comparison across records | Deterministic |
| Source review | Human confirmation/rejection state | Deterministic |
| Guided comparison | Validated finite choice workflow | Deterministic |
| Missing-evidence search | Privacy-bounded topic query | Hybrid/external search |
| Action catalog | Bounded LLM generation + ID/reference validation | Hybrid |
| Perspectives | Asynchronous fan-out/fan-in over three role prompts | Hybrid |
| Claim support | Batched fail-closed entailment audit | Hybrid |
| Challenges and next steps | LLM proposal + allow-list validation | Hybrid |
| Tacit question generation | Prompted proposal + structural gate | Hybrid, incomplete hard gate |
| Answer interpretation | Direct mapping or exact-quote LLM interpretation | Hybrid |
| Decision rules | Explicit finite-state machine | Deterministic |
| Persistence | Optimistic concurrency control + append-only history | Deterministic |
| UI orchestration | Stale-response guard + server revision chaining | Deterministic |

## 1. Board scoping and identity

**Current implementation:** `board_scope_key`, `key`, and the workspace-key construction in `frontend/src/app/page.tsx`.

The project/query context creates a workspace memory key. The persona suffix is replaced by `research-board`, so personas in the same project/query share the board. Entity IDs are content-derived SHA-256 prefixes, making identical inputs stable and duplicate-resistant.

**Algorithm:** canonicalization plus content-addressed identifiers.

```text
FUNCTION board_scope(memory_key):
    RETURN replace_final_persona_suffix(memory_key, "research-board")

FUNCTION stable_id(prefix, value):
    canonical_json = JSON_ENCODE(value, sort_keys=true)
    digest = SHA256(canonical_json)
    RETURN prefix + "_" + first_20_hex_characters(digest)
```

## 2. Evidence-preparation orchestration

**Current implementation:** `prepareBoardStages` in `frontend/src/features/biotech-workspace/lib/prepare-evidence.ts`.

“Prepare evidence” runs comparison first and perspectives second. Each returned board is saved to UI state before the next request, and the next request uses the new server revision. If comparison succeeds but perspective generation fails, the comparison remains saved.

**Algorithm:** checkpointed sequential pipeline with context cancellation.

```text
FUNCTION prepare_board(board, workspace, state):
    current = board

    FOR stage IN [COMPARE, START_PERSPECTIVES]:
        IF active_screen_changed():
            RETURN cancelled

        result = POST(stage,
            workspace_key=workspace,
            expected_revision=current.revision OR 0,
            explicit_state=state)

        IF active_screen_changed():
            RETURN cancelled

        current = result.board
        save_current_board_to_UI(current)

    RETURN complete
```

## 3. Verified PDF evidence

**Current implementation:** `verified_pdf_evidence` in `backend/research_board.py` and `paper_evidence_root` in `backend/paper_storage.py`.

Only annotations marked `pdf_passage` are candidates. The server searches its PDF store, recomputes each original PDF’s SHA-256, parses only required pages, stops at a page headed “References,” and accepts a quote only if its normalized text is found on the annotated page. A matching quote proves location, not the truth of a later interpretation.

**Algorithm:** content-addressed provenance verification with bounded PDF parsing.

```text
FUNCTION verify_pdf_evidence(workspace_state, pdf_root):
    requested = group annotations by source_sha256
    accepted = []

    FOR original_pdf IN pdf_root/*/*/original.pdf:
        digest = SHA256_STREAM(original_pdf)
        IF digest not requested OR digest already processed:
            CONTINUE

        needed_pages = pages requested for digest
        parsed_pages = {}

        FOR page IN original_pdf:
            IF page heading equals "References":
                BREAK
            IF page.number IN needed_pages:
                parsed_pages[page.number] = NORMALIZE(page.text)

        FOR annotation IN requested[digest]:
            quote = CLEAN(annotation.snippet)
            IF NORMALIZE(quote) is substring of parsed_pages[annotation.page]:
                accepted.ADD(BoardEvidence(
                    id=stable_id(digest, page, quote),
                    source_id=stable_id(digest),
                    quote=quote,
                    page=annotation.page))

    RETURN accepted in original annotation order
```

## 4. Target-product relevance screening

**Current implementation:** `relevant_evidence` in `backend/evidence_grounding.py`.

The target product is tokenized into required terms. Evidence is grouped by paper. A paper remains eligible only if all required target-product tokens occur somewhere in its verified quotes plus first-page document context. Client labels and generated summaries do not establish relevance.

**Algorithm:** document-level conjunctive lexical filter.

```text
FUNCTION relevant_evidence(state, evidence):
    required_tokens = TARGET_PRODUCT_TOKENS(state.project.end_product)
    IF required_tokens is empty:
        RETURN evidence

    papers = GROUP_BY(evidence, source_id)
    eligible_papers = []

    FOR paper IN papers:
        observed = TOKENIZE(CONCAT(paper.quotes, paper.document_context))
        IF required_tokens is subset of observed:
            eligible_papers.ADD(paper.id)

    RETURN evidence where source_id IN eligible_papers
```

## 5. Atomic experiment-fact extraction

**Current implementation:** `build_comparison` and `accept_facts` in `backend/evidence_comparison.py`.

The LLM receives at most six papers and eight passages per paper. It proposes atomic facts in a fixed schema: dimension, exact value, intervention type, and explicit link anchors. Code then checks that values and anchors are literal substrings of the cited quote. Measurements must contain a number and a recognized unit pattern. A non-intervention dimension cannot carry a genetic/process intervention label.

**Algorithm:** bounded map extraction followed by exact-span validation.

```text
FUNCTION extract_facts(evidence):
    facts = []

    FOR paper IN first_6(GROUP_BY(evidence, source_id)):
        response = LLM_EXTRACT(first_8(paper.passages), schema=ExperimentFact)

        FOR proposal IN first_48(response.facts):
            IF proposal.evidence_id not in supplied_passages:
                REJECT
            IF proposal.dimension not allowed:
                REJECT
            IF proposal.value not exact substring of cited_quote:
                REJECT
            IF measurement AND lacks_number_or_unit(proposal.value):
                REJECT

            anchors = only anchors whose exact value occurs in cited_quote
            intervention_type = proposal.intervention_type
            IF proposal.dimension != "intervention":
                intervention_type = "none"

            facts.ADD(content_addressed_fact(proposal, anchors))

    RETURN deduplicate_by_fact_id(facts)
```

## 6. Fed-batch and comparator semantics

**Current implementation:** extraction prompt plus deterministic dimension handling in `accept_facts`.

The prompt tells the model that fed-batch is a cultivation setting unless a changed feeding treatment is explicit. Deterministically, any fact whose dimension is not `intervention` has its intervention type forced to `none`. Comparators are represented as reported baselines; neither extraction nor linking turns their presence into a causal claim.

**Algorithm:** semantic constraint plus type normalization.

```text
IF extracted_dimension != INTERVENTION:
    intervention_type = NONE

DISPLAY comparator AS "reported baseline"
DO NOT derive "intervention caused outcome" from comparator presence
```

## 7. Small ontology alignment

**Current implementation:** `ontology_terms` in `backend/evidence_comparison.py`.

Broad roles receive fixed OBI/BFO tags. Carbon-source values receive ChEBI mappings only for exact lexical recognition of glucose or glycerol. Tags are metadata and do not validate facts or links.

**Algorithm:** deterministic rule-based lookup.

```text
FUNCTION ontology_terms(dimension, value):
    terms = []

    IF dimension IN [host, carbon_source]:
        terms.ADD(BFO material entity)
    IF dimension IN [titer, yield, productivity]:
        terms.ADD(OBI assay)
    IF dimension IN [intervention, cultivation]:
        terms.ADD(OBI planned process)

    IF dimension == carbon_source AND word "glucose" occurs:
        terms.ADD(CHEBI:17234)
    IF dimension == carbon_source AND word "glycerol" occurs:
        terms.ADD(CHEBI:17754)

    RETURN terms
```

## 8. Experiment-record linking

**Current implementation:** the linking pass in `build_comparison` and deterministic `accept_links`.

The LLM proposes groups of fact IDs. A group is rejected if it mixes distinct carbon-source values, distinct cultivation values, or both genetic and process interventions. Facts from multiple passages must come from one paper and every fact must contain the same explicit anchor `(kind, normalized value)`. Allowed anchors are strain, condition, figure, or table. Unused facts remain as unresolved one-fact records.

**Algorithm:** guarded record linkage with a shared-key join.

```text
FUNCTION link_experiments(facts, evidence, proposals):
    records = []
    used = SET()

    FOR proposal IN proposals:
        selected = valid unused facts named by proposal
        IF selected is empty:
            CONTINUE
        IF multiple distinct carbon_source values:
            REJECT proposal
        IF multiple distinct cultivation values:
            REJECT proposal
        IF mixes genetic and process interventions:
            REJECT proposal

        passage_ids = UNIQUE(selected.evidence_id)
        IF count(passage_ids) > 1:
            IF facts span multiple papers:
                REJECT proposal
            anchor = proposal.link_anchor
            IF anchor.kind not in [strain, condition, figure, table]:
                REJECT proposal
            IF same normalized anchor absent from any selected fact:
                REJECT proposal
            status = LINKED
        ELSE:
            status = SINGLE_PASSAGE

        records.ADD(record(selected, status))
        used.ADD(selected.ids)

    FOR fact NOT IN used:
        records.ADD(one_fact_record(fact, status=UNRESOLVED))

    RETURN records
```

## 9. Experiment category and transfer differences

**Current implementation:** `_category` and the final pass of `accept_links`.

A record is a pathway change if it includes a genetic intervention, a cultivation change if it includes a process intervention or cultivation fact, and otherwise unresolved. The system compares the sets of carbon-source and cultivation values across records and adds a difference warning when sets differ.

**Algorithm:** priority rule classification plus pairwise set contrast.

```text
FUNCTION category(record):
    IF record has genetic intervention:
        RETURN PATHWAY
    IF record has process intervention OR cultivation fact:
        RETURN CULTIVATION
    RETURN UNRESOLVED

FOR each record:
    FOR dimension IN [carbon_source, cultivation]:
        mine = normalized values in record
        others = normalized values in all other records
        IF mine exists AND others exists AND mine != others:
            record.differences.ADD(dimension + " differs")
```

## 10. Human source review and rejection cascade

**Current implementation:** `/compare-choice` in `backend/research_board_api.py`.

A fact starts `unreviewed`. The researcher can confirm or reject it. Rejecting a fact withdraws dependent draft rules, revokes dependent confirmed rules, removes the fact from experiment records, deletes empty records, and downgrades a formerly cross-passage link if only one passage remains.

**Algorithm:** dependency-aware invalidation.

```text
FUNCTION review_fact(fact_id, decision):
    fact.review = decision

    IF decision == REJECTED:
        dependent_judgments = judgments using fact_id
        dependent_rules = rules derived from dependent_judgments

        FOR rule IN dependent_rules:
            IF rule is draft: REJECT rule
            IF rule is confirmed: REVOKE rule

        FOR record containing fact_id:
            REMOVE fact_id
            RECOMPUTE evidence_refs
            IF linked record now has fewer than 2 passages:
                status = SINGLE_PASSAGE
                clear link anchors

        DELETE empty records
```

## 11. Guided researcher comparison

**Current implementation:** `guided_judgment` and `EvidenceComparisonPanel`.

The user can compare a confirmed fact with their setup using fixed choices: same, different, unavailable, or unknown. The basis is current setup, past case, or uncertainty. Past cases require a cue, response, and revisit condition. Unknown/uncertain judgments cannot allow or exclude an action. They may only save context or request measurement.

**Algorithm:** validation-driven finite choice workflow.

```text
FUNCTION save_comparison(fact, relation, basis, consequence, actions):
    REQUIRE fact.review == CONFIRMED
    REQUIRE relation and basis are allowed values

    IF basis == PAST_CASE:
        REQUIRE cue, response, exception are selected

    IF relation == UNKNOWN OR basis == UNCERTAIN:
        FORBID consequence IN [ALLOW, AVOID]

    IF consequence IN [ALLOW, AVOID]:
        REQUIRE one or more valid action IDs
    ELSE:
        actions = []

    judgment = content_addressed_judgment(all selections)
    APPEND judgment and researcher post unless duplicate

    IF consequence == MEASURE:
        ADD resolution step RUN_EXPERIMENT
    IF consequence IN [ALLOW, AVOID]:
        CREATE already-answered board question
        CREATE draft decision rule
```

## 12. Missing-evidence search

**Current implementation:** `/gap-sources` in `backend/research_board_api.py`.

The search string uses only public topic fields: end product, target host, and selected comparison dimension. Project goals, recalled cases, and local judgments are deliberately excluded. Results are candidates requiring later full-text review.

**Algorithm:** privacy-bounded query construction plus federated literature search.

```text
FUNCTION find_gap_sources(board, dimension):
    REQUIRE board.project.end_product exists

    query = JOIN(
        board.project.end_product,
        board.project.target_host,
        label(dimension))

    results = SEARCH_LITERATURE(query, max_results=3)
    STORE title, DOI, PMID, scope, reason, provider sources
    STORE provider errors as warnings
```

## 13. Action-catalog generation

**Current implementation:** first phase of `generate_board`.

Evidence is interleaved round-robin across papers, capped at ten passages, so a prolific first paper does not consume the entire prompt. If no catalog already exists, the LLM proposes two to three actions. Code requires valid evidence IDs, removes normalized duplicate labels, creates stable action IDs, and aborts if fewer than two distinct actions remain.

**Algorithm:** round-robin evidence sampling plus constrained candidate generation.

```text
FUNCTION generate_action_catalog(evidence):
    by_paper = GROUP_BY(evidence, source_id)
    prompt_evidence = ROUND_ROBIN(by_paper, limit=10)

    IF existing action catalog is empty:
        proposals = LLM_GENERATE_ACTIONS(prompt_evidence)
        seen = SET()

        FOR proposal IN first_4(proposals):
            label_key = normalize_without_articles_or_punctuation(proposal.label)
            refs = proposal.refs intersect supplied_evidence_ids
            IF label empty OR refs empty OR label_key in seen:
                CONTINUE
            ADD action(stable_id(label_key), proposal.label, refs)
            seen.ADD(label_key)

        REQUIRE at least 2 actions

    RETURN catalog
```

## 14. Independent role perspectives

**Current implementation:** nested `perspective` function and `asyncio.TaskGroup` in `generate_board`.

Three role prompts—strain engineering, measurement/evidence, and process feasibility—run concurrently. None sees another current-round response. Each must cite one exact catalog action and verified evidence, identify a supporting experiment comparison, and state a transfer limitation. Invalid or failed role outputs are recorded as rejected proposals.

**Algorithm:** asynchronous fan-out/fan-in with independent contexts.

```text
FUNCTION generate_perspectives(context, actions):
    tasks = []

    FOR role IN [STRAIN, MEASUREMENT, PROCESS]:
        tasks.ADD(ASYNC LLM_PERSPECTIVE(role, context, actions))

    results = AWAIT_ALL(tasks)

    FOR result IN results:
        IF result has valid evidence refs, nonempty text, exact action_id:
            APPEND perspective post
        ELSE:
            board.status = PARTIAL
            APPEND rejection diagnostic
```

## 15. Fail-closed claim-support audit

**Current implementation:** `supported_items` and `structural_problem` in `backend/evidence_grounding.py`.

Actions and perspectives first receive deterministic checks for valid references, false multi-paper language, and unsupported assertions about local capability. Remaining items are audited by the LLM in batches of at most two. Every item must receive exactly one Boolean decision with a reason. Malformed, missing, timed-out, or unsupported checks reject the item. Unsupported actions are deleted; posts tied to deleted actions are also deleted.

**Algorithm:** structural prefilter plus batched fail-closed entailment classification.

```text
FUNCTION supported_items(items, evidence, researcher_accounts):
    candidates = []

    FOR item IN items:
        IF references missing or invalid:
            REJECT with diagnostic
        ELSE IF claims multiple papers but cites fewer than two papers:
            REJECT with diagnostic
        ELSE IF asserts local capability/history without account:
            REJECT with diagnostic
        ELSE:
            candidates.ADD(item)

    accepted = SET()
    FOR batch IN chunks(candidates, size=2):
        TRY:
            checks = LLM_AUDIT_EACH_ITEM(batch, cited_quotes, accounts)
            FOR item IN batch:
                IF exactly_one_well_formed_check(item) AND check.supported == TRUE:
                    accepted.ADD(item.id)
                ELSE:
                    REJECT with reason
        CATCH any error:
            REJECT entire batch

    RETURN accepted
```

## 16. Partial-board behavior

**Current implementation:** filtering and early return in `generate_board`.

If any action or post fails support review, board status becomes `partial`. If no current perspective survives, the system preserves the comparison, adds a literature-search resolution step, and returns before challenges or tacit questions are generated. It does not insert stock content.

**Algorithm:** fail-closed degradation with preserved prior stage.

```text
supported = supported_items(actions + current_perspectives)
DELETE unsupported actions
DELETE unsupported perspectives
DELETE perspectives whose action was deleted

IF anything was rejected:
    status = PARTIAL

IF no current perspective remains:
    ADD resolution step SEARCH_LITERATURE
    RETURN board_with_saved_comparison
```

## 17. Evidence challenges and resolution routing

**Current implementation:** second review prompt in `generate_board` and `accept_review`.

The model may propose challenges and one of four resolver types: inspect workspace, search literature, run experiment, or compare evidence. Challenge text is support-audited before acceptance. Code requires a valid target post and verified evidence reference.

**Algorithm:** allow-listed routing plus referential-integrity validation.

```text
review = LLM_REVIEW(actions, perspectives, evidence, context)
audited = SUPPORT_AUDIT(review.questions + review.challenges)

FOR challenge IN audited.challenges:
    IF challenge.reply_to is existing post
       AND challenge has valid evidence refs
       AND challenge.text not empty:
        APPEND challenge post

FOR step IN review.resolution_steps:
    IF step.resolver IN allowed_resolvers:
        APPEND cleaned step
```

## 18. Conditional tacit-knowledge question generation

**Current implementation:** review prompt in `generate_board`, support audit, then structural acceptance in `accept_review`.

The model is instructed to ask only about unresolved preferences, local constraints, or past experiences that could exclude an action; paper facts route to retrieval and empirical unknowns route to experiments. The support auditor checks the question against cited evidence. Deterministic acceptance then requires valid evidence, source posts, exact action IDs, an allowed ownership type, `unresolved=true`, ownership rationale, and a reason retrieval cannot answer it. Evidence must be inherited from the cited source posts. Questions whose rationale says measurement/experimentation/optimization is required are rejected and routed to `run_experiment`. Questions are deduplicated by decision plus affected action IDs.

**Important current limitation:** there is no separate deterministic function that proves (1) the exact requirement is encoded in a linked experiment record, (2) the local capability is absent from every workspace field, and (3) different possible answers would switch the selected next action. Those three conditions are currently mostly prompt-gated and support-audited rather than formally computed.

**Algorithm:** LLM proposal plus structural eligibility gate; not yet a formal decision-switch algorithm.

```text
FUNCTION accept_tacit_question(proposal, board):
    refs = valid evidence IDs
    posts = valid source post IDs
    actions = valid exact catalog action IDs

    REMOVE actions already covered by confirmed rules

    IF why_not_retrieve says measurement/experiment/optimization needed:
        REJECT question
        ADD resolution step RUN_EXPERIMENT
        RETURN

    REQUIRE refs, posts, actions are nonempty
    REQUIRE ownership IN [preference, local_constraint, experience]
    REQUIRE unresolved == TRUE
    REQUIRE ownership_rationale and why_not_retrieve are nonempty
    REQUIRE refs are subset of evidence cited by source posts

    question_id = HASH(decision_key, sorted(actions))
    IF same active question already exists:
        RETURN
    IF confirmed rule already resolves all actions:
        RETURN

    question_text = proposed concrete question if it ends with "?"
                    else generic local-constraint fallback
    APPEND pending question
```

## 19. Question answering and experience interpretation

**Current implementation:** `answer_board`.

Direct “keep” and “exclude” answers map deterministically to draft rules. “Unsure” defers and creates no rule. A free-text past case is interpreted by the LLM, but a rule is accepted only if it has an allow/avoid effect, a nonempty statement, and an exact quote copied from the user’s account. The model may abstain.

**Algorithm:** guarded branching plus exact-substring attribution.

```text
FUNCTION answer_question(question, answer_type, text):
    REQUIRE question.status == PENDING
    APPEND researcher reply post

    IF answer_type == UNSURE OR text begins with explicit uncertainty:
        question.status = DEFERRED
        ADD INSPECT_WORKSPACE resolution step
        RETURN without rule

    IF answer_type IN [ALLOW, AVOID]:
        effect = answer_type
        statement = deterministic action statement
        quote = displayed answer

    IF answer_type == EXPERIENCE:
        REQUIRE text length >= 12
        interpretation = LLM_INTERPRET_EXPERIENCE(text, actions)
        IF interpretation.abstain:
            question.status = DEFERRED
            RETURN
        REQUIRE effect IN [ALLOW, AVOID]
        REQUIRE user_quote is exact substring of text
        REQUIRE statement not empty

    question.status = ANSWERED
    APPEND draft decision rule(effect, action_ids, user_quote)
```

## 20. Decision-rule lifecycle and action eligibility

**Current implementation:** `review_rule`, `apply_rules`, and `confirmed_rule_context`.

Draft rules do not affect actions. Only explicit confirmation applies them. A confirmed `avoid` rule excludes its actions; `allow` keeps them eligible but does not override a conflicting confirmed avoid rule. Conflicting confirmation is rejected until the existing rule is explicitly revoked. Rules are scoped to one decision key.

**Algorithm:** explicit finite-state machine plus deterministic policy evaluation.

```text
STATE TRANSITIONS:
    draft --confirm--> confirmed
    draft --reject--> rejected
    confirmed --revoke--> revoked
    all other transitions are invalid

FUNCTION confirm_rule(rule):
    REQUIRE rule.decision_key == board.decision_key
    REQUIRE no confirmed opposite-effect rule overlaps rule.action_ids
    rule.status = CONFIRMED
    APPLY_RULES()

FUNCTION apply_rules():
    FOR action IN actions:
        applicable = confirmed rules for current decision containing action.id
        action.applied_rule_ids = applicable.ids
        action.disposition = EXCLUDED if any applicable effect == AVOID
                             else ELIGIBLE
```

## 21. Researcher comments

**Current implementation:** `/comment` in `backend/research_board_api.py`.

A comment must reply to an existing post. It is stored as a researcher post and inherits the target post’s evidence references. It is context, not independent PDF evidence and not a decision rule.

**Algorithm:** validated threaded append.

```text
FUNCTION add_comment(reply_to, text):
    target = find existing post(reply_to)
    REQUIRE target exists and cleaned text is nonempty

    APPEND BoardPost(
        kind=USER,
        reply_to=target.id,
        evidence_refs=target.evidence_refs,
        text=clean(text))
```

## 22. Persistence and concurrent edits

**Current implementation:** `BoardRepository` and request `expected_revision` checks.

The latest board is stored as JSON in SQLite. Every mutation starts an immediate transaction, compares the stored revision with the request revision, increments on success, updates the current snapshot, and writes the same payload to append-only history. Stale requests return HTTP 409.

**Algorithm:** optimistic concurrency control with transactional compare-and-swap.

```text
FUNCTION save(board, expected_revision):
    BEGIN IMMEDIATE TRANSACTION
    actual_revision = SELECT revision for workspace OR 0

    IF actual_revision != expected_revision:
        ROLLBACK
        RAISE conflict

    board.revision = actual_revision + 1
    UPSERT latest board JSON
    INSERT immutable history(workspace, revision, board JSON)
    COMMIT
    RETURN board
```

## 23. UI stale-state protection and presentation

**Current implementation:** `ResearchBoardPanel` and `EvidenceComparisonPanel`.

The UI records a scope string containing workspace and normalized query. An in-flight request is ignored if the user switches context before it finishes. The board is marked stale when its saved query differs from the current question. Experiment records are grouped into pathway, cultivation, and unresolved sections; source details expand on demand. Discussion and diagnostics are separate tabs/details.

**Algorithm:** request-scope token plus derived-view grouping.

```text
FUNCTION mutate_from_UI(operation, payload):
    IF another request is running:
        RETURN

    request_scope = current_workspace + normalized_query
    result = POST(operation, expected_revision=current_board.revision)

    IF current_scope == request_scope:
        replace_UI_board(result.board)
    ELSE:
        discard response as stale

FUNCTION render_experiments(records):
    pathway = records where category == PATHWAY
    cultivation = records where category == CULTIVATION
    unresolved = records where category == UNRESOLVED
    render compact cards with baseline, outcomes, differences
    render exact sources only when expanded
```

## 24. Confirmed-rule propagation back into the workspace

**Current implementation:** `confirmedBoardRules`, `boardRuleAnswers`, and `explicitWorkspaceState` in `frontend/src/app/page.tsx`.

Only confirmed rules for the current board workspace, exact current question, grounding version, and decision key are copied into the wider workspace state. They appear both as structured `confirmed_research_rules` and as labeled clarification answers. Draft/rejected/revoked rules do not propagate.

**Algorithm:** scope-filtered state projection.

```text
FUNCTION rules_for_workspace(board, current_workspace, current_question):
    IF board.version is old
       OR board.workspace_key != current_workspace
       OR board.query != normalize(current_question):
        RETURN []

    RETURN rules where status == CONFIRMED
                 AND decision_key == board.decision_key

explicit_workspace_state.confirmed_research_rules = selected_rules
explicit_workspace_state.clarifying_answers += readable projections(selected_rules)
```

## What the system does not currently implement

- No causal-inference algorithm: a comparator does not establish causality.
- No calibrated probability, utility, VOI, or EVSI calculation in the research board.
- No automatic selection of a single “best” action.
- No deterministic semantic proof that an LLM-extracted exact span has been interpreted correctly.
- No complete deterministic gate for conditional tacit-question generation.
- No automatic rule application from model agreement; researcher confirmation is required.
- No cross-paper experiment linking.

## Primary source files

- `backend/research_board.py`
- `backend/research_board_api.py`
- `backend/evidence_grounding.py`
- `backend/evidence_comparison.py`
- `backend/comparison_models.py`
- `backend/paper_storage.py`
- `frontend/src/features/biotech-workspace/lib/prepare-evidence.ts`
- `frontend/src/features/biotech-workspace/components/ResearchBoardPanel.tsx`
- `frontend/src/features/biotech-workspace/components/EvidenceComparisonPanel.tsx`
- `frontend/src/features/biotech-workspace/board-types.ts`
- `frontend/src/app/page.tsx`
