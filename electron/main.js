/**
 * Carina Desktop — Electron main process.
 *
 * Lifecycle:
 *   1. Start the Carina Python backend (uvicorn subprocess)
 *   2. Wait for the HTTP port to become ready
 *   3. Open a BrowserWindow pointed at the local UI
 *   4. Set up a system-tray icon with a context menu
 *   5. On quit, gracefully shut down the Python process
 */

"use strict";

const { app, BrowserWindow, shell } = require("electron");
const path = require("path");
const { PythonManager } = require("./python-manager");
const { createTray } = require("./tray");

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const HOST = process.env.CARINA_HOST || "127.0.0.1";
const PORT = parseInt(process.env.CARINA_PORT || "8787", 10);
const BASE_URL = `http://${HOST}:${PORT}`;

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

let mainWindow = null;
let python = null;
let tray = null;
let isQuitting = false;

// ---------------------------------------------------------------------------
// Window
// ---------------------------------------------------------------------------

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1000,
    height: 720,
    minWidth: 680,
    minHeight: 480,
    title: "Carina",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  mainWindow.loadURL(BASE_URL);

  // Open external links in the default browser instead of new Electron windows.
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith("http") && !url.startsWith(BASE_URL)) {
      shell.openExternal(url);
      return { action: "deny" };
    }
    return { action: "allow" };
  });

  // Hide to tray instead of closing (platform convention).
  mainWindow.on("close", (e) => {
    if (!isQuitting) {
      e.preventDefault();
      mainWindow.hide();
    }
  });

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

// ---------------------------------------------------------------------------
// App lifecycle
// ---------------------------------------------------------------------------

app.whenReady().then(async () => {
  // 1. Start Python backend.
  python = new PythonManager(PORT, HOST);
  python.start();

  try {
    await python.waitForReady(15_000);
  } catch (err) {
    console.error("Carina backend failed to start:", err.message);
    // Still open the window — the user can see the error in the UI.
  }

  // 2. Create window.
  createWindow();

  // 3. System tray.
  tray = createTray(mainWindow, python, () => {
    isQuitting = true;
    app.quit();
  });

  app.on("activate", () => {
    // macOS: re-show window when dock icon is clicked.
    if (mainWindow) {
      mainWindow.show();
    }
  });
});

app.on("before-quit", () => {
  isQuitting = true;
});

app.on("window-all-closed", () => {
  // On macOS the app stays in the dock; on other platforms quit.
  if (process.platform !== "darwin") {
    isQuitting = true;
    app.quit();
  }
});

app.on("will-quit", async () => {
  if (python) {
    await python.stop();
    python = null;
  }
});
