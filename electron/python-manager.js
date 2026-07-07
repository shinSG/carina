/**
 * Manages the Carina Python backend as a child process.
 *
 * Features:
 *   - Auto-detects the best Python / carina executable
 *   - Graceful stop (SIGTERM → wait → SIGKILL)
 *   - Port readiness probe (HTTP GET loop)
 *   - EventEmitter for status changes
 */

"use strict";

const { spawn } = require("child_process");
const http = require("http");
const path = require("path");
const { EventEmitter } = require("events");

class PythonManager extends EventEmitter {
  /**
   * @param {number} port  HTTP port the backend should listen on.
   * @param {string} host  Bind address.
   */
  constructor(port = 8787, host = "127.0.0.1") {
    super();
    this.port = port;
    this.host = host;
    this._proc = null;
    this._status = "stopped"; // stopped | starting | running | error
  }

  get status() {
    return this._status;
  }

  get pid() {
    return this._proc ? this._proc.pid : null;
  }

  // -----------------------------------------------------------------------
  // Public API
  // -----------------------------------------------------------------------

  /** Spawn the Python backend. */
  start() {
    if (this._proc) return;
    this._setStatus("starting");

    const { cmd, args, opts } = this._resolveCommand();
    console.log(`[carina-electron] starting: ${cmd} ${args.join(" ")}`);

    this._proc = spawn(cmd, args, opts);

    this._proc.stdout.on("data", (d) => {
      const msg = d.toString().trim();
      if (msg) console.log(`[carina] ${msg}`);
    });

    this._proc.stderr.on("data", (d) => {
      const msg = d.toString().trim();
      if (msg) console.error(`[carina] ${msg}`);
    });

    this._proc.on("error", (err) => {
      console.error("[carina-electron] process error:", err.message);
      this._setStatus("error");
      this._proc = null;
    });

    this._proc.on("exit", (code, signal) => {
      console.log(`[carina-electron] exited (code=${code}, signal=${signal})`);
      this._proc = null;
      this._setStatus("stopped");
    });
  }

  /** Gracefully stop the backend. */
  async stop() {
    const proc = this._proc;
    if (!proc) return;

    return new Promise((resolve) => {
      const killTimeout = setTimeout(() => {
        console.warn("[carina-electron] SIGKILL after timeout");
        try {
          proc.kill("SIGKILL");
        } catch {}
      }, 5000);

      proc.on("exit", () => {
        clearTimeout(killTimeout);
        this._proc = null;
        this._setStatus("stopped");
        resolve();
      });

      try {
        proc.kill(process.platform === "win32" ? undefined : "SIGTERM");
      } catch {
        clearTimeout(killTimeout);
        resolve();
      }
    });
  }

  /**
   * Poll until the HTTP port responds or timeout is reached.
   * @param {number} timeoutMs
   * @returns {Promise<void>}
   */
  waitForReady(timeoutMs = 10_000) {
    return new Promise((resolve, reject) => {
      const deadline = Date.now() + timeoutMs;

      const check = () => {
        if (this._status === "error" || this._status === "stopped") {
          return reject(new Error("Backend process exited unexpectedly"));
        }
        if (Date.now() > deadline) {
          return reject(new Error("Backend readiness timeout"));
        }

        const req = http.get(
          { host: this.host, port: this.port, path: "/api/health", timeout: 2000 },
          (res) => {
            res.resume();
            if (res.statusCode < 500) {
              this._setStatus("running");
              return resolve();
            }
            setTimeout(check, 500);
          }
        );

        req.on("error", () => setTimeout(check, 500));
        req.on("timeout", () => {
          req.destroy();
          setTimeout(check, 500);
        });
      };

      // Give the process a moment to bind.
      setTimeout(check, 800);
    });
  }

  // -----------------------------------------------------------------------
  // Internals
  // -----------------------------------------------------------------------

  _setStatus(s) {
    if (this._status === s) return;
    this._status = s;
    this.emit("status", s);
  }

  /**
   * Figure out how to start the Carina server.
   *
   * Priority:
   *   1. `carina` CLI on PATH (pip-installed)
   *   2. Project-local venv: .venv/bin/carina
   *   3. `python -m carina` (module invocation)
   */
  _resolveCommand() {
    const env = { ...process.env, CARINA_HOST: this.host, CARINA_PORT: String(this.port) };
    const cwd = this._projectRoot();

    // Try venv first (most reliable in dev).
    const venvBin = process.platform === "win32" ? "Scripts" : "bin";
    const venvCarina = path.join(cwd, ".venv", venvBin, process.platform === "win32" ? "carina.exe" : "carina");
    const venvPython = path.join(cwd, ".venv", venvBin, process.platform === "win32" ? "python.exe" : "python");

    // If the venv carina script exists, use it.
    try {
      require("fs").accessSync(venvCarina);
      return { cmd: venvCarina, args: [], opts: { env, cwd, stdio: ["pipe", "pipe", "pipe"] } };
    } catch {}

    // Fallback: venv python -m carina
    try {
      require("fs").accessSync(venvPython);
      return { cmd: venvPython, args: ["-m", "carina"], opts: { env, cwd, stdio: ["pipe", "pipe", "pipe"] } };
    } catch {}

    // Last resort: system python
    return {
      cmd: process.platform === "win32" ? "python" : "python3",
      args: ["-m", "carina"],
      opts: { env, cwd, stdio: ["pipe", "pipe", "pipe"] },
    };
  }

  /** Walk up from __dirname to find the project root (where pyproject.toml lives). */
  _projectRoot() {
    let dir = path.resolve(__dirname, "..");
    // In packaged app __dirname is inside resources/app.asar/electron/,
    // so go up to resources/app.asar/ which is the project root.
    return dir;
  }
}

module.exports = { PythonManager };
