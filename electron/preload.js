/**
 * Preload script — exposes a safe IPC bridge to the renderer.
 *
 * Currently minimal; can be extended later for settings, logs, etc.
 */

"use strict";

const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("carinaDesktop", {
  /** Platform identifier (darwin | win32 | linux). */
  platform: process.platform,

  /** App version from package.json. */
  version: require("../package.json").version || "0.0.0",
});
