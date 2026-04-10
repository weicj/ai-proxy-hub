function protocolText(protocol) {
  return platformText(protocol);
}

function endpointModeText(mode = endpointMode()) {
  return mode === "split" ? t("endpointModeSplit") : t("endpointModeShared");
}

function normalizedServiceProtocols(service) {
  return (service?.active_protocols || [])
    .map((protocol) => normalizeUpstreamProtocol(protocol))
    .filter((protocol, index, array) => PROTOCOL_ORDER.includes(protocol) && array.indexOf(protocol) === index);
}

function serviceProtocolsLabel(protocols) {
  return protocols.length
    ? protocols.map((protocol) => protocolText(protocol)).join(" / ")
    : t("runtimeServiceNone");
}

function globalModeKey(service, clients) {
  if (service?.state === "external") {
    return "external";
  }
  const activeProtocols = normalizedServiceProtocols(service);
  const clientControlledProtocols = activeProtocols.filter((protocol) => protocol !== "local_llm");
  if (!activeProtocols.length && service?.state !== "running" && service?.state !== "partial") {
    return "stopped";
  }
  if (!activeProtocols.length) {
    return "stopped";
  }
  if (!clientControlledProtocols.length) {
    return "forwarding";
  }
  const localBindingCount = clientControlledProtocols.filter((protocol) => {
    const client = clients?.[clientForProtocol(protocol)] || {};
    return client.state === "switched";
  }).length;
  if (localBindingCount === clientControlledProtocols.length) {
    return "proxy";
  }
  if (localBindingCount === 0) {
    return "forwarding";
  }
  return "mixed";
}

function globalModeLabel(mode) {
  if (mode === "proxy") {
    return t("runtimeModeProxy");
  }
  if (mode === "forwarding") {
    return t("runtimeModeForwarding");
  }
  if (mode === "mixed") {
    return t("runtimeModeMixed");
  }
  if (mode === "external") {
    return t("runtimeModeExternal");
  }
  return t("runtimeModeStopped");
}

function protocolServiceStatusInfo(protocol, service) {
  const activeProtocols = normalizedServiceProtocols(service);
  if (service?.state === "error") {
    return { kind: "error", label: t("runtimeServiceError"), active: false };
  }
  if (service?.owner === "external") {
    if (activeProtocols.includes(protocol)) {
      return { kind: "warning", label: t("runtimeServiceExternal"), active: true };
    }
    return { kind: "stopped", label: t("runtimeServiceStopped"), active: false };
  }
  if (activeProtocols.includes(protocol) || service?.state === "running") {
    return { kind: "running", label: t("runtimeServiceRunning"), active: true };
  }
  return { kind: "stopped", label: t("runtimeServiceStopped"), active: false };
}

function bindingStatusText(prefix, info) {
  if (!info?.state) {
    return t(`${prefix}NotSwitched`);
  }
  if (info?.state === "error") {
    return t(`${prefix}Error`);
  }
  if (info?.state === "external") {
    return t(`${prefix}External`);
  }
  if (info?.state === "not_switched") {
    return t(`${prefix}NotSwitched`);
  }
  return t(`${prefix}Switched`);
}

function serviceStatusKind(service) {
  if (service?.state === "error") {
    return "error";
  }
  if (service?.state === "partial" || service?.partially_started) {
    return "warning";
  }
  if (service?.state === "external") {
    return "warning";
  }
  if (service?.state === "stopped") {
    return "stopped";
  }
  return "running";
}

function bindingStatusKind(info) {
  if (!info?.state || info?.state === "not_switched") {
    return "stopped";
  }
  if (info?.state === "error") {
    return "error";
  }
  if (info?.state === "external") {
    return "warning";
  }
  return "running";
}

function protocolForClient(client) {
  if (client === "claude") {
    return "anthropic";
  }
  if (client === "gemini") {
    return "gemini";
  }
  return "openai";
}

function clientForProtocol(protocol) {
  if (protocol === "anthropic") {
    return "claude";
  }
  if (protocol === "gemini") {
    return "gemini";
  }
  if (protocol === "local_llm") {
    return "local_llm";
  }
  return "codex";
}

function runtimeBindingPrefixForProtocol(protocol) {
  if (protocol === "anthropic") {
    return "runtimeClaude";
  }
  if (protocol === "gemini") {
    return "runtimeGemini";
  }
  if (protocol === "local_llm") {
    return "runtimeLocalLLM";
  }
  return "runtimeCodex";
}

function runtimeLabelForProtocol(protocol) {
  return t(runtimeBindingPrefixForProtocol(protocol));
}

function runtimeUrlForProtocol(runtime, protocol) {
  if (protocol === "anthropic") {
    return runtime.claude_base_url || "-";
  }
  if (protocol === "gemini") {
    return runtime.gemini_base_url || "-";
  }
  if (protocol === "local_llm") {
    return runtime.local_llm_base_url || "-";
  }
  return runtime.openai_base_url || "-";
}

function runtimeProtocolMetaText(protocol, routing) {
  const section = routing?.protocols?.[protocol] || {};
  if (!Object.keys(section).length) {
    return [
      t("runtimeInlineMode", { mode: "-" }),
      t("runtimeInlineActive", { active: "-" }),
    ];
  }
  const modeText = section.auto_routing_enabled
    ? t("previewModeAuto", { mode: section.routing_mode_label || "-" })
    : t("previewModeManual");
  const activeText = section.auto_routing_enabled
    ? t("previewActivePair", { manual: section.manual_active_upstream_name || "-", last: section.last_used_upstream_name || "-" })
    : (section.manual_active_upstream_name || "-");
  return [
    t("runtimeInlineMode", { mode: modeText }),
    t("runtimeInlineActive", { active: activeText }),
  ];
}

function proxyMetaText(serviceInfo, service) {
  if (serviceInfo.kind === "error") {
    return service?.error || t("workspaceProxyMetaError");
  }
  if (service?.owner === "external" && serviceInfo.active) {
    return t("workspaceProxyMetaExternal");
  }
  if (serviceInfo.active) {
    return t("workspaceProxyMetaRunning");
  }
  return t("workspaceProxyMetaStopped");
}

function bindingTargetUrl(info, runtime, protocol) {
  if (info?.base_url) {
    return info.base_url;
  }
  if (info?.state === "switched") {
    return runtimeUrlForProtocol(runtime, protocol);
  }
  return t("runtimeBindingTargetLocalDefault");
}

function renderRuntimeClientStatuses(runtime, clients) {
  const container = document.getElementById("runtimeClientStatusList");
  if (!container) {
    return;
  }
  container.innerHTML = PROTOCOL_ORDER.map((protocol) => {
    const clientId = clientForProtocol(protocol);
    const info = clients?.[clientId] || {};
    const prefix = runtimeBindingPrefixForProtocol(protocol);
    const statusLabel = bindingStatusText(prefix, info);
    return `
      <div class="meta-card runtime-mini-card">
        <div class="runtime-mini-heading">${protocolLabelMarkup(protocol, platformText(protocol), true)}</div>
        <strong>${statusIndicatorMarkup(bindingStatusKind(info), statusLabel)}</strong>
        <div class="tiny runtime-mini-target">${escapeHtml(t("runtimeBindingTarget", { url: bindingTargetUrl(info, runtime, protocol) }))}</div>
      </div>
    `;
  }).join("");
}

function renderRuntime() {
  if (!state.status) {
    return;
  }
  const runtime = state.status.runtime || {};
  const service = state.status.service || {};
  const clients = state.status.clients || {};
  const codex = clients.codex || state.status.codex || {};
  const claude = clients.claude || {};
  const gemini = clients.gemini || {};
  const local_llm = clients.local_llm || {};
  const routing = state.status.routing || {};
  const activeProtocols = normalizedServiceProtocols(service);
  const partiallyRunning = service.owner !== "external" && (service.state === "partial" || Boolean(service.partially_started));
  const runtimeSignature = signatureOf({
    language: currentLanguage(),
    currentProtocol: currentProtocol(),
    runtime,
    service,
    clients,
    routing,
  });
  if (runtimeSignature === state.runtimeRenderSignature) {
    return;
  }
  state.runtimeRenderSignature = runtimeSignature;
  const serviceText =
    service.state === "error"
      ? t("runtimeServiceError")
      : partiallyRunning
      ? t("runtimeServicePartial")
      : service.state === "external"
      ? t("runtimeServiceExternal")
      : service.state === "stopped"
        ? t("runtimeServiceStopped")
        : t("runtimeServiceRunning");
  document.getElementById("runtimeServiceStatus").innerHTML = statusIndicatorMarkup(serviceStatusKind(service), serviceText);
  const globalMode = globalModeKey(service, clients);
  document.getElementById("runtimeServiceMeta").textContent = t("runtimeModeSummary", {
    mode: globalModeLabel(globalMode),
    portMode: endpointModeText(runtime.endpoint_mode || endpointMode()),
  });
  document.getElementById("runtimeServiceActive").textContent = t("runtimeServiceActiveServices", {
    services: serviceProtocolsLabel(activeProtocols),
  });
  renderRuntimeClientStatuses(runtime, { codex, claude, gemini, local_llm });
  setModeButtonState(document.getElementById("globalForwardingBtn"), globalMode === "forwarding");
  setModeButtonState(document.getElementById("globalProxyBtn"), globalMode === "proxy");
  setModeButtonState(document.getElementById("globalStopBtn"), globalMode === "stopped", {
    disabled: service.state === "external",
  });

  const current = currentProtocol();
  const currentClient = clientForProtocol(current);
  const currentServiceInfo = protocolServiceStatusInfo(current, service);
  const currentInfo = currentClient === "claude"
    ? claude
    : currentClient === "gemini"
    ? gemini
    : currentClient === "local_llm"
    ? local_llm
    : codex;
  const bindingPrefix = runtimeBindingPrefixForProtocol(current);
  const currentAction = clientBindingNextAction(currentInfo);
  const currentToggle = document.getElementById("workspaceBindingToggle");
  const serviceToggle = document.getElementById("workspaceServiceToggle");
  document.getElementById("workspaceProxyStatus").innerHTML = statusIndicatorMarkup(
    currentServiceInfo.kind,
    currentServiceInfo.label,
  );
  document.getElementById("workspaceProxyMeta").textContent = proxyMetaText(currentServiceInfo, service);
  document.getElementById("workspaceProxyUrl").textContent = t("runtimeLocalUrl", { url: runtimeUrlForProtocol(runtime, current) });
  document.getElementById("workspaceLocalStatus").innerHTML = statusIndicatorMarkup(
    bindingStatusKind(currentInfo),
    bindingStatusText(bindingPrefix, currentInfo),
  );
  document.getElementById("workspaceLocalMeta").innerHTML = runtimeProtocolMetaText(current, routing)
    .map((line) => escapeHtml(line))
    .join("<br>");
  document.getElementById("workspaceLocalUrl").textContent = t("runtimeBindingTarget", {
    url: bindingTargetUrl(currentInfo, runtime, current),
  });
  serviceToggle.dataset.serviceProtocol = current;
  serviceToggle.dataset.serviceAction = currentServiceInfo.active ? "stop_protocol" : "start_protocol";
  setSwitchChipState(
    serviceToggle,
    currentServiceInfo.active && service.state !== "external",
    t("protocolServiceSwitchLabel"),
    {
      disabled: service.state === "external",
    },
  );
  currentToggle.dataset.clientToggle = currentClient;
  currentToggle.dataset.clientAction = currentAction;
  setSwitchChipState(currentToggle, currentAction === "restore", t("clientHubSwitchLabel"));
  renderCurrentProtocolRouteOrder();
}

async function refreshStatus(options = {}) {
  try {
    state.status = await getJson("/api/status");
    renderProtocolTabs();
    renderRuntime();
    renderLocalKeys();
    updateUpstreamSummaryDom();
    refreshDirtyState();
  } catch (error) {
    if (!options.silent) {
      flash(t("flashRefreshFailed", { message: error.message }), "bad");
    }
  }
}

async function ensureProtocolProxyReady(protocol) {
  const normalizedProtocol = normalizeUpstreamProtocol(protocol);
  const service = state.status?.service || {};
  const serviceInfo = protocolServiceStatusInfo(normalizedProtocol, service);
  if (serviceInfo.active) {
    return true;
  }
  const mode = (state.status?.runtime?.endpoint_mode || endpointMode()) === "split" ? "split" : "shared";
  const action = mode === "split" ? "start_protocol" : "start_forwarding";
  const ok = await controlService(action, normalizedProtocol, { silent: true, skipRender: true });
  return ok !== false;
}

async function controlClientBinding(client, action) {
  try {
    if (action === "switch") {
      const ready = await ensureProtocolProxyReady(protocolForClient(client));
      if (!ready) {
        return;
      }
    }
    await getJson("/api/client/control", {
      method: "POST",
      body: JSON.stringify({ client, action }),
    });
    await refreshStatus();
    flash(
      action === "switch"
        ? t("flashClientConnectSuccess", { client: clientDisplayName(client) })
        : t("flashClientDisconnectSuccess", { client: clientDisplayName(client) }),
    );
  } catch (error) {
    try {
      await refreshStatus();
    } catch (_refreshError) {
      // Keep the original control error as the user-facing failure.
    }
    const message = error.status === 404 && error.url === "/api/client/control"
      ? t("flashClientUpgradeNeeded")
      : error.message;
    flash(
      t("flashClientActionFailed", {
        client: clientDisplayName(client),
        message,
      }),
      "bad",
    );
  }
}

async function controlService(action, protocol = "", options = {}) {
  try {
    const response = await getJson("/api/service/control", {
      method: "POST",
      body: JSON.stringify({ action, protocol }),
    });
    if (response?.status) {
      state.status = response.status;
      if (!options.skipRender) {
        renderRuntime();
        renderLocalKeys();
        updateUpstreamSummaryDom();
      }
    } else {
      if (options.skipRender) {
        state.status = await getJson("/api/status");
      } else {
        await refreshStatus();
      }
    }
    if (options.silent) {
      return true;
    }
    if (action === "start_protocol" || action === "stop_protocol") {
      flash(
        action === "stop_protocol"
          ? t("flashProtocolServiceStopSuccess", { platform: platformText(protocol || currentProtocol()) })
          : t("flashProtocolServiceStartSuccess", { platform: platformText(protocol || currentProtocol()) }),
      );
      return true;
    }
    if (action === "start_forwarding") {
      flash(t("flashServiceStartForwardingSuccess"));
      return true;
    }
    if (action === "start_proxy" || action === "start_all") {
      flash(t("flashServiceStartProxySuccess"));
      return true;
    }
    flash(action === "stop_all" ? t("flashServiceStopAllSuccess") : t("flashServiceStartAllSuccess"));
    return true;
  } catch (error) {
    const unsupported = error.payload?.message === "shared_mode_requires_start_all" || error.payload?.message === "shared_mode_requires_stop_all";
    const message = error.status === 404 || error.status === 501
      ? t("flashServiceUpgradeNeeded")
      : unsupported
      ? t("flashProtocolServiceUnsupported")
      : error.message;
    if (!options.silent) {
      flash(t("flashServiceActionFailed", { message }), "bad");
    }
    return false;
  }
}
