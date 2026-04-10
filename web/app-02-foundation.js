const USAGE_RANGES = ["minute", "hour", "day", "week"];
const UPSTREAM_COLORS = ["#77b6ff", "#7be1a2", "#f2c56f", "#ff8894", "#bd9bff", "#79d7d7", "#ffb86a", "#9db8ff"];
const PROTOCOL_ORDER = ["openai", "anthropic", "gemini", "local_llm"];
const LOCAL_LLM_UPSTREAM_PROTOCOLS = ["openai", "anthropic", "gemini"];
const DEFAULT_SHARED_API_PREFIXES = {
  openai: "/openai",
  anthropic: "/claude",
  gemini: "/gemini",
  local_llm: "/local",
};
const NATIVE_API_PREFIXES = {
  openai: "/v1",
  anthropic: "/v1",
  gemini: "/v1beta",
  local_llm: "/v1",
};
const DEFAULT_SPLIT_API_PORTS = {
  openai: 8787,
  anthropic: 8788,
  gemini: 8789,
  local_llm: 8790,
};

const state = {
  savedConfig: null,
  config: null,
  status: null,
  usage: null,
  usageRange: "hour",
  usageAutoScrollKey: "",
  usageScope: "all",
  usageLocalKey: "all",
  usageLocalKeyMenuOpen: false,
  usageLocalKeyQuery: "",
  hoveredUsageBucketIndex: -1,
  renderedUsageBuckets: [],
  editorDrafts: {},
  localProbeResults: {},
  expandedUpstreamIds: new Set(),
  expandedLocalKeyIds: new Set(),
  draggingUpstreamId: "",
  currentProtocolTab: "openai",
  workspaceOpen: false,
  autoSaveTimer: null,
  autoSaveInFlight: false,
  autoSaveQueued: false,
  postSaveRefreshTimer: null,
  pollTimer: null,
  pollInFlight: false,
  lastUsageRefreshAt: 0,
  runtimeRenderSignature: "",
  localKeyRenderSignature: "",
  upstreamSummarySignature: "",
  usageRenderSignature: "",
};

function cloneDeep(value) {
  return JSON.parse(JSON.stringify(value));
}

function signatureOf(value) {
  try {
    return JSON.stringify(value);
  } catch (_error) {
    return String(Date.now());
  }
}

function detectSystemLanguage() {
  const candidates = [...(navigator.languages || []), navigator.language || ""].map((item) => String(item || "").toLowerCase());
  if (candidates.some((item) => item.startsWith("zh"))) {
    return "zh";
  }
  return "en";
}

function detectSystemTheme() {
  return window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

function currentLanguage() {
  const choice = state.config?.ui_language || "auto";
  return choice === "auto" ? detectSystemLanguage() : choice;
}

function currentTheme() {
  const choice = state.config?.theme_mode || "auto";
  return choice === "auto" ? detectSystemTheme() : choice;
}

function applyTheme() {
  document.documentElement.dataset.theme = currentTheme();
}

function finishBootMotion() {
  document.documentElement.dataset.motion = "steady";
}

function t(key, vars = {}) {
  const language = currentLanguage();
  const table = I18N[language] || I18N.en;
  let text = table[key] || I18N.zh[key] || key;
  Object.entries(vars).forEach(([name, value]) => {
    text = text.replaceAll(`{${name}}`, String(value));
  });
  return text;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function normalizeUpstreamProtocol(protocol) {
  if (protocol === "anthropic" || protocol === "gemini" || protocol === "local_llm") {
    return protocol;
  }
  return "openai";
}

const ICON_PATHS = {
  globe: '<circle cx="12" cy="12" r="9"></circle><path d="M3 12h18"></path><path d="M12 3c2.5 2.5 4 5.8 4 9s-1.5 6.5-4 9c-2.5-2.5-4-5.8-4-9s1.5-6.5 4-9Z"></path>',
  theme: '<circle cx="12" cy="12" r="4"></circle><path d="M12 2v2"></path><path d="M12 20v2"></path><path d="m4.93 4.93 1.41 1.41"></path><path d="m17.66 17.66 1.41 1.41"></path><path d="M2 12h2"></path><path d="M20 12h2"></path><path d="m6.34 17.66-1.41 1.41"></path><path d="m19.07 4.93-1.41 1.41"></path>',
  sliders: '<path d="M4 21v-7"></path><path d="M4 10V3"></path><path d="M12 21v-9"></path><path d="M12 8V3"></path><path d="M20 21v-5"></path><path d="M20 12V3"></path><path d="M2 14h4"></path><path d="M10 8h4"></path><path d="M18 16h4"></path>',
  plug: '<path d="M12 22v-5"></path><path d="M9 8V2"></path><path d="M15 8V2"></path><path d="M18 8H6v4a6 6 0 0 0 12 0V8Z"></path>',
  eye: '<path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6-10-6-10-6Z"></path><circle cx="12" cy="12" r="3"></circle>',
  layout: '<rect x="3" y="4" width="18" height="16" rx="2"></rect><path d="M9 4v16"></path><path d="M9 12h12"></path>',
  settings: '<circle cx="12" cy="12" r="3"></circle><path d="M12 2v3"></path><path d="M12 19v3"></path><path d="m4.93 4.93 2.12 2.12"></path><path d="m16.95 16.95 2.12 2.12"></path><path d="M2 12h3"></path><path d="M19 12h3"></path><path d="m4.93 19.07 2.12-2.12"></path><path d="m16.95 7.05 2.12-2.12"></path>',
  key: '<circle cx="8" cy="15" r="4"></circle><path d="M12 15h9"></path><path d="M18 15v3"></path><path d="M21 15v2"></path>',
  save: '<path d="M4 4h12l4 4v12H4z"></path><path d="M8 4v6h8"></path><path d="M8 20v-6h8v6"></path>',
  refresh: '<path d="M21 12a9 9 0 1 1-2.64-6.36"></path><path d="M21 3v6h-6"></path>',
  upload: '<path d="M12 16V4"></path><path d="m7 9 5-5 5 5"></path><path d="M4 20h16"></path>',
  download: '<path d="M12 4v12"></path><path d="m7 11 5 5 5-5"></path><path d="M4 20h16"></path>',
  plus: '<path d="M12 5v14"></path><path d="M5 12h14"></path>',
  wand: '<path d="m7 21 7-7"></path><path d="m5 7 3-3"></path><path d="m8 10-3-3"></path><path d="M15 4h.01"></path><path d="M18 7h.01"></path><path d="M20 2h.01"></path><path d="M21 5h.01"></path><path d="m14 14 6 6"></path>',
  cloud: '<path d="M7 18a5 5 0 1 1 .8-9.94A6 6 0 1 1 18 18Z"></path>',
  chart: '<path d="M4 19V9"></path><path d="M10 19V5"></path><path d="M16 19v-8"></path><path d="M22 19v-4"></path>',
  server: '<rect x="3" y="4" width="18" height="6" rx="1"></rect><rect x="3" y="14" width="18" height="6" rx="1"></rect><path d="M7 7h.01"></path><path d="M7 17h.01"></path>',
  power: '<path d="M12 2v10"></path><path d="M18.36 5.64a9 9 0 1 1-12.72 0"></path>',
  terminal: '<path d="m4 17 6-6-6-6"></path><path d="M12 19h8"></path>',
  message: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>',
  sparkles: '<path d="M12 3l1.6 3.9L17 8.5l-3.4 1.6L12 14l-1.6-3.9L7 8.5l3.4-1.6L12 3z"></path><path d="M19 14l.9 2.1L22 17l-2.1.9L19 20l-.9-2.1L16 17l2.1-.9L19 14z"></path><path d="M5 14l.9 2.1L8 17l-2.1.9L5 20l-.9-2.1L2 17l2.1-.9L5 14z"></path>',
  codexBrand: '<g transform="translate(2.4 2.4) scale(1.2)"><path fill="currentColor" stroke="none" d="M14.949 6.547a3.94 3.94 0 0 0-.348-3.273 4.11 4.11 0 0 0-4.4-1.934A4.1 4.1 0 0 0 8.423.2 4.15 4.15 0 0 0 6.305.086a4.1 4.1 0 0 0-1.891.948 4.04 4.04 0 0 0-1.158 1.753 4.1 4.1 0 0 0-1.563.679A4 4 0 0 0 .554 4.72a3.99 3.99 0 0 0 .502 4.731 3.94 3.94 0 0 0 .346 3.274 4.11 4.11 0 0 0 4.402 1.933c.382.425.852.764 1.377.995.526.231 1.095.35 1.67.346 1.78.002 3.358-1.132 3.901-2.804a4.1 4.1 0 0 0 1.563-.68 4 4 0 0 0 1.14-1.253 3.99 3.99 0 0 0-.506-4.716m-6.097 8.406a3.05 3.05 0 0 1-1.945-.694l.096-.054 3.23-1.838a.53.53 0 0 0 .265-.455v-4.49l1.366.778q.02.011.025.035v3.722c-.003 1.653-1.361 2.992-3.037 2.996m-6.53-2.75a2.95 2.95 0 0 1-.36-2.01l.095.057L5.29 12.09a.53.53 0 0 0 .527 0l3.949-2.246v1.555a.05.05 0 0 1-.022.041L6.473 13.3c-1.454.826-3.311.335-4.15-1.098m-.85-6.94A3.02 3.02 0 0 1 3.07 3.949v3.785a.51.51 0 0 0 .262.451l3.93 2.237-1.366.779a.05.05 0 0 1-.048 0L2.585 9.342a2.98 2.98 0 0 1-1.113-4.094zm11.216 2.571L8.747 5.576l1.362-.776a.05.05 0 0 1 .048 0l3.265 1.86a3 3 0 0 1 1.173 1.207 2.96 2.96 0 0 1-.27 3.2 3.05 3.05 0 0 1-1.36.997V8.279a.52.52 0 0 0-.276-.445m1.36-2.015-.097-.057-3.226-1.855a.53.53 0 0 0-.53 0L6.249 6.153V4.598a.04.04 0 0 1 .019-.04L9.533 2.7a3.07 3.07 0 0 1 3.257.139c.474.325.843.778 1.066 1.303.223.526.289 1.103.191 1.664zM5.503 8.575 4.139 7.8a.05.05 0 0 1-.026-.037V4.049c0-.57.166-1.127.476-1.607s.752-.864 1.275-1.105a3.08 3.08 0 0 1 3.234.41l-.096.054-3.23 1.838a.53.53 0 0 0-.265.455zm.742-1.577 1.758-1 1.762 1v2l-1.755 1-1.762-1z"/></g>',
  claudeBrand: '<path fill="currentColor" stroke="none" d="M17.3041 3.541h-3.6718l6.696 16.918H24Zm-10.6082 0L0 20.459h3.7442l1.3693-3.5527h7.0052l1.3693 3.5528h3.7442L10.5363 3.5409Zm-.3712 10.2232 2.2914-5.9456 2.2914 5.9456Z"/>',
  geminiBrand: '<path fill="currentColor" stroke="none" d="M11.04 19.32Q12 21.51 12 24q0-2.49.93-4.68.96-2.19 2.58-3.81t3.81-2.55Q21.51 12 24 12q-2.49 0-4.68-.93a12.3 12.3 0 0 1-3.81-2.58 12.3 12.3 0 0 1-2.58-3.81Q12 2.49 12 0q0 2.49-.96 4.68-.93 2.19-2.55 3.81a12.3 12.3 0 0 1-3.81 2.58Q2.49 12 0 12q2.49 0 4.68.96 2.19.93 3.81 2.55t2.55 3.81"/>',
  ggmlBrand: '<path fill="currentColor" stroke="none" d="M12 2L2 7v10l10 5 10-5V7L12 2zm0 2.18L19.82 8 12 11.82 4.18 8 12 4.18zM4 9.48l7 3.5v7.84l-7-3.5V9.48zm16 0v7.84l-7 3.5v-7.84l7-3.5z"/>',
  flask: '<path d="M10 2v7l-5 8a4 4 0 0 0 3.4 6h7.2A4 4 0 0 0 19 17l-5-8V2"></path><path d="M8 6h8"></path>',
  check: '<path d="m20 6-11 11-5-5"></path>',
  undo: '<path d="M9 14 4 9l5-5"></path><path d="M20 20a8 8 0 0 0-8-8H4"></path>',
  trash: '<path d="M3 6h18"></path><path d="M8 6V4h8v2"></path><path d="M19 6l-1 14H6L5 6"></path><path d="M10 11v6"></path><path d="M14 11v6"></path>',
  pencil: '<path d="M12 20h9"></path><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"></path>',
  chevronUp: '<path d="m6 14 6-6 6 6"></path>',
  grip: '<circle cx="9" cy="6" r="1"></circle><circle cx="15" cy="6" r="1"></circle><circle cx="9" cy="12" r="1"></circle><circle cx="15" cy="12" r="1"></circle><circle cx="9" cy="18" r="1"></circle><circle cx="15" cy="18" r="1"></circle>',
};

function iconMarkup(name, iconClass = "icon icon-sm") {
  const paths = ICON_PATHS[name] || ICON_PATHS.sparkles;
  return `<svg class="${escapeHtml(iconClass)}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths}</svg>`;
}

function protocolIconName(protocol) {
  const normalized = normalizeUpstreamProtocol(protocol);
  if (normalized === "anthropic") {
    return "claudeBrand";
  }
  if (normalized === "gemini") {
    return "geminiBrand";
  }
  if (normalized === "local_llm") {
    return "ggmlBrand";
  }
  return "codexBrand";
}

function protocolBrandMarkup(protocol, compact = false) {
  const normalized = normalizeUpstreamProtocol(protocol);
  return `<span class="protocol-brand ${escapeHtml(normalized)} ${compact ? "compact" : ""}">${iconMarkup(protocolIconName(normalized), compact ? "icon icon-sm" : "icon icon-md")}</span>`;
}

function protocolLabelMarkup(protocol, label, compact = false) {
  return `<span class="${compact ? "protocol-inline" : "protocol-brand-label"}">${protocolBrandMarkup(protocol, compact)}<span>${escapeHtml(label)}</span></span>`;
}

function iconLabelMarkup(iconName, label, iconClass = "icon icon-sm") {
  return `${iconMarkup(iconName, iconClass)}<span>${escapeHtml(label)}</span>`;
}

function buttonLabelMarkup(iconName, label, iconClass = "icon icon-sm") {
  return iconLabelMarkup(iconName, label, iconClass);
}

function setIconLabel(id, iconName, label, iconClass = "icon icon-sm") {
  const node = document.getElementById(id);
  if (!node) {
    return;
  }
  node.innerHTML = iconLabelMarkup(iconName, label, iconClass);
}

function statusIndicatorMarkup(kind, label) {
  return `<span class="status-indicator"><span class="status-dot ${escapeHtml(kind)}"></span><span>${escapeHtml(label)}</span></span>`;
}

function setModeButtonState(button, active, options = {}) {
  if (!button) {
    return;
  }
  button.classList.toggle("active", Boolean(active));
  button.disabled = Boolean(options.disabled);
}

function randomKey() {
  return `sk-local-${crypto.randomUUID().replaceAll("-", "").slice(0, 24)}`;
}

function sanitizeHttpMessage(text) {
  return String(text || "")
    .replace(/<[^>]*>/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 180);
}

async function getJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const rawText = await response.text();
  let payload = null;
  if (rawText) {
    try {
      payload = JSON.parse(rawText);
    } catch {
      payload = null;
    }
  }
  if (!response.ok) {
    const message = payload?.error?.message || payload?.message || sanitizeHttpMessage(rawText) || `HTTP ${response.status}`;
    const error = new Error(message);
    error.status = response.status;
    error.url = url;
    error.payload = payload;
    throw error;
  }
  if (payload !== null) {
    return payload;
  }
  return rawText ? { raw: rawText } : {};
}

function flash(message, kind = "ok") {
  const node = document.getElementById("flash");
  node.textContent = message;
  node.className = `flash ${kind}`;
}

function renderSwitchChipHtml({ label, active = false, compact = false, className = "", attrs = "" }) {
  const classes = ["switch-chip"];
  if (compact) {
    classes.push("compact");
  }
  if (active) {
    classes.push("active");
  }
  if (className) {
    classes.push(className);
  }
  return `
    <button class="${classes.join(" ")}" type="button" aria-pressed="${active ? "true" : "false"}" ${attrs}>
      <span class="switch-track"><span class="switch-knob"></span></span>
      <span class="switch-label">${escapeHtml(label)}</span>
    </button>
  `;
}

function setSwitchChipState(button, active, label, options = {}) {
  if (!button) {
    return;
  }
  button.classList.toggle("active", Boolean(active));
  button.classList.toggle("partial", Boolean(options.partial));
  button.disabled = Boolean(options.disabled);
  button.setAttribute("aria-pressed", active ? "true" : "false");
  const labelNode = button.querySelector(".switch-label");
  if (labelNode) {
    labelNode.textContent = label;
  }
}

function switchChipIsActive(control) {
  if (!control) {
    return false;
  }
  if (typeof control.checked === "boolean") {
    return Boolean(control.checked);
  }
  return control.getAttribute("aria-pressed") === "true";
}

function clientBindingNextAction(info) {
  return info?.state === "not_switched" || !info?.state ? "switch" : "restore";
}
