function normalizeClientConfigSnapshot(config) {
  const normalized = cloneDeep(config || {});
  normalized.upstreams = Array.isArray(normalized.upstreams) ? normalized.upstreams : [];
  normalizeLocalKeys(normalized);
  ensureEndpointConfig(normalized);
  normalized.upstreams = normalized.upstreams.map((upstream) => {
    const nextUpstream = cloneDeep(upstream || {});
    nextUpstream.protocol = normalizeUpstreamProtocol(nextUpstream.protocol);
    nextUpstream.subscriptions = normalizeUpstreamSubscriptions(nextUpstream);
    return nextUpstream;
  });
  ensureRoutingByProtocol(normalized);
  return normalized;
}

function applyServerConfigSnapshot(config, { replaceCurrent = false, clearEditorDrafts = false } = {}) {
  const normalized = normalizeClientConfigSnapshot(config);
  state.savedConfig = cloneDeep(normalized);
  if (replaceCurrent) {
    state.config = cloneDeep(normalized);
  }
  if (clearEditorDrafts) {
    state.editorDrafts = {};
  }
  return normalized;
}

function getPersistableConfig(includeEditorDrafts = true) {
  const merged = cloneDeep(state.config || {});
  const baseUpstreams = Array.isArray(merged.upstreams) ? merged.upstreams : [];
  merged.upstreams = baseUpstreams.map((upstream) =>
    cloneDeep(includeEditorDrafts ? (state.editorDrafts[upstream.id] || upstream) : upstream)
  );
  return normalizeClientConfigSnapshot(merged);
}

function snapshotEquals(left, right) {
  return signatureOf(left) === signatureOf(right);
}

function runtimeApplyComparisonEnabled() {
  const service = state.status?.service || {};
  if (service.owner === "external") {
    return false;
  }
  if (service.state === "running" || service.state === "partial") {
    return true;
  }
  return Array.isArray(service.active_protocols) && service.active_protocols.length > 0;
}

function previewConfigSliceFromNormalized(config) {
  ensureEndpointConfig(config);
  const payload = {
    endpoint_mode: config.endpoint_mode,
    listen_host: String(config.listen_host || "127.0.0.1"),
    web_ui_port: Number(config.web_ui_port || 0) || webUiPortForNormalizedConfig(config),
  };
  if (config.endpoint_mode === "shared") {
    payload.listen_port = Number(config.listen_port || 8787) || 8787;
    payload.shared_api_prefixes = cloneDeep(config.shared_api_prefixes || DEFAULT_SHARED_API_PREFIXES);
    return payload;
  }
  payload.split_api_ports = cloneDeep(config.split_api_ports || DEFAULT_SPLIT_API_PORTS);
  return payload;
}

function protocolNetworkSliceFromNormalized(config, protocol) {
  ensureEndpointConfig(config);
  const normalizedProtocol = normalizeUpstreamProtocol(protocol);
  if (config.endpoint_mode === "shared") {
    return {
      endpoint_mode: "shared",
      listen_host: String(config.listen_host || "127.0.0.1"),
      listen_port: Number(config.listen_port || 8787) || 8787,
      path: config.shared_api_prefixes?.[normalizedProtocol] || DEFAULT_SHARED_API_PREFIXES[normalizedProtocol],
    };
  }
  return {
    endpoint_mode: "split",
    listen_host: String(config.listen_host || "127.0.0.1"),
    listen_port: Number(config.split_api_ports?.[normalizedProtocol] || DEFAULT_SPLIT_API_PORTS[normalizedProtocol]) || DEFAULT_SPLIT_API_PORTS[normalizedProtocol],
  };
}

function protocolBasicSettingsSliceFromNormalized(config, protocol = currentProtocol()) {
  ensureEndpointConfig(config);
  ensureRoutingByProtocol(config);
  const normalizedProtocol = normalizeUpstreamProtocol(protocol);
  return {
    protocol: normalizedProtocol,
    network: protocolNetworkSliceFromNormalized(config, normalizedProtocol),
    request_timeout_sec: Number(config.request_timeout_sec || 0),
    cooldown_seconds: Number(config.cooldown_seconds || 0),
    default_model_mode: String(config.default_model_mode || "upstream"),
    global_default_model: String(config.global_default_model || ""),
    routing: cloneDeep(config.routing_by_protocol?.[normalizedProtocol] || {}),
  };
}

function protocolUpstreamsSliceFromNormalized(config, protocol = currentProtocol()) {
  const normalizedProtocol = normalizeUpstreamProtocol(protocol);
  return (config.upstreams || [])
    .filter((upstream) => normalizeUpstreamProtocol(upstream.protocol) === normalizedProtocol)
    .map((upstream) => cloneDeep(upstream));
}

function workspaceSliceFromNormalized(config) {
  ensureRoutingByProtocol(config);
  return {
    request_timeout_sec: Number(config.request_timeout_sec || 0),
    cooldown_seconds: Number(config.cooldown_seconds || 0),
    default_model_mode: String(config.default_model_mode || "upstream"),
    global_default_model: String(config.global_default_model || ""),
    protocols: PROTOCOL_ORDER.map((protocol) => ({
      protocol,
      network: protocolNetworkSliceFromNormalized(config, protocol),
      routing: cloneDeep(config.routing_by_protocol?.[protocol] || {}),
    })),
    upstreams: cloneDeep(config.upstreams || []),
  };
}

function localKeysSliceFromNormalized(config) {
  normalizeLocalKeys(config);
  return cloneDeep(config.local_api_keys || []);
}

function webUiPortForNormalizedConfig(config) {
  const basePort = Number(config.listen_port || 8787) || 8787;
  if (config.endpoint_mode === "shared") {
    return basePort;
  }
  const fallbackWebPort = Number(config.split_api_ports?.openai || basePort) + 10;
  const apiPorts = Object.values(config.split_api_ports || {}).map((value) => Number(value || 0));
  const current = Number(config.web_ui_port || fallbackWebPort) || fallbackWebPort;
  if (!Number.isInteger(current) || current < 1 || current > 65535 || apiPorts.includes(current)) {
    return fallbackWebPort;
  }
  return current;
}

function runtimeSnapshotConfig() {
  if (!state.status?.runtime) {
    return null;
  }
  const runtime = state.status.runtime;
  const runtimeConfig = {
    listen_host: String(runtime.listen_host || runtime.host || "127.0.0.1"),
    listen_port: Number(runtime.listen_port || 8787) || 8787,
    endpoint_mode: runtime.endpoint_mode === "split" ? "split" : "shared",
    shared_api_prefixes: cloneDeep(runtime.shared_api_prefixes || DEFAULT_SHARED_API_PREFIXES),
    split_api_ports: cloneDeep(runtime.split_api_ports || DEFAULT_SPLIT_API_PORTS),
    web_ui_port: Number(runtime.web_ui_port || runtime.port || 0) || 0,
    upstreams: [],
    local_api_keys: [],
  };
  return normalizeClientConfigSnapshot(runtimeConfig);
}

function computeDirtySections() {
  const emptySections = {
    preview: false,
    localKeys: false,
    workspace: false,
    basicSettings: false,
    upstreamList: false,
  };
  if (!state.config) {
    return { overall: false, sections: emptySections };
  }

  const currentConfig = getPersistableConfig(true);
  const savedConfig = state.savedConfig ? normalizeClientConfigSnapshot(state.savedConfig) : currentConfig;
  const runtimeConfig = runtimeApplyComparisonEnabled() ? runtimeSnapshotConfig() : null;
  const currentProtocolId = currentProtocol();

  const previewUnsaved = !snapshotEquals(
    previewConfigSliceFromNormalized(currentConfig),
    previewConfigSliceFromNormalized(savedConfig),
  );
  const previewRuntimePending = Boolean(runtimeConfig) && !snapshotEquals(
    previewConfigSliceFromNormalized(savedConfig),
    previewConfigSliceFromNormalized(runtimeConfig),
  );

  const localKeysDirty = !snapshotEquals(
    localKeysSliceFromNormalized(currentConfig),
    localKeysSliceFromNormalized(savedConfig),
  );

  const workspaceUnsaved = !snapshotEquals(
    workspaceSliceFromNormalized(currentConfig),
    workspaceSliceFromNormalized(savedConfig),
  );
  const workspaceRuntimePending = Boolean(runtimeConfig) && !snapshotEquals(
    PROTOCOL_ORDER.map((protocol) => protocolNetworkSliceFromNormalized(savedConfig, protocol)),
    PROTOCOL_ORDER.map((protocol) => protocolNetworkSliceFromNormalized(runtimeConfig, protocol)),
  );

  const basicUnsaved = !snapshotEquals(
    protocolBasicSettingsSliceFromNormalized(currentConfig, currentProtocolId),
    protocolBasicSettingsSliceFromNormalized(savedConfig, currentProtocolId),
  );
  const basicRuntimePending = Boolean(runtimeConfig) && !snapshotEquals(
    protocolNetworkSliceFromNormalized(savedConfig, currentProtocolId),
    protocolNetworkSliceFromNormalized(runtimeConfig, currentProtocolId),
  );

  const upstreamListDirty = !snapshotEquals(
    protocolUpstreamsSliceFromNormalized(currentConfig, currentProtocolId),
    protocolUpstreamsSliceFromNormalized(savedConfig, currentProtocolId),
  );

  const sections = {
    preview: previewUnsaved || previewRuntimePending,
    localKeys: localKeysDirty,
    workspace: workspaceUnsaved || workspaceRuntimePending,
    basicSettings: basicUnsaved || basicRuntimePending,
    upstreamList: upstreamListDirty,
  };
  return {
    overall: Object.values(sections).some(Boolean),
    sections,
  };
}

function setSectionDirtyBadge(id, dirty) {
  const node = document.getElementById(id);
  if (!node) {
    return;
  }
  node.hidden = !dirty;
  node.textContent = dirty ? t("draftDirtyShort") : "";
}

function refreshDirtyState() {
  const dirtyState = computeDirtySections();
  const node = document.getElementById("draftState");
  if (node) {
    node.textContent = dirtyState.overall ? t("draftDirtyShort") : t("draftCleanShort");
    node.className = `draft-state ${dirtyState.overall ? "dirty" : "clean"}`;
  }
  setSectionDirtyBadge("previewDirtyBadge", dirtyState.sections.preview);
  setSectionDirtyBadge("localKeysDirtyBadge", dirtyState.sections.localKeys);
  setSectionDirtyBadge("workspaceDirtyBadge", dirtyState.sections.workspace);
  setSectionDirtyBadge("basicSettingsDirtyBadge", dirtyState.sections.basicSettings);
  setSectionDirtyBadge("upstreamListDirtyBadge", dirtyState.sections.upstreamList);
}

function scheduleConfigAutoSave(delayMs = 500) {
  if (state.autoSaveTimer) {
    clearTimeout(state.autoSaveTimer);
  }
  state.autoSaveTimer = window.setTimeout(() => {
    state.autoSaveTimer = null;
    void saveConfigSnapshot();
  }, delayMs);
}

async function saveConfigSnapshot() {
  if (state.autoSaveInFlight) {
    state.autoSaveQueued = true;
    return;
  }
  state.autoSaveInFlight = true;
  try {
    const payload = getPersistableConfig(false);
    const response = await getJson("/api/config", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    applyServerConfigSnapshot(response.config);
    refreshDirtyState();
  } catch (error) {
    flash(error.message, "bad");
    refreshDirtyState();
  } finally {
    state.autoSaveInFlight = false;
    if (state.autoSaveQueued) {
      state.autoSaveQueued = false;
      scheduleConfigAutoSave(120);
    }
  }
}

function noteConfigMutation({ autosave = false, immediate = false, silentDirty = false } = {}) {
  if (!silentDirty) {
    refreshDirtyState();
  }
  if (autosave) {
    scheduleConfigAutoSave(immediate ? 0 : 500);
  }
}

function ensureManualActiveStillValid() {
  ensureRoutingByProtocol(state.config);
  PROTOCOL_ORDER.forEach((protocol) => {
    setManualActiveUpstreamId(state.config.routing_by_protocol[protocol].manual_active_upstream_id, protocol);
  });
}
