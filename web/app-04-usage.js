async function refreshUsage(options = {}) {
  if (!state.config) {
    return;
  }
  try {
    state.usage = await getJson(`/api/usage?range=${state.usageRange}`);
    state.lastUsageRefreshAt = Date.now();
    renderUsage();
  } catch (error) {
    if (!options.silent) {
      flash(t("flashRefreshFailed", { message: error.message }), "bad");
    }
  }
}

function renderUsageFilters() {
  const container = document.getElementById("usageFilters");
  container.innerHTML = USAGE_RANGES
    .map((rangeKey) => {
      const labelKey = rangeKey === "minute" ? "rangeMinute" : rangeKey === "hour" ? "rangeHour" : rangeKey === "day" ? "rangeDay" : "rangeWeek";
      return `<button class="filter-chip ${state.usageRange === rangeKey ? "active" : ""}" type="button" data-range="${rangeKey}">${escapeHtml(t(labelKey))}</button>`;
    })
    .join("");
}

function renderUsageScopeFilters() {
  const container = document.getElementById("usageScopeFilters");
  if (!container) {
    return;
  }
  container.innerHTML = [
    `<button class="filter-chip ${usageScopeKey() === "all" ? "active" : ""}" type="button" data-usage-scope="all">${escapeHtml(t("usageScopeAll"))}</button>`,
    ...PROTOCOL_ORDER.map((protocol) =>
      `<button class="filter-chip ${usageScopeKey() === protocol ? "active" : ""}" type="button" data-usage-scope="${escapeHtml(protocol)}">${protocolLabelMarkup(protocol, platformText(protocol), true)}</button>`
    ),
  ].join("");
}

function usageActiveLocalKeyIds() {
  const visibleUpstreamIds = usageVisibleUpstreamIds();
  return new Set(
    (state.usage?.buckets || []).flatMap((bucket) => {
      const rawPairs = Array.isArray(bucket.pairs)
        ? bucket.pairs
        : Object.entries(bucket.by_upstream || {}).map(([upstream_id, count]) => ({ upstream_id, local_key_id: "", count }));
      return rawPairs
        .filter((pair) => visibleUpstreamIds.has(pair.upstream_id))
        .map((pair) => String(pair.local_key_id || ""));
    }),
  );
}

function usageLocalKeyMenuOptions(activePairLocalKeys = usageActiveLocalKeyIds()) {
  const items = [{ id: "all", name: t("usageLocalKeyAll") }];
  const keyedOptions = usageLocalKeyOptions().filter((item) => activePairLocalKeys.size === 0 || activePairLocalKeys.has(item.id));
  items.push(...keyedOptions.map((item) => ({ id: String(item.id || ""), name: String(item.name || item.id || "") })));
  if (activePairLocalKeys.has("")) {
    items.push({ id: "", name: t("usageLocalKeyDirect") });
  }
  return items;
}

function usageLocalKeyFilteredOptions(activePairLocalKeys = usageActiveLocalKeyIds()) {
  const query = String(state.usageLocalKeyMenuOpen ? state.usageLocalKeyQuery || "" : "").trim().toLowerCase();
  const items = usageLocalKeyMenuOptions(activePairLocalKeys);
  if (!query) {
    return items;
  }
  return items.filter((item) => {
    const name = String(item.name || "").toLowerCase();
    const id = String(item.id || "").toLowerCase();
    return name.includes(query) || id.includes(query);
  });
}

function renderUsageLocalKeyInput() {
  const input = document.getElementById("usageLocalKeyInput");
  const toggle = document.getElementById("usageLocalKeyToggle");
  const menu = document.getElementById("usageLocalKeyMenu");
  if (!input || !toggle || !menu) {
    return;
  }
  const activePairLocalKeys = usageActiveLocalKeyIds();
  const filteredOptions = usageLocalKeyFilteredOptions(activePairLocalKeys);
  const selectedKey = usageLocalKeyKey();
  const displayValue = usageLocalKeyDisplayValue();
  input.value = state.usageLocalKeyMenuOpen
    ? (String(state.usageLocalKeyQuery || "").length ? String(state.usageLocalKeyQuery || "") : displayValue)
    : displayValue;
  toggle.innerHTML = iconMarkup("chevronUp", "icon icon-sm usage-key-toggle-icon");
  toggle.setAttribute("aria-expanded", state.usageLocalKeyMenuOpen ? "true" : "false");
  toggle.classList.toggle("active", Boolean(state.usageLocalKeyMenuOpen));
  menu.hidden = !state.usageLocalKeyMenuOpen;
  if (!state.usageLocalKeyMenuOpen) {
    menu.innerHTML = "";
    return;
  }
  if (!filteredOptions.length) {
    menu.innerHTML = `<div class="usage-key-option empty">${escapeHtml(t("usageLocalKeyNoMatch"))}</div>`;
    return;
  }
  menu.innerHTML = filteredOptions
    .map((item) => {
      const selected = item.id === selectedKey;
      const idLabel = item.id && item.id !== "all" && item.id !== item.name ? `<span class="usage-key-option-id">${escapeHtml(item.id)}</span>` : "";
      return `
        <button
          class="usage-key-option ${selected ? "selected" : ""}"
          type="button"
          role="option"
          aria-selected="${selected ? "true" : "false"}"
          data-usage-local-key="${escapeHtml(item.id)}"
        >
          <span class="usage-key-option-text">${escapeHtml(item.name)}</span>
          ${idLabel}
        </button>
      `;
    })
    .join("");
}

function usagePrecisionSummary() {
  if (state.usageRange === "minute") {
    return t("usagePrecisionMinute");
  }
  if (state.usageRange === "hour") {
    return t("usagePrecisionHour");
  }
  if (state.usageRange === "day") {
    return t("usagePrecisionDay");
  }
  return t("usagePrecisionWeek");
}

function formatBucketLabel(startTs) {
  const date = new Date(startTs);
  const hour = String(date.getHours()).padStart(2, "0");
  const minute = String(date.getMinutes()).padStart(2, "0");
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  if (state.usageRange === "minute") {
    return t("chartBucketLabelMinute", { hour, minute });
  }
  if (state.usageRange === "hour") {
    return t("chartBucketLabelHour", { hour, minute });
  }
  if (state.usageRange === "day") {
    return t("chartBucketLabelDay", { month, day });
  }
  return t("chartBucketLabelWeek", { month, day });
}

function formatBucketDetailLabel(bucket) {
  const start = new Date(bucket.start_ts);
  const end = new Date(Math.max(bucket.end_ts - 1, bucket.start_ts));
  const startYear = String(start.getFullYear());
  const startMonth = String(start.getMonth() + 1).padStart(2, "0");
  const startDay = String(start.getDate()).padStart(2, "0");
  const startHour = String(start.getHours()).padStart(2, "0");
  const startMinute = String(start.getMinutes()).padStart(2, "0");
  const endYear = String(end.getFullYear());
  const endMonth = String(end.getMonth() + 1).padStart(2, "0");
  const endDay = String(end.getDate()).padStart(2, "0");
  if (state.usageRange === "minute") {
    return `${startYear}-${startMonth}-${startDay} ${startHour}:${startMinute}`;
  }
  if (state.usageRange === "hour") {
    return `${startYear}-${startMonth}-${startDay} ${startHour}:00`;
  }
  if (state.usageRange === "day") {
    return `${startYear}-${startMonth}-${startDay}`;
  }
  return `${startYear}-${startMonth}-${startDay} ~ ${endYear}-${endMonth}-${endDay}`;
}

function usageColorForGroup(groupId) {
  const orderedIds = (state.config?.upstreams || []).map((item) => item.id);
  const directIndex = orderedIds.indexOf(groupId);
  if (directIndex !== -1) {
    return UPSTREAM_COLORS[directIndex % UPSTREAM_COLORS.length];
  }
  let hash = 0;
  for (const character of String(groupId || "")) {
    hash = ((hash * 33) + character.charCodeAt(0)) >>> 0;
  }
  return UPSTREAM_COLORS[hash % UPSTREAM_COLORS.length];
}

function usageGroupName(groupId) {
  return getRenderedUpstream(groupId)?.name || groupId;
}

function usageVisibleUpstreamIds() {
  const scopeProtocol = usageScopeProtocol();
  return new Set(
    (state.config?.upstreams || [])
      .filter((item) => !scopeProtocol || normalizeUpstreamProtocol(item.protocol) === scopeProtocol)
      .map((item) => item.id),
  );
}

function usagePairsForScope(bucket, visibleUpstreamIds) {
  const rawPairs = Array.isArray(bucket.pairs)
    ? bucket.pairs
    : Object.entries(bucket.by_upstream || {}).map(([upstream_id, count]) => ({ upstream_id, local_key_id: "", count }));
  const selectedLocalKey = usageLocalKeyKey();
  return rawPairs.filter((pair) => {
    if (!visibleUpstreamIds.has(pair.upstream_id)) {
      return false;
    }
    if (selectedLocalKey === "all") {
      return true;
    }
    return String(pair.local_key_id || "") === selectedLocalKey;
  });
}

function aggregateUsageBucket(bucket, visibleUpstreamIds) {
  const grouped = {};
  let total = 0;
  for (const pair of usagePairsForScope(bucket, visibleUpstreamIds)) {
    const groupId = String(pair.upstream_id || "");
    const count = Number(pair.count || 0);
    if (count <= 0) {
      continue;
    }
    grouped[groupId] = (grouped[groupId] || 0) + count;
    total += count;
  }
  return { ...bucket, grouped, total };
}

function usageLegendItems(visibleUpstreamIds, filteredBuckets) {
  const activeIds = new Set(filteredBuckets.flatMap((bucket) => Object.keys(bucket.grouped || {})));
  const visibleUpstreams = (state.config?.upstreams || []).filter((item) => visibleUpstreamIds.has(item.id));
  const activeUpstreams = visibleUpstreams.filter((item) => activeIds.has(item.id));
  const sourceItems = activeUpstreams.length ? activeUpstreams : visibleUpstreams;
  return sourceItems.map((item) => ({
    id: item.id,
    name: getRenderedUpstream(item.id)?.name || item.name || item.id,
  }));
}

function renderUsageHoverDetail() {
  const detail = document.getElementById("usageHoverDetail");
  const chart = document.getElementById("usageChart");
  chart.querySelectorAll(".chart-bar-wrap").forEach((node, index) => {
    node.classList.toggle("active", index === state.hoveredUsageBucketIndex);
  });
  const bucket = state.renderedUsageBuckets[state.hoveredUsageBucketIndex];
  if (!bucket) {
    detail.innerHTML = `<span class="usage-hover-empty">${escapeHtml(t("usageHoverDefault"))}</span>`;
    return;
  }
  const tokens = Object.entries(bucket.grouped || {})
    .sort((left, right) => Number(right[1]) - Number(left[1]))
    .map(([groupId, count]) => {
      const color = usageColorForGroup(groupId);
      return `
        <span class="usage-hover-token group">
          <span class="usage-hover-swatch" style="background:${color}"></span>
          <span class="usage-hover-key">${escapeHtml(usageGroupName(groupId))}</span>
          <span class="usage-hover-value" style="color:${color}">${escapeHtml(count)}</span>
        </span>
      `;
    });
  detail.innerHTML = [
    `
      <span class="usage-hover-token period">
        <span class="usage-hover-key">${escapeHtml(t("usageHoverPeriodLabel"))}</span>
        <span class="usage-hover-value">${escapeHtml(formatBucketDetailLabel(bucket))}</span>
      </span>
    `,
    `
      <span class="usage-hover-token total">
        <span class="usage-hover-key">${escapeHtml(t("usageHoverTotalLabel"))}</span>
        <span class="usage-hover-value">${escapeHtml(bucket.total)}</span>
      </span>
    `,
    ...tokens,
  ].join("");
}

function usageAutoScrollSignature(filteredBuckets) {
  const lastBucket = filteredBuckets[filteredBuckets.length - 1];
  return [
    usageScopeKey(),
    usageScopeProtocol() || "all",
    usageLocalKeyKey(),
    state.usageRange,
    filteredBuckets.length,
    lastBucket?.start_ts || 0,
    lastBucket?.end_ts || 0,
  ].join(":");
}

function ensureUsageChartShowsLatest(filteredBuckets) {
  const chart = document.getElementById("usageChart");
  const signature = usageAutoScrollSignature(filteredBuckets);
  if (state.usageAutoScrollKey === signature) {
    return;
  }
  state.usageAutoScrollKey = signature;
  requestAnimationFrame(() => {
    chart.scrollLeft = chart.scrollWidth;
  });
}

function renderUsage() {
  const renderSignature = signatureOf({
    language: currentLanguage(),
    range: state.usageRange,
    scope: usageScopeKey(),
    localKey: usageLocalKeyKey(),
    usage: state.usage,
    upstreamNames: (state.config?.upstreams || []).map((item) => ({
      id: item.id,
      name: getRenderedUpstream(item.id)?.name || item.name || "",
      protocol: normalizeUpstreamProtocol(item.protocol),
    })),
  });
  if (renderSignature === state.usageRenderSignature) {
    renderUsageHoverDetail();
    return;
  }
  state.usageRenderSignature = renderSignature;
  renderUsageScopeFilters();
  renderUsageLocalKeyInput();
  renderUsageFilters();

  const chart = document.getElementById("usageChart");
  const legend = document.getElementById("usageLegend");
  const axisMax = document.getElementById("usageAxisMax");
  const axisTitle = document.getElementById("usageAxisTitle");
  const axisNote = document.getElementById("usageAxisTitleNote");

  axisTitle.textContent = state.usage?.metric === "requests" ? t("usageAxisRequests") : (state.usage?.metric || t("usageAxisRequests"));
  axisNote.textContent = usagePrecisionSummary();

  const visibleUpstreamIds = usageVisibleUpstreamIds();
  const filteredBuckets = (state.usage?.buckets || [])
    .map((bucket) => aggregateUsageBucket(bucket, visibleUpstreamIds))
    .filter((bucket) => bucket.total > 0);
  state.renderedUsageBuckets = filteredBuckets;

  const maxTotal = filteredBuckets.reduce((max, bucket) => Math.max(max, bucket.total), 0);
  axisMax.textContent = String(maxTotal);
  if (!state.usage || !filteredBuckets.length || maxTotal === 0) {
    chart.innerHTML = `<div class="empty">${escapeHtml(t("usageEmpty"))}</div>`;
    legend.innerHTML = "";
    state.usageAutoScrollKey = "";
    state.hoveredUsageBucketIndex = -1;
    renderUsageHoverDetail();
    return;
  }

  chart.innerHTML = filteredBuckets
    .map((bucket, index) => {
      const totalHeight = maxTotal > 0 ? (bucket.total / maxTotal) * 100 : 0;
      const groups = Object.entries(bucket.grouped || {}).sort((left, right) => Number(right[1]) - Number(left[1]));
      const segments = groups
        .map(([groupId, count]) => {
          const height = bucket.total > 0 ? (count / bucket.total) * 100 : 0;
          const name = usageGroupName(groupId);
          return `<div class="chart-segment" style="height:${height}%; background:${usageColorForGroup(groupId)}" title="${escapeHtml(name)}: ${count}"></div>`;
        })
        .join("");
      const tooltipLines = groups
        .map(([groupId, count]) => t("chartTooltipLine", { name: usageGroupName(groupId), count }))
        .join(" | ");
      const tooltip = `${formatBucketDetailLabel(bucket)} | ${t("chartTooltipTotal", { total: bucket.total })}${tooltipLines ? ` | ${tooltipLines}` : ""}`;
      return `
        <div class="chart-bar-wrap ${index === state.hoveredUsageBucketIndex ? "active" : ""}" title="${escapeHtml(tooltip)}" data-bucket-index="${index}">
          <div class="chart-bar-frame">
            <div class="chart-stack" style="height:${Math.max(totalHeight, 2)}%">
              ${segments}
            </div>
          </div>
          <div class="chart-label">${escapeHtml(formatBucketLabel(bucket.start_ts))}</div>
        </div>
      `;
    })
    .join("");

  const legendItems = usageLegendItems(visibleUpstreamIds, filteredBuckets);
  legend.innerHTML = legendItems
    .map((item) => `
      <div class="legend-item">
        <span class="legend-swatch" style="background:${usageColorForGroup(item.id)}"></span>
        <span>${escapeHtml(item.name || item.id)}</span>
      </div>
    `)
    .join("");

  if (state.hoveredUsageBucketIndex >= filteredBuckets.length) {
    state.hoveredUsageBucketIndex = filteredBuckets.length - 1;
  }
  ensureUsageChartShowsLatest(filteredBuckets);
  renderUsageHoverDetail();
}
