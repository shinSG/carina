/**
 * System tray for Carina Desktop.
 *
 * Shows a context menu with:
 *   - Current backend status
 *   - Show / hide window
 *   - Restart backend
 *   - Quit
 */

"use strict";

const { Tray, Menu, nativeImage, app } = require("electron");
const path = require("path");

/**
 * Create and return a system Tray.
 *
 * @param {Electron.BrowserWindow} win
 * @param {import('./python-manager').PythonManager} python
 * @param {() => void} onQuit  Called when the user selects "Quit".
 * @returns {Electron.Tray}
 */
function createTray(win, python, onQuit) {
  const iconPath = _getIconPath();
  const tray = new Tray(iconPath);
  tray.setToolTip("Carina — model proxy");

  function buildMenu() {
    const statusLabels = {
      stopped: "⏹  Backend: stopped",
      starting: "🔄  Backend: starting…",
      running: "✅  Backend: running",
      error: "❌  Backend: error",
    };

    return Menu.buildFromTemplate([
      { label: "Carina", enabled: false },
      { type: "separator" },
      { label: statusLabels[python.status] || python.status, enabled: false },
      { type: "separator" },
      {
        label: "Show Window",
        click: () => {
          if (win) {
            win.show();
            win.focus();
          }
        },
      },
      { type: "separator" },
      {
        label: "Restart Backend",
        click: async () => {
          await python.stop();
          python.start();
          try {
            await python.waitForReady(15_000);
          } catch {}
          _refresh();
          if (win) win.reload();
        },
      },
      { type: "separator" },
      {
        label: "Quit Carina",
        click: onQuit,
      },
    ]);
  }

  function _refresh() {
    tray.setContextMenu(buildMenu());
  }

  // Refresh the menu whenever backend status changes.
  python.on("status", _refresh);

  // Initial menu.
  _refresh();

  // Double-click / single-click (platform-dependent) shows the window.
  tray.on("click", () => {
    if (win) {
      win.show();
      win.focus();
    }
  });

  return tray;
}

/**
 * Resolve the tray icon path.
 * Uses a small generated PNG in electron/icons/ or falls back to a nativeImage.
 */
function _getIconPath() {
  const ico = path.join(__dirname, "icons", "tray-icon.png");
  try {
    require("fs").accessSync(ico);
    return ico;
  } catch {}

  // Fallback: create a simple 16×16 icon programmatically.
  return nativeImage.createEmpty();
}

module.exports = { createTray };
