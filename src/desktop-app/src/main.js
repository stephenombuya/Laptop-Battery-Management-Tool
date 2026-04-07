/**
 * main.js — BatteryOS Electron Main Process
 * ==========================================
 * Creates the BrowserWindow, manages the Python core-service child process,
 * and wires IPC channels between the renderer and the backend.
 *
 * IPC channels
 * ------------
 *   Renderer → Main  (ipcMain.handle)
 *     'battery:get-snapshot'      → returns the latest BatterySnapshot JSON
 *     'battery:set-thresholds'    → { min, max }
 *     'battery:stop-charging'     → void
 *     'battery:start-charging'    → void
 *     'battery:get-config'        → returns current manager config
 *
 *   Main → Renderer  (webContents.send)
 *     'battery:snapshot-update'   → BatterySnapshot JSON (pushed every interval)
 */

"use strict";

const path = require("path");
const { app, BrowserWindow, ipcMain, Tray, Menu, nativeImage } = require("electron");
const { spawn } = require("child_process");

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const WINDOW_WIDTH  = 1280;
const WINDOW_HEIGHT = 860;
const ICON_PATH     = path.join(__dirname, "..", "assets", "icon.png");

// Path to the Python entry point (relative to project root)
const PYTHON_ENTRY  = path.join(__dirname, "..", "..", "core-service", "__main__.py");
const PYTHON_BIN    = process.platform === "win32" ? "python" : "python3";

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

/** @type {BrowserWindow | null} */
let mainWindow = null;

/** @type {Tray | null} */
let tray = null;

/** @type {import("child_process").ChildProcess | null} */
let pythonProcess = null;

/** @type {object} */
let latestSnapshot = {};

// ---------------------------------------------------------------------------
// Window management
// ---------------------------------------------------------------------------

/**
 * Create and configure the main browser window.
 * @returns {BrowserWindow}
 */
function createWindow() {
  const win = new BrowserWindow({
    width:  WINDOW_WIDTH,
    height: WINDOW_HEIGHT,
    minWidth:  900,
    minHeight: 600,
    title: "BatteryOS",
    icon:  ICON_PATH,
    backgroundColor: "#080c10",
    webPreferences: {
      preload:         path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration:  false,   // security: keep Node out of renderer
      sandbox:          false,
    },
  });

  win.loadFile(path.join(__dirname, "index.html"));

  // Open DevTools in development only
  if (process.env.NODE_ENV === "development") {
    win.webContents.openDevTools({ mode: "detach" });
  }

  // Push snapshot updates to the renderer on each tick
  win.on("close", (event) => {
    if (!app.isQuitting) {
      // Minimise to tray instead of closing
      event.preventDefault();
      win.hide();
    }
  });

  return win;
}

// ---------------------------------------------------------------------------
// System tray
// ---------------------------------------------------------------------------

function createTray() {
  const icon = nativeImage.createFromPath(ICON_PATH).resize({ width: 16, height: 16 });
  tray = new Tray(icon);

  const menu = Menu.buildFromTemplate([
    { label: "Show BatteryOS", click: () => mainWindow?.show() },
    { type:  "separator" },
    { label: "Quit", click: () => { app.isQuitting = true; app.quit(); } },
  ]);

  tray.setContextMenu(menu);
  tray.setToolTip("BatteryOS — Battery Monitor");
  tray.on("double-click", () => mainWindow?.show());
}

// ---------------------------------------------------------------------------
// Python bridge
// ---------------------------------------------------------------------------

/**
 * Spawn the Python core-service in JSON-streaming mode.
 * The Python process is expected to write a JSON object per line to stdout,
 * each object being a BatterySnapshot.
 */
function startPythonProcess() {
  const args = [
    PYTHON_ENTRY,
    "--no-gui",
    "--log-level", "INFO",
  ];

  pythonProcess = spawn(PYTHON_BIN, args, {
    stdio: ["ignore", "pipe", "pipe"],
  });

  pythonProcess.stdout.setEncoding("utf8");
  pythonProcess.stdout.on("data", (raw) => {
    raw.split("\n").forEach((line) => {
      line = line.trim();
      if (!line) return;
      try {
        const snapshot = JSON.parse(line);
        latestSnapshot = snapshot;
        mainWindow?.webContents.send("battery:snapshot-update", snapshot);
      } catch {
        // Not every line is JSON (e.g. startup messages) — ignore silently
      }
    });
  });

  pythonProcess.stderr.setEncoding("utf8");
  pythonProcess.stderr.on("data", (msg) => {
    if (process.env.NODE_ENV === "development") {
      console.error("[Python]", msg.trim());
    }
  });

  pythonProcess.on("exit", (code, signal) => {
    console.warn(`Python process exited — code=${code}, signal=${signal}`);
    pythonProcess = null;
  });

  console.log(`Python service started (PID ${pythonProcess.pid}).`);
}

/**
 * Gracefully terminate the Python child process.
 */
function stopPythonProcess() {
  if (!pythonProcess) return;
  pythonProcess.kill("SIGTERM");
  pythonProcess = null;
}

// ---------------------------------------------------------------------------
// IPC handlers
// ---------------------------------------------------------------------------

function registerIpcHandlers() {
  ipcMain.handle("battery:get-snapshot", () => latestSnapshot);

  ipcMain.handle("battery:set-thresholds", (_event, { min, max }) => {
    sendCommandToPython({ command: "set_thresholds", min, max });
    return { ok: true };
  });

  ipcMain.handle("battery:stop-charging", () => {
    sendCommandToPython({ command: "stop_charging" });
    return { ok: true };
  });

  ipcMain.handle("battery:start-charging", () => {
    sendCommandToPython({ command: "start_charging" });
    return { ok: true };
  });

  ipcMain.handle("battery:get-config", () => ({
    platform: process.platform,
    pythonRunning: pythonProcess !== null,
  }));
}

/**
 * Write a JSON command to the Python process's stdin.
 * @param {object} payload
 */
function sendCommandToPython(payload) {
  if (!pythonProcess?.stdin?.writable) {
    console.warn("Python process is not running — command dropped.", payload);
    return;
  }
  pythonProcess.stdin.write(JSON.stringify(payload) + "\n");
}

// ---------------------------------------------------------------------------
// App lifecycle
// ---------------------------------------------------------------------------

app.whenReady().then(() => {
  mainWindow = createWindow();
  createTray();
  registerIpcHandlers();
  startPythonProcess();

  app.on("activate", () => {
    // macOS: re-open when clicking the dock icon
    if (BrowserWindow.getAllWindows().length === 0) {
      mainWindow = createWindow();
    } else {
      mainWindow?.show();
    }
  });
});

app.on("window-all-closed", () => {
  // On macOS apps stay running until the user explicitly quits
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("before-quit", () => {
  app.isQuitting = true;
  stopPythonProcess();
});
