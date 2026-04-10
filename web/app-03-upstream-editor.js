function ensureEditorDraft(upstreamId) {
  if (state.editorDrafts[upstreamId]) {
    return state.editorDrafts[upstreamId];
  }
  const upstream = getConfigUpstream(upstreamId) || getRenderedUpstream(upstreamId);
  if (!upstream) {
    return null;
  }
  state.editorDrafts[upstreamId] = cloneDeep(upstream);
  return state.editorDrafts[upstreamId];
}

function applyDraftFieldValue(draft, field, control) {
  if (!draft || !field) {
    return;
  }
  if (field === "enabled") {
    draft.enabled = control.checked;
    return;
  }
  if (field === "extra_headers") {
    draft.extra_headers = parseExtraHeaders(control.value);
    return;
  }
  draft[field] = control.value;
}

function applySubscriptionFieldValue(subscription, field, control) {
  if (!subscription || !field) {
    return;
  }
  if (field === "enabled") {
    subscription.enabled = switchChipIsActive(control);
    return;
  }
  if (field === "permanent") {
    subscription.permanent = control.value !== "false";
    if (subscription.permanent) {
      subscription.expires_at = "";
    }
    return;
  }
  if (field === "failure_threshold") {
    subscription.failure_threshold = Math.max(1, Number(control.value || "1") || 1);
    return;
  }
  if (field === "refresh_times") {
    subscription.refresh_times = normalizeRefreshTimes(
      String(control.value || "")
        .split(/[\s,]+/)
        .filter(Boolean),
    );
    return;
  }
  subscription[field] = control.value;
}

function buildDraftFromEditor(card) {
  const upstreamId = card?.dataset?.upstreamId;
  if (!upstreamId) {
    return null;
  }
  const base = cloneDeep(getRenderedUpstream(upstreamId));
  if (!base) {
    return null;
  }
  const editor = card.querySelector(".upstream-editor");
  if (!editor || editor.hasAttribute("hidden")) {
    return base;
  }
  editor.querySelectorAll("[data-field]").forEach((control) => {
    applyDraftFieldValue(base, control.dataset.field, control);
  });
  const subscriptionCards = [...editor.querySelectorAll(".subscription-card")];
  if (subscriptionCards.length) {
    const currentSubscriptions = normalizeUpstreamSubscriptions(base);
    const subscriptionMap = new Map(currentSubscriptions.map((item) => [item.id, item]));
    base.subscriptions = subscriptionCards.map((subscriptionCard, index) => {
      const subscriptionId = subscriptionCard.dataset.subscriptionId || "";
      const current = cloneDeep(subscriptionMap.get(subscriptionId) || defaultSubscription(index, base.name || ""));
      subscriptionCard.querySelectorAll("[data-subscription-field]").forEach((control) => {
        applySubscriptionFieldValue(current, control.dataset.subscriptionField, control);
      });
      return normalizeSubscription(current, index, base.name || "");
    });
  }
  base.subscriptions = normalizeUpstreamSubscriptions(base);
  return base;
}

function buildProbePayload(upstreamId) {
  syncOpenEditorDraftsFromDom();
  return {
    id: upstreamId,
    upstream: getRenderedUpstream(upstreamId),
  };
}

function recordLocalProbeSuccess(upstreamId, result) {
  state.localProbeResults[upstreamId] = {
    status: result.status,
    latency_ms: result.latency_ms,
    models_count: result.models_count,
    models: Array.isArray(result.models) ? result.models : [],
    error: "",
  };
}

function recordLocalProbeFailure(upstreamId, errorMessage) {
  state.localProbeResults[upstreamId] = {
    status: null,
    latency_ms: null,
    models_count: null,
    models: [],
    error: errorMessage,
  };
}

async function testUpstream(upstreamId) {
  try {
    const result = await getJson("/api/test", {
      method: "POST",
      body: JSON.stringify(buildProbePayload(upstreamId)),
    });
    recordLocalProbeSuccess(upstreamId, result.result);
    renderUpstreams();
    const models = result.result.models_count == null ? "" : currentLanguage() === "zh" ? `，模型数 ${result.result.models_count}` : `, models ${result.result.models_count}`;
    const latency = result.result.latency_ms == null ? "" : currentLanguage() === "zh" ? `，延迟 ${result.result.latency_ms} ms` : `, latency ${result.result.latency_ms} ms`;
    flash(t("flashTestSuccess", { status: result.result.status, models, latency }));
    await refreshStatus();
  } catch (error) {
    recordLocalProbeFailure(upstreamId, error.message);
    renderUpstreams();
    flash(t("flashTestFailed", { message: error.message }), "bad");
  }
}

function allProtocolUpstreamEntries() {
  return PROTOCOL_ORDER.flatMap((protocol) => (
    protocolRenderedUpstreams(protocol).map((upstream) => ({ protocol, upstream }))
  ));
}

async function testAllUpstreams() {
  const upstreams = protocolRenderedUpstreams(currentProtocol());
  if (!upstreams.length) {
    flash(t("noUpstreamsForProtocol", { platform: platformText() }), "bad");
    return;
  }
  flash(t("flashTestingAllStart"));
  let success = 0;
  let failed = 0;
  for (const [index, item] of upstreams.entries()) {
    flash(t("flashTestingProgress", { index: index + 1, total: upstreams.length, name: getRenderedUpstream(item.id)?.name || item.id }));
    try {
      const result = await getJson("/api/test", {
        method: "POST",
        body: JSON.stringify(buildProbePayload(item.id)),
      });
      recordLocalProbeSuccess(item.id, result.result);
      success += 1;
    } catch (error) {
      recordLocalProbeFailure(item.id, error.message);
      failed += 1;
    }
    renderUpstreams();
  }
  await refreshStatus();
  flash(t("flashTestingAllDone", { success, failed }), failed > 0 ? "bad" : "ok");
}

async function testAllWorkspaceUpstreams() {
  const entries = allProtocolUpstreamEntries();
  if (!entries.length) {
    flash(t("noUpstreams"), "bad");
    return;
  }
  flash(t("flashTestingWorkspaceAllStart"));
  let success = 0;
  let failed = 0;
  for (const [index, entry] of entries.entries()) {
    const name = getRenderedUpstream(entry.upstream.id)?.name || entry.upstream.id;
    flash(t("flashTestingWorkspaceProgress", {
      platform: platformText(entry.protocol),
      index: index + 1,
      total: entries.length,
      name,
    }));
    try {
      const result = await getJson("/api/test", {
        method: "POST",
        body: JSON.stringify(buildProbePayload(entry.upstream.id)),
      });
      recordLocalProbeSuccess(entry.upstream.id, result.result);
      success += 1;
    } catch (error) {
      recordLocalProbeFailure(entry.upstream.id, error.message);
      failed += 1;
    }
    if (entry.protocol === currentProtocol()) {
      renderUpstreams();
    } else {
      renderProtocolTabs();
    }
  }
  await refreshStatus();
  flash(t("flashTestingWorkspaceAllDone", { success, failed }), failed > 0 ? "bad" : "ok");
}

function reorderUpstreams(fromId, toId) {
  if (!fromId || !toId || fromId === toId) {
    return;
  }
  const protocol = currentProtocol();
  const upstreams = [...state.config.upstreams];
  const visible = upstreams.filter((item) => normalizeUpstreamProtocol(item.protocol) === protocol);
  const fromIndex = visible.findIndex((item) => item.id === fromId);
  const toIndex = visible.findIndex((item) => item.id === toId);
  if (fromIndex === -1 || toIndex === -1) {
    return;
  }
  const [moved] = visible.splice(fromIndex, 1);
  visible.splice(toIndex, 0, moved);
  let visibleIndex = 0;
  state.config.upstreams = upstreams.map((item) => (
    normalizeUpstreamProtocol(item.protocol) === protocol ? visible[visibleIndex++] : item
  ));
  renderProtocolWorkspace();
  noteConfigMutation({ autosave: true, immediate: true });
}

function addUpstream() {
  const protocol = currentProtocol();
  const protocolCount = protocolConfigUpstreams(protocol).length;
  const newUpstream = {
    id: crypto.randomUUID().replaceAll("-", "").slice(0, 12),
    name: `${currentLanguage() === "zh" ? "上游" : "Upstream"} ${protocolCount + 1}`,
    protocol,
    base_url: "",
    api_key: "",
    enabled: true,
    notes: "",
    default_model: "",
    extra_headers: {},
    subscriptions: [defaultSubscription(0)],
  };
  state.config.upstreams.push(newUpstream);
  state.editorDrafts[newUpstream.id] = cloneDeep(newUpstream);
  state.expandedUpstreamIds.add(newUpstream.id);
  ensureManualActiveStillValid();
  renderProtocolWorkspace();
  noteConfigMutation({ autosave: true, immediate: true });
}

function removeUpstream(id) {
  const upstream = getRenderedUpstream(id);
  if (!window.confirm(t("confirmDeleteUpstream", { name: upstream?.name || id }))) {
    return;
  }
  state.config.upstreams = state.config.upstreams.filter((item) => item.id !== id);
  delete state.editorDrafts[id];
  delete state.localProbeResults[id];
  state.expandedUpstreamIds.delete(id);
  ensureManualActiveStillValid();
  renderProtocolWorkspace();
  noteConfigMutation({ autosave: true, immediate: true });
}

function addSubscription(upstreamId) {
  const upstream = getRenderedUpstream(upstreamId);
  if (!upstream) {
    return;
  }
  const draft = ensureEditorDraft(upstreamId);
  draft.subscriptions = normalizeUpstreamSubscriptions(draft);
  draft.subscriptions.push(defaultSubscription(draft.subscriptions.length, draft.name || upstream.name || ""));
  renderUpstreams();
  noteConfigMutation();
}

function removeSubscription(upstreamId, subscriptionId) {
  const draft = ensureEditorDraft(upstreamId);
  if (!draft) {
    return;
  }
  const subscriptions = normalizeUpstreamSubscriptions(draft);
  if (subscriptions.length <= 1) {
    flash(t("flashSubscriptionKeepOne"), "bad");
    return;
  }
  const nextSubscriptions = subscriptions.filter((item) => item.id !== subscriptionId);
  if (nextSubscriptions.length === subscriptions.length) {
    return;
  }
  const current = subscriptions.find((item) => item.id === subscriptionId);
  if (!window.confirm(t("confirmDeleteSubscription", { name: current?.name || subscriptionId }))) {
    return;
  }
  draft.subscriptions = nextSubscriptions;
  renderUpstreams();
  noteConfigMutation();
}

function openEditor(id) {
  ensureEditorDraft(id);
  state.expandedUpstreamIds.add(id);
  renderUpstreams();
}

function collapseEditor(id) {
  state.expandedUpstreamIds.delete(id);
  renderUpstreams();
}

function saveEditorDraft(id) {
  if (!state.editorDrafts[id]) {
    collapseEditor(id);
    return;
  }
  state.config.upstreams = state.config.upstreams.map((item) => (item.id === id ? cloneDeep(state.editorDrafts[id]) : item));
  delete state.editorDrafts[id];
  collapseEditor(id);
  ensureManualActiveStillValid();
  renderProtocolWorkspace();
  noteConfigMutation({ autosave: true, immediate: true });
  flash(t("flashEditorSaved"));
}

function cancelEditorDraft(id) {
  delete state.editorDrafts[id];
  collapseEditor(id);
  renderUpstreams();
  noteConfigMutation();
  flash(t("flashEditorCanceled"));
}

async function reactivateUpstream(id) {
  try {
    const response = await getJson("/api/upstream/control", {
      method: "POST",
      body: JSON.stringify({ id, action: "reactivate" }),
    });
    state.status = response.status;
    flash(t("flashUpstreamReactivated"));
    renderUpstreams();
  } catch (error) {
    flash(error.message, "bad");
  }
}

async function toggleUpstreamEnabled(id) {
  const upstream = getRenderedUpstream(id);
  if (!upstream) {
    return;
  }
  const status = statusMap().get(id);
  if (status?.subscription_manual_enable_required || status?.subscription_state === "quota_exhausted") {
    await reactivateUpstream(id);
    return;
  }
  const nextEnabled = !upstream.enabled;
  state.config.upstreams = state.config.upstreams.map((item) => (
    item.id === id ? { ...item, enabled: nextEnabled } : item
  ));
  if (state.editorDrafts[id]) {
    state.editorDrafts[id] = {
      ...cloneDeep(state.editorDrafts[id]),
      enabled: nextEnabled,
    };
  }
  refreshUpstreamDraftPreview();
  noteConfigMutation({ autosave: true, immediate: true, silentDirty: true });
}

function syncEditorField(control) {
  const card = control.closest(".upstream-card");
  if (!card) {
    return;
  }
  const upstreamId = card.dataset.upstreamId;
  const draft = buildDraftFromEditor(card);
  if (!draft) {
    return;
  }
  state.editorDrafts[upstreamId] = draft;
  if (
    control.dataset.subscriptionField === "kind"
    || control.dataset.subscriptionField === "permanent"
    || control.dataset.subscriptionField === "expires_at"
  ) {
    renderUpstreams();
  }
  refreshUpstreamDraftPreview();
  noteConfigMutation();
}

function parseExtraHeaders(raw) {
  const headers = {};
  raw
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .forEach((line) => {
      const index = line.indexOf(":");
      if (index === -1) {
        return;
      }
      const key = line.slice(0, index).trim();
      const value = line.slice(index + 1).trim();
      if (key) {
        headers[key] = value;
      }
    });
  return headers;
}

function extraHeadersToText(headers) {
  return Object.entries(headers || {})
    .map(([key, value]) => `${key}: ${value}`)
    .join("\n");
}
