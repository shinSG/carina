"use strict";

const api = {
  async list() {
    const r = await fetch("/api/providers");
    return r.json();
  },
  async health() {
    const r = await fetch("/api/health");
    return r.json();
  },
  async create(body) {
    return fetch("/api/providers", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  },
  async update(id, body) {
    return fetch(`/api/providers/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  },
  async remove(id) {
    return fetch(`/api/providers/${id}`, { method: "DELETE" });
  },
  async activate(id) {
    return fetch(`/api/providers/${id}/activate`, { method: "POST" });
  },
  async test(id) {
    const r = await fetch(`/api/providers/${id}/test`, { method: "POST" });
    return r.json();
  },
};

const $ = (id) => document.getElementById(id);

function healthFor(records, id) {
  return (records || []).find((r) => r.provider_id === id) || {};
}

/** Parse "key=value" lines into an object. */
function parseModelMap(text) {
  const map = {};
  for (const line of text.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    const eq = trimmed.indexOf("=");
    if (eq < 1) continue;
    map[trimmed.slice(0, eq).trim()] = trimmed.slice(eq + 1).trim();
  }
  return map;
}

/** Serialize object back to "key=value" lines. */
function serializeModelMap(obj) {
  if (!obj || typeof obj !== "object") return "";
  return Object.entries(obj)
    .map(([k, v]) => `${k}=${v}`)
    .join("\n");
}

/** Parse comma-separated fallback models. */
function parseFallbackModels(text) {
  return text
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

/** Serialize array to comma-separated string. */
function serializeFallbackModels(arr) {
  if (!Array.isArray(arr)) return "";
  return arr.join(", ");
}

async function render() {
  const [data, h] = await Promise.all([api.list(), api.health()]);
  const records = h.providers || [];
  const box = $("providers");
  if (!data.providers.length) {
    box.textContent = "No providers yet. Add one below.";
    return;
  }
  box.innerHTML = "";
  for (const p of data.providers) {
    const isActive = p.id === data.active_id;
    const hr = healthFor(records, p.id);
    const el = document.createElement("div");
    el.className = "row";
    el.style.padding = "10px 0";
    el.style.borderTop = "1px solid #262a33";

    // Build info line
    let infoParts = [
      `${escapeHtml(p.base_url)}`,
      `model ${escapeHtml(p.default_model || "—")}`,
      `prio ${p.priority}`,
    ];
    const mapKeys = p.model_map ? Object.keys(p.model_map) : [];
    if (mapKeys.length) {
      infoParts.push(`map: ${mapKeys.length} rule${mapKeys.length > 1 ? "s" : ""}`);
    }
    if (p.fallback_models && p.fallback_models.length) {
      infoParts.push(`fallback: ${p.fallback_models.join(" → ")}`);
    }

    el.innerHTML = `
      <div>
        <div class="row" style="gap:8px; justify-content:flex-start;">
          <strong>${escapeHtml(p.name)}</strong>
          <span class="pill">${p.protocol}</span>
          ${isActive ? '<span class="pill active">active</span>' : ""}
          <span class="pill ${hr.state || "closed"}">${hr.state || "unknown"}</span>
        </div>
        <div class="muted">${infoParts.join(" · ")}</div>
      </div>
      <div class="actions"></div>`;
    const actions = el.querySelector(".actions");
    if (!isActive) actions.append(btn("Activate", () => api.activate(p.id).then(render)));
    actions.append(btn("Test", async () => {
      const res = await api.test(p.id);
      alert(res.ok ? "OK: " + res.detail : "Failed: " + res.detail);
    }, "secondary"));
    actions.append(btn("Edit", () => editProvider(p), "secondary"));
    actions.append(btn("Delete", () => {
      if (confirm(`Delete ${p.name}?`)) api.remove(p.id).then(render);
    }, "danger"));
    box.append(el);
  }
}

function btn(label, onClick, cls) {
  const b = document.createElement("button");
  b.textContent = label;
  if (cls) b.className = cls;
  b.onclick = onClick;
  return b;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

function editProvider(p) {
  $("form-title").textContent = "Edit provider";
  $("f-id").value = p.id;
  $("f-name").value = p.name;
  $("f-protocol").value = p.protocol;
  $("f-base_url").value = p.base_url;
  $("f-default_model").value = p.default_model || "";
  $("f-api_key").value = "";
  $("f-priority").value = p.priority;
  $("f-model_map").value = serializeModelMap(p.model_map);
  $("f-fallback_models").value = serializeFallbackModels(p.fallback_models);
}

function resetForm() {
  $("form-title").textContent = "Add provider";
  ["f-id", "f-name", "f-base_url", "f-default_model", "f-api_key", "f-model_map", "f-fallback_models"].forEach((i) => ($(i).value = ""));
  $("f-protocol").value = "openai";
  $("f-priority").value = "100";
}

async function save() {
  const id = $("f-id").value;
  const body = {
    name: $("f-name").value.trim(),
    protocol: $("f-protocol").value,
    base_url: $("f-base_url").value.trim(),
    default_model: $("f-default_model").value.trim() || null,
    priority: Number($("f-priority").value) || 100,
    model_map: parseModelMap($("f-model_map").value),
    fallback_models: parseFallbackModels($("f-fallback_models").value),
  };
  const key = $("f-api_key").value;
  if (!body.name || !body.base_url) {
    alert("Name and base URL are required.");
    return;
  }
  if (id) {
    if (key) body.api_key = key;
    await api.update(id, body);
  } else {
    body.api_key = key;
    await api.create(body);
  }
  resetForm();
  render();
}

$("save").onclick = save;
$("reset").onclick = resetForm;
render();
