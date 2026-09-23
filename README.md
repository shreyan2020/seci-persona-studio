# SECI Persona Studio

A research workspace for turning an underspecified biotech question into a project with literature evidence, explicit judgments, and working drafts. Users explore questions through collaborator personas, inspect evidence, and retain context as a project develops.

The application combines a Next.js interface, a FastAPI backend, local models through Ollama, and an Electron desktop shell. It also includes retrieval and extraction evaluation tools.

## Explore the code

| Path | Purpose |
| --- | --- |
| [`frontend/`](frontend/) | Research interface and Electron application |
| [`backend/`](backend/) | Project state, literature workflows, reasoning, and report generation |
| [`backend/evals/`](backend/evals/) | Retrieval and extraction evaluation runners |
| [`docker-compose.yml`](docker-compose.yml) | Server deployment with a report worker and Ollama |

## Run locally

Install Python 3.11+, Node.js, and Ollama. From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
cd frontend
npm ci
```

Start Ollama and pull the model used by the backend:

```bash
ollama pull qwen2.5:7b-instruct
ollama serve
```

If Ollama is already running, a second server is unnecessary. Start the API from the repository root in a separate terminal with the virtual environment activated:

```bash
python -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Then start the interface in another terminal:

```bash
cd frontend
npm run dev
```

Open `http://localhost:3000`. The API health endpoint is `http://127.0.0.1:8000/health`.

## Evaluate without a model server

The bundled smoke suite runs retrieval and extraction checks on small local fixtures:

```bash
cd backend
python -m evals.run_suite --config evals/suites/local_smoke.json --output-dir data/eval_runs/local_smoke
```

See the [evaluation guide](backend/evals/README.md) for data formats, metrics, and larger benchmark configurations. Passing the fixture suite checks the evaluation pipeline; it does not establish the quality of generated research findings.

## Desktop and server builds

On Windows, `npm run desktop:dev` starts the desktop development environment. `npm run desktop:dist:win` builds a Windows installer into `frontend/dist`. An installer is a build output, not a file guaranteed to exist after cloning.

The Docker setup runs five services: nginx, frontend, backend, worker, and Ollama. Copy `.env.example` to `.env`, review the settings, then run `docker compose up --build -d`. The supplied Ollama service requests NVIDIA GPU access; adapt that setting for a CPU-only host. Pull the configured model with `docker compose exec ollama ollama pull qwen2.5:7b-instruct`.

## Research use

Generated objectives, claims, and reports require review against the cited sources. Keep a record of model and dataset versions when comparing runs. This repository provides a research prototype and evaluation tools; it does not establish that persona-guided reasoning improves research outcomes.
