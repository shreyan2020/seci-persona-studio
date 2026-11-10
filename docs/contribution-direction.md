# Contribution direction: evidence-aware research resolution

## Product claim

Help a researcher move an underspecified biotech question toward an actionable decision by keeping evidence, project constraints, unresolved premises, and the next resolution step connected. Better models are replaceable reasoning engines within this workspace. The contribution to test is better allocation of research effort and human attention.

This is a product hypothesis, not an established scientific novelty or a demonstrated advantage over frontier models. A model with the same tools and records is the appropriate competitive baseline.

## Component decisions

| Component | Useful role | Recommendation |
| --- | --- | --- |
| Literature and source references | Let users inspect the basis of a claim | Keep; source-ID validity alone does not prove textual entailment |
| Persistent project memory and journey | Carry decisions and constraints across sessions | Keep; test retrieval and stale-context handling |
| Gap routing | Distinguish a user judgment from a missing measurement or document | Make central; expose the next resolution steps |
| Persona perspectives | Help inspect a problem from different roles | Optional exploration aid; do not count agreement as independent evidence |
| Multi-stage generation | Decompose work where it improves outcomes | Require an ablation before making each stage mandatory |
| Ontology | Useful if it enables a concrete consistency or dependency check | Retain existing features, avoid expanding schema for its own sake |
| EVSI and geometric scores | Inspect behavior under specified assumptions | Diagnostic; generated probabilities and losses are not calibrated benefits |
| Reports and drafts | Turn the workspace into usable outputs | Keep as outputs, not the central research contribution |
| Exact caching | Avoid repeating identical model work | Keep; semantic reuse needs its own correctness evaluation |

## Implemented slice

The existing literature-backed elicitation path previously required at least one user question. Valid analyses containing only experiment, retrieval, or workspace routes therefore raised an exception, with a possible generic fallback if the request allowed it.

Now valid non-user routing creates a successful resolution-only session, preserves the trace, and displays suggested resolution steps. It skips dynamic question generation and its possible numerical repair call. For N source mapping calls, the no-user path takes N+1 generation invocations instead of at least N+2. This is a structural call-count saving, not a measured latency or quality improvement. Exact caching may already avoid some actual inference work.

Empty or invalid routing still raises an error. An unresolved ask-user gap without usable questions still raises an error. A question must target a variable belonging to the same gap. Resolution-only sessions do not synthesize beliefs or decision actions, and the UI hides meaningless zero-valued uncertainty metrics. Finishing elicitation does not mean the research is complete.

The resolver routes and their rationales are still model proposals. Source identifiers are validated but scientific correctness and user ownership are not established by that validation. This change does not execute experiments, searches, or document inspections automatically. It applies to the literature-backed path; the no-literature path retains its existing behavior.

## Evaluation that can justify the contribution

Use expert-authored biotech decision cases containing source excerpts, project records, a concrete decision, and independently labeled missing premises. Include user-owned trade-offs, answerable document questions, missing experiments, conflicting studies, and already-resolved cases. Reserve cases and source sets for testing; do not treat model-generated labels as ground truth.

Compare (A) one strong model with the same context and tools, (B) the existing complete workflow, and (C) the workflow with resolution routing. Keep the model/version, available sources, user-answer oracle, and token budget fixed. Repeat across at least two model capabilities to test whether the workflow advantage persists with stronger reasoning. Add a no-persona ablation before claiming personas improve decisions.

Primary outcomes: unnecessary user interruptions per case, correct resolver selection, and blinded expert-rated decision adequacy. A reduction in questions counts as a benefit only if adequacy is preserved. Also record missed necessary questions, unsupported claims, model calls, tokens, elapsed time, and failure/fallback rates. Report paired case-level differences and bootstrap confidence intervals. Set an acceptable adequacy margin with experts before running the comparison.

The publishable hypothesis is that explicit routing of missing premises improves the allocation of human attention and research actions beyond a model-only baseline. Generic clarification, VOI, provenance, and multiple personas are not individually novel claims.

## Adjacent work checked

- Anthropic, Building effective agents: https://www.anthropic.com/engineering/building-effective-agents — recommends simple architectures and adding complexity when justified.
- Value of Information: A Framework for Human-Agent Communication: https://arxiv.org/abs/2601.06407 — prior work on utility/cost-based clarification; excludes a broad novelty claim for VOI questioning.

This is a targeted adjacent-work check, not an exhaustive novelty review.

## Verification

26 focused Python tests passed across resolution routing, epistemic harness, adaptive elicitation, and its benchmark tests. The new controlled regression exercises all eight non-user routes, verifies that question generation is skipped, and checks malformed and contradictory payload rejection. Frontend TypeScript checking passed. No live-model quality comparison or browser layout verification was performed.
