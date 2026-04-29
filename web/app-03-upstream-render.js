function upstreamSwitchActive(upstream, statusEntry = {}) {
  if (!upstream?.enabled) {
    return false;
  }
  if (Object.prototype.hasOwnProperty.call(statusEntry, "effective_enabled")) {
    return Boolean(statusEntry.effective_enabled);
  }
  return true;
}

function upstreamIsTemporarilyUnavailable(upstream, statusEntry = {}) {
  if (!upstream?.enabled) {
    return false;
  }
  if (statusEntry.temporarily_disabled) {
    return true;
  }
  const cooldownSeconds = Math.max(0, Number(statusEntry?.stats?.cooldown_remaining_sec || 0));
  if (cooldownSeconds > 0) {
    return true;
  }
  return ["manual_lock", "temporary_exhausted", "quota_exhausted", "expired"].includes(String(statusEntry.subscription_state || ""));
}

function getActivationMeta(upstreamId, enabled, protocol) {
  const statusItem = statusMap().get(upstreamId) || {};
  const cooldownSeconds = Math.max(0, Number(statusItem?.stats?.cooldown_remaining_sec || 0));
  const lastError = String(statusItem?.stats?.last_error || "").toLowerCase();
  const isLikelyNetworkCooldown = (
    !statusItem?.stats?.last_status
    || [
      "timed out",
      "timeout",
      "connection",
      "reset by peer",
      "broken pipe",
      "refused",
      "unreachable",
      "ssl",
      "tls",
      "econn",
      "network",
      "socket",
    ].some((marker) => lastError.includes(marker))
  );
  if (enabled && statusItem.subscription_state === "manual_lock") {
    return { label: t("subscriptionStateManualLock"), kind: "bad" };
  }
  if (enabled && statusItem.subscription_state === "expired") {
    return { label: t("subscriptionStateExpired"), kind: "muted" };
  }
  if (enabled && statusItem.subscription_state === "temporary_exhausted") {
    return {
      label: t("subscriptionStateWaitingReset", {
        remaining: formatSubscriptionCountdown(statusItem.subscription_next_reset_at),
      }),
      kind: "warn",
    };
  }
  if (enabled && statusItem.subscription_state === "quota_exhausted") {
    return { label: t("subscriptionStateQuotaExhausted"), kind: "bad" };
  }
  if (enabled && cooldownSeconds > 0) {
    return {
      label: t(
        isLikelyNetworkCooldown ? "subscriptionStateNetworkCooling" : "subscriptionStateCooling",
        { seconds: cooldownSeconds },
      ),
      kind: "warn",
    };
  }
  const routing = effectiveProtocolRoutingState(protocol);
  const preview = routing.preview_order || [];
  const previewIndex = preview.findIndex((item) => item.id === upstreamId);
  if (!enabled) {
    return { label: t("summaryDisabled"), kind: "bad" };
  }
  if (routing.auto_routing_enabled === false) {
    if (routing.manual_active_upstream_id === upstreamId) {
      return { label: t("summaryManualActive"), kind: "ok" };
    }
    return { label: t("summaryInactive"), kind: "warn" };
  }
  if (previewIndex === 0) {
    return { label: t("summaryPreferred"), kind: "ok" };
  }
  if (previewIndex > 0) {
    return { label: t("summaryCandidate", { index: previewIndex + 1 }), kind: "info" };
  }
  return { label: t("summaryStandby"), kind: "warn" };
}

function formatSubscriptionDateTime(value) {
  if (!value) {
    return t("subscriptionPermanent");
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString(currentLanguage() === "zh" ? "zh-CN" : "en-US", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatSubscriptionCountdown(value) {
  if (!value) {
    return currentLanguage() === "zh" ? "即将重置" : "soon";
  }
  const target = new Date(value);
  if (Number.isNaN(target.getTime())) {
    return formatSubscriptionDateTime(value);
  }
  const totalSeconds = Math.max(0, Math.ceil((target.getTime() - Date.now()) / 1000));
  if (totalSeconds <= 60) {
    return currentLanguage() === "zh" ? "1 分钟内" : "< 1 min";
  }
  const days = Math.floor(totalSeconds / 86400);
  const hours = Math.floor((totalSeconds % 86400) / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  if (currentLanguage() === "zh") {
    if (days > 0) {
      return `${days}天${hours}小时`;
    }
    if (hours > 0) {
      return `${hours}小时${minutes}分`;
    }
    return `${Math.max(1, minutes)}分`;
  }
  if (days > 0) {
    return `${days}d ${hours}h`;
  }
  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }
  return `${Math.max(1, minutes)}m`;
}

function subscriptionKindText(kind) {
  if (kind === "periodic") {
    return t("subscriptionKindPeriodic");
  }
  if (kind === "quota") {
    return t("subscriptionKindQuota");
  }
  return t("subscriptionKindUnlimited");
}

function subscriptionFailureModeText(mode) {
  if (mode === "consecutive_days") {
    return t("subscriptionFailureDays");
  }
  return t("subscriptionFailureFailures");
}

function subscriptionStatusMeta(subscription, runtime = {}) {
  const state = runtime.state || "ready";
  if (state === "disabled") {
    return { label: t("subscriptionItemDisabled"), kind: "warn" };
  }
  if (state === "expired") {
    return { label: t("subscriptionItemExpired"), kind: "bad" };
  }
  if (state === "invalid_schedule") {
    return { label: t("subscriptionItemInvalidSchedule"), kind: "bad" };
  }
  if (state === "pending_refresh") {
    return runtime.next_reset_at
      ? { label: t("subscriptionItemWaitingReset", { remaining: formatSubscriptionCountdown(runtime.next_reset_at) }), kind: "warn" }
      : { label: t("subscriptionStateWaitingReset", { remaining: formatSubscriptionCountdown("") }), kind: "warn" };
  }
  if (state === "exhausted" && runtime.next_reset_at) {
    return { label: t("subscriptionItemWaitingReset", { remaining: formatSubscriptionCountdown(runtime.next_reset_at) }), kind: "warn" };
  }
  if (state === "exhausted") {
    return { label: t("subscriptionItemExhausted"), kind: "bad" };
  }
  return { label: t("subscriptionItemReady"), kind: "ok" };
}

function subscriptionRefreshSummary(subscription) {
  if (subscription.kind !== "periodic") {
    return t("subscriptionNoReset");
  }
  const times = normalizeRefreshTimes(subscription.refresh_times);
  return times.length ? times.join(", ") : t("subscriptionNoReset");
}

function subscriptionDisplayRank(runtime = {}) {
  const state = String(runtime.state || "ready");
  if (state === "ready") {
    return 0;
  }
  if (state === "awaiting_probe") {
    return 1;
  }
  if (state === "pending_refresh") {
    return 2;
  }
  if (state === "exhausted") {
    return 3;
  }
  if (state === "expired") {
    return 90;
  }
  if (state === "disabled") {
    return 100;
  }
  return 10;
}

function renderSubscriptionEditors(upstreamId, upstream) {
  const statusEntry = statusMap().get(upstreamId) || {};
  const runtimeMap = new Map((statusEntry.subscriptions || []).map((item) => [item.id, item]));
  const subscriptions = normalizeUpstreamSubscriptions(upstream)
    .map((subscription, index) => ({
      subscription,
      runtime: runtimeMap.get(subscription.id) || {},
      sourceIndex: index,
    }))
    .sort((left, right) => (
      subscriptionDisplayRank(left.runtime) - subscriptionDisplayRank(right.runtime)
      || left.sourceIndex - right.sourceIndex
    ));
  return `
    <section class="subscription-section">
      <div class="subscription-header">
        <div>
          <h4>${escapeHtml(t("subscriptionSectionTitle"))}</h4>
          <p>${escapeHtml(t("subscriptionSectionHint"))}</p>
        </div>
        <button class="secondary" type="button" data-action="add-subscription">${buttonLabelMarkup("plus", t("subscriptionAdd"))}</button>
      </div>
      <div class="subscription-list">
        ${subscriptions.map(({ subscription, runtime, sourceIndex }) => {
          const statusMeta = subscriptionStatusMeta(subscription, runtime);
          const subscriptionExpired = runtime.state === "expired" || subscription.expired;
          const subscriptionEnabled = runtime.effective_enabled ?? (subscription.enabled && !subscriptionExpired);
          return `
            <div class="subscription-card" data-subscription-id="${escapeHtml(subscription.id)}">
              <div class="subscription-card-head">
                <div class="subscription-card-title">
                  <strong>${escapeHtml(subscription.name || t("subscriptionFallbackName", { index: sourceIndex + 1 }))}</strong>
                  <span class="pill ${escapeHtml(statusMeta.kind)}">${escapeHtml(statusMeta.label)}</span>
                </div>
                <button class="ghost" type="button" data-action="remove-subscription" data-subscription-id="${escapeHtml(subscription.id)}">${buttonLabelMarkup("trash", t("subscriptionRemove"))}</button>
              </div>
              <div class="editor-grid subscription-grid">
                <label>
                  <span>${escapeHtml(t("subscriptionName"))}</span>
                  <input data-subscription-field="name" value="${escapeHtml(subscription.name || "")}" />
                </label>
                <label>
                  <span>${escapeHtml(t("subscriptionKindLabel"))}</span>
                  <select data-subscription-field="kind">
                    <option value="unlimited" ${subscription.kind === "unlimited" ? "selected" : ""}>${escapeHtml(subscriptionKindText("unlimited"))}</option>
                    <option value="periodic" ${subscription.kind === "periodic" ? "selected" : ""}>${escapeHtml(subscriptionKindText("periodic"))}</option>
                    <option value="quota" ${subscription.kind === "quota" ? "selected" : ""}>${escapeHtml(subscriptionKindText("quota"))}</option>
                  </select>
                </label>
                <label>
                  <span>${escapeHtml(t("subscriptionExpiryMode"))}</span>
                  <select data-subscription-field="permanent">
                    <option value="true" ${subscription.permanent ? "selected" : ""}>${escapeHtml(t("subscriptionPermanent"))}</option>
                    <option value="false" ${subscription.permanent ? "" : "selected"}>${escapeHtml(t("subscriptionExpiresAt"))}</option>
                  </select>
                </label>
                <label>
                  <span>${escapeHtml(t("subscriptionExpiryLabel"))}</span>
                  <input type="date" data-subscription-field="expires_at" value="${escapeHtml(subscription.expires_at || "")}" ${subscription.permanent ? "disabled" : ""} />
                </label>
                <label>
                  <span>${escapeHtml(t("subscriptionRefreshTimes"))}</span>
                  <input data-subscription-field="refresh_times" value="${escapeHtml(subscriptionRefreshSummary(subscription))}" placeholder="09:00, 21:00" ${subscription.kind === "periodic" ? "" : "disabled"} />
                </label>
                <label>
                  <span>${escapeHtml(t("subscriptionFailureModeLabel"))}</span>
                  <select data-subscription-field="failure_mode" ${subscription.kind === "unlimited" ? "disabled" : ""}>
                    <option value="consecutive_failures" ${subscription.failure_mode === "consecutive_failures" ? "selected" : ""}>${escapeHtml(subscriptionFailureModeText("consecutive_failures"))}</option>
                    <option value="consecutive_days" ${subscription.failure_mode === "consecutive_days" ? "selected" : ""}>${escapeHtml(subscriptionFailureModeText("consecutive_days"))}</option>
                  </select>
                </label>
                <label>
                  <span>${escapeHtml(t("subscriptionFailureThresholdLabel"))}</span>
                  <input type="number" min="1" data-subscription-field="failure_threshold" value="${escapeHtml(subscription.failure_threshold || 1)}" ${subscription.kind === "unlimited" ? "disabled" : ""} />
                </label>
                <label class="subscription-enabled-field">
                  <span>${escapeHtml(t("subscriptionEnabled"))}</span>
                  ${renderSwitchChipHtml({
                    label: t("toggleEnabledShort"),
                    active: subscriptionEnabled,
                    compact: true,
                    className: "micro subscription-switch",
                    attrs: `data-subscription-field="enabled" ${subscriptionExpired ? "disabled" : ""}`,
                  })}
                </label>
              </div>
            </div>
          `;
        }).join("")}
      </div>
    </section>
  `;
}

function getProbeSummary(upstreamId, stats) {
  const probe = state.localProbeResults[upstreamId];
  const probeStatus = probe?.status ?? stats?.last_probe_status;
  const probeError = probe?.error ?? stats?.last_probe_error;
  const probeLatency = probe?.latency_ms ?? stats?.last_probe_latency_ms;
  if (!probeStatus && !probeError) {
    return { label: t("summaryNeverTested"), kind: "" };
  }
  if (probeStatus) {
    const latency = probeLatency == null ? "" : ` / ${probeLatency}ms`;
    return { label: t("summaryProbeOk", { status: probeStatus, latency }), kind: "ok" };
  }
  return { label: t("summaryProbeFail"), kind: "bad" };
}

function getDetectedModels(upstreamId) {
  const rawModels = Array.isArray(state.localProbeResults[upstreamId]?.models) ? state.localProbeResults[upstreamId].models : [];
  const models = [];
  const seen = new Set();
  rawModels.forEach((item) => {
    const value = String(item || "").trim();
    if (!value || seen.has(value)) {
      return;
    }
    seen.add(value);
    models.push(value);
  });
  return models;
}

function formatDetectedModelLabel(protocol, value) {
  const model = String(value || "").trim();
  if (!model) {
    return "";
  }
  if (normalizeUpstreamProtocol(protocol) === "gemini" && model.startsWith("models/")) {
    return model.slice("models/".length);
  }
  return model;
}

function detectedModelNoteText(upstreamId) {
  const models = getDetectedModels(upstreamId);
  if (models.length) {
    return t("editorDetectedModelsReady", { count: models.length });
  }
  const probe = state.localProbeResults[upstreamId];
  if (probe?.error) {
    const cleaned = String(probe.error || "")
      .replace(/^测试失败[:：]\s*/i, "")
      .replace(/^test failed:\s*/i, "")
      .trim();
    return t("editorDetectedModelsFailed", { message: cleaned || probe.error });
  }
  if (probe?.status) {
    return t("editorDetectedModelsNone");
  }
  return t("editorDetectedModelsEmpty");
}

function detectedModelNoteClass(upstreamId) {
  return getDetectedModels(upstreamId).length ? "upstream-model-note highlight" : "upstream-model-note";
}

function renderDetectedModelPicker(upstreamId, upstream) {
  const models = getDetectedModels(upstreamId);
  const currentValue = String(upstream.default_model || "");
  const datalistId = `upstream-model-options-${upstreamId}`;
  const options = models.map((model) => (
    `<option value="${escapeHtml(model)}">${escapeHtml(formatDetectedModelLabel(upstream.protocol, model))}</option>`
  )).join("");
  return `
    <input data-field="default_model" ${models.length ? `list="${escapeHtml(datalistId)}"` : ""} value="${escapeHtml(currentValue)}" placeholder="${escapeHtml(defaultModelPlaceholder(upstream.protocol))}" />
    ${models.length ? `<datalist id="${escapeHtml(datalistId)}">${options}</datalist>` : ""}
  `;
}

function getRequestSummary(stats) {
  return t("summaryRequests", {
    success: stats?.success_count || 0,
    total: stats?.request_count || 0,
  });
}

function upstreamColor(upstreamId) {
  const index = (state.config.upstreams || []).findIndex((item) => item.id === upstreamId);
  return UPSTREAM_COLORS[(index === -1 ? 0 : index) % UPSTREAM_COLORS.length];
}

function renderUpstreams() {
  const list = document.getElementById("upstreamList");
  const protocol = currentProtocol();
  const upstreams = protocolConfigUpstreams(protocol);
  state.upstreamSummarySignature = "";
  if (!upstreams.length) {
    renderProtocolTabs();
    list.innerHTML = `<div class="empty">${escapeHtml(t("noUpstreamsForProtocol", { platform: platformText(protocol) }))}</div>`;
    return;
  }

  list.innerHTML = upstreams.map((baseUpstream, index) => {
    const upstream = getRenderedUpstream(baseUpstream.id);
    const expanded = state.expandedUpstreamIds.has(baseUpstream.id);
    const statusEntry = statusMap().get(baseUpstream.id) || {};
    const switchActive = upstreamSwitchActive(upstream, statusEntry);
    return `
      <article class="upstream-card" data-upstream-id="${escapeHtml(baseUpstream.id)}">
        <div class="upstream-summary">
          <div class="summary-main">
            <button class="drag-handle ghost" type="button" draggable="true" data-drag-handle="true" aria-label="Drag to reorder">${iconMarkup("grip", "icon icon-sm")}</button>
            <div class="summary-copy">
              <div class="summary-title">
                <h3 class="summary-name" data-role="summary-name">${escapeHtml(upstream.name || `Upstream ${index + 1}`)}</h3>
                <span class="pill" data-role="protocol"></span>
                <span class="pill" data-role="probe"></span>
              </div>
              <div class="summary-base" data-role="summary-base">${escapeHtml(upstream.base_url || "—")}</div>
            </div>
          </div>
          <div class="summary-badges">
            <span class="pill" data-role="activation"></span>
            <span class="pill" data-role="requests"></span>
          </div>
          <div class="summary-actions">
            ${renderSwitchChipHtml({
              label: t("toggleEnabledShort"),
              active: switchActive,
              compact: true,
              attrs: 'data-action="toggle-enabled"',
            })}
            <button class="primary" type="button" data-action="toggle">${buttonLabelMarkup(expanded ? "chevronUp" : "pencil", expanded ? t("collapse") : t("edit"))}</button>
          </div>
        </div>
          <div class="upstream-editor" ${expanded ? "" : "hidden"}>
          <div class="editor-shell">
            <div class="editor-grid">
              <label>
                <span>${escapeHtml(t("editorName"))}</span>
                <input data-field="name" value="${escapeHtml(upstream.name || "")}" />
              </label>
              <label>
                <span>${escapeHtml(t("editorBaseUrl"))}</span>
                <input data-field="base_url" value="${escapeHtml(upstream.base_url || "")}" placeholder="https://example.com/v1" />
              </label>
              <label>
                <span>${escapeHtml(t("editorApiKey"))}</span>
                <input data-field="api_key" value="${escapeHtml(upstream.api_key || "")}" />
              </label>
              ${protocol === "local_llm" ? `
              <label>
                <span>${escapeHtml(t("editorUpstreamProtocol"))}</span>
                <select data-field="upstream_protocol">
                  ${LOCAL_LLM_UPSTREAM_PROTOCOLS.map((p) => `<option value="${escapeHtml(p)}" ${(upstream.upstream_protocol || "openai") === p ? "selected" : ""}>${escapeHtml(protocolText(p))}</option>`).join("")}
                </select>
              </label>
              ` : ""}
              <label>
                <span>${escapeHtml(t("editorDefaultModel"))}</span>
                ${renderDetectedModelPicker(baseUpstream.id, upstream)}
              </label>
            </div>
            ${renderSubscriptionEditors(baseUpstream.id, upstream)}
            <div class="editor-grid" style="margin-top: 12px">
              <label>
                <span>${escapeHtml(t("editorHeaders"))}</span>
                <textarea data-field="extra_headers">${escapeHtml(extraHeadersToText(upstream.extra_headers))}</textarea>
              </label>
              <label>
                <span>${escapeHtml(t("editorNotes"))}</span>
                <textarea data-field="notes">${escapeHtml(upstream.notes || "")}</textarea>
              </label>
            </div>
            <div class="editor-footer">
              <div class="editor-actions">
                <button class="secondary" type="button" data-action="test">${buttonLabelMarkup("flask", t("editorTest"))}</button>
                ${upstreamIsTemporarilyUnavailable(upstream, statusEntry) ? `<button class="secondary" type="button" data-action="reactivate-upstream">${buttonLabelMarkup("power", t("subscriptionReactivate"))}</button>` : ""}
                <button class="ghost" type="button" data-action="save-editor">${buttonLabelMarkup("check", t("editorSave"))}</button>
                <button class="ghost" type="button" data-action="cancel-editor">${buttonLabelMarkup("undo", t("editorCancel"))}</button>
                <button class="danger" type="button" data-action="remove">${buttonLabelMarkup("trash", t("editorDelete"))}</button>
              </div>
              <p class="${escapeHtml(detectedModelNoteClass(baseUpstream.id))}">${escapeHtml(detectedModelNoteText(baseUpstream.id))}</p>
            </div>
          </div>
        </div>
      </article>
    `;
  }).join("");

  updateUpstreamSummaryDom();
  renderProtocolTabs();
}

function updateUpstreamSummaryDom() {
  const protocol = currentProtocol();
  const renderSignature = signatureOf({
    language: currentLanguage(),
    protocol,
    upstreams: protocolConfigUpstreams(protocol).map((item) => ({
      id: item.id,
      name: getRenderedUpstream(item.id)?.name || item.name || "",
      base_url: getRenderedUpstream(item.id)?.base_url || item.base_url || "",
      protocol: getRenderedUpstream(item.id)?.protocol || item.protocol || "",
      enabled: Boolean(getRenderedUpstream(item.id)?.enabled ?? item.enabled),
      status: (state.status?.upstreams || []).find((statusItem) => statusItem.id === item.id) || {},
      probe: state.localProbeResults[item.id] || null,
    })),
    routing: effectiveProtocolRoutingState(protocol),
  });
  if (renderSignature === state.upstreamSummarySignature) {
    return;
  }
  state.upstreamSummarySignature = renderSignature;
  const map = statusMap();
  document.querySelectorAll(".upstream-card").forEach((card) => {
    const upstreamId = card.dataset.upstreamId;
    const upstream = getRenderedUpstream(upstreamId);
    if (!upstream) {
      return;
    }
    const statusEntry = map.get(upstreamId) || {};
    const stats = statusEntry.stats || {};
    const activation = getActivationMeta(upstreamId, upstream.enabled, upstream.protocol);
    const probe = getProbeSummary(upstreamId, stats);
    const requests = getRequestSummary(stats);
    const switchActive = upstreamSwitchActive(upstream, statusEntry);

    card.querySelector("[data-role='summary-name']").textContent = upstream.name || "-";
    card.querySelector("[data-role='summary-base']").textContent = upstream.base_url || "—";
    const protocolEl = card.querySelector("[data-role='protocol']");
    protocolEl.innerHTML = protocolLabelMarkup(upstream.protocol || "openai", protocolText(upstream.protocol || "openai"), true);
    protocolEl.className = "pill protocol-pill";

    const probeEl = card.querySelector("[data-role='probe']");
    probeEl.textContent = probe.label;
    probeEl.className = `pill ${probe.kind}`;

    const activationEl = card.querySelector("[data-role='activation']");
    activationEl.textContent = activation.label;
    activationEl.className = `pill ${activation.kind}`;

    const requestEl = card.querySelector("[data-role='requests']");
    requestEl.textContent = requests;
    requestEl.className = "pill";

    const toggleButton = card.querySelector("button[data-action='toggle-enabled']");
    setSwitchChipState(toggleButton, switchActive, t("toggleEnabledShort"));
  });
}

function renderProtocolWorkspace() {
  renderSettings();
  renderUpstreams();
  renderUsage();
}

function refreshUpstreamDraftPreview() {
  renderProtocolTabs();
  updateUpstreamSummaryDom();
  renderUsage();
}
