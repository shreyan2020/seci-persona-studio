# SECI Persona Studio

A research workspace for finding papers, comparing experimental evidence, and deciding what to investigate next. Researchers can inspect source passages, explore three specialist perspectives, and bring their own laboratory experience into the discussion.

## Try the example

The included itaconic-acid project contains two papers, six experiment records, three specialist perspectives, and a review challenge. It is ready to browse without a backend or language model:

```bash
cd frontend
npm ci
npm run dev
```

Open [localhost:3000/examples/itaconate](http://localhost:3000/examples/itaconate), or select **Open example project** on the home page. Select a result to inspect its conditions and source, then open **Perspectives & history** to follow the discussion. The saved comparisons and perspectives were source-reviewed and edited; see [example provenance](docs/example-project.md).

## How it works

1. Create a project and frame a research question.
2. Find papers, prepare their PDFs, and compare reported interventions, conditions, and outcomes alongside their source passages.
3. Gather perspectives from three concurrent LLM roles: strain engineering, measurement and evidence, and process feasibility. A review stage challenges their proposals and identifies questions that need researcher input.
4. Add practical constraints or previous experience. Review any resulting draft rule before confirming how it affects the proposed actions; confirmed rules can be revoked.

The workspace saves the evidence, discussion, and decision history in SQLite. The [architecture guide](docs/architecture.md) maps this workflow to the implementation.

## SECI

SECI stands for **Socialization, Externalization, Combination, and Internalization**, from [Nonaka’s model of knowledge creation](https://doi.org/10.1287/orsc.5.1.14). It informs how the workspace connects published evidence with researchers’ practical knowledge:

- **Socialization:** discuss interpretations and previous experience.
- **Externalization:** record the constraint or observation behind a judgment.
- **Combination:** bring source passages, experiment records, and competing proposals together.
- **Internalization:** revisit recorded decisions and lessons when planning later work.

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

Use the existing Ollama server if it is already running. In another terminal, activate the Python environment and start the API:

```bash
cd backend
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Start the frontend as above and open [localhost:3000](http://localhost:3000). Set `OLLAMA_MODEL` to use another installed model. Optional model and deployment settings are described in the [architecture guide](docs/architecture.md).

## Development

The frontend is a Next.js application; the backend uses FastAPI, SQLite, and Ollama. Tests cover source verification, experiment linking, role orchestration, confirmed rules, persistence, and frontend state handling.

```bash
# From backend/
python -m unittest discover -s tests -p "test_*.py"

# From frontend/
npm test
npm run build
```

See [testing](docs/testing.md) for coverage and [Electron setup](frontend/ELECTRON.md) for the desktop application. Runtime databases, interviews, downloaded PDFs, and model responses are excluded from Git.
