function renderStaticTexts() {
  const platform = platformText();
  applyTheme();
  document.documentElement.lang = currentLanguage() === "zh" ? "zh-CN" : "en";
  document.getElementById("appTitle").textContent = t("appTitle");
  document.getElementById("appSubtitle").textContent = t("appSubtitle");
  setIconLabel("projectMetaTitle", "info", t("projectMetaTitle"), "icon icon-md");
  document.getElementById("projectMetaHint").textContent = t("projectMetaHint");
  setIconLabel("workspaceTitle", "layout", t("workspaceTitle"), "icon icon-md");
  document.getElementById("workspaceHint").textContent = t("workspaceHint");
  document.getElementById("workspaceCollapsedHint").textContent = t("workspaceCollapsedHint");
  document.getElementById("workspaceTestAllBtn").innerHTML = buttonLabelMarkup("flask", t("testAllConnections"));
  setIconLabel("languageLabel", "globe", t("languageLabel"));
  setIconLabel("themeLabel", "theme", t("themeLabel"));
  document.getElementById("endpointModeLabel").textContent = t("endpointModeLabel");
  document.getElementById("webUiPortLabel").textContent = t("webUiPort");
  document.getElementById("sharedListenHostLabel").textContent = t("listenHost");
  document.getElementById("lanAccessLabel").textContent = t("lanAccessLabel");
  document.getElementById("lanAccessHint").textContent = "";
  document.getElementById("lanAccessHint").hidden = true;
  document.getElementById("sharedListenPortLabel").textContent = t("listenPort");
  setIconLabel(
    "basicSettingsTitle",
    protocolIconName(currentProtocol()),
    t("basicSettingsTitle", { platform }),
    `icon icon-md protocol-title-icon title-icon-${currentProtocol()}`,
  );
  document.getElementById("basicSettingsHint").textContent = t("basicSettingsHint", { platform });
  document.getElementById("workspaceRuntimeSectionLabel").textContent = t("workspaceRuntimeSectionLabel");
  document.getElementById("workspaceRuntimeHint").textContent = t("workspaceRuntimeHint");
  document.getElementById("workspaceProxyLabel").textContent = t("workspaceProxyCardLabel");
  document.getElementById("workspaceLocalLabel").textContent = t("workspaceLocalCardLabel");
  document.getElementById("networkSectionLabel").textContent = t("networkSection");
  document.getElementById("modelSectionLabel").textContent = t("modelSection");
  document.getElementById("routingSectionLabel").textContent = t("routingSection");
  document.getElementById("protocolListenHostLabel").textContent = t("protocolListenHost");
  document.getElementById("protocolListenPortLabel").textContent = t("protocolListenPort");
  document.getElementById("protocolPathLabel").textContent = t("protocolPath");
  document.getElementById("protocolLocalUrlLabel").textContent = t("protocolLocalUrl");
  setIconLabel("localKeysPanelTitle", "key", t("localKeysPanelTitle"), "icon icon-md");
  document.getElementById("localKeysPanelHint").textContent = t("localKeysPanelHint");
  document.getElementById("timeoutLabel").textContent = t("timeoutSeconds");
  document.getElementById("cooldownLabel").textContent = t("cooldownSeconds");
  document.getElementById("defaultModelModeLabel").textContent = t("defaultModelMode");
  document.getElementById("globalDefaultModelLabel").textContent = t("globalDefaultModel");
  document.getElementById("routingStrategyLabel").textContent = t("routingStrategy");
  document.getElementById("saveAllBtn").innerHTML = buttonLabelMarkup("save", t("saveAll"));
  document.getElementById("refreshBtn").innerHTML = buttonLabelMarkup("refresh", t("refreshStatus"));
  document.getElementById("exportConfigBtn").innerHTML = buttonLabelMarkup("download", t("exportConfig"));
  document.getElementById("importConfigBtn").innerHTML = buttonLabelMarkup("upload", t("importConfig"));
  document.getElementById("addLocalKeyBtn").innerHTML = buttonLabelMarkup("plus", t("localKeyAdd"));
  document.getElementById("generateLocalKeyBtn").innerHTML = buttonLabelMarkup("wand", t("localKeyAddGenerated"));
  setIconLabel("previewTitle", "plug", t("previewTitle"), "icon icon-md");
  document.getElementById("previewHint").textContent = t("previewHint");
  setIconLabel("runtimeServiceLabel", "server", t("runtimeService"));
  setIconLabel("globalModeSectionLabel", "plug", t("globalModeSectionLabel"));
  document.getElementById("globalModeSectionHint").textContent = t("globalModeSectionHint");
  setIconLabel("globalForwardingTitle", "server", t("globalModeForwardingTitle"));
  setIconLabel("globalProxyTitle", "plug", t("globalModeProxyTitle"));
  setIconLabel("globalStopTitle", "power", t("globalModeStopTitle"));
  document.getElementById("globalForwardingDesc").textContent = t("globalModeForwardingDesc");
  document.getElementById("globalProxyDesc").textContent = t("globalModeProxyDesc");
  document.getElementById("globalStopDesc").textContent = t("globalModeStopDesc");
  document.getElementById("workspaceServiceToggleLabel").textContent = t("protocolServiceSwitchLabel");
  document.getElementById("workspaceBindingToggleLabel").textContent = t("clientHubSwitchLabel");
  document.getElementById("currentProtocolRouteOrderLabel").textContent = t("currentProtocolRouteOrder");
  setIconLabel("upstreamListTitle", "cloud", t("upstreamListTitle", { platform }), "icon icon-md");
  document.getElementById("upstreamListHint").textContent = t("upstreamListHint", { platform });
  document.getElementById("testAllBtn").innerHTML = buttonLabelMarkup("flask", t("testConnection"));
  document.getElementById("addUpstreamBtn").innerHTML = buttonLabelMarkup("plus", t("addUpstream"));
  setIconLabel("usageTitle", "chart", usageTitleText(), "icon icon-md");
  document.getElementById("usageHint").textContent = usageSummaryText();
  document.getElementById("usageLocalKeyLabel").textContent = t("usageLocalKeyFilterLabel");
  document.getElementById("usageAxisTitle").textContent = t("usageAxisRequests");
  document.getElementById("usageAxisTitleNote").textContent = usagePrecisionSummary();
  document.getElementById("usageAxisMin").textContent = "0";
  document.getElementById("listen_host").placeholder = t("listenHostPlaceholder");
  document.getElementById("protocol_listen_host").placeholder = t("listenHostPlaceholder");
  document.getElementById("global_default_model").placeholder = defaultModelPlaceholder();
  document.getElementById("usageLocalKeyInput").placeholder = t("usageLocalKeyFilterPlaceholder");
}

function renderProjectMeta() {
  const meta = state.status?.app || {};
  const license = meta.license || {};
  const source = meta.source || {};
  const updates = meta.updates || {};
  const badges = [
    [t("projectMetaVersion"), `v${meta.version || "-"}`],
    [t("projectMetaConfigVersion"), `v${meta.config_version || "-"}`],
    [t("projectMetaLicense"), license.name || "-"],
    [t("projectMetaAuthor"), meta.author || "-"],
    [t("projectMetaSource"), source.configured ? (source.host || "GitHub") : t("projectMetaSourcePending")],
    [
      t("projectMetaUpdates"),
      updates.channel === "manual"
        ? t("projectMetaUpdatesManual")
        : updates.configured
          ? String(updates.channel || "-")
          : t("projectMetaUpdatesPending"),
    ],
  ];
  document.getElementById("projectMetaBadges").innerHTML = badges.map(([label, value]) => `
    <div class="project-meta-chip">
      <span class="project-meta-chip-label">${escapeHtml(label)}</span>
      <strong class="project-meta-chip-value">${escapeHtml(value)}</strong>
    </div>
  `).join("");

  const links = [];
  if (license.url) {
    links.push(
      `<a class="secondary project-meta-link" href="${escapeHtml(license.url)}" target="_blank" rel="noreferrer noopener">${buttonLabelMarkup("check", t("projectMetaLicenseLink"))}</a>`,
    );
  }
  if (source.configured && source.url) {
    links.push(
      `<a class="secondary project-meta-link" href="${escapeHtml(source.url)}" target="_blank" rel="noreferrer noopener">${buttonLabelMarkup("cloud", t("projectMetaSourceLink"))}</a>`,
    );
  } else {
    links.push(`<span class="project-meta-link muted">${escapeHtml(t("projectMetaSourcePending"))}</span>`);
  }
  if (updates.configured && updates.url) {
    links.push(
      `<a class="secondary project-meta-link" href="${escapeHtml(updates.url)}" target="_blank" rel="noreferrer noopener">${buttonLabelMarkup("download", t("projectMetaUpdatesLink"))}</a>`,
    );
  } else {
    links.push(`<span class="project-meta-link muted">${escapeHtml(t("projectMetaUpdatesPending"))}</span>`);
  }
  document.getElementById("projectMetaLinks").innerHTML = links.join("");
}

function renderProtocolTabs() {
  const container = document.getElementById("workspaceProtocolTabs");
  container.innerHTML = PROTOCOL_ORDER.map((protocol) => {
    const connectivity = protocolConnectivitySummary(protocol);
    const { connected, total, kind } = connectivity;
    const isCurrent = currentProtocol() === protocol;
    const expanded = isCurrent && workspaceExpanded();
    return `
      <button
        class="protocol-nav-btn ${expanded ? "active" : ""}"
        type="button"
        data-protocol-tab="${escapeHtml(protocol)}"
        data-expanded="${expanded ? "true" : "false"}"
        aria-expanded="${expanded ? "true" : "false"}"
      >
        <div class="protocol-nav-title">
          ${protocolLabelMarkup(protocol, platformText(protocol))}
          <span class="protocol-nav-side">
            <span class="pill ${kind}">${connected}/${total}</span>
            <span class="protocol-nav-toggle">${iconMarkup("chevronUp", "icon icon-sm protocol-nav-chevron")}</span>
          </span>
        </div>
        <div class="protocol-nav-meta">${escapeHtml(t("protocolTabMeta", { connected, total }))}</div>
      </button>
    `;
  }).join("");
}

function renderLanguageOptions() {
  const select = document.getElementById("ui_language");
  const value = state.config.ui_language || "auto";
  select.innerHTML = `
    <option value="auto">${escapeHtml(t("languageAuto"))}</option>
    <option value="zh">${escapeHtml(t("languageZh"))}</option>
    <option value="en">${escapeHtml(t("languageEn"))}</option>
  `;
  select.value = value;
}

function renderThemeOptions() {
  const select = document.getElementById("theme_mode");
  const value = state.config.theme_mode || "auto";
  select.innerHTML = `
    <option value="auto">${escapeHtml(t("themeAuto"))}</option>
    <option value="dark">${escapeHtml(t("themeDark"))}</option>
    <option value="light">${escapeHtml(t("themeLight"))}</option>
    <option value="blue">${escapeHtml(t("themeBlue"))}</option>
    <option value="green">${escapeHtml(t("themeGreen"))}</option>
    <option value="amber">${escapeHtml(t("themeAmber"))}</option>
    <option value="rose">${escapeHtml(t("themeRose"))}</option>
    <option value="teal">${escapeHtml(t("themeTeal"))}</option>
  `;
  select.value = value;
}

function renderDefaultModelModeOptions() {
  const select = document.getElementById("default_model_mode");
  const value = state.config.default_model_mode || "upstream";
  select.innerHTML = `
    <option value="global">${escapeHtml(t("defaultModelModeGlobal"))}</option>
    <option value="upstream">${escapeHtml(t("defaultModelModeUpstream"))}</option>
  `;
  select.value = value;
}

function renderEndpointModeOptions() {
  ensureEndpointConfig(state.config);
  const select = document.getElementById("endpoint_mode");
  select.innerHTML = `
    <option value="shared">${escapeHtml(t("endpointModeShared"))}</option>
    <option value="split">${escapeHtml(t("endpointModeSplit"))}</option>
  `;
  select.value = endpointMode();
}

function renderEndpointSettings() {
  ensureEndpointConfig(state.config);
  const mode = endpointMode();
  const protocol = currentProtocol();
  const sharedHostWrapper = document.getElementById("sharedListenHostWrapper");
  const sharedPortWrapper = document.getElementById("sharedListenPortWrapper");
  const webUiPortWrapper = document.getElementById("webUiPortWrapper");
  sharedHostWrapper.style.display = mode === "shared" ? "grid" : "none";
  sharedPortWrapper.style.display = mode === "shared" ? "grid" : "none";
  webUiPortWrapper.style.display = "grid";
  document.getElementById("endpointModeHint").textContent = "";
  document.getElementById("endpointModeHint").hidden = true;
  document.getElementById("listen_host").value = state.config.listen_host || "127.0.0.1";
  document.getElementById("listen_port").value = state.config.listen_port || 8787;
  document.getElementById("web_ui_port").value = mode === "shared" ? (state.config.listen_port || 8787) : (state.config.web_ui_port || "");
  document.getElementById("web_ui_port").disabled = mode === "shared";
  setSwitchChipState(
    document.getElementById("lanAccessToggle"),
    lanAccessEnabled(state.config),
    lanAccessEnabled(state.config) ? t("lanAccessOn") : t("lanAccessOff"),
  );

  const protocolHostInput = document.getElementById("protocol_listen_host");
  const protocolPortInput = document.getElementById("protocol_listen_port");
  const protocolPathInput = document.getElementById("protocol_path");
  const protocolLocalUrlInput = document.getElementById("protocol_local_url");
  protocolHostInput.value = state.config.listen_host || "127.0.0.1";
  protocolPortInput.value = protocolListenPort(state.config, protocol);
  protocolPathInput.value = protocolLocalPath(state.config, protocol);
  protocolLocalUrlInput.value = protocolLocalUrl(state.config, protocol);

  protocolHostInput.disabled = mode === "shared";
  protocolPortInput.disabled = mode === "shared";
  protocolPathInput.disabled = mode !== "shared";
  document.getElementById("networkHint").textContent = mode === "shared" ? t("networkHintShared") : t("networkHintSplit");
}

function syncLanAccessToggle() {
  const toggle = document.getElementById("lanAccessToggle");
  if (!toggle) {
    return;
  }
  const enabled = lanAccessEnabled(state.config);
  setSwitchChipState(toggle, enabled, enabled ? t("lanAccessOn") : t("lanAccessOff"));
}

function renderRoutingStrategyOptions() {
  const select = document.getElementById("routing_strategy");
  const value = getRoutingStrategyFromConfig(state.config, currentProtocol());
  select.innerHTML = `
    <option value="manual">${escapeHtml(t("routingStrategyManual"))}</option>
    <option value="auto">${escapeHtml(t("routingStrategyAuto"))}</option>
  `;
  select.value = value;
}

function renderManualActiveOptions() {
  const select = document.getElementById("manual_active_upstream_id");
  const label = document.getElementById("manualActiveLabel");
  const protocol = currentProtocol();
  const strategy = getRoutingStrategyFromConfig(state.config, protocol);
  if (strategy === "auto") {
    label.textContent = t("autoRoutingModeLabel");
    const value = getAutoRoutingModeFromConfig(state.config, protocol);
    select.innerHTML = `
      <option value="priority">${escapeHtml(t("routingModePriority"))}</option>
      <option value="round_robin">${escapeHtml(t("routingModeRoundRobin"))}</option>
      <option value="latency">${escapeHtml(t("routingModeLatency"))}</option>
    `;
    select.value = value;
    return;
  }

  label.textContent = t("manualActiveUpstream");
  const upstreams = protocolRenderedUpstreams(protocol);
  ensureManualActiveStillValid();
  if (!upstreams.length) {
    select.innerHTML = `<option value="">${escapeHtml(t("noUpstreamsForProtocol", { platform: platformText(protocol) }))}</option>`;
    select.value = "";
    return;
  }
  select.innerHTML = upstreams
    .map((upstream) => `<option value="${escapeHtml(upstream.id)}">${escapeHtml(upstream.name || upstream.id)}</option>`)
    .join("");
  select.value = state.config.routing_by_protocol[protocol].manual_active_upstream_id || upstreams[0].id;
}

function updateHints() {
  const routingStrategy = document.getElementById("routing_strategy").value;
  const manualWrapper = document.getElementById("manualActiveWrapper");
  manualWrapper.style.display = "grid";

  document.getElementById("routingHint").textContent =
    routingStrategy === "manual"
      ? t("routingHintManual")
      : document.getElementById("manual_active_upstream_id").value === "round_robin"
        ? t("routingHintRoundRobin")
        : document.getElementById("manual_active_upstream_id").value === "latency"
          ? t("routingHintLatency")
          : t("routingHintPriority");

  const mode = document.getElementById("default_model_mode").value;
  const globalInput = document.getElementById("global_default_model");
  globalInput.disabled = mode !== "global";
  document.getElementById("defaultModelHint").textContent = mode === "global" ? t("globalDefaultModelHint") : t("upstreamDefaultModelHint");
}

function renderLocalKeys() {
  normalizeLocalKeys(state.config);
  const renderSignature = signatureOf({
    language: currentLanguage(),
    config: state.config?.local_api_keys || [],
    status: state.status?.local_api_keys || [],
    expanded: [...state.expandedLocalKeyIds].sort(),
  });
  if (renderSignature === state.localKeyRenderSignature) {
    return;
  }
  state.localKeyRenderSignature = renderSignature;
  const list = document.getElementById("localKeyList");
  const statusById = localKeyStatusMap();
  const primary = primaryLocalKey();
  list.innerHTML = (state.config.local_api_keys || [])
    .map((item) => {
      const statusItem = statusById.get(item.id);
      const stats = statusItem?.stats || {};
      const expanded = state.expandedLocalKeyIds.has(item.id);
      const usageText = t("localKeyUsage", {
        success: stats.success_count || 0,
        total: stats.request_count || 0,
      });
      const lastUsedText = t("localKeyLastUsed", {
        time: formatLocalKeyLastUsed(stats.last_used_at),
      });
      return `
        <article class="local-key-card" data-local-key-id="${escapeHtml(item.id)}">
          <div class="local-key-summary">
            <div class="summary-main">
              <div>
                <div class="summary-title">
                  <h3 class="summary-name">${escapeHtml(item.name || "-")}</h3>
                  ${primary?.id === item.id ? `<span class="pill ok">${escapeHtml(t("localKeyPrimary"))}</span>` : ""}
                  <span class="pill">${escapeHtml(localKeyProtocolSummary(item.allowed_protocols))}</span>
                </div>
                <div class="summary-base">${escapeHtml(`${usageText} · ${lastUsedText}`)}</div>
              </div>
            </div>
            <div class="summary-actions">
              ${renderSwitchChipHtml({
                label: t("toggleEnabledShort"),
                active: item.enabled,
                compact: true,
                attrs: 'data-action="local-key-enabled-toggle"',
              })}
              <button class="primary" type="button" data-action="local-key-toggle">${buttonLabelMarkup(expanded ? "chevronUp" : "pencil", expanded ? t("collapse") : t("edit"))}</button>
            </div>
          </div>
          <div class="local-key-editor" ${expanded ? "" : "hidden"}>
            <div class="editor-shell">
              <div class="editor-grid">
                <label>
                  <span>${escapeHtml(t("localKeyName"))}</span>
                  <input type="text" data-local-key-field="name" value="${escapeHtml(item.name || "")}" />
                </label>
                <label>
                  <span>${escapeHtml(t("localKeyValue"))}</span>
                  <input type="text" data-local-key-field="key" value="${escapeHtml(item.key || "")}" />
                </label>
              </div>
              <div class="editor-grid" style="margin-top: 12px">
                <label style="grid-column: 1 / -1;">
                  <span>${escapeHtml(t("localKeyAllowedTypes"))}</span>
                  <div class="local-key-type-row">
                    <div class="protocol-checks">
                      ${PROTOCOL_ORDER.map((protocol) => `
                        <button
                          class="protocol-check ${normalizeLocalKeyProtocols(item.allowed_protocols).includes(protocol) ? "active" : ""}"
                          type="button"
                          data-action="local-key-protocol-toggle"
                          data-local-key-protocol="${escapeHtml(protocol)}"
                          aria-pressed="${normalizeLocalKeyProtocols(item.allowed_protocols).includes(protocol) ? "true" : "false"}"
                        >
                          ${protocolLabelMarkup(protocol, platformText(protocol), true)}
                        </button>
                      `).join("")}
                    </div>
                    <div class="editor-actions local-key-action-row">
                      <button class="ghost" type="button" data-action="local-key-primary">${buttonLabelMarkup("key", t("localKeySetPrimary"))}</button>
                      <button class="secondary" type="button" data-action="local-key-generate">${buttonLabelMarkup("wand", t("localKeyGenerate"))}</button>
                      <button class="danger" type="button" data-action="local-key-remove" ${state.config.local_api_keys.length <= 1 ? "disabled" : ""}>${buttonLabelMarkup("trash", t("localKeyDelete"))}</button>
                    </div>
                  </div>
                </label>
              </div>
            </div>
          </div>
        </article>
      `;
    })
    .join("");
}

function renderSettings() {
  normalizeLocalKeys(state.config);
  ensureRoutingByProtocol(state.config);
  ensureEndpointConfig(state.config);
  document.getElementById("request_timeout_sec").value = state.config.request_timeout_sec || 120;
  document.getElementById("cooldown_seconds").value = state.config.cooldown_seconds || 60;
  document.getElementById("global_default_model").value = state.config.global_default_model || "";
  renderProtocolTabs();
  renderWorkspacePanels();
  renderLanguageOptions();
  renderThemeOptions();
  renderEndpointModeOptions();
  renderEndpointSettings();
  renderDefaultModelModeOptions();
  renderRoutingStrategyOptions();
  renderManualActiveOptions();
  renderLocalKeys();
  updateHints();
  renderCurrentProtocolRouteOrder();
}

function renderCurrentProtocolRouteOrder() {
  const node = document.getElementById("currentProtocolRouteOrder");
  if (!node) {
    return;
  }
  const preview = effectiveProtocolRoutingState(currentProtocol()).preview_order || [];
  if (preview.length) {
    node.textContent = preview
      .map((item, index) => `${index + 1}. ${item.name || item.id || "-"}`)
      .join(" → ");
    return;
  }
  const fallback = protocolRenderedUpstreams(currentProtocol());
  node.textContent = fallback.length
    ? fallback.map((item, index) => `${index + 1}. ${item.name || item.id || "-"}`).join(" → ")
    : t("currentProtocolRouteOrderEmpty");
}
