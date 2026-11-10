const { app, BrowserWindow, nativeTheme, dialog, ipcMain, shell } = require('electron');
const path = require('path');
const fs = require('fs');
const net = require('net');
const { spawn, spawnSync } = require('child_process');

const isDev = process.env.ELECTRON_DEV === '1' || !app.isPackaged;
const WEB_URL = process.env.ELECTRON_WEB_URL || 'http://localhost:3000';

const FRONTEND_PORT = Number(process.env.FRONTEND_PORT || 3000);
const BACKEND_PORT = Number(process.env.BACKEND_PORT || 8000);
const DEFAULT_RUNTIME_CONFIG = {
  ollamaBaseUrl: 'http://localhost:11434',
  ollamaModel: 'qwen3.5:latest',
};

const PYTHON_IMPORT_CHECK = [
  'import fastapi, uvicorn, pydantic, httpx, pypdf, fitz',
  'import multipart',
].join('; ');

let mainWindow = null;
let webProc = null;
let apiProc = null;
let activeFrontendPort = FRONTEND_PORT;

ipcMain.handle('open-path', async (_event, targetPath) => {
  if (!targetPath || typeof targetPath !== 'string') {
    return { ok: false, error: 'missing_path' };
  }
  const errorMessage = await shell.openPath(targetPath);
  return errorMessage ? { ok: false, error: errorMessage } : { ok: true };
});

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function createMainWindow() {
  mainWindow = new BrowserWindow({
    width: 1500,
    height: 980,
    minWidth: 1180,
    minHeight: 760,
    backgroundColor: '#0b1220',
    show: false,
    title: 'SECI Persona Studio',
    titleBarStyle: 'hidden',
    titleBarOverlay: {
      color: '#0f172a',
      symbolColor: '#e2e8f0',
      height: 34,
    },
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      devTools: true,
    },
  });

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });

  mainWindow.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
}

function wireProcessLogs(label, proc, capture) {
  if (!proc) return;
  proc.stdout?.on('data', (chunk) => {
    const text = String(chunk);
    process.stdout.write(`[${label}] ${text}`);
    if (capture) capture.push(text);
  });
  proc.stderr?.on('data', (chunk) => {
    const text = String(chunk);
    process.stderr.write(`[${label}] ${text}`);
    if (capture) capture.push(text);
  });
}

function ensureRuntimeConfig(userData) {
  const runtimeConfigPath = path.join(userData, 'app-config.json');
  if (!fs.existsSync(runtimeConfigPath)) {
    fs.writeFileSync(runtimeConfigPath, `${JSON.stringify(DEFAULT_RUNTIME_CONFIG, null, 2)}\n`, 'utf8');
    return { configPath: runtimeConfigPath, config: { ...DEFAULT_RUNTIME_CONFIG } };
  }

  try {
    const raw = fs.readFileSync(runtimeConfigPath, 'utf8');
    const parsed = JSON.parse(raw);
    const config = {
      ...DEFAULT_RUNTIME_CONFIG,
      ...(parsed && typeof parsed === 'object' ? parsed : {}),
    };
    return { configPath: runtimeConfigPath, config };
  } catch (err) {
    throw new Error(
      `Invalid app config at ${runtimeConfigPath}. Please use valid JSON with fields like "ollamaModel" and "ollamaBaseUrl". ${String(err)}`
    );
  }
}

function pythonCommandCandidates() {
  if (process.platform === 'win32') {
    return [
      { cmd: 'python', args: [] },
      { cmd: 'py', args: ['-3'] },
    ];
  }
  return [{ cmd: 'python3', args: [] }, { cmd: 'python', args: [] }];
}

function runPython(candidate, extraArgs, options = {}) {
  return spawnSync(candidate.cmd, [...candidate.args, ...extraArgs], {
    encoding: 'utf8',
    windowsHide: true,
    ...options,
  });
}

function findUsablePython() {
  for (const candidate of pythonCommandCandidates()) {
    const version = runPython(candidate, ['--version']);
    if (version.error || version.status !== 0) continue;

    const check = runPython(candidate, ['-c', PYTHON_IMPORT_CHECK]);
    if (!check.error && check.status === 0) {
      return { candidate, ready: true, details: 'dependencies available' };
    }
    return {
      candidate,
      ready: false,
      details: `${check.stderr || check.stdout || 'missing backend dependency'}`.trim(),
    };
  }

  return { candidate: null, ready: false, details: 'Python was not found on PATH.' };
}

function ensureBackendDependencies(candidate, backendDir) {
  const requirementsPath = path.join(backendDir, 'requirements.txt');
  if (!fs.existsSync(requirementsPath)) {
    throw new Error(`Missing backend requirements file: ${requirementsPath}`);
  }

  const install = runPython(candidate, ['-m', 'pip', 'install', '--disable-pip-version-check', '-r', requirementsPath], {
    cwd: backendDir,
  });
  if (install.error || install.status !== 0) {
    throw new Error(
      [
        'Backend Python dependencies are missing and automatic installation failed.',
        '',
        `Command: ${candidate.cmd} ${[...candidate.args, '-m', 'pip', 'install', '-r', requirementsPath].join(' ')}`,
        install.stderr || install.stdout || String(install.error || 'unknown pip error'),
      ].join('\n')
    );
  }

  const recheck = runPython(candidate, ['-c', PYTHON_IMPORT_CHECK]);
  if (recheck.error || recheck.status !== 0) {
    throw new Error(`Backend dependencies were installed, but import validation still failed: ${recheck.stderr || recheck.stdout || recheck.error}`);
  }
}

async function findAvailablePort(startPort, maxTries = 20) {
  for (let port = startPort; port < startPort + maxTries; port += 1) {
    const free = await new Promise((resolve) => {
      const server = net.createServer();
      server.unref();
      server.on('error', () => resolve(false));
      server.listen({ host: '127.0.0.1', port }, () => {
        server.close(() => resolve(true));
      });
    });
    if (free) return port;
  }
  throw new Error(`No free port found in range ${startPort}-${startPort + maxTries - 1}`);
}

function startBackendPackaged() {
  const userData = app.getPath('userData');
  const runtimeDataRoot = path.join(userData, 'runtime-data');
  fs.mkdirSync(runtimeDataRoot, { recursive: true });
  const { configPath, config } = ensureRuntimeConfig(userData);

  const backendDir = path.join(process.resourcesPath, 'backend');
  const dbPath = path.join(runtimeDataRoot, 'unspecified_queries.db');
  const interviewRoot = path.join(runtimeDataRoot, 'interviews');

  let python = findUsablePython();
  if (!python.candidate) {
    throw new Error('Python is required to run the local backend, but it was not found on PATH.');
  }
  if (!python.ready) {
    ensureBackendDependencies(python.candidate, backendDir);
    python = findUsablePython();
  }
  if (!python.ready || !python.candidate) {
    throw new Error(`Backend Python dependency check failed: ${python.details}`);
  }

  const proc = spawn(
    python.candidate.cmd,
    [...python.candidate.args, '-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', String(BACKEND_PORT), '--app-dir', backendDir],
    {
      cwd: runtimeDataRoot,
      env: {
        ...process.env,
        DATABASE_PATH: dbPath,
        INTERVIEW_TEXT_ROOT: interviewRoot,
        APP_CONFIG_PATH: configPath,
        OLLAMA_MODEL: String(config.ollamaModel || DEFAULT_RUNTIME_CONFIG.ollamaModel),
        OLLAMA_BASE_URL: String(config.ollamaBaseUrl || DEFAULT_RUNTIME_CONFIG.ollamaBaseUrl),
        OLLAMA_URL: String(config.ollamaBaseUrl || DEFAULT_RUNTIME_CONFIG.ollamaBaseUrl),
      },
      stdio: ['ignore', 'pipe', 'pipe'],
    }
  );

  proc.on('error', (err) => {
    dialog.showErrorBox('SECI Persona Studio Backend Failed', String(err));
  });

  apiProc = proc;
  wireProcessLogs('API', apiProc);
}

async function startWebPackaged() {
  const webDir = path.join(process.resourcesPath, 'web');
  const serverJs = path.join(webDir, 'server.js');
  if (!fs.existsSync(serverJs)) {
    throw new Error(`Missing packaged web server: ${serverJs}`);
  }

  activeFrontendPort = await findAvailablePort(FRONTEND_PORT, 30);

  const attempts = [
    {
      label: 'electron-as-node',
      cmd: process.execPath,
      args: [serverJs],
      envPatch: { ELECTRON_RUN_AS_NODE: '1' },
    },
    {
      label: 'system-node',
      cmd: 'node',
      args: [serverJs],
      envPatch: {},
    },
  ];

  const errors = [];

  for (const attempt of attempts) {
    let proc;
    const captured = [];
    try {
      proc = spawn(attempt.cmd, attempt.args, {
        cwd: webDir,
        env: {
          ...process.env,
          ...attempt.envPatch,
          PORT: String(activeFrontendPort),
          HOSTNAME: '127.0.0.1',
          NEXT_PUBLIC_API_URL: `http://127.0.0.1:${BACKEND_PORT}`,
        },
        stdio: ['ignore', 'pipe', 'pipe'],
      });
      wireProcessLogs('WEB', proc, captured);

      await sleep(2500);
      if (proc.exitCode !== null) {
        errors.push(`${attempt.label} exited early with code ${proc.exitCode}. ${captured.join(' ')}`);
        continue;
      }

      webProc = proc;
      return;
    } catch (err) {
      errors.push(`${attempt.label} failed: ${String(err)}`);
      try {
        if (proc && !proc.killed) proc.kill();
      } catch {}
    }
  }

  throw new Error(`Failed to start packaged web server. ${errors.join(' | ')}`);
}

async function waitForUrl(url, timeoutMs = 60000) {
  const start = Date.now();
  let lastErr = null;
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch(url, { method: 'GET' });
      if (res.ok || res.status < 500) {
        return;
      }
    } catch (err) {
      lastErr = err;
    }
    await sleep(600);
  }
  throw new Error(`Timed out waiting for ${url}. Last error: ${String(lastErr || 'none')}`);
}

function stopChildProcesses() {
  try {
    if (webProc && !webProc.killed) webProc.kill();
  } catch {}
  try {
    if (apiProc && !apiProc.killed) apiProc.kill();
  } catch {}
}

async function startApp() {
  createMainWindow();

  if (isDev) {
    await mainWindow.loadURL(WEB_URL);
    return;
  }

  startBackendPackaged();
  await startWebPackaged();

  await waitForUrl(`http://127.0.0.1:${BACKEND_PORT}/docs`, 90000);
  await waitForUrl(`http://127.0.0.1:${activeFrontendPort}`, 90000);
  await mainWindow.loadURL(`http://127.0.0.1:${activeFrontendPort}`);
}

app.whenReady().then(async () => {
  nativeTheme.themeSource = 'light';

  try {
    await startApp();
  } catch (err) {
    stopChildProcesses();
    dialog.showErrorBox(
      'SECI Persona Studio Startup Failed',
      [
        String(err),
        '',
        'Check prerequisites:',
        '1) Python installed and available in PATH',
        '2) Internet access if the app needs to install missing Python packages on first launch',
        '3) Ollama installed and running',
      ].join('\n')
    );
    app.quit();
    return;
  }

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createMainWindow();
      if (isDev) {
        mainWindow.loadURL(WEB_URL).catch(() => {});
      } else {
        mainWindow.loadURL(`http://127.0.0.1:${activeFrontendPort}`).catch(() => {});
      }
    }
  });
});

app.on('before-quit', () => {
  stopChildProcesses();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
