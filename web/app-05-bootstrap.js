function renderAll() {
  state.runtimeRenderSignature = "";
  state.localKeyRenderSignature = "";
  state.upstreamSummarySignature = "";
  state.usageRenderSignature = "";
  renderStaticTexts();
  renderRuntime();
  renderSettings();
  renderUpstreams();
  renderUsage();
  refreshDirtyState();
}

async function loadAll() {
  const config = await getJson("/api/config");
  applyServerConfigSnapshot(config, {
    replaceCurrent: true,
    clearEditorDrafts: true,
  });
  state.status = await getJson("/api/status");
  state.usage = await getJson(`/api/usage?range=${state.usageRange}`);
  const firstPopulatedProtocol = PROTOCOL_ORDER.find((protocol) => protocolUpstreamIds(state.config, protocol).length);
  state.currentProtocolTab = firstPopulatedProtocol || state.currentProtocolTab || "openai";
  state.workspaceOpen = Boolean(state.workspaceOpen);
  renderAll();
}

function schedulePolling() {
  if (state.pollTimer) {
    clearTimeout(state.pollTimer);
  }
  const tick = async () => {
    if (state.pollInFlight) {
      state.pollTimer = window.setTimeout(tick, 10000);
      return;
    }
    if (document.hidden) {
      state.pollTimer = window.setTimeout(tick, 10000);
      return;
    }
    state.pollInFlight = true;
    try {
      await refreshStatus({ silent: true });
      if ((Date.now() - (state.lastUsageRefreshAt || 0)) >= 30000) {
        await refreshUsage({ silent: true });
      }
    } finally {
      state.pollInFlight = false;
      state.pollTimer = window.setTimeout(tick, 10000);
    }
  };
  state.pollTimer = window.setTimeout(tick, 10000);
}

function bindNodeEvent(id, eventName, handler) {
  const node = document.getElementById(id);
  if (node) {
    node.addEventListener(eventName, handler);
  }
}

function nextLocalKeyName() {
  const index = (state.config?.local_api_keys || []).length + 1;
  return currentLanguage() === "zh" ? `本地 Key ${index}` : `Local Key ${index}`;
}

function appendLocalKey({ generated = false } = {}) {
  normalizeLocalKeys(state.config);
  const newId = crypto.randomUUID().replaceAll("-", "").slice(0, 12);
  state.config.local_api_keys.push({
    id: newId,
    name: nextLocalKeyName(),
    key: generated ? randomKey() : "",
    enabled: false,
    created_at: new Date().toISOString(),
    allowed_protocols: [...PROTOCOL_ORDER],
  });
  normalizeLocalKeys(state.config);
  state.expandedLocalKeyIds.add(newId);
  renderLocalKeys();
  noteConfigMutation({ autosave: true, immediate: true });
}

function bindTextField(id, applyValue, options = {}) {
  bindNodeEvent(id, "input", (event) => {
    applyValue(event.target.value, event);
    noteConfigMutation({ autosave: true, immediate: Boolean(options.immediate) });
  });
}

function bindNumberField(id, applyValue, options = {}) {
  bindTextField(
    id,
    (value, event) => applyValue(Number(value || "0"), event),
    options,
  );
}

function handleLocalKeyCardClick(button, keyId) {
  const keys = state.config.local_api_keys || [];
  const index = keys.findIndex((item) => item.id === keyId);
  if (index === -1) {
    return;
  }
  let silentDirty = false;
  if (button.dataset.action === "local-key-toggle") {
    if (state.expandedLocalKeyIds.has(keyId)) {
      state.expandedLocalKeyIds.delete(keyId);
    } else {
      state.expandedLocalKeyIds.add(keyId);
    }
  } else if (button.dataset.action === "local-key-protocol-toggle") {
    const protocol = button.dataset.localKeyProtocol;
    const selected = new Set(normalizeLocalKeyProtocols(keys[index].allowed_protocols));
    if (selected.has(protocol)) {
      if (selected.size > 1) {
        selected.delete(protocol);
      }
    } else {
      selected.add(protocol);
    }
    keys[index].allowed_protocols = normalizeLocalKeyProtocols([...selected]);
  } else if (button.dataset.action === "local-key-enabled-toggle") {
    keys[index].enabled = !keys[index].enabled;
    silentDirty = true;
  } else if (button.dataset.action === "local-key-primary") {
    const [item] = keys.splice(index, 1);
    item.enabled = true;
    keys.unshift(item);
  } else if (button.dataset.action === "local-key-generate") {
    keys[index].key = randomKey();
  } else if (button.dataset.action === "local-key-remove") {
    if (keys.length <= 1) {
      return;
    }
    if (!window.confirm(t("confirmDeleteLocalKey", { name: keys[index].name || keyId }))) {
      return;
    }
    keys.splice(index, 1);
    state.expandedLocalKeyIds.delete(keyId);
    flash(t("flashLocalKeyDeleted"));
  }
  normalizeLocalKeys(state.config);
  renderLocalKeys();
  noteConfigMutation({ autosave: true, immediate: true, silentDirty });
}

function handleUpstreamAction(action, upstreamId, button) {
  if (action === "toggle") {
    if (state.expandedUpstreamIds.has(upstreamId)) {
      collapseEditor(upstreamId);
    } else {
      openEditor(upstreamId);
    }
    return;
  }
  if (action === "toggle-enabled") {
    void toggleUpstreamEnabled(upstreamId);
    return;
  }
  if (action === "test") {
    void testUpstream(upstreamId);
    return;
  }
  if (action === "save-editor") {
    saveEditorDraft(upstreamId);
    return;
  }
  if (action === "cancel-editor") {
    cancelEditorDraft(upstreamId);
    return;
  }
  if (action === "remove") {
    removeUpstream(upstreamId);
    return;
  }
  if (action === "add-subscription") {
    addSubscription(upstreamId);
    return;
  }
  if (action === "remove-subscription") {
    const subscriptionId = button?.dataset?.subscriptionId || "";
    removeSubscription(upstreamId, subscriptionId);
    return;
  }
  if (action === "reactivate-upstream") {
    void reactivateUpstream(upstreamId);
  }
}

function bindControls() {
  ["global_default_model"].forEach((id) => {
    bindTextField(id, (value) => {
      state.config[id] = value;
    });
  });

  ["request_timeout_sec", "cooldown_seconds"].forEach((id) => {
    bindNumberField(id, (value) => {
      state.config[id] = value;
    });
  });

  bindNodeEvent("endpoint_mode", "change", (event) => {
    ensureEndpointConfig(state.config);
    state.config.endpoint_mode = event.target.value === "split" ? "split" : "shared";
    if (state.config.endpoint_mode === "shared") {
      state.config.web_ui_port = state.config.listen_port;
    }
    renderSettings();
    noteConfigMutation({ autosave: true, immediate: true });
  });

  bindNodeEvent("lanAccessToggle", "click", () => {
    ensureEndpointConfig(state.config);
    state.config.listen_host = lanAccessEnabled(state.config) ? "127.0.0.1" : "0.0.0.0";
    document.getElementById("listen_host").value = state.config.listen_host;
    document.getElementById("protocol_listen_host").value = state.config.listen_host;
    document.getElementById("protocol_local_url").value = protocolLocalUrl(state.config, currentProtocol());
    syncLanAccessToggle();
    noteConfigMutation({ autosave: true, immediate: true });
  });

  bindTextField("listen_host", (value) => {
    ensureEndpointConfig(state.config);
    state.config.listen_host = value;
    if (endpointMode() === "shared") {
      document.getElementById("protocol_listen_host").value = state.config.listen_host;
      document.getElementById("protocol_local_url").value = protocolLocalUrl(state.config, currentProtocol());
    }
    syncLanAccessToggle();
  });

  bindNumberField("listen_port", (value) => {
    ensureEndpointConfig(state.config);
    state.config.listen_port = value;
    if (endpointMode() === "shared") {
      state.config.web_ui_port = state.config.listen_port;
      document.getElementById("protocol_listen_port").value = String(state.config.listen_port || "");
      document.getElementById("web_ui_port").value = String(state.config.listen_port || "");
      document.getElementById("protocol_local_url").value = protocolLocalUrl(state.config, currentProtocol());
    }
  });

  bindNumberField("web_ui_port", (value) => {
    ensureEndpointConfig(state.config);
    if (endpointMode() === "shared") {
      state.config.web_ui_port = state.config.listen_port;
      document.getElementById("web_ui_port").value = String(state.config.listen_port || "");
      return;
    }
    state.config.web_ui_port = value;
  });

  bindTextField("protocol_listen_host", (value) => {
    ensureEndpointConfig(state.config);
    if (endpointMode() !== "split") {
      return;
    }
    state.config.listen_host = value;
    document.getElementById("protocol_local_url").value = protocolLocalUrl(state.config, currentProtocol());
    syncLanAccessToggle();
  });

  bindNumberField("protocol_listen_port", (value) => {
    ensureEndpointConfig(state.config);
    if (endpointMode() !== "split") {
      return;
    }
    state.config.split_api_ports[currentProtocol()] = value;
    document.getElementById("protocol_local_url").value = protocolLocalUrl(state.config, currentProtocol());
  });

  bindTextField("protocol_path", (value) => {
    ensureEndpointConfig(state.config);
    if (endpointMode() !== "shared") {
      return;
    }
    state.config.shared_api_prefixes[currentProtocol()] = normalizeApiPrefix(
      value,
      DEFAULT_SHARED_API_PREFIXES[currentProtocol()],
    );
    document.getElementById("protocol_local_url").value = protocolLocalUrl(state.config, currentProtocol());
  });

  bindNodeEvent("ui_language", "change", (event) => {
    state.config.ui_language = event.target.value;
    renderAll();
    noteConfigMutation({ autosave: true, immediate: true });
  });

  bindNodeEvent("theme_mode", "change", (event) => {
    state.config.theme_mode = event.target.value;
    renderAll();
    noteConfigMutation({ autosave: true, immediate: true });
  });

  bindNodeEvent("default_model_mode", "change", (event) => {
    state.config.default_model_mode = event.target.value;
    updateHints();
    noteConfigMutation({ autosave: true, immediate: true });
  });

  bindNodeEvent("routing_strategy", "change", (event) => {
    applyRoutingStrategyToConfig(event.target.value, currentProtocol());
    renderSettings();
    noteConfigMutation({ autosave: true, immediate: true });
  });

  bindNodeEvent("manual_active_upstream_id", "change", (event) => {
    if (document.getElementById("routing_strategy").value === "manual") {
      setManualActiveUpstreamId(event.target.value, currentProtocol());
    } else {
      setAutoRoutingMode(event.target.value, currentProtocol());
    }
    updateHints();
    noteConfigMutation({ autosave: true, immediate: true });
  });

  bindNodeEvent("workspaceProtocolTabs", "click", (event) => {
    const button = event.target.closest("button[data-protocol-tab]");
    if (!button) {
      return;
    }
    const nextProtocol = normalizeUpstreamProtocol(button.dataset.protocolTab);
    if (state.currentProtocolTab === nextProtocol) {
      state.workspaceOpen = !workspaceExpanded();
    } else {
      state.currentProtocolTab = nextProtocol;
      state.workspaceOpen = true;
    }
    renderAll();
  });

  bindNodeEvent("workspaceTestAllBtn", "click", testAllWorkspaceUpstreams);

  bindNodeEvent("workspaceServiceToggle", "click", async (event) => {
    const button = event.currentTarget;
    if (!button || button.disabled) {
      return;
    }
    await controlService(button.dataset.serviceAction || "start_protocol", button.dataset.serviceProtocol || currentProtocol());
  });

  bindNodeEvent("workspaceBindingToggle", "click", async (event) => {
    const button = event.currentTarget;
    if (!button || button.disabled) {
      return;
    }
    await controlClientBinding(button.dataset.clientToggle, button.dataset.clientAction || "switch");
  });

  bindNodeEvent("globalModeButtons", "click", async (event) => {
    const button = event.target.closest("button[data-service-action]");
    if (!button || button.disabled) {
      return;
    }
    await controlService(button.dataset.serviceAction || "start_proxy");
  });

  bindNodeEvent("localKeyList", "input", (event) => {
    const card = event.target.closest("[data-local-key-id]");
    if (!card) {
      return;
    }
    const localKey = (state.config.local_api_keys || []).find((item) => item.id === card.dataset.localKeyId);
    if (!localKey) {
      return;
    }
    const field = event.target.dataset.localKeyField;
    if (field === "name" || field === "key") {
      localKey[field] = event.target.value;
    }
    normalizeLocalKeys(state.config);
    noteConfigMutation({ autosave: true });
  });

  bindNodeEvent("localKeyList", "click", (event) => {
    const button = event.target.closest("button[data-action]");
    const card = event.target.closest("[data-local-key-id]");
    if (!button || !card) {
      return;
    }
    handleLocalKeyCardClick(button, card.dataset.localKeyId);
  });

  bindNodeEvent("saveAllBtn", "click", saveAllConfig);
  bindNodeEvent("refreshBtn", "click", async () => {
    await refreshStatus();
    await refreshUsage();
  });
  bindNodeEvent("exportConfigBtn", "click", () => {
    window.location.assign("/api/config/export");
  });
  bindNodeEvent("importConfigBtn", "click", () => {
    document.getElementById("importConfigInput").click();
  });
  bindNodeEvent("importConfigInput", "change", async (event) => {
    const [file] = Array.from(event.target.files || []);
    event.target.value = "";
    await importConfigFile(file);
  });
  bindNodeEvent("addLocalKeyBtn", "click", () => appendLocalKey());
  bindNodeEvent("generateLocalKeyBtn", "click", () => appendLocalKey({ generated: true }));
  bindNodeEvent("addUpstreamBtn", "click", addUpstream);
  bindNodeEvent("testAllBtn", "click", testAllUpstreams);

  bindNodeEvent("usageFilters", "click", async (event) => {
    const button = event.target.closest("button[data-range]");
    if (!button) {
      return;
    }
    state.usageRange = button.dataset.range;
    state.hoveredUsageBucketIndex = -1;
    await refreshUsage();
  });

  bindNodeEvent("usageScopeFilters", "click", (event) => {
    const button = event.target.closest("button[data-usage-scope]");
    if (!button) {
      return;
    }
    state.usageScope = PROTOCOL_ORDER.includes(button.dataset.usageScope) ? button.dataset.usageScope : "all";
    state.usageAutoScrollKey = "";
    state.hoveredUsageBucketIndex = -1;
    renderAll();
  });

  const applyUsageLocalKeyFilter = (rawValue, allowRaw = false) => {
    const nextValue = resolveUsageLocalKeyInputValue(rawValue, { allowRaw });
    if (nextValue === null || nextValue === state.usageLocalKey) {
      return;
    }
    state.usageLocalKey = nextValue;
    state.usageLocalKeyQuery = "";
    state.usageAutoScrollKey = "";
    state.hoveredUsageBucketIndex = -1;
    renderAll();
  };

  const setUsageLocalKeyMenuOpen = (open, { resetQuery = false, focusInput = false, selectText = false } = {}) => {
    state.usageLocalKeyMenuOpen = Boolean(open);
    if (resetQuery) {
      state.usageLocalKeyQuery = "";
    }
    renderUsageLocalKeyInput();
    if (!open || !focusInput) {
      return;
    }
    const input = document.getElementById("usageLocalKeyInput");
    if (!input) {
      return;
    }
    input.focus();
    if (selectText) {
      input.select();
    }
  };

  const firstUsageLocalKeyOption = () => usageLocalKeyFilteredOptions(usageActiveLocalKeyIds())[0] || null;

  bindNodeEvent("usageLocalKeyToggle", "click", () => {
    const nextOpen = !state.usageLocalKeyMenuOpen;
    setUsageLocalKeyMenuOpen(nextOpen, { resetQuery: nextOpen, focusInput: nextOpen });
  });

  bindNodeEvent("usageLocalKeyInput", "focus", () => {
    if (!state.usageLocalKeyMenuOpen) {
      setUsageLocalKeyMenuOpen(true, { resetQuery: true, selectText: true });
    }
  });

  bindNodeEvent("usageLocalKeyInput", "click", () => {
    if (!state.usageLocalKeyMenuOpen) {
      setUsageLocalKeyMenuOpen(true, { resetQuery: true, selectText: true });
    }
  });

  bindNodeEvent("usageLocalKeyInput", "input", (event) => {
    state.usageLocalKeyQuery = event.target.value;
    if (!state.usageLocalKeyMenuOpen) {
      state.usageLocalKeyMenuOpen = true;
    }
    renderUsageLocalKeyInput();
  });

  bindNodeEvent("usageLocalKeyInput", "change", (event) => {
    const nextValue = resolveUsageLocalKeyInputValue(event.target.value, { allowRaw: true });
    if (nextValue !== null) {
      applyUsageLocalKeyFilter(event.target.value, true);
    }
    setUsageLocalKeyMenuOpen(false, { resetQuery: true });
  });

  bindNodeEvent("usageLocalKeyInput", "keydown", (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      setUsageLocalKeyMenuOpen(false, { resetQuery: true });
      event.target.blur();
      return;
    }
    if (event.key !== "Enter") {
      return;
    }
    event.preventDefault();
    const firstOption = firstUsageLocalKeyOption();
    if (firstOption) {
      applyUsageLocalKeyFilter(firstOption.id === "all" ? t("usageLocalKeyAll") : (firstOption.name || firstOption.id), true);
    } else {
      applyUsageLocalKeyFilter(event.target.value, true);
    }
    setUsageLocalKeyMenuOpen(false, { resetQuery: true });
    event.target.blur();
  });

  bindNodeEvent("usageLocalKeyMenu", "mousedown", (event) => {
    event.preventDefault();
  });

  bindNodeEvent("usageLocalKeyMenu", "click", (event) => {
    const option = event.target.closest("[data-usage-local-key]");
    if (!option) {
      return;
    }
    const nextValue = String(option.dataset.usageLocalKey || "");
    if (nextValue === "all") {
      applyUsageLocalKeyFilter(t("usageLocalKeyAll"), true);
    } else if (nextValue === "") {
      applyUsageLocalKeyFilter(t("usageLocalKeyDirect"), true);
    } else {
      applyUsageLocalKeyFilter(nextValue, true);
    }
    setUsageLocalKeyMenuOpen(false, { resetQuery: true });
  });

  document.addEventListener("click", (event) => {
    const field = event.target.closest(".usage-key-combobox");
    if (field) {
      return;
    }
    if (!state.usageLocalKeyMenuOpen) {
      return;
    }
    setUsageLocalKeyMenuOpen(false, { resetQuery: true });
  });

  bindNodeEvent("usageChart", "mousemove", (event) => {
    const bar = event.target.closest(".chart-bar-wrap[data-bucket-index]");
    if (!bar) {
      return;
    }
    const nextIndex = Number(bar.dataset.bucketIndex);
    if (nextIndex === state.hoveredUsageBucketIndex) {
      return;
    }
    state.hoveredUsageBucketIndex = nextIndex;
    renderUsageHoverDetail();
  });

  bindNodeEvent("usageChart", "mouseleave", () => {
    if (state.hoveredUsageBucketIndex === -1) {
      return;
    }
    state.hoveredUsageBucketIndex = -1;
    renderUsageHoverDetail();
  });

  const upstreamList = document.getElementById("upstreamList");

  upstreamList.addEventListener("click", (event) => {
    const toggleButton = event.target.closest("button[data-subscription-field='enabled']");
    if (toggleButton) {
      const nextActive = toggleButton.getAttribute("aria-pressed") !== "true";
      setSwitchChipState(toggleButton, nextActive, t("toggleEnabledShort"));
      syncEditorField(toggleButton);
      return;
    }

    const button = event.target.closest("button[data-action]");
    if (!button) {
      return;
    }
    const card = button.closest(".upstream-card");
    if (!card) {
      return;
    }
    const upstreamId = card.dataset.upstreamId;
    handleUpstreamAction(button.dataset.action, upstreamId, button);
  });

  const handleUpstreamFieldChange = (event) => {
    const control = event.target.closest("[data-field], [data-subscription-field]");
    if (!control) {
      return;
    }
    syncEditorField(control);
  };

  upstreamList.addEventListener("input", handleUpstreamFieldChange);
  upstreamList.addEventListener("change", handleUpstreamFieldChange);

  upstreamList.addEventListener("dragstart", (event) => {
    const handle = event.target.closest("[data-drag-handle='true']");
    if (!handle) {
      return;
    }
    const card = handle.closest(".upstream-card");
    if (!card) {
      return;
    }
    state.draggingUpstreamId = card.dataset.upstreamId;
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", state.draggingUpstreamId);
  });

  upstreamList.addEventListener("dragover", (event) => {
    const card = event.target.closest(".upstream-card");
    if (!card || !state.draggingUpstreamId) {
      return;
    }
    event.preventDefault();
    upstreamList.querySelectorAll(".upstream-card").forEach((node) => node.classList.remove("drag-over"));
    card.classList.add("drag-over");
  });

  upstreamList.addEventListener("drop", (event) => {
    const card = event.target.closest(".upstream-card");
    if (!card || !state.draggingUpstreamId) {
      return;
    }
    event.preventDefault();
    upstreamList.querySelectorAll(".upstream-card").forEach((node) => node.classList.remove("drag-over"));
    reorderUpstreams(state.draggingUpstreamId, card.dataset.upstreamId);
    state.draggingUpstreamId = "";
  });

  upstreamList.addEventListener("dragend", () => {
    state.draggingUpstreamId = "";
    upstreamList.querySelectorAll(".upstream-card").forEach((node) => node.classList.remove("drag-over"));
  });
}

bindControls();
applyTheme();
if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
  finishBootMotion();
} else {
  window.setTimeout(finishBootMotion, 550);
}
if (window.matchMedia) {
  const themeQuery = window.matchMedia("(prefers-color-scheme: light)");
  const handleThemeChange = () => {
    if ((state.config?.theme_mode || "auto") === "auto") {
      applyTheme();
    }
  };
  if (typeof themeQuery.addEventListener === "function") {
    themeQuery.addEventListener("change", handleThemeChange);
  } else if (typeof themeQuery.addListener === "function") {
    themeQuery.addListener(handleThemeChange);
  }
}
document.addEventListener("visibilitychange", () => {
  if (document.hidden || state.pollInFlight) {
    return;
  }
  void refreshStatus({ silent: true });
  void refreshUsage({ silent: true });
});
loadAll().catch((error) => {
  flash(t("flashInitFailed", { message: error.message }), "bad");
});
schedulePolling();
