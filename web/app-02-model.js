function normalizeLocalKeyProtocols(value) {
  const rawItems = Array.isArray(value) ? value : value ? [value] : [];
  const aliases = {
    openai: "openai",
    codex: "openai",
    anthropic: "anthropic",
    claude: "anthropic",
    gemini: "gemini",
  };
  const normalized = rawItems
    .map((item) => aliases[String(item || "").trim().toLowerCase()] || "")
    .filter(Boolean)
    .filter((item, index, array) => array.indexOf(item) === index);
  return normalized.length ? normalized : [...PROTOCOL_ORDER];
}

function normalizeSubscriptionKind(value) {
  return value === "periodic" || value === "quota" ? value : "unlimited";
}

function normalizeSubscriptionFailureMode(value, kind = "unlimited") {
  if (value === "consecutive_days" || value === "consecutive_failures") {
    return value;
  }
  return kind === "quota" ? "consecutive_days" : "consecutive_failures";
}

function normalizeRefreshTime(value) {
  const match = String(value || "").trim().match(/^(\d{1,2}):(\d{1,2})/);
  if (!match) {
    return "";
  }
  const hour = Number(match[1]);
  const minute = Number(match[2]);
  if (!Number.isInteger(hour) || !Number.isInteger(minute) || hour < 0 || hour > 23 || minute < 0 || minute > 59) {
    return "";
  }
  return `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
}

function normalizeRefreshTimes(value) {
  const items = Array.isArray(value) ? value : value ? [value] : [];
  return [...new Set(items.map((item) => normalizeRefreshTime(item)).filter(Boolean))].sort();
}

function subscriptionExpiryDateTime(subscription) {
  if (subscription?.permanent !== false) {
    return null;
  }
  const raw = String(subscription?.expires_at || "").trim();
  if (!raw) {
    return null;
  }
  const dateValue = new Date(`${raw}T00:00:00`);
  if (Number.isNaN(dateValue.getTime())) {
    return null;
  }
  if (normalizeSubscriptionKind(subscription?.kind) === "periodic") {
    const resetTimes = normalizeRefreshTimes(subscription?.refresh_times || subscription?.reset_times);
    const latestReset = (resetTimes.length ? resetTimes : ["00:00"]).slice(-1)[0];
    const [hourRaw, minuteRaw] = latestReset.split(":");
    dateValue.setHours(Number(hourRaw || 0), Number(minuteRaw || 0), 0, 0);
    return dateValue;
  }
  dateValue.setHours(23, 59, 59, 999);
  return dateValue;
}

function subscriptionIsExpired(subscription) {
  const expiry = subscriptionExpiryDateTime(subscription);
  if (!expiry) {
    return false;
  }
  return Date.now() > expiry.getTime();
}

function defaultSubscription(index = 0, upstreamName = "") {
  const nameBase = upstreamName || (currentLanguage() === "zh" ? "订阅" : "Subscription");
  return {
    id: crypto.randomUUID().replaceAll("-", "").slice(0, 12),
    name: currentLanguage() === "zh" ? `${nameBase} ${index + 1}` : `${nameBase} ${index + 1}`,
    kind: "unlimited",
    enabled: true,
    permanent: true,
    expires_at: "",
    refresh_times: [],
    failure_mode: "consecutive_failures",
    failure_threshold: 1,
  };
}

function normalizeSubscription(item, index = 0, upstreamName = "") {
  const kind = normalizeSubscriptionKind(item?.kind || item?.type);
  const permanent = item?.permanent !== false && !String(item?.expires_at || "").trim() ? true : item?.permanent !== false;
  const normalized = {
    id: item?.id || crypto.randomUUID().replaceAll("-", "").slice(0, 12),
    name: item?.name || (currentLanguage() === "zh" ? `${upstreamName || "订阅"} ${index + 1}` : `${upstreamName || "Subscription"} ${index + 1}`),
    kind,
    enabled: item?.enabled !== false,
    permanent,
    expires_at: permanent ? "" : String(item?.expires_at || "").trim(),
    refresh_times: kind === "periodic" ? normalizeRefreshTimes(item?.refresh_times || item?.reset_times) : [],
    failure_mode: normalizeSubscriptionFailureMode(item?.failure_mode, kind),
    failure_threshold: Math.max(1, Number(item?.failure_threshold || (kind === "quota" ? 2 : 1)) || (kind === "quota" ? 2 : 1)),
  };
  if (kind === "quota" && normalized.failure_mode !== "consecutive_days" && !item?.failure_mode) {
    normalized.failure_mode = "consecutive_days";
    normalized.failure_threshold = Math.max(1, Number(item?.failure_threshold || 2) || 2);
  }
  if (kind === "periodic" && !normalized.refresh_times.length) {
    normalized.refresh_times = ["09:00"];
  }
  normalized.expired = subscriptionIsExpired(normalized);
  if (normalized.expired) {
    normalized.enabled = false;
  }
  return normalized;
}

function normalizeUpstreamSubscriptions(upstream) {
  const subscriptions = Array.isArray(upstream?.subscriptions) ? upstream.subscriptions : [];
  const normalized = subscriptions.map((item, index) => normalizeSubscription(item, index, upstream?.name || ""));
  return normalized.length ? normalized : [defaultSubscription(0, upstream?.name || "")];
}

function currentProtocol() {
  return PROTOCOL_ORDER.includes(state.currentProtocolTab) ? state.currentProtocolTab : "openai";
}

function platformText(protocol = currentProtocol()) {
  if (protocol === "anthropic") {
    return t("platformClaude");
  }
  if (protocol === "gemini") {
    return t("platformGemini");
  }
  if (protocol === "local_llm") {
    return t("platformLocalLLM");
  }
  return t("platformCodex");
}

function defaultModelPlaceholder(protocol = currentProtocol()) {
  const normalized = normalizeUpstreamProtocol(protocol);
  if (normalized === "anthropic") {
    return t("globalDefaultModelPlaceholderAnthropic");
  }
  if (normalized === "gemini") {
    return t("globalDefaultModelPlaceholderGemini");
  }
  if (normalized === "local_llm") {
    return t("globalDefaultModelPlaceholderLocalLLM");
  }
  return t("globalDefaultModelPlaceholderOpenAI");
}

function localKeyProtocolSummary(protocols) {
  const normalized = normalizeLocalKeyProtocols(protocols);
  if (normalized.length === PROTOCOL_ORDER.length) {
    return t("localKeyAllTypes");
  }
  return normalized.map((protocol) => platformText(protocol)).join(" / ");
}

function normalizeLocalKeys(config) {
  if (!config.local_api_keys || !config.local_api_keys.length) {
    config.local_api_keys = [
      {
        id: crypto.randomUUID().replaceAll("-", "").slice(0, 12),
        name: currentLanguage() === "zh" ? "本地 Key 1" : "Local Key 1",
        key: config.local_api_key || randomKey(),
        enabled: true,
        created_at: new Date().toISOString(),
        allowed_protocols: [...PROTOCOL_ORDER],
      },
    ];
  }
  config.local_api_keys = config.local_api_keys
    .map((item, index) => ({
      id: item.id || crypto.randomUUID().replaceAll("-", "").slice(0, 12),
      name: item.name || (currentLanguage() === "zh" ? `本地 Key ${index + 1}` : `Local Key ${index + 1}`),
      key: item.key || item.api_key || item.value || randomKey(),
      enabled: item.enabled !== false,
      created_at: item.created_at || new Date().toISOString(),
      allowed_protocols: normalizeLocalKeyProtocols(item.allowed_protocols || item.protocols),
    }))
    .filter((item, index, array) => item.key && array.findIndex((candidate) => candidate.key === item.key) === index);
  if (!config.local_api_keys.length) {
    config.local_api_keys = [
      {
        id: crypto.randomUUID().replaceAll("-", "").slice(0, 12),
        name: currentLanguage() === "zh" ? "本地 Key 1" : "Local Key 1",
        key: randomKey(),
        enabled: true,
        created_at: new Date().toISOString(),
        allowed_protocols: [...PROTOCOL_ORDER],
      },
    ];
  }
  if (!config.local_api_keys.some((item) => item.enabled)) {
    config.local_api_keys[0].enabled = true;
  }
  const primary = config.local_api_keys.find((item) => item.enabled) || config.local_api_keys[0];
  config.local_api_key = primary.key;
  return config;
}

function primaryLocalKey() {
  const keys = state.config?.local_api_keys || [];
  return keys.find((item) => item.enabled) || keys[0] || null;
}

function localKeyStatusMap() {
  return new Map((state.status?.local_api_keys || []).map((item) => [item.id, item]));
}

function getConfigLocalKey(id) {
  return (state.config?.local_api_keys || []).find((item) => item.id === id);
}

function getRenderedLocalKey(id) {
  return getConfigLocalKey(id) || (state.usage?.local_keys || []).find((item) => item.id === id) || null;
}

function localKeyAllowsProtocol(entry, protocol) {
  if (!protocol) {
    return true;
  }
  return normalizeLocalKeyProtocols(entry?.allowed_protocols || entry?.protocols).includes(protocol);
}

function formatLocalKeyLastUsed(value) {
  if (!value) {
    return t("localKeyNeverUsed");
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString(currentLanguage() === "zh" ? "zh-CN" : "en-US");
}

function normalizeRoutingMode(mode) {
  return mode === "round_robin" || mode === "latency" || mode === "priority" ? mode : "priority";
}

function workspaceExpanded() {
  return state.workspaceOpen !== false;
}

function usageScopeKey() {
  return PROTOCOL_ORDER.includes(state.usageScope) ? state.usageScope : "all";
}

function usageScopeProtocol() {
  return PROTOCOL_ORDER.includes(usageScopeKey()) ? usageScopeKey() : "";
}

function usageLocalKeyOptions() {
  const protocol = usageScopeProtocol();
  const configuredKeys = (state.config?.local_api_keys || [])
    .filter((item) => !protocol || localKeyAllowsProtocol(item, protocol))
    .map((item) => ({ id: item.id, name: item.name || item.id }));
  const seen = new Set(configuredKeys.map((item) => item.id));
  for (const item of state.usage?.local_keys || []) {
    if (!item?.id || seen.has(item.id)) {
      continue;
    }
    configuredKeys.push({ id: item.id, name: item.name || item.id });
    seen.add(item.id);
  }
  return configuredKeys;
}

function usageLocalKeyKey() {
  const selected = String(state.usageLocalKey ?? "all").trim();
  if (!selected || selected === t("usageLocalKeyAll")) {
    return "all";
  }
  if (selected === t("usageLocalKeyDirect")) {
    return "";
  }
  return selected;
}

function usageLocalKeyDisplayValue(value = usageLocalKeyKey()) {
  if (value === "all") {
    return t("usageLocalKeyAll");
  }
  if (value === "") {
    return t("usageLocalKeyDirect");
  }
  const matched = usageLocalKeyOptions().find((item) => item.id === value);
  return matched ? (matched.name || matched.id) : value;
}

function resolveUsageLocalKeyInputValue(rawValue, { allowRaw = false } = {}) {
  const value = String(rawValue ?? "").trim();
  if (!value || value === t("usageLocalKeyAll")) {
    return "all";
  }
  if (value === t("usageLocalKeyDirect")) {
    return "";
  }
  const matched = usageLocalKeyOptions().find((item) => value === item.id || value === item.name);
  if (matched) {
    return matched.id;
  }
  return allowRaw ? value : null;
}

function usageTitleText() {
  const protocol = usageScopeProtocol();
  return !protocol
    ? t("usageTitleGlobal")
    : t("usageTitle", { platform: platformText(protocol) });
}

function usageHintText() {
  const protocol = usageScopeProtocol();
  return !protocol
    ? t("usageHintGlobal")
    : t("usageHint", { platform: platformText(protocol) });
}

function usageSummaryText() {
  return `${usageHintText()} ${t("usageMetricLabel")} · ${t("usageMetricHint")}`;
}

function renderWorkspacePanels() {
  const expanded = workspaceExpanded();
  const collapsedPanel = document.getElementById("workspaceCollapsedPanel");
  const detailPanel = document.getElementById("workspaceDetailPanel");
  if (collapsedPanel) {
    collapsedPanel.hidden = expanded;
  }
  if (detailPanel) {
    detailPanel.hidden = !expanded;
  }
}

function clientDisplayName(client) {
  if (client === "claude") {
    return t("platformClaude");
  }
  if (client === "gemini") {
    return t("platformGemini");
  }
  return t("platformCodex");
}

function displayRuntimeHost(host) {
  return host && !["0.0.0.0", "::"].includes(host) ? host : "127.0.0.1";
}

function lanAccessEnabled(config = state.config) {
  ensureEndpointConfig(config);
  const host = String(config?.listen_host || "").trim().toLowerCase();
  return !["127.0.0.1", "localhost", "::1", ""].includes(host);
}

function normalizeApiPrefix(value, fallback) {
  const raw = String(value || fallback || "").trim() || fallback;
  const withSlash = raw.startsWith("/") ? raw : `/${raw}`;
  return withSlash === "/" ? withSlash : withSlash.replace(/\/+$/, "");
}

function ensureEndpointConfig(config = state.config) {
  if (!config) {
    return;
  }
  config.endpoint_mode = config.endpoint_mode === "split" ? "split" : "shared";
  config.listen_host = String(config.listen_host || "127.0.0.1").trim() || "127.0.0.1";
  config.listen_port = Number(config.listen_port || 8787) || 8787;
  config.shared_api_prefixes = {
    ...DEFAULT_SHARED_API_PREFIXES,
    ...(config.shared_api_prefixes || {}),
  };
  PROTOCOL_ORDER.forEach((protocol) => {
    config.shared_api_prefixes[protocol] = normalizeApiPrefix(
      config.shared_api_prefixes[protocol],
      DEFAULT_SHARED_API_PREFIXES[protocol],
    );
  });
  const basePort = Number(config.listen_port || 8787) || 8787;
  config.split_api_ports = {
    openai: Number(config.split_api_ports?.openai || basePort) || basePort,
    anthropic: Number(config.split_api_ports?.anthropic || DEFAULT_SPLIT_API_PORTS.anthropic) || DEFAULT_SPLIT_API_PORTS.anthropic,
    gemini: Number(config.split_api_ports?.gemini || DEFAULT_SPLIT_API_PORTS.gemini) || DEFAULT_SPLIT_API_PORTS.gemini,
    local_llm: Number(config.split_api_ports?.local_llm || DEFAULT_SPLIT_API_PORTS.local_llm) || DEFAULT_SPLIT_API_PORTS.local_llm,
  };
  const fallbackWebPort = config.endpoint_mode === "shared"
    ? basePort + 10
    : config.split_api_ports.openai + 10;
  if (config.endpoint_mode === "shared") {
    config.web_ui_port = basePort;
    return;
  }
  const apiPorts = config.endpoint_mode === "shared"
    ? [basePort]
    : Object.values(config.split_api_ports || {}).map((value) => Number(value || 0));
  let parsedWebPort = Number(config.web_ui_port || fallbackWebPort) || fallbackWebPort;
  if (
    !(config.endpoint_mode === "shared" && parsedWebPort === basePort)
    && (!Number.isInteger(parsedWebPort) || parsedWebPort < 1 || parsedWebPort > 65535 || apiPorts.includes(parsedWebPort))
  ) {
    parsedWebPort = fallbackWebPort;
  }
  config.web_ui_port = parsedWebPort;
}

function endpointMode() {
  ensureEndpointConfig(state.config);
  return state.config.endpoint_mode;
}

function protocolLocalPath(config = state.config, protocol = currentProtocol()) {
  ensureEndpointConfig(config);
  if (config.endpoint_mode === "split") {
    return NATIVE_API_PREFIXES[protocol];
  }
  return config.shared_api_prefixes?.[protocol] || DEFAULT_SHARED_API_PREFIXES[protocol];
}

function protocolListenPort(config = state.config, protocol = currentProtocol()) {
  ensureEndpointConfig(config);
  if (config.endpoint_mode === "split") {
    return Number(config.split_api_ports?.[protocol] || DEFAULT_SPLIT_API_PORTS[protocol]) || DEFAULT_SPLIT_API_PORTS[protocol];
  }
  return Number(config.listen_port || 8787) || 8787;
}

function protocolLocalUrl(config = state.config, protocol = currentProtocol()) {
  ensureEndpointConfig(config);
  const host = displayRuntimeHost(String(config.listen_host || "127.0.0.1"));
  const port = protocolListenPort(config, protocol);
  const path = protocolLocalPath(config, protocol);
  return `http://${host}:${port}${path}`;
}

function dashboardUrlForConfig(config = state.config) {
  ensureEndpointConfig(config);
  const target = new URL(window.location.href);
  target.port = String(Number(config.web_ui_port || target.port || "80"));
  target.pathname = "/";
  target.search = "";
  target.hash = "";
  return target.toString();
}

function protocolUpstreamIds(config, protocol) {
  return (config?.upstreams || [])
    .filter((item) => normalizeUpstreamProtocol(item.protocol) === protocol)
    .map((item) => item.id);
}

function ensureRoutingByProtocol(config) {
  if (!config) {
    return;
  }
  if (!config.routing_by_protocol || typeof config.routing_by_protocol !== "object") {
    config.routing_by_protocol = {};
  }
  PROTOCOL_ORDER.forEach((protocol) => {
    const ids = protocolUpstreamIds(config, protocol);
    const existing = config.routing_by_protocol[protocol] || {};
    let manualId = String(
      existing.manual_active_upstream_id || (protocol === "openai" ? config.manual_active_upstream_id || "" : ids[0] || ""),
    ).trim();
    if (!ids.includes(manualId)) {
      manualId = ids[0] || "";
    }
    config.routing_by_protocol[protocol] = {
      auto_routing_enabled:
        typeof existing.auto_routing_enabled === "boolean"
          ? existing.auto_routing_enabled
          : (protocol === "openai" ? config.auto_routing_enabled !== false : true),
      routing_mode: normalizeRoutingMode(existing.routing_mode || (protocol === "openai" ? config.routing_mode : "priority")),
      manual_active_upstream_id: manualId,
    };
  });
  const openai = config.routing_by_protocol.openai;
  config.auto_routing_enabled = openai.auto_routing_enabled;
  config.routing_mode = openai.routing_mode;
  config.manual_active_upstream_id = openai.manual_active_upstream_id;
}

function getRoutingStrategyFromConfig(config, protocol = currentProtocol()) {
  ensureRoutingByProtocol(config);
  const section = config?.routing_by_protocol?.[protocol] || {};
  return section.auto_routing_enabled === false ? "manual" : "auto";
}

function getAutoRoutingModeFromConfig(config, protocol = currentProtocol()) {
  ensureRoutingByProtocol(config);
  const section = config?.routing_by_protocol?.[protocol] || {};
  return normalizeRoutingMode(section.routing_mode || "priority");
}

function applyRoutingStrategyToConfig(strategy, protocol = currentProtocol()) {
  ensureRoutingByProtocol(state.config);
  const section = state.config.routing_by_protocol[protocol];
  if (strategy === "manual") {
    section.auto_routing_enabled = false;
  } else {
    section.auto_routing_enabled = true;
    section.routing_mode = normalizeRoutingMode(section.routing_mode || "priority");
  }
  if (protocol === "openai") {
    state.config.auto_routing_enabled = section.auto_routing_enabled;
    state.config.routing_mode = section.routing_mode;
    state.config.manual_active_upstream_id = section.manual_active_upstream_id;
  }
}

function setAutoRoutingMode(mode, protocol = currentProtocol()) {
  ensureRoutingByProtocol(state.config);
  const section = state.config.routing_by_protocol[protocol];
  section.auto_routing_enabled = true;
  section.routing_mode = normalizeRoutingMode(mode);
  if (protocol === "openai") {
    state.config.auto_routing_enabled = true;
    state.config.routing_mode = section.routing_mode;
  }
}

function setManualActiveUpstreamId(upstreamId, protocol = currentProtocol()) {
  ensureRoutingByProtocol(state.config);
  const validIds = protocolUpstreamIds(state.config, protocol);
  const fallback = validIds[0] || "";
  const manualId = validIds.includes(upstreamId) ? upstreamId : fallback;
  state.config.routing_by_protocol[protocol].manual_active_upstream_id = manualId;
  if (protocol === "openai") {
    state.config.manual_active_upstream_id = manualId;
  }
}

function getConfigUpstream(id) {
  return (state.config?.upstreams || []).find((item) => item.id === id);
}

function getRenderedUpstream(id) {
  const upstream = state.editorDrafts[id] || getConfigUpstream(id);
  if (!upstream) {
    return upstream;
  }
  return {
    ...upstream,
    protocol: normalizeUpstreamProtocol(upstream.protocol),
    subscriptions: normalizeUpstreamSubscriptions(upstream),
  };
}

function statusMap() {
  return new Map((state.status?.upstreams || []).map((item) => [item.id, item]));
}

function protocolStatus(protocol = currentProtocol()) {
  return state.status?.routing?.protocols?.[protocol] || {};
}

function protocolConfigUpstreams(protocol = currentProtocol()) {
  return (state.config?.upstreams || []).filter((item) => normalizeUpstreamProtocol(item.protocol) === protocol);
}

function protocolRenderedUpstreams(protocol = currentProtocol()) {
  return protocolConfigUpstreams(protocol)
    .map((item) => getRenderedUpstream(item.id))
    .filter(Boolean);
}

function statusTimestamp(value) {
  const parsed = Date.parse(String(value || ""));
  return Number.isFinite(parsed) ? parsed : 0;
}

function latestUpstreamConnectivityState(upstreamId) {
  const localProbe = state.localProbeResults?.[upstreamId];
  if (localProbe && (localProbe.status || localProbe.error)) {
    return localProbe.status ? "connected" : "disconnected";
  }
  const statusEntry = statusMap().get(upstreamId) || {};
  const stats = statusEntry.stats || {};
  const probeTs = statusTimestamp(stats.last_probe_at);
  const requestTs = statusTimestamp(stats.last_attempt_at);
  const hasProbeSignal = Boolean(stats.last_probe_status) || Boolean(stats.last_probe_error);
  const hasRequestSignal = stats.last_status != null || Boolean(stats.last_error);
  if (probeTs >= requestTs && hasProbeSignal) {
    return stats.last_probe_status ? "connected" : "disconnected";
  }
  if (requestTs > probeTs && hasRequestSignal) {
    const statusCode = Number(stats.last_status || 0);
    return statusCode >= 200 && statusCode < 400 ? "connected" : "disconnected";
  }
  if (hasProbeSignal) {
    return stats.last_probe_status ? "connected" : "disconnected";
  }
  if (hasRequestSignal) {
    const statusCode = Number(stats.last_status || 0);
    return statusCode >= 200 && statusCode < 400 ? "connected" : "disconnected";
  }
  return "unknown";
}

function upstreamCountsAsConnected(upstream) {
  if (!upstream?.enabled || !String(upstream.base_url || "").trim() || !String(upstream.api_key || "").trim()) {
    return false;
  }
  const statusEntry = statusMap().get(upstream.id) || {};
  if (Object.keys(statusEntry).length && statusEntry.subscription_available === false) {
    return false;
  }
  return latestUpstreamConnectivityState(upstream.id) === "connected";
}

function protocolConnectivitySummary(protocol = currentProtocol()) {
  const upstreams = protocolRenderedUpstreams(protocol);
  const total = upstreams.length;
  const connected = upstreams.filter((item) => upstreamCountsAsConnected(item)).length;
  let kind = "";
  if (total > 0) {
    kind = connected === total ? "ok" : connected > 0 ? "warn" : "bad";
  }
  return { connected, total, kind };
}

function localProtocolRoutingState(protocol = currentProtocol()) {
  ensureRoutingByProtocol(state.config);
  const upstreams = protocolRenderedUpstreams(protocol);
  const preview = upstreams.map((item) => ({ id: item.id, name: item.name || item.id }));
  const section = state.config?.routing_by_protocol?.[protocol] || {};
  return {
    auto_routing_enabled: section.auto_routing_enabled !== false,
    routing_mode: normalizeRoutingMode(section.routing_mode || "priority"),
    manual_active_upstream_id: section.manual_active_upstream_id || upstreams[0]?.id || "",
    preview_order: preview,
  };
}

function effectiveProtocolRoutingState(protocol = currentProtocol()) {
  const upstreamIds = new Set(protocolRenderedUpstreams(protocol).map((item) => item.id));
  const remote = protocolStatus(protocol);
  const remotePreview = Array.isArray(remote.preview_order) ? remote.preview_order : [];
  const remoteCoversCurrentUpstreams =
    (remote.manual_active_upstream_id && upstreamIds.has(remote.manual_active_upstream_id)) ||
    remotePreview.some((item) => upstreamIds.has(item.id));
  if (remoteCoversCurrentUpstreams) {
    return remote;
  }
  return localProtocolRoutingState(protocol);
}
