function syncTopLevelDraftFromDom() {
  ensureEndpointConfig(state.config);
  state.config.endpoint_mode = document.getElementById("endpoint_mode").value === "split" ? "split" : "shared";
  state.config.listen_host = document.getElementById("listen_host").value;
  state.config.listen_port = Number(document.getElementById("listen_port").value || "0");
  state.config.web_ui_port = state.config.endpoint_mode === "shared"
    ? state.config.listen_port
    : (Number(document.getElementById("web_ui_port").value || "0") || state.config.web_ui_port);
  state.config.listen_host = document.getElementById("protocol_listen_host").disabled
    ? state.config.listen_host
    : document.getElementById("protocol_listen_host").value;
  if (document.getElementById("protocol_listen_port").disabled) {
    state.config.listen_port = Number(document.getElementById("listen_port").value || "0");
  } else {
    state.config.split_api_ports[currentProtocol()] = Number(document.getElementById("protocol_listen_port").value || "0");
  }
  if (!document.getElementById("protocol_path").disabled) {
    state.config.shared_api_prefixes[currentProtocol()] = normalizeApiPrefix(
      document.getElementById("protocol_path").value,
      DEFAULT_SHARED_API_PREFIXES[currentProtocol()],
    );
  }
  state.config.request_timeout_sec = Number(document.getElementById("request_timeout_sec").value || "0");
  state.config.cooldown_seconds = Number(document.getElementById("cooldown_seconds").value || "0");
  state.config.ui_language = document.getElementById("ui_language").value;
  state.config.theme_mode = document.getElementById("theme_mode").value;
  state.config.default_model_mode = document.getElementById("default_model_mode").value;
  state.config.global_default_model = document.getElementById("global_default_model").value;
  applyRoutingStrategyToConfig(document.getElementById("routing_strategy").value, currentProtocol());
  if (document.getElementById("routing_strategy").value === "manual") {
    setManualActiveUpstreamId(document.getElementById("manual_active_upstream_id").value, currentProtocol());
  } else {
    setAutoRoutingMode(document.getElementById("manual_active_upstream_id").value, currentProtocol());
  }
  normalizeLocalKeys(state.config);
}

function syncOpenEditorDraftsFromDom() {
  document.querySelectorAll(".upstream-card").forEach((card) => {
    const editor = card.querySelector(".upstream-editor");
    if (!card.dataset.upstreamId || !editor || editor.hasAttribute("hidden")) {
      return;
    }
    const draft = buildDraftFromEditor(card);
    if (!draft) {
      return;
    }
    state.editorDrafts[card.dataset.upstreamId] = draft;
  });
}

function schedulePostSaveRefresh(delayMs = 700) {
  if (state.postSaveRefreshTimer) {
    clearTimeout(state.postSaveRefreshTimer);
  }
  state.postSaveRefreshTimer = window.setTimeout(async () => {
    state.postSaveRefreshTimer = null;
    await refreshStatus({ silent: true });
    await refreshUsage({ silent: true });
  }, delayMs);
}

async function saveAllConfig() {
  try {
    if (state.autoSaveTimer) {
      clearTimeout(state.autoSaveTimer);
      state.autoSaveTimer = null;
    }
    state.autoSaveQueued = false;
    syncTopLevelDraftFromDom();
    syncOpenEditorDraftsFromDom();
    ensureManualActiveStillValid();
    const payload = getPersistableConfig(true);
    const currentDashboardPort = Number(window.location.port || (window.location.protocol === "https:" ? "443" : "80"));
    const response = await getJson("/api/config", {
      method: "POST",
      body: JSON.stringify({
        config: payload,
        apply_runtime_changes: true,
      }),
    });
    applyServerConfigSnapshot(response.config, {
      replaceCurrent: true,
      clearEditorDrafts: true,
    });
    refreshDirtyState();
    renderAll();
    await refreshStatus({ silent: true });
    await refreshUsage({ silent: true });
    if (response.runtime_apply_error) {
      flash(t("flashSaveAppliedWarning", { message: response.runtime_apply_error }), "bad");
      return;
    }
    const nextDashboardPort = Number(response.config.web_ui_port || currentDashboardPort);
    if (response.runtime_apply_scheduled && nextDashboardPort !== currentDashboardPort) {
      flash(t("flashSaveSuccessWithRebind"));
      window.setTimeout(() => {
        window.location.assign(dashboardUrlForConfig(response.config));
      }, 900);
      return;
    }
    if (response.runtime_apply_scheduled) {
      schedulePostSaveRefresh();
    }
    flash(t("flashSaveSuccess"));
  } catch (error) {
    flash(error.message, "bad");
  }
}

async function importConfigFile(file) {
  if (!file) {
    return;
  }
  try {
    const text = await file.text();
    const payload = JSON.parse(text);
    const configPayload = payload?.config && typeof payload.config === "object" ? payload.config : payload;
    await getJson("/api/config/import", {
      method: "POST",
      body: JSON.stringify({ config: configPayload }),
    });
    state.editorDrafts = {};
    state.expandedUpstreamIds.clear();
    state.expandedLocalKeyIds.clear();
    state.localProbeResults = {};
    await loadAll();
    flash(t("flashImportSuccess"));
  } catch (error) {
    flash(t("flashImportFailed", { message: error.message }), "bad");
  }
}
