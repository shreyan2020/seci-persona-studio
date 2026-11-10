# Desktop app

The Electron wrapper runs the same frontend and backend in a desktop window.
Install Node.js, Python 3.11+, and Ollama separately. Pull the model you plan to use.

## Development

From `frontend`, with your Python environment activated:

```powershell
npm ci
python -m pip install -r ../backend/requirements.txt
npm run desktop:dev
```

This starts FastAPI on port 8000, Next.js on port 3000, and the Electron window.

## Windows installer

```powershell
npm run desktop:dist:win
```

The NSIS installer is written to `frontend/dist`. The package includes frontend
and backend code; Python, Python dependencies, and Ollama must be available on
the machine where it runs. Writable application data is stored in the application
user-data directory.

## Model configuration

The packaged app creates `app-config.json` in its application user-data directory
on first launch:

```json
{
  "ollamaBaseUrl": "http://localhost:11434",
  "ollamaModel": "qwen3.5:latest"
}
```

Change `ollamaModel` to another installed model and restart the app to use it.
