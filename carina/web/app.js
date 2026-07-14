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
  async routingMetrics() {
    const r = await fetch("/api/routing/metrics");
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
  async routingConfig() {
    const r = await fetch("/api/routing/config");
    return r.json();
  },
  async saveRouting(body) {
    return fetch("/api/routing/config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  },
};

const $ = (id) => document.getElementById(id);

function healthFor(records, id) {
  return (records || []).find((r) => r.provider_id === id) || {};
}

function metricsFor(records, id) {
  return (records || []).find((r) => r.provider_id === id) || {};
}

async function render() {
  const [data, h, routing, metrics] = await Promise.all([
    api.list(), api.health(), api.routingConfig(), api.routingMetrics(),
  ]);
  $("r-mode").value = routing.mode;
  $("r-latency").value = routing.latency_target_ms;
  $("r-rules").value = JSON.stringify(routing.rules || [], null, 2);
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
    const mr = metricsFor(metrics.providers, p.id);
    const success = mr.success_rate == null ? "—" : `${Math.round(mr.success_rate * 100)}%`;
    const latency = mr.latency_ewma_ms == null ? "—" : `${Math.round(mr.latency_ewma_ms)}ms`;
    const el = document.createElement("div");
    el.className = "row";
    el.style.padding = "10px 0";
    el.style.borderTop = "1px solid #262a33";
    el.innerHTML = `
      <div>
        <div class="row" style="gap:8px; justify-content:flex-start;">
          <strong>${escapeHtml(p.name)}</strong>
          <span class="pill">${p.protocol}</span>
          ${isActive ? '<span class="pill active">active</span>' : ""}
          <span class="pill ${hr.state || "closed"}">${hr.state || "unknown"}</span>
        </div>
        <div class="muted">${escapeHtml(p.base_url)} · model ${escapeHtml(p.default_model || "—")} · prio ${p.priority}</div>
        <div class="muted">patterns ${escapeHtml((p.model_patterns || []).join(", ") || "any")} · tags ${escapeHtml((p.tags || []).join(", ") || "—")}</div>
        <div class="muted">runtime success ${success} · latency ${latency}</div>
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
  $("f-model_patterns").value = (p.model_patterns || []).join(", ");
  $("f-tags").value = (p.tags || []).join(", ");
  $("f-capabilities").value = (p.capabilities || []).join(", ");
  $("f-context_window").value = p.context_window || "";
  $("f-max_output_tokens").value = p.max_output_tokens || "";
  $("f-input_cost").value = p.input_cost_per_million ?? "";
  $("f-output_cost").value = p.output_cost_per_million ?? "";
}

function resetForm() {
  $("form-title").textContent = "Add provider";
  [
    "f-id", "f-name", "f-base_url", "f-default_model", "f-api_key",
    "f-model_patterns", "f-tags", "f-capabilities", "f-context_window", "f-max_output_tokens",
    "f-input_cost", "f-output_cost",
  ].forEach((i) => ($(i).value = ""));
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
    priority: $("f-priority").value === "" ? 100 : Number($("f-priority").value),
    model_patterns: csv($("f-model_patterns").value),
    tags: csv($("f-tags").value),
    capabilities: csv($("f-capabilities").value),
    context_window: optionalNumber($("f-context_window").value),
    max_output_tokens: optionalNumber($("f-max_output_tokens").value),
    input_cost_per_million: optionalNumber($("f-input_cost").value),
    output_cost_per_million: optionalNumber($("f-output_cost").value),
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

function csv(value) {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function optionalNumber(value) {
  return value === "" ? null : Number(value);
}

async function saveRouting() {
  let rules;
  try {
    rules = JSON.parse($("r-rules").value);
    if (!Array.isArray(rules)) throw new Error("rules must be an array");
  } catch (error) {
    alert("Invalid rules JSON: " + error.message);
    return;
  }
  const current = await api.routingConfig();
  current.mode = $("r-mode").value;
  current.latency_target_ms = Number($("r-latency").value);
  current.rules = rules;
  const response = await api.saveRouting(current);
  if (!response.ok) {
    const detail = await response.json();
    alert("Could not save routing config: " + JSON.stringify(detail));
    return;
  }
  await render();
}

$("save").onclick = save;
$("reset").onclick = resetForm;
$("routing-save").onclick = saveRouting;
render();
