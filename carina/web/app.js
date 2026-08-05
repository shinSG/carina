"use strict";

const translations = {
  en: {
    "page.title": "carina — model proxy",
    "header.subtitle": "local model-service proxy",
    "language.label": "Language",
    "common.loading": "Loading…",
    "common.save": "Save",
    "common.clear": "Clear",
    "common.any": "any",
    "common.unknown": "unknown",
    "providers.title": "Providers",
    "providers.empty": "No providers yet. Add one below.",
    "routing.title": "Smart routing",
    "routing.mode": "Mode",
    "routing.modeManual": "manual — active provider first",
    "routing.modeRule": "rule — request rules and priority",
    "routing.modeAdaptive": "adaptive — rules and live scoring",
    "routing.latencyTarget": "Latency target (ms)",
    "routing.rules": "Rules (JSON array)",
    "routing.rulesHelp": "Rules match model_patterns and stream; they can use provider_ids, require_tags, prefer_tags, and strict.",
    "routing.save": "Save routing",
    "provider.addTitle": "Add provider",
    "provider.editTitle": "Edit provider",
    "provider.name": "Name",
    "provider.namePlaceholder": "My provider",
    "provider.protocol": "Protocol",
    "provider.baseUrl": "Base URL",
    "provider.defaultModel": "Default model",
    "provider.apiKey": "API key",
    "provider.apiKeyPlaceholder": "leave blank to keep existing",
    "provider.priority": "Priority (lower = preferred)",
    "provider.modelPatterns": "Model patterns (comma separated)",
    "provider.tags": "Tags (comma separated)",
    "provider.tagsPlaceholder": "fast, cheap",
    "provider.capabilities": "Capabilities",
    "provider.contextWindow": "Context window",
    "provider.maxOutputTokens": "Max output tokens",
    "provider.inputCost": "Input cost / 1M tokens",
    "provider.outputCost": "Output cost / 1M tokens",
    "provider.active": "active",
    "provider.summary": "{url} · model {model} · priority {priority}",
    "provider.routingMeta": "patterns {patterns} · tags {tags}",
    "provider.runtime": "runtime success {success} · latency {latency}",
    "action.activate": "Activate",
    "action.test": "Test",
    "action.edit": "Edit",
    "action.delete": "Delete",
    "status.closed": "closed",
    "status.open": "open",
    "status.half_open": "half-open",
    "status.unknown": "unknown",
    "message.testOk": "OK: {detail}",
    "message.testFailed": "Failed: {detail}",
    "message.deleteConfirm": "Delete {name}?",
    "message.required": "Name and base URL are required.",
    "message.rulesArray": "rules must be an array",
    "message.invalidRules": "Invalid rules JSON: {message}",
    "message.saveRoutingFailed": "Could not save routing config: {detail}",
  },
  "zh-CN": {
    "page.title": "carina — 模型代理",
    "header.subtitle": "本地模型服务代理",
    "language.label": "语言",
    "common.loading": "加载中…",
    "common.save": "保存",
    "common.clear": "清空",
    "common.any": "不限",
    "common.unknown": "未知",
    "providers.title": "供应商",
    "providers.empty": "暂无供应商，请在下方添加。",
    "routing.title": "智能路由",
    "routing.mode": "模式",
    "routing.modeManual": "manual — 当前供应商优先",
    "routing.modeRule": "rule — 按请求规则和优先级",
    "routing.modeAdaptive": "adaptive — 按规则和实时评分",
    "routing.latencyTarget": "延迟目标（毫秒）",
    "routing.rules": "规则（JSON 数组）",
    "routing.rulesHelp": "规则可匹配 model_patterns 和 stream，并可使用 provider_ids、require_tags、prefer_tags 与 strict。",
    "routing.save": "保存路由配置",
    "provider.addTitle": "添加供应商",
    "provider.editTitle": "编辑供应商",
    "provider.name": "名称",
    "provider.namePlaceholder": "我的供应商",
    "provider.protocol": "协议",
    "provider.baseUrl": "基础 URL",
    "provider.defaultModel": "默认模型",
    "provider.apiKey": "API 密钥",
    "provider.apiKeyPlaceholder": "留空则保留现有密钥",
    "provider.priority": "优先级（数值越小越优先）",
    "provider.modelPatterns": "模型匹配模式（逗号分隔）",
    "provider.tags": "标签（逗号分隔）",
    "provider.tagsPlaceholder": "快速, 低成本",
    "provider.capabilities": "能力",
    "provider.contextWindow": "上下文窗口",
    "provider.maxOutputTokens": "最大输出 Token 数",
    "provider.inputCost": "每百万输入 Token 成本",
    "provider.outputCost": "每百万输出 Token 成本",
    "provider.active": "当前",
    "provider.summary": "{url} · 模型 {model} · 优先级 {priority}",
    "provider.routingMeta": "匹配模式 {patterns} · 标签 {tags}",
    "provider.runtime": "运行成功率 {success} · 延迟 {latency}",
    "action.activate": "设为当前",
    "action.test": "测试",
    "action.edit": "编辑",
    "action.delete": "删除",
    "status.closed": "正常",
    "status.open": "熔断",
    "status.half_open": "半开",
    "status.unknown": "未知",
    "message.testOk": "测试成功：{detail}",
    "message.testFailed": "测试失败：{detail}",
    "message.deleteConfirm": "确定删除 {name}？",
    "message.required": "名称和基础 URL 为必填项。",
    "message.rulesArray": "规则必须是数组",
    "message.invalidRules": "规则 JSON 无效：{message}",
    "message.saveRoutingFailed": "保存路由配置失败：{detail}",
  },
};

const supportedLanguages = new Set(Object.keys(translations));
let currentLanguage = initialLanguage();

function initialLanguage() {
  const saved = localStorage.getItem("carina.language");
  if (supportedLanguages.has(saved)) return saved;
  return navigator.language.toLowerCase().startsWith("zh") ? "zh-CN" : "en";
}

function t(key, values = {}) {
  const template = translations[currentLanguage][key] ?? translations.en[key] ?? key;
  return template.replace(/\{(\w+)\}/g, (_, name) => values[name] ?? `{${name}}`);
}

function applyTranslations() {
  document.documentElement.lang = currentLanguage;
  document.title = t("page.title");
  $("language").value = currentLanguage;
  document.querySelectorAll("[data-i18n]").forEach((element) => {
    element.textContent = t(element.dataset.i18n);
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((element) => {
    element.placeholder = t(element.dataset.i18nPlaceholder);
  });
  updateFormTitle();
}

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
    box.textContent = t("providers.empty");
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
          ${isActive ? `<span class="pill active">${t("provider.active")}</span>` : ""}
          <span class="pill ${hr.state || "closed"}">${t(`status.${hr.state || "unknown"}`)}</span>
        </div>
        <div class="muted">${escapeHtml(t("provider.summary", { url: p.base_url, model: p.default_model || "—", priority: p.priority }))}</div>
        <div class="muted">${escapeHtml(t("provider.routingMeta", { patterns: (p.model_patterns || []).join(", ") || t("common.any"), tags: (p.tags || []).join(", ") || "—" }))}</div>
        <div class="muted">${escapeHtml(t("provider.runtime", { success, latency }))}</div>
      </div>
      <div class="actions"></div>`;
    const actions = el.querySelector(".actions");
    if (!isActive) actions.append(btn(t("action.activate"), () => api.activate(p.id).then(render)));
    actions.append(btn(t("action.test"), async () => {
      const res = await api.test(p.id);
      alert(t(res.ok ? "message.testOk" : "message.testFailed", { detail: res.detail }));
    }, "secondary"));
    actions.append(btn(t("action.edit"), () => editProvider(p), "secondary"));
    actions.append(btn(t("action.delete"), () => {
      if (confirm(t("message.deleteConfirm", { name: p.name }))) api.remove(p.id).then(render);
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
  $("f-id").value = p.id;
  updateFormTitle();
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
  [
    "f-id", "f-name", "f-base_url", "f-default_model", "f-api_key",
    "f-model_patterns", "f-tags", "f-capabilities", "f-context_window", "f-max_output_tokens",
    "f-input_cost", "f-output_cost",
  ].forEach((i) => ($(i).value = ""));
  $("f-protocol").value = "openai";
  $("f-priority").value = "100";
  updateFormTitle();
}

function updateFormTitle() {
  $("form-title").textContent = t($("f-id").value ? "provider.editTitle" : "provider.addTitle");
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
    alert(t("message.required"));
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
    if (!Array.isArray(rules)) throw new Error(t("message.rulesArray"));
  } catch (error) {
    alert(t("message.invalidRules", { message: error.message }));
    return;
  }
  const current = await api.routingConfig();
  current.mode = $("r-mode").value;
  current.latency_target_ms = Number($("r-latency").value);
  current.rules = rules;
  const response = await api.saveRouting(current);
  if (!response.ok) {
    const detail = await response.json();
    alert(t("message.saveRoutingFailed", { detail: JSON.stringify(detail) }));
    return;
  }
  await render();
}

$("save").onclick = save;
$("reset").onclick = resetForm;
$("routing-save").onclick = saveRouting;
$("language").onchange = (event) => {
  currentLanguage = event.target.value;
  localStorage.setItem("carina.language", currentLanguage);
  applyTranslations();
  render();
};
applyTranslations();
render();
