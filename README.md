# SECI Persona Studio

A research workspace that helps researchers find literature, compare experimental evidence, explore different interpretations, and bring their own experience into decisions about what to investigate next.

## Explore a completed example

The repository includes an **itaconic-acid production example** with two papers, 16 source passages, six experiment records, three specialist perspectives, and a review challenge. You can browse it without creating a project, installing Python, or running a language model:

```bash
cd frontend
npm ci
npm run dev
```

Open [the example](http://localhost:3000/examples/itaconate), or choose **Open example project** on the landing page. Select a plotted result to inspect its conditions and source, then open **Perspectives & history** to see the discussion. The saved comparison and perspectives were source-reviewed and edited; [example provenance](docs/example-project.md) explains their origin.

## What the interface helps researchers do

1. **Frame a research question.** Specify the product, host organism, goal, and context, then choose the investigation focus.
2. **Find and inspect evidence.** Retrieve candidate papers, prepare PDFs, inspect relevant passages, and compare reported interventions, conditions, and outcomes.
3. **Explore alternative interpretations.** Three LLM roles examine shared evidence from strain engineering, measurement and evidence, and process feasibility perspectives. A subsequent review challenges unsupported claims and identifies unresolved issues.
4. **Contribute knowledge the papers cannot supply.** Researchers can record equipment limits, practical constraints, and previous experience. Questions about missing paper facts are directed toward retrieval; unknown experimental effects require measurement.
5. **Keep decisions reviewable.** Researcher responses can produce scoped draft rules. Only confirmation changes which proposed actions remain eligible, and rules can be revoked. Discussion and decision history persist in SQLite.

The roles are predefined prompts using the configured model. The interface generates context-specific contributions and questions; it does not automatically discover a separate intent for each role. Agreement among roles is not counted as additional evidence.

## What SECI means

**SECI** stands for **Socialization, Externalization, Combination, and Internalization**, the four processes in [Nonaka’s model of knowledge creation](https://doi.org/10.1287/orsc.5.1.14). The design connects published knowledge with the experience researchers bring to a problem:

| Process | Meaning | How it informs this workspace |
| --- | --- | --- |
| Socialization | Sharing experience and practical knowledge | Discuss interpretations, limitations, and remembered cases. |
| Externalization | Making implicit knowledge explicit | Record the local constraint or experience behind a judgment. |
| Combination | Organizing explicit knowledge | Bring together source passages, experimental comparisons, and competing proposals. |
| Internalization | Learning through applying knowledge | Revisit recorded decisions and lessons when planning the next investigation. |

These are design principles. A saved note supports reflection and reuse; it is not a measurement of researcher learning.

## The geometry idea

The research motivation is to represent evidence by **what was studied and under which conditions**, so researchers can tell which findings belong in the same comparison. Two passages can use similar words while describing different strains, substrates, populations, or outcomes. The useful question is which missing detail would resolve that difference.

We explored information-geometric combinations of retrieval scores, followed by learned representations and graphs connecting source-backed findings. In the graph experiments, a question supplies an initial signal; diffusion or wave dynamics spread it through connections between findings to rank evidence. The connection must preserve experimental context: proximity or a strong propagated signal does not establish scientific support.

These are evaluated research components, rather than the mechanism behind every interface action. The results below include unsuccessful approaches: ordinary retrieval fusion beat the early geometric merge, and the later wave model did not establish an advantage over direct scoring or diffusion.

## What has been evaluated

| Evaluation | Data and comparison | Observed result |
| --- | --- | --- |
| Software smoke suite | Small bundled retrieval and extraction fixtures | 2/2 tasks passed in the saved run; checks the harness. |
| Early retrieval ablation | 10 SciFact queries, 5,183 documents | Query-only and ontology-augmented retrieval tied: Recall@10 **0.7500**, nDCG@10 **0.6849**. |
| Geometric retrieval | SciFact development set: 300 claims, 188 with gold evidence | Recall@5: rank fusion **0.906**, dense **0.869**, Fisher–Rao feedback **0.862**. |
| Context-sensitive passage retrieval | Evidence Inference: 985 additional questions from 252 papers, three seeds | Mixed ordinary/context negatives: Hit@1 **64.7%**, versus ordinary **61.7%** and context-only **58.5%**. |
| Evidence reconciliation | 48 questions from 24 previously unused Evidence Inference paper IDs | Reference matches: direct reader **41/48**, generic review **40/48**, repaired structured method **36/48**. |
| Learned evidence graph | 20 fresh TREC-PM cases, 480 papers | nDCG@10: direct **0.7108**, diffusion **0.7250**, wave **0.7186**; no established wave advantage. |

The [evaluation record](docs/evaluations.md) explains the baselines, sample boundaries, and later representation failures, and links to saved reports. Retrieval scores, benchmark-label agreement, and software checks measure different things. No completed researcher study establishes that the multi-role interface improves scientific decisions or reduces effort.

## Run the full workspace

Install Python 3.11+, Node.js, and Ollama. From the repository root:

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -r backend/requirements.txt
ollama pull qwen3.5:latest
ollama serve
```

If Ollama is already running, use the existing server. In a separate terminal with the Python environment activated:

```bash
cd backend
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Then start the frontend as shown above. Open [the workspace](http://localhost:3000); the API health endpoint is [localhost:8000/health](http://localhost:8000/health). Set `OLLAMA_MODEL` to use another installed model. Model choice and hardware affect generation speed and output quality.

The saved example remains available without Ollama. New retrieval, PDF preparation, and model-generated perspectives use the full backend workflow.

## Code map

| Path | Responsibility |
| --- | --- |
| [`frontend/src/app/`](frontend/src/app/) | Workspace, project navigation, and example page |
| [`frontend/src/examples/itaconate.json`](frontend/src/examples/itaconate.json) | Portable example data, without personal project history |
| [`backend/research_board.py`](backend/research_board.py) | Concurrent roles, review, questions, confirmed rules, and persistence |
| [`backend/evidence_grounding.py`](backend/evidence_grounding.py) | Source relevance and claim-support checks |
| [`backend/evidence_comparison.py`](backend/evidence_comparison.py) | Experimental facts, comparisons, and researcher context |
| [`backend/research_tools.py`](backend/research_tools.py) | Literature retrieval and PDF passage preparation |
| [`backend/evals/`](backend/evals/) | Retrieval and extraction evaluation runners |

See [workflow mechanics](docs/research-workflow-mechanics.md) for the evidence and decision rules, and [the algorithm map](docs/research-board-algorithm-map.md) for implementation details.

## Checks and packaging

```bash
cd backend
python -m unittest research_board_tests evidence_comparison_tests evidence_grounding_tests
python -m evals.run_suite --config evals/suites/local_smoke.json --output-dir data/eval_runs/local_smoke
```

From `frontend`, `npx tsc --noEmit` checks types and `npm run build` builds the web application. On Windows, `npm run desktop:dev` opens the Electron development app; `npm run desktop:dist:win` builds an installer into `frontend/dist`.

For Docker, copy `.env.example` to `.env`, review the settings, then run `docker compose up --build -d`. The five services are nginx, frontend, backend, worker, and Ollama. The supplied Ollama service requests NVIDIA GPU access; adapt it for a CPU-only host and pull the model configured in your environment. Runtime databases, interviews, model responses, and downloaded PDFs are excluded from source control.
