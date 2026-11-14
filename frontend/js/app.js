/* TollRail402 Frontend Application Controller */
(function () {
  const API = window.TollRailAPI;
  const Charts = window.TollRailCharts;

  const PAGE_TITLES = {
    overview: "Dashboard",
    demo: "Live 402 Demo",
    agents: "Agent Management",
    marketplace: "API Marketplace",
    activity: "Payment Activity",
    channels: "Payment Channels",
    policies: "Spending Policies",
    explorer: "Transaction Explorer",
    audit: "Audit Logs",
    docs: "Documentation",
    settings: "Settings",
  };

  const state = {
    currentPage: "overview",
    overviewDays: 7,
    agents: [],
    services: [],
    channels: [],
    settings: null,
    lastDemoResult: null,
    demoPreselectServiceId: null,
    openCreateAgentOnLoad: false,
  };

  function esc(val) {
    if (val === null || val === undefined) return "";
    return String(val)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function fmtUsdc(val) {
    return `$${Number(val || 0).toFixed(4)}`;
  }

  function fmtUsdcExact(val) {
    return `$${Number(val || 0).toFixed(6)}`;
  }

  function fmtUsdcCard(val) {
    const n = Number(val || 0);
    return n >= 1 ? `$${n.toFixed(2)}` : `$${n.toFixed(4)}`;
  }

  function shortAddr(addr) {
    if (!addr || addr.length < 14) return esc(addr || "");
    return `${esc(addr.slice(0, 4))}...${esc(addr.slice(-4))}`;
  }

  function fmtTime(iso) {
    if (!iso) return "-";
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? esc(iso) : d.toLocaleString();
  }

  function fmtRelative(iso) {
    if (!iso) return "-";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return esc(iso);
    const diffSec = Math.max(0, Math.floor((Date.now() - d.getTime()) / 1000));
    if (diffSec < 60) return `${diffSec}s ago`;
    if (diffSec < 3600) return `${Math.floor(diffSec / 60)} min ago`;
    if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
    return `${Math.floor(diffSec / 86400)}d ago`;
  }

  function toast(msg, type = "default") {
    const region = document.getElementById("toast-region");
    const el = document.createElement("div");
    el.className = `toast ${type === "error" ? "toast-error" : type === "success" ? "toast-success" : ""}`;
    el.textContent = msg;
    region.appendChild(el);
    setTimeout(() => el.remove(), 4200);
  }

  function openDrawer(title, htmlContent) {
    document.getElementById("drawer-title").textContent = title;
    document.getElementById("drawer-body").innerHTML = htmlContent;
    document.getElementById("drawer-backdrop").classList.remove("hidden");
    document.getElementById("detail-drawer").classList.remove("hidden");
  }

  function closeDrawer() {
    document.getElementById("drawer-backdrop").classList.add("hidden");
    document.getElementById("detail-drawer").classList.add("hidden");
  }

  async function refreshGlobalChrome() {
    try {
      const cfg = await API.getSettings();
      state.settings = cfg;
      const connected = cfg.algorand_node_status && cfg.algorand_node_status.connected;
      const isTestnet = cfg.tollrail_mode === "algorand_testnet";

      document.getElementById("topbar-mode-label").textContent = isTestnet ? "TestNet" : "Local Demo";
      document.getElementById("topbar-wallet-short").textContent = shortAddr(cfg.merchant_algorand_address);

      const dot = document.getElementById("sidebar-net-dot");
      const netState = document.getElementById("sidebar-net-state");
      if (connected) {
        dot.classList.remove("offline");
        netState.textContent = `Connected · #${cfg.algorand_node_status.last_round}`;
        netState.style.color = "#34d399";
      } else {
        dot.classList.add("offline");
        netState.textContent = "Offline";
        netState.style.color = "#fbbf24";
      }
    } catch (_) {
      document.getElementById("sidebar-net-state").textContent = "Disconnected";
    }
  }

  function navigate(page) {
    if (!PAGE_TITLES[page]) page = "overview";
    state.currentPage = page;
    window.location.hash = page;
    document.querySelectorAll(".nav-item").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.page === page);
    });
    document.getElementById("sidebar").classList.remove("open");
    renderCurrentPage();
  }

  async function renderCurrentPage() {
    const container = document.getElementById("page-content");
    container.innerHTML = `<div class="loading-state">Loading ${esc(PAGE_TITLES[state.currentPage])}...</div>`;
    try {
      await refreshGlobalChrome();
      switch (state.currentPage) {
        case "overview":
          await renderOverview(container);
          break;
        case "demo":
          await renderDemoPage(container);
          break;
        case "agents":
          await renderAgentsPage(container);
          break;
        case "marketplace":
          await renderMarketplacePage(container);
          break;
        case "activity":
          await renderActivityPage(container);
          break;
        case "channels":
          await renderChannelsPage(container);
          break;
        case "policies":
          await renderPoliciesPage(container);
          break;
        case "explorer":
          await renderExplorerPage(container);
          break;
        case "audit":
          await renderAuditPage(container);
          break;
        case "docs":
          renderDocsPage(container);
          break;
        case "settings":
          await renderSettingsPage(container);
          break;
      }
    } catch (err) {
      container.innerHTML = `<div class="notice notice-warning"><strong>Failed to load view:</strong> ${esc(err.message)}</div>`;
    }
  }

  /* ================= 1. OVERVIEW DASHBOARD ================= */
  async function renderOverview(el) {
    const data = await API.getOverview(state.overviewDays);
    const isTestnet = data.execution_mode === "algorand_testnet";

    const exactCount = data.exact_vs_channel.exact_count || 0;
    const channelCount = data.exact_vs_channel.channel_count || 0;
    const totalSettledCount = exactCount + channelCount;
    const exactPct = totalSettledCount > 0 ? Math.round((exactCount / totalSettledCount) * 100) : 100;
    const channelPct = totalSettledCount > 0 ? 100 - exactPct : 0;

    const maxAgentSpend = Math.max(...(data.top_agents || []).map((a) => a.total_spent_usdc), 0.001);

    el.innerHTML = `
      <div class="welcome-row">
        <div>
          <h1 class="welcome-title">Welcome back, Developer!</h1>
          <p class="welcome-sub">Your agentic payment platform is running in ${isTestnet ? "Algorand TestNet" : "Local Demo"} mode (${esc(data.avg_verification_time_ms.toFixed(1))} ms avg verify).</p>
        </div>

        <div class="operational-pill">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true">
            <circle cx="12" cy="12" r="10" fill="#009e5c" stroke="#009e5c"/>
            <path d="M8.5 12.5l2.3 2.3 4.8-5" stroke="#ffffff" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          <span>${data.algorand_connected ? "All systems operational" : "Local engine active (TestNet offline)"}</span>
        </div>

        <div>
          <select id="ov-days-select" class="timeframe-select" aria-label="Timeframe filter">
            <option value="1" ${state.overviewDays === 1 ? "selected" : ""}>Last 24 hours</option>
            <option value="7" ${state.overviewDays === 7 ? "selected" : ""}>Last 7 days</option>
            <option value="0" ${state.overviewDays === 0 ? "selected" : ""}>All time</option>
          </select>
        </div>
      </div>

      <!-- 6-Column KPI Strip -->
      <div class="kpi-grid-6">
        <div class="kpi-card">
          <div class="kpi-icon-badge icon-green">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M7 16l-4-4 4-4M17 8l4 4-4 4M3 12h18" stroke-linecap="round" stroke-linejoin="round"/></svg>
          </div>
          <div class="kpi-value">${esc(data.total_requests.toLocaleString())}</div>
          <div class="kpi-footer">
            <span class="kpi-label">API Requests</span>
            <span class="kpi-delta delta-up">402 gated</span>
          </div>
        </div>

        <div class="kpi-card">
          <div class="kpi-icon-badge icon-green">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M20 6L9 17l-5-5" stroke-linecap="round" stroke-linejoin="round"/></svg>
          </div>
          <div class="kpi-value">${esc(data.successful_paid_requests.toLocaleString())}</div>
          <div class="kpi-footer">
            <span class="kpi-label">Successful Payments</span>
            <span class="kpi-delta delta-up">Settled</span>
          </div>
        </div>

        <div class="kpi-card">
          <div class="kpi-icon-badge icon-red">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><circle cx="12" cy="12" r="9"/><path d="M12 8v4M12 16h.01" stroke-linecap="round"/></svg>
          </div>
          <div class="kpi-value">${esc(data.failed_payment_attempts.toLocaleString())}</div>
          <div class="kpi-footer">
            <span class="kpi-label">Failed Attempts</span>
            <span class="kpi-delta delta-down">Blocked</span>
          </div>
        </div>

        <div class="kpi-card">
          <div class="kpi-icon-badge icon-green">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v20M17 6.5c0-1.9-2.2-3.5-5-3.5s-5 1.6-5 3.5 2.2 3.5 5 3.5 5 1.6 5 3.5-2.2 3.5-5 3.5-5-1.6-5-3.5" stroke-linecap="round"/></svg>
          </div>
          <div class="kpi-value">${fmtUsdcCard(data.total_usdc_spent)}</div>
          <div class="kpi-footer">
            <span class="kpi-label">Total USDC Spent</span>
            <span class="kpi-delta delta-up">ASA ${esc(data.usdc_asset_id)}</span>
          </div>
        </div>

        <div class="kpi-card">
          <div class="kpi-icon-badge icon-blue">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="4" y="7" width="16" height="12" rx="3"/><path d="M12 3v4M9 12h.01M15 12h.01M9 16h6" stroke-linecap="round"/></svg>
          </div>
          <div class="kpi-value">${esc(data.active_agents)}</div>
          <div class="kpi-footer">
            <span class="kpi-label">Active Agents</span>
            <span class="kpi-delta" style="color:var(--text-muted);">of ${esc(data.total_agents)}</span>
          </div>
        </div>

        <div class="kpi-card">
          <div class="kpi-icon-badge icon-green">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 10h18"/></svg>
          </div>
          <div class="kpi-value">${esc(data.active_channels)}</div>
          <div class="kpi-footer">
            <span class="kpi-label">Payment Channels</span>
            <span class="kpi-delta delta-up">${esc(data.channel_vouchers_count)} vouchers</span>
          </div>
        </div>
      </div>

      <!-- Row 2: Activity Chart + Payment Methods + Cost Breakdown -->
      <div class="dash-mid-grid">
        <div class="panel">
          <div class="panel-header">
            <div class="panel-title-wrap">
              <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#009e5c" stroke-width="2.2"><path d="M4 20V10M10 20V4M16 20v-7M22 20v-4" stroke-linecap="round"/></svg>
              <h2 class="panel-title">Payment Activity Overview</h2>
            </div>
            <div style="display:flex;align-items:center;gap:14px;font-size:12px;color:var(--text-secondary);">
              <span style="display:inline-flex;align-items:center;gap:5px;"><span class="legend-dot" style="margin:0;background:#009e5c;"></span>Successful</span>
              <span style="display:inline-flex;align-items:center;gap:5px;"><span class="legend-dot" style="margin:0;background:#f59e0b;"></span>Failed</span>
            </div>
          </div>
          <div class="chart-wrap"><canvas id="chart-activity"></canvas></div>
        </div>

        <div class="panel">
          <div class="panel-header">
            <h2 class="panel-title">Payment Methods</h2>
          </div>
          <div class="doughnut-layout">
            <div class="doughnut-box">
              <canvas id="chart-modes"></canvas>
              <div class="doughnut-center">
                <div class="doughnut-pct">${exactPct}%</div>
                <div class="doughnut-sub">Exact Mode</div>
              </div>
            </div>
            <div class="legend-stack">
              <div class="legend-item">
                <span class="legend-dot" style="background:#009e5c;"></span>
                <div>
                  <div style="font-weight:700;">Exact Mode</div>
                  <div class="mono" style="font-size:12.5px;color:var(--text-secondary);">${exactPct}% (${esc(exactCount)})</div>
                </div>
              </div>
              <div class="legend-item">
                <span class="legend-dot" style="background:#f59e0b;"></span>
                <div>
                  <div style="font-weight:700;">Channel Mode</div>
                  <div class="mono" style="font-size:12.5px;color:var(--text-secondary);">${channelPct}% (${esc(channelCount)})</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="panel-mint">
          <div>
            <div class="panel-header" style="margin-bottom:10px;">
              <div class="panel-title-wrap">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#009e5c" stroke-width="2"><path d="M12 2v20M17 6.5c0-1.9-2.2-3.5-5-3.5s-5 1.6-5 3.5 2.2 3.5 5 3.5 5 1.6 5 3.5-2.2 3.5-5 3.5-5-1.6-5-3.5" stroke-linecap="round"/></svg>
                <h2 class="panel-title">Cost Breakdown</h2>
              </div>
            </div>
            <div class="cost-hero tabular">${fmtUsdcExact(data.total_usdc_spent)}</div>
            <div class="cost-sub">Total Spent</div>

            <div class="cost-lines">
              <div class="cost-line">
                <span style="display:inline-flex;align-items:center;gap:7px;"><span class="legend-dot" style="margin:0;background:#009e5c;"></span>Exact Payments</span>
                <span class="mono" style="font-weight:700;">${fmtUsdcExact(data.exact_vs_channel.exact_usdc)}</span>
              </div>
              <div class="cost-line">
                <span style="display:inline-flex;align-items:center;gap:7px;"><span class="legend-dot" style="margin:0;background:#f59e0b;"></span>Channel Payments</span>
                <span class="mono" style="font-weight:700;">${fmtUsdcExact(data.exact_vs_channel.channel_usdc)}</span>
              </div>
            </div>
          </div>

          <div class="cost-savings-box">
            <span>${data.channel_vouchers_count} off-chain voucher${data.channel_vouchers_count === 1 ? "" : "s"} batched via payment channels</span>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#009e5c" stroke-width="2.2"><path d="M3 17l6-6 4 4 8-8M17 7h4v4" stroke-linecap="round" stroke-linejoin="round"/></svg>
          </div>
        </div>
      </div>

      <!-- Row 3: Recent Transactions + Top Agents + Quick Actions -->
      <div class="dash-bot-grid">
        <div class="panel">
          <div class="panel-header">
            <h2 class="panel-title">Recent Transactions</h2>
            <button class="link-btn" id="ov-all-tx-btn">View All →</button>
          </div>
          ${renderTransactionsMiniTable(data.recent_transactions)}
        </div>

        <div class="panel">
          <div class="panel-header">
            <h2 class="panel-title">Top Agents by Spending</h2>
            <button class="link-btn" id="ov-all-agents-btn">View All →</button>
          </div>
          ${data.top_agents && data.top_agents.length ? `
            <div class="agent-rank-list">
              ${data.top_agents.slice(0, 4).map((ag, idx) => {
                const widthPct = Math.max(8, Math.round((ag.total_spent_usdc / maxAgentSpend) * 100));
                return `
                  <div class="agent-rank-item">
                    <div class="agent-avatar av-${idx % 4}">${esc(ag.initials)}</div>
                    <div class="agent-rank-mid">
                      <div style="display:flex;justify-content:space-between;gap:8px;align-items:baseline;">
                        <span class="agent-rank-name">${esc(ag.agent_name)}</span>
                        <span class="mono" style="font-size:12.5px;font-weight:700;">${fmtUsdcExact(ag.total_spent_usdc)}</span>
                      </div>
                      <div class="progress-track"><div class="progress-fill" style="width:${widthPct}%;"></div></div>
                    </div>
                  </div>
                `;
              }).join("")}
            </div>
          ` : `<div class="empty-state">No agent spending recorded yet.</div>`}
        </div>

        <div class="panel">
          <div class="panel-header">
            <h2 class="panel-title">Quick Actions</h2>
          </div>
          <div class="quick-actions-stack">
            <button id="ov-demo-btn" class="qa-primary" type="button">
              <div class="qa-primary-title">▶ Try API Demo</div>
              <div class="qa-primary-sub">See the HTTP 402 payment flow in action</div>
            </button>
            <button id="ov-new-agent-btn" class="qa-secondary" type="button">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M20 8v6M23 11h-6" stroke-linecap="round"/></svg>
              <span>Create New Agent</span>
            </button>
            <button id="ov-marketplace-btn" class="qa-secondary" type="button">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 9l2-5h14l2 5M3 9v11a1 1 0 0 0 1 1h16a1 1 0 0 0 1-1V9M3 9h18" stroke-linejoin="round"/></svg>
              <span>Explore API Marketplace</span>
            </button>
          </div>
        </div>
      </div>
    `;

    document.getElementById("ov-days-select").onchange = (e) => {
      state.overviewDays = Number(e.target.value);
      renderCurrentPage();
    };
    document.getElementById("ov-demo-btn").onclick = () => navigate("demo");
    document.getElementById("ov-all-tx-btn").onclick = () => navigate("explorer");
    document.getElementById("ov-all-agents-btn").onclick = () => navigate("agents");
    document.getElementById("ov-marketplace-btn").onclick = () => navigate("marketplace");
    document.getElementById("ov-new-agent-btn").onclick = () => {
      state.openCreateAgentOnLoad = true;
      navigate("agents");
    };

    el.querySelectorAll("[data-tx-detail]").forEach((row) => {
      row.onclick = () => showTransactionDrawer(row.dataset.txDetail);
    });

    Charts.renderActivityChart("chart-activity", data.activity_series);
    Charts.renderModeComparisonChart("chart-modes", data.exact_vs_channel);
  }

  function renderTransactionsMiniTable(txs) {
    if (!txs.length) return `<div class="empty-state">No payment transactions recorded yet.</div>`;
    return `
      <div class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Agent</th>
              <th>Amount</th>
              <th>Status</th>
              <th>Mode</th>
            </tr>
          </thead>
          <tbody>
            ${txs.slice(0, 5).map((t) => `
              <tr style="cursor:pointer;" data-tx-detail="${esc(t.id)}">
                <td style="font-size:12px;color:var(--text-secondary);white-space:nowrap;">${fmtRelative(t.created_at)}</td>
                <td style="font-weight:600;">${esc(t.agent_name || t.agent_id)}</td>
                <td class="mono">${fmtUsdc(t.amount_usdc)} USDC</td>
                <td><span class="status-badge ${t.verification_status === "verified" ? "badge-success" : "badge-error"}">${t.verification_status === "verified" ? "Success" : "Failed"}</span></td>
                <td style="text-transform:capitalize;">${esc(t.settlement_mode)}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    `;
  }

  /* ================= 2. LIVE 402 PROTOCOL DEMO ================= */
  async function renderDemoPage(el) {
    const [agents, services, channels] = await Promise.all([
      API.listAgents(),
      API.listServices(),
      API.listChannels(),
    ]);
    state.agents = agents;
    state.services = services;
    state.channels = channels;

    const defaultSvcId = state.demoPreselectServiceId || (services[0] && services[0].id) || "";
    state.demoPreselectServiceId = null;

    el.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-heading">Interactive HTTP 402 Protocol Demonstration</h1>
          <p class="page-subtitle">Execute a live autonomous agent request and inspect the HTTP 402 challenge, policy check, Ed25519 signature, settlement, and protected payload.</p>
        </div>
      </div>

      <div class="demo-layout">
        <div class="panel">
          <div class="panel-header">
            <h2 class="panel-title">Request Configuration</h2>
          </div>
          <div style="display:flex;flex-direction:column;gap:14px;">
            <div class="form-field">
              <label class="form-label" for="demo-agent-select">1. Autonomous Agent</label>
              <select id="demo-agent-select" class="select">
                ${agents.map((a) => `<option value="${esc(a.id)}">${esc(a.name)} (${fmtUsdc(a.local_balance_usdc)})</option>`).join("")}
              </select>
            </div>

            <div id="demo-agent-summary" style="background:var(--bg-subtle);padding:10px 12px;border-radius:8px;font-size:12.5px;"></div>

            <div class="form-field">
              <label class="form-label" for="demo-service-select">2. Paid API Service</label>
              <select id="demo-service-select" class="select">
                ${services.map((s) => `<option value="${esc(s.id)}" ${s.id === defaultSvcId ? "selected" : ""}>${esc(s.name)} — ${esc(s.method)} ${esc(s.endpoint)} (${fmtUsdc(s.price_usdc)})</option>`).join("")}
              </select>
            </div>

            <div class="form-field">
              <label class="form-label" for="demo-mode-select">3. Settlement Mode</label>
              <select id="demo-mode-select" class="select">
                <option value="exact">Exact Mode (1 tx per request)</option>
                <option value="channel">Channel Mode (cumulative Ed25519 voucher)</option>
              </select>
            </div>

            <div class="form-field hidden" id="demo-channel-wrap">
              <label class="form-label" for="demo-channel-select">Open Payment Channel</label>
              <select id="demo-channel-select" class="select"></select>
            </div>

            <div class="form-field">
              <label class="form-label" for="demo-payload-input">Request Payload (JSON)</label>
              <textarea id="demo-payload-input" class="textarea"></textarea>
            </div>

            <button id="demo-send-btn" class="btn btn-primary" style="width:100%;">Send API Request</button>
          </div>
        </div>

        <div id="demo-inspector-panel">
          ${state.lastDemoResult ? renderDemoTrace(state.lastDemoResult) : `
            <div class="panel">
              <div class="empty-state">
                Select an agent and paid API on the left, then click <strong>Send API Request</strong>.<br/><br/>
                Try running <strong>AI Text Generation API ($0.005)</strong> for an approved settlement, or select <strong>Image Processing API ($0.015)</strong> with the Research Agent ($0.01 limit) to verify policy rejection.
              </div>
            </div>
          `}
        </div>
      </div>
    `;

    const agentSelect = document.getElementById("demo-agent-select");
    const serviceSelect = document.getElementById("demo-service-select");
    const modeSelect = document.getElementById("demo-mode-select");
    const channelWrap = document.getElementById("demo-channel-wrap");
    const channelSelect = document.getElementById("demo-channel-select");
    const payloadInput = document.getElementById("demo-payload-input");

    function syncAgentAndMode() {
      const ag = state.agents.find((x) => x.id === agentSelect.value);
      if (!ag) return;
      document.getElementById("demo-agent-summary").innerHTML = `
        <div><strong>Wallet:</strong> <span class="mono">${shortAddr(ag.wallet_address)}</span></div>
        <div style="margin-top:4px;"><strong>Local Balance:</strong> ${fmtUsdc(ag.local_balance_usdc)} · <strong>Per-Req Cap:</strong> ${fmtUsdc(ag.per_request_limit_usdc)} · <strong>Daily Cap:</strong> ${fmtUsdc(ag.daily_limit_usdc)}</div>
        <div style="margin-top:4px;"><strong>Status:</strong> ${ag.is_active ? "Active" : "Deactivated"} · <strong>Default Mode:</strong> ${esc(ag.default_settlement_mode)}</div>
      `;
      modeSelect.value = ag.default_settlement_mode;
      syncChannels();
    }

    function syncChannels() {
      const isChannel = modeSelect.value === "channel";
      channelWrap.classList.toggle("hidden", !isChannel);
      const openChans = state.channels.filter((c) => c.agent_id === agentSelect.value && c.status === "open");
      if (openChans.length) {
        channelSelect.innerHTML = openChans.map((c) => `<option value="${esc(c.id)}">${esc(c.id)} (Remaining ${fmtUsdc(c.remaining_usdc)})</option>`).join("");
      } else {
        channelSelect.innerHTML = `<option value="">No open channel for this agent</option>`;
      }
    }

    function syncServicePayload() {
      const svc = state.services.find((s) => s.id === serviceSelect.value);
      if (svc) payloadInput.value = JSON.stringify(svc.sample_payload || {}, null, 2);
    }

    agentSelect.onchange = syncAgentAndMode;
    modeSelect.onchange = syncChannels;
    serviceSelect.onchange = syncServicePayload;
    syncAgentAndMode();
    syncServicePayload();

    document.getElementById("demo-send-btn").onclick = async () => {
      const btn = document.getElementById("demo-send-btn");
      let parsedPayload = {};
      try {
        parsedPayload = JSON.parse(payloadInput.value || "{}");
      } catch (e) {
        toast("Invalid JSON request payload", "error");
        return;
      }

      btn.disabled = true;
      btn.textContent = "Executing HTTP 402 Lifecycle...";
      try {
        const res = await API.runDemo({
          agent_id: agentSelect.value,
          service_id: serviceSelect.value,
          settlement_mode: modeSelect.value,
          channel_id: modeSelect.value === "channel" && channelSelect.value ? channelSelect.value : null,
          payload: parsedPayload,
        });
        state.lastDemoResult = res;
        state.agents = await API.listAgents();
        state.channels = await API.listChannels();
        syncAgentAndMode();
        document.getElementById("demo-inspector-panel").innerHTML = renderDemoTrace(res);
        toast(res.success ? "HTTP 402 payment settled & API delivered" : "Request blocked — inspect trace", res.success ? "success" : "error");
      } catch (err) {
        toast(err.message, "error");
      } finally {
        btn.disabled = false;
        btn.textContent = "Send API Request";
      }
    };
  }

  function renderDemoTrace(res) {
    return `
      <div class="panel" style="margin-bottom:16px;">
        <div class="panel-header">
          <div>
            <h2 class="panel-title">Protocol Execution Trace · <span class="mono">${esc(res.trace_id)}</span></h2>
            <div class="panel-meta">Mode: ${esc(res.settlement_mode)} · Environment: ${esc(res.execution_mode)} · Final HTTP Status: <span class="mono">${esc(res.final_http_status)}</span></div>
          </div>
          <span class="status-badge ${res.success ? "badge-success" : "badge-error"}">${res.success ? "200 OK · Settled" : `HTTP ${esc(res.final_http_status)} · Rejected`}</span>
        </div>

        <div class="step-list">
          ${res.steps.map((st) => `
            <div class="step-item">
              <div class="step-head">
                <div class="step-title">${esc(st.step)}. ${esc(st.title)}</div>
                <span class="status-badge ${st.status === "completed" ? "badge-success" : "badge-error"}">
                  ${st.http_status ? `HTTP ${esc(st.http_status)} · ` : ""}${st.status === "completed" ? "Done" : "Failed"}
                </span>
              </div>
              <div class="step-meta">${esc(st.summary)} · <span class="mono">${fmtTime(st.timestamp)}</span></div>
              ${(st.headers || st.body) ? `
                <div class="step-details">
                  ${st.headers ? `<div style="font-size:11.5px;font-weight:600;color:var(--text-muted);margin-bottom:4px;">HTTP Headers</div><pre class="code-block" style="margin-bottom:8px;">${esc(JSON.stringify(st.headers, null, 2))}</pre>` : ""}
                  ${st.body ? `<div style="font-size:11.5px;font-weight:600;color:var(--text-muted);margin-bottom:4px;">Payload / Inspection</div><pre class="code-block">${esc(JSON.stringify(st.body, null, 2))}</pre>` : ""}
                </div>
              ` : ""}
            </div>
          `).join("")}
        </div>
      </div>

      ${res.audit_events && res.audit_events.length ? `
        <div class="panel">
          <div class="panel-header">
            <h3 class="panel-title">Audit Ledger Timeline for Trace</h3>
          </div>
          <div class="table-wrap">
            <table class="data-table">
              <thead><tr><th>Stage</th><th>Message</th><th class="num-col">Timestamp</th></tr></thead>
              <tbody>
                ${res.audit_events.map((a) => `
                  <tr>
                    <td class="mono" style="font-size:12px;">${esc(a.event_type)}</td>
                    <td>${esc(a.message)}</td>
                    <td class="num-col" style="font-size:11.5px;">${fmtTime(a.created_at)}</td>
                  </tr>
                `).join("")}
              </tbody>
            </table>
          </div>
        </div>
      ` : ""}
    `;
  }

  /* ================= 3. AGENT MANAGEMENT ================= */
  async function renderAgentsPage(el) {
    const agents = await API.listAgents(false);
    state.agents = agents;
    const showCreate = state.openCreateAgentOnLoad;
    state.openCreateAgentOnLoad = false;

    el.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-heading">Autonomous Agents &amp; Wallets</h1>
          <p class="page-subtitle">Manage agent Algorand Ed25519 wallets, spending policies, and balances. Private keys are encrypted at rest and never returned by APIs.</p>
        </div>
        <button id="ag-new-toggle" class="btn btn-primary">Register New Agent</button>
      </div>

      <div id="ag-create-panel" class="panel ${showCreate ? "" : "hidden"}" style="margin-bottom:20px;">
        <div class="panel-header">
          <h2 class="panel-title">Register Autonomous Payment Agent</h2>
          <button id="ag-create-cancel" class="btn btn-ghost btn-sm">Cancel</button>
        </div>
        <form id="ag-create-form" class="form-grid">
          <div class="form-field">
            <label class="form-label">Agent Name</label>
            <input class="input" name="name" required placeholder="e.g., Arbitrage Analyst Agent" />
          </div>
          <div class="form-field">
            <label class="form-label">Default Settlement Mode</label>
            <select class="select" name="default_settlement_mode">
              <option value="exact">Exact (1 tx per request)</option>
              <option value="channel">Channel (voucher escrow)</option>
            </select>
          </div>
          <div class="form-field">
            <label class="form-label">Per-Request Limit (USDC)</label>
            <input class="input" type="number" step="0.001" name="per_request_limit_usdc" value="0.01" required />
          </div>
          <div class="form-field">
            <label class="form-label">Daily Spending Limit (USDC)</label>
            <input class="input" type="number" step="0.1" name="daily_limit_usdc" value="5.00" required />
          </div>
          <div class="form-field">
            <label class="form-label">Initial Local Demo Balance (USDC)</label>
            <input class="input" type="number" step="0.1" name="initial_local_balance_usdc" value="2.00" required />
          </div>
          <div class="form-field">
            <label class="form-label">Wallet Provisioning</label>
            <select class="select" name="wallet_mode" id="ag-wallet-mode">
              <option value="generate">Generate New Algorand Ed25519 Wallet</option>
              <option value="import_address">Import Existing Address / Mnemonic</option>
            </select>
          </div>
          <div class="form-field full hidden" id="ag-import-fields">
            <label class="form-label">Algorand Address (or 25-word Mnemonic for managed TestNet signing)</label>
            <input class="input mono" name="imported_wallet_address" placeholder="58-char Algorand TestNet Address (watch-only)" style="margin-bottom:8px;" />
            <input class="input mono" type="password" name="imported_mnemonic" placeholder="Optional 25-word Algorand mnemonic (encrypted server-side)" />
          </div>
          <div class="form-field full">
            <label class="form-label">Allowed API Hosts (comma-separated)</label>
            <input class="input mono" name="allowed_hosts" value="api.tollrail402.local, localhost, 127.0.0.1" />
          </div>
          <div class="form-field full" style="flex-direction:row;justify-content:flex-end;">
            <button type="submit" class="btn btn-primary">Create Agent</button>
          </div>
        </form>
      </div>

      <div class="panel">
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>Agent</th>
                <th>Algorand Wallet</th>
                <th class="num-col">Local Balance</th>
                <th class="num-col">Per-Req Cap</th>
                <th class="num-col">Daily Spent / Cap</th>
                <th>Mode</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              ${agents.map((a) => `
                <tr>
                  <td>
                    <div style="font-weight:600;">${esc(a.name)}</div>
                    <div class="mono" style="font-size:11.5px;color:var(--text-muted);">${esc(a.id)}</div>
                  </td>
                  <td>
                    <div class="mono" style="font-size:12px;" title="${esc(a.wallet_address)}">${shortAddr(a.wallet_address)}</div>
                    <div style="font-size:11.5px;color:var(--text-muted);">${a.has_managed_key ? "Managed Ed25519 Key" : "Watch-only"}</div>
                  </td>
                  <td class="num-col">${fmtUsdc(a.local_balance_usdc)}</td>
                  <td class="num-col">${fmtUsdc(a.per_request_limit_usdc)}</td>
                  <td class="num-col">${fmtUsdc(a.daily_spent_usdc)} / ${fmtUsdc(a.daily_limit_usdc)}</td>
                  <td style="text-transform:capitalize;">${esc(a.default_settlement_mode)}</td>
                  <td><span class="status-badge ${a.is_active ? "badge-success" : "badge-error"}">${a.is_active ? "Active" : "Paused"}</span></td>
                  <td>
                    <div style="display:flex;gap:6px;flex-wrap:wrap;">
                      <button class="btn btn-ghost btn-sm" data-ag-bal="${esc(a.id)}">TestNet Bal</button>
                      <button class="btn btn-ghost btn-sm" data-ag-fund="${esc(a.id)}">+ $1 Demo</button>
                      <button class="btn btn-ghost btn-sm" data-ag-policy="${esc(a.id)}">Policy</button>
                      <button class="btn btn-ghost btn-sm" data-ag-toggle="${esc(a.id)}" data-active="${a.is_active ? "1" : "0"}">${a.is_active ? "Pause" : "Activate"}</button>
                      <button class="btn btn-ghost btn-sm" data-ag-activity="${esc(a.id)}">Activity</button>
                    </div>
                  </td>
                </tr>
              `).join("")}
            </tbody>
          </table>
        </div>
      </div>
    `;

    const createPanel = document.getElementById("ag-create-panel");
    document.getElementById("ag-new-toggle").onclick = () => createPanel.classList.toggle("hidden");
    document.getElementById("ag-create-cancel").onclick = () => createPanel.classList.add("hidden");
    document.getElementById("ag-wallet-mode").onchange = (e) => {
      document.getElementById("ag-import-fields").classList.toggle("hidden", e.target.value !== "import_address");
    };

    document.getElementById("ag-create-form").onsubmit = async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      try {
        await API.createAgent({
          name: fd.get("name"),
          default_settlement_mode: fd.get("default_settlement_mode"),
          per_request_limit_usdc: Number(fd.get("per_request_limit_usdc")),
          daily_limit_usdc: Number(fd.get("daily_limit_usdc")),
          initial_local_balance_usdc: Number(fd.get("initial_local_balance_usdc")),
          wallet_mode: fd.get("wallet_mode"),
          imported_wallet_address: fd.get("imported_wallet_address") || null,
          imported_mnemonic: fd.get("imported_mnemonic") || null,
          allowed_hosts: String(fd.get("allowed_hosts") || "").split(",").map((s) => s.trim()).filter(Boolean),
        });
        toast("Agent registered with encrypted Algorand wallet", "success");
        renderCurrentPage();
      } catch (err) {
        toast(err.message, "error");
      }
    };

    el.querySelectorAll("[data-ag-bal]").forEach((btn) => {
      btn.onclick = async () => {
        try {
          const bal = await API.getAgentBalance(btn.dataset.agBal);
          const tn = bal.testnet;
          openDrawer("Agent Wallet & Live TestNet Balance", `
            <div class="kv-row"><span class="kv-key">Agent ID</span><span class="kv-val mono">${esc(bal.agent_id)}</span></div>
            <div class="kv-row"><span class="kv-key">Algorand Address</span><span class="kv-val mono">${esc(bal.wallet_address)}</span></div>
            <div class="kv-row"><span class="kv-key">Local Demo Balance</span><span class="kv-val mono">${fmtUsdcExact(bal.local_demo_balance_usdc)} USDC</span></div>
            <div class="divider"></div>
            <h3 style="margin:0 0 8px;font-size:14px;">Algorand TestNet On-Chain Lookup</h3>
            ${tn.success ? `
              <div class="kv-row"><span class="kv-key">TestNet ALGO</span><span class="kv-val mono">${esc(tn.algo)} ALGO</span></div>
              <div class="kv-row"><span class="kv-key">USDC Opt-In (ASA ${esc(tn.usdc_asset_id)})</span><span class="kv-val">${tn.usdc_opted_in ? "Opted In" : "Not Opted In"}</span></div>
              <div class="kv-row"><span class="kv-key">TestNet USDC Balance</span><span class="kv-val mono">${fmtUsdcExact(tn.usdc)} USDC</span></div>
              <div style="margin-top:14px;"><a class="btn btn-secondary btn-sm" href="${esc(bal.explorer_url)}" target="_blank" rel="noopener">Open in Algorand TestNet Explorer</a></div>
            ` : `<div class="notice notice-warning">TestNet lookup: ${esc(tn.error)}</div>`}
          `);
        } catch (err) {
          toast(err.message, "error");
        }
      };
    });

    el.querySelectorAll("[data-ag-fund]").forEach((btn) => {
      btn.onclick = async () => {
        try {
          await API.fundAgentLocal(btn.dataset.agFund, 1.0);
          toast("Credited $1.0000 local demo USDC", "success");
          renderCurrentPage();
        } catch (err) {
          toast(err.message, "error");
        }
      };
    });

    el.querySelectorAll("[data-ag-toggle]").forEach((btn) => {
      btn.onclick = async () => {
        try {
          const next = btn.dataset.active !== "1";
          await API.toggleAgentStatus(btn.dataset.agToggle, next);
          toast(`Agent ${next ? "activated" : "paused"}`, "success");
          renderCurrentPage();
        } catch (err) {
          toast(err.message, "error");
        }
      };
    });

    el.querySelectorAll("[data-ag-policy]").forEach((btn) => {
      btn.onclick = () => {
        const ag = state.agents.find((x) => x.id === btn.dataset.agPolicy);
        if (!ag) return;
        openDrawer(`Edit Spending Policy — ${ag.name}`, `
          <form id="drawer-policy-form" style="display:flex;flex-direction:column;gap:14px;">
            <div class="form-field">
              <label class="form-label">Per-Request Limit (USDC)</label>
              <input class="input" type="number" step="0.001" name="per_request_limit_usdc" value="${esc(ag.per_request_limit_usdc)}" required />
            </div>
            <div class="form-field">
              <label class="form-label">Daily Spending Limit (USDC)</label>
              <input class="input" type="number" step="0.1" name="daily_limit_usdc" value="${esc(ag.daily_limit_usdc)}" required />
            </div>
            <div class="form-field">
              <label class="form-label">Default Settlement Mode</label>
              <select class="select" name="default_settlement_mode">
                <option value="exact" ${ag.default_settlement_mode === "exact" ? "selected" : ""}>Exact Mode</option>
                <option value="channel" ${ag.default_settlement_mode === "channel" ? "selected" : ""}>Channel Mode</option>
              </select>
            </div>
            <div class="form-field">
              <label class="form-label">Allowed API Hosts (comma-separated)</label>
              <input class="input mono" name="allowed_hosts" value="${esc(ag.allowed_hosts.join(", "))}" required />
            </div>
            <button type="submit" class="btn btn-primary">Save Spending Policy</button>
          </form>
        `);
        document.getElementById("drawer-policy-form").onsubmit = async (e) => {
          e.preventDefault();
          const fd = new FormData(e.target);
          try {
            await API.updateAgentPolicy(ag.id, {
              per_request_limit_usdc: Number(fd.get("per_request_limit_usdc")),
              daily_limit_usdc: Number(fd.get("daily_limit_usdc")),
              default_settlement_mode: fd.get("default_settlement_mode"),
              allowed_hosts: String(fd.get("allowed_hosts")).split(",").map((s) => s.trim()).filter(Boolean),
            });
            closeDrawer();
            toast("Agent spending policy updated", "success");
            renderCurrentPage();
          } catch (err) {
            toast(err.message, "error");
          }
        };
      };
    });

    el.querySelectorAll("[data-ag-activity]").forEach((btn) => {
      btn.onclick = async () => {
        try {
          const data = await API.getAgentActivity(btn.dataset.agActivity);
          openDrawer(`Activity — ${data.agent.name}`, `
            <h3 style="margin:0 0 10px;font-size:14px;">Transactions (${data.transactions.length})</h3>
            ${data.transactions.length ? data.transactions.map((t) => `
              <div class="kv-row">
                <span class="mono">${esc(t.endpoint)} · ${esc(t.settlement_mode)}</span>
                <span class="mono">${fmtUsdcExact(t.amount_usdc)} (${esc(t.verification_status)})</span>
              </div>
            `).join("") : `<div class="empty-state">No transactions for this agent yet.</div>`}
            <div class="divider"></div>
            <h3 style="margin:0 0 10px;font-size:14px;">Recent Audit Logs</h3>
            ${data.audit_logs.slice(0, 12).map((a) => `
              <div style="padding:7px 0;border-bottom:1px solid var(--border-hairline);font-size:12.5px;">
                <div class="mono" style="font-size:11.5px;color:var(--text-muted);">${esc(a.event_type)} · ${fmtTime(a.created_at)}</div>
                <div>${esc(a.message)}</div>
              </div>
            `).join("")}
          `);
        } catch (err) {
          toast(err.message, "error");
        }
      };
    });
  }

  /* ================= 4. API MARKETPLACE ================= */
  async function renderMarketplacePage(el) {
    const [services, agents] = await Promise.all([API.listServices(), API.listAgents()]);
    state.services = services;
    state.agents = agents;

    el.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-heading">Paid API Marketplace</h1>
          <p class="page-subtitle">Every endpoint below enforces HTTP 402 Payment Required challenges on the backend before releasing its protected response.</p>
        </div>
      </div>

      <div class="panel" style="margin-bottom:20px;">
        <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;">
          <div>
            <strong>Executing Agent:</strong>
            <select id="mkt-agent-select" class="select" style="width:auto;display:inline-block;margin-left:8px;">
              ${agents.map((a) => `<option value="${esc(a.id)}">${esc(a.name)} (${fmtUsdc(a.local_balance_usdc)})</option>`).join("")}
            </select>
          </div>
          <div class="panel-meta">Click "Execute Paid Call" on any service to run a live HTTP 402 request or open in the Protocol Inspector.</div>
        </div>
      </div>

      <div class="grid-2">
        ${services.map((s) => `
          <div class="panel" style="display:flex;flex-direction:column;justify-content:space-between;gap:14px;">
            <div>
              <div style="font-size:12px;color:var(--text-muted);margin-bottom:4px;">${esc(s.category)} · ${esc(s.provider_name)} · ${s.is_available ? "Available" : "Unavailable"}</div>
              <div style="display:flex;align-items:baseline;justify-content:space-between;gap:12px;">
                <h2 style="margin:0;font-size:16px;font-weight:700;">${esc(s.name)}</h2>
                <span class="mono" style="font-weight:700;color:#009e5c;">${fmtUsdc(s.price_usdc)} ${esc(s.asset_symbol)}</span>
              </div>
              <p style="margin:8px 0 12px;color:var(--text-secondary);font-size:13px;">${esc(s.description)}</p>
              <div class="kv-row"><span class="kv-key">Endpoint</span><span class="kv-val mono">${esc(s.method)} ${esc(s.endpoint)}</span></div>
              <div class="kv-row"><span class="kv-key">Asset / Network</span><span class="kv-val mono">ASA ${esc(s.asset_id)} · ${esc(s.network)}</span></div>
              <div class="kv-row"><span class="kv-key">Recipient</span><span class="kv-val mono">${shortAddr(s.recipient_address)}</span></div>
            </div>
            <div style="display:flex;gap:8px;">
              <button class="btn btn-primary btn-sm" data-mkt-exec="${esc(s.id)}">Execute Paid Call</button>
              <button class="btn btn-secondary btn-sm" data-mkt-inspect="${esc(s.id)}">Open in 402 Inspector</button>
            </div>
          </div>
        `).join("")}
      </div>
    `;

    el.querySelectorAll("[data-mkt-inspect]").forEach((btn) => {
      btn.onclick = () => {
        state.demoPreselectServiceId = btn.dataset.mktInspect;
        navigate("demo");
      };
    });

    el.querySelectorAll("[data-mkt-exec]").forEach((btn) => {
      btn.onclick = async () => {
        const agentId = document.getElementById("mkt-agent-select").value;
        btn.disabled = true;
        btn.textContent = "Paying...";
        try {
          const res = await API.runDemo({ agent_id: agentId, service_id: btn.dataset.mktExec });
          state.lastDemoResult = res;
          openDrawer(res.success ? "Paid API Response Delivered" : "HTTP 402 Payment Rejected", `
            <div class="notice ${res.success ? "notice-success" : "notice-warning"}">
              Final Status: <strong>HTTP ${esc(res.final_http_status)}</strong> · Trace: <span class="mono">${esc(res.trace_id)}</span>
            </div>
            <h3 style="margin:0 0 8px;font-size:14px;">API Response Payload</h3>
            <pre class="code-block">${esc(JSON.stringify(res.api_response, null, 2))}</pre>
            <div style="margin-top:14px;">
              <button class="btn btn-primary btn-sm" id="drawer-open-trace">View Full 402 Header Trace</button>
            </div>
          `);
          document.getElementById("drawer-open-trace").onclick = () => {
            closeDrawer();
            navigate("demo");
          };
          toast(res.success ? "Paid API call succeeded" : "Paid API call rejected", res.success ? "success" : "error");
        } catch (err) {
          toast(err.message, "error");
        } finally {
          btn.disabled = false;
          btn.textContent = "Execute Paid Call";
        }
      };
    });
  }

  /* ================= 5. PAYMENT ACTIVITY ================= */
  async function renderActivityPage(el) {
    const [txs, overview] = await Promise.all([API.listPayments({ limit: 80 }), API.getOverview(0)]);
    el.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-heading">Payment Activity Feed</h1>
          <p class="page-subtitle">Live settlement velocity across Exact per-call transactions and Channel cumulative vouchers.</p>
        </div>
      </div>

      <div class="kpi-grid">
        <div class="kpi-card">
          <div class="kpi-label">Exact Mode Settled</div>
          <div class="kpi-value" style="margin-top:6px;">${esc(overview.exact_vs_channel.exact_count)}</div>
          <div class="kpi-sub">${fmtUsdcExact(overview.exact_vs_channel.exact_usdc)} USDC total</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">Channel Mode Settled</div>
          <div class="kpi-value" style="margin-top:6px;">${esc(overview.exact_vs_channel.channel_count)}</div>
          <div class="kpi-sub">${fmtUsdcExact(overview.exact_vs_channel.channel_usdc)} USDC total</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">Successful Verifications</div>
          <div class="kpi-value" style="margin-top:6px;">${esc(overview.successful_paid_requests)}</div>
          <div class="kpi-sub">Replay &amp; Ed25519 verified</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">Rejected / Failed</div>
          <div class="kpi-value" style="margin-top:6px;">${esc(overview.failed_payment_attempts)}</div>
          <div class="kpi-sub">Policy or signature blocks</div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-header">
          <h2 class="panel-title">Chronological Settlement Stream</h2>
        </div>
        ${txs.length ? `
          <div class="table-wrap">
            <table class="data-table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Agent</th>
                  <th>Service</th>
                  <th>Settlement</th>
                  <th>Status</th>
                  <th class="num-col">Amount</th>
                  <th class="num-col">Verify Time</th>
                </tr>
              </thead>
              <tbody>
                ${txs.map((t) => `
                  <tr style="cursor:pointer;" data-tx-detail="${esc(t.id)}">
                    <td style="font-size:12px;">${fmtTime(t.created_at)}</td>
                    <td>${esc(t.agent_name || t.agent_id)}</td>
                    <td class="mono">${esc(t.endpoint)}</td>
                    <td>${esc(t.settlement_mode)} · ${t.is_simulated ? "Local Sim" : "TestNet"}</td>
                    <td><span class="status-badge ${t.verification_status === "verified" ? "badge-success" : "badge-error"}">${t.verification_status === "verified" ? "Success" : "Failed"}</span></td>
                    <td class="num-col">${fmtUsdcExact(t.amount_usdc)}</td>
                    <td class="num-col">${Number(t.verification_time_ms).toFixed(2)} ms</td>
                  </tr>
                `).join("")}
              </tbody>
            </table>
          </div>
        ` : `<div class="empty-state">No payment activity yet.</div>`}
      </div>
    `;

    el.querySelectorAll("[data-tx-detail]").forEach((row) => {
      row.onclick = () => showTransactionDrawer(row.dataset.txDetail);
    });
  }

  /* ================= 6. PAYMENT CHANNELS ================= */
  async function renderChannelsPage(el) {
    const [channels, agents, escrow] = await Promise.all([
      API.listChannels(),
      API.listAgents(),
      API.getEscrowStatus(),
    ]);
    state.channels = channels;
    state.agents = agents;

    el.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-heading">Voucher Payment Channels</h1>
          <p class="page-subtitle">Batch high-frequency API micropayments using cumulative Ed25519 vouchers backed by Algorand escrow contracts.</p>
        </div>
      </div>

      <div class="notice ${escrow.is_onchain_escrow ? "notice-success" : "notice-warning"}">
        <strong>Escrow Mode:</strong> ${esc(escrow.mode_label)}<br/>
        <span>${esc(escrow.details)}</span>
      </div>

      <div class="panel" style="margin-bottom:20px;">
        <div class="panel-header">
          <h2 class="panel-title">Open New Payment Channel</h2>
        </div>
        <form id="chn-create-form" class="filter-bar" style="margin-bottom:0;">
          <select class="select" name="agent_id" style="max-width:280px;">
            ${agents.map((a) => `<option value="${esc(a.id)}">${esc(a.name)} (${fmtUsdc(a.local_balance_usdc)})</option>`).join("")}
          </select>
          <input class="input" type="number" step="0.1" min="0.01" name="deposit_usdc" value="0.50" style="max-width:160px;" placeholder="Deposit USDC" required />
          <button type="submit" class="btn btn-primary">Open Channel &amp; Deposit</button>
        </form>
      </div>

      <div style="display:flex;flex-direction:column;gap:16px;">
        ${channels.length ? channels.map((c) => `
          <div class="panel">
            <div class="panel-header">
              <div>
                <h3 class="panel-title"><span class="mono">${esc(c.id)}</span> · ${esc(c.agent_name || c.agent_id)}</h3>
                <div class="panel-meta">${esc(c.escrow_mode_label)} · Nonce #${esc(c.last_nonce)} · <span class="status-badge ${c.status === "open" ? "badge-success" : "badge-info"}">${c.status === "open" ? "Open" : "Closed"}</span></div>
              </div>
              <div style="display:flex;gap:8px;flex-wrap:wrap;">
                ${c.status === "open" ? `
                  <button class="btn btn-secondary btn-sm" data-chn-deposit="${esc(c.id)}">+ $0.50 Deposit</button>
                  <button class="btn btn-primary btn-sm" data-chn-settle="${esc(c.id)}">Batch Settle Vouchers</button>
                  <button class="btn btn-danger btn-sm" data-chn-close="${esc(c.id)}">Close &amp; Refund</button>
                ` : ""}
              </div>
            </div>

            <div class="kpi-grid" style="margin-bottom:14px;">
              <div class="kpi-card">
                <div class="kpi-label">Deposited Escrow</div>
                <div class="kpi-value" style="font-size:18px;margin-top:4px;">${fmtUsdcExact(c.deposited_usdc)}</div>
              </div>
              <div class="kpi-card">
                <div class="kpi-label">Cumulative Spent</div>
                <div class="kpi-value" style="font-size:18px;margin-top:4px;">${fmtUsdcExact(c.cumulative_spent_usdc)}</div>
              </div>
              <div class="kpi-card">
                <div class="kpi-label">Remaining Balance</div>
                <div class="kpi-value" style="font-size:18px;margin-top:4px;">${fmtUsdcExact(c.remaining_usdc)}</div>
              </div>
              <div class="kpi-card">
                <div class="kpi-label">Batch Settled</div>
                <div class="kpi-value" style="font-size:18px;margin-top:4px;">${fmtUsdcExact(c.settled_usdc)}</div>
              </div>
            </div>

            ${c.vouchers && c.vouchers.length ? `
              <div class="table-wrap">
                <table class="data-table">
                  <thead>
                    <tr>
                      <th>Voucher ID</th>
                      <th>Nonce</th>
                      <th class="num-col">Delta</th>
                      <th class="num-col">Cumulative</th>
                      <th>Ed25519 Signature</th>
                      <th>Settlement</th>
                    </tr>
                  </thead>
                  <tbody>
                    ${c.vouchers.map((v) => `
                      <tr>
                        <td class="mono">${esc(v.id)}</td>
                        <td class="mono">#${esc(v.nonce)}</td>
                        <td class="num-col">${fmtUsdcExact(v.delta_amount_usdc)}</td>
                        <td class="num-col">${fmtUsdcExact(v.cumulative_amount_usdc)}</td>
                        <td class="mono" style="font-size:11.5px;">${esc(v.signature.slice(0, 24))}...</td>
                        <td><span class="status-badge ${v.settled ? "badge-success" : "badge-warning"}">${v.settled ? `Settled (${esc(v.settlement_tx_id)})` : "Pending Batch"}</span></td>
                      </tr>
                    `).join("")}
                  </tbody>
                </table>
              </div>
            ` : `<div class="empty-state" style="padding:12px;">No vouchers issued yet. Run an API request using Channel Mode to issue signed vouchers.</div>`}
          </div>
        `).join("") : `<div class="panel"><div class="empty-state">No payment channels opened yet.</div></div>`}
      </div>
    `;

    document.getElementById("chn-create-form").onsubmit = async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      try {
        await API.createChannel({ agent_id: fd.get("agent_id"), deposit_usdc: Number(fd.get("deposit_usdc")) });
        toast("Payment channel opened", "success");
        renderCurrentPage();
      } catch (err) {
        toast(err.message, "error");
      }
    };

    el.querySelectorAll("[data-chn-deposit]").forEach((btn) => {
      btn.onclick = async () => {
        try {
          await API.depositChannel(btn.dataset.chnDeposit, 0.5);
          toast("Deposited $0.50 USDC to channel", "success");
          renderCurrentPage();
        } catch (err) {
          toast(err.message, "error");
        }
      };
    });

    el.querySelectorAll("[data-chn-settle]").forEach((btn) => {
      btn.onclick = async () => {
        try {
          const res = await API.batchSettleChannel(btn.dataset.chnSettle);
          toast(res.message, "success");
          renderCurrentPage();
        } catch (err) {
          toast(err.message, "error");
        }
      };
    });

    el.querySelectorAll("[data-chn-close]").forEach((btn) => {
      btn.onclick = async () => {
        try {
          await API.closeChannel(btn.dataset.chnClose, "Closed via dashboard");
          toast("Channel closed and unspent funds refunded", "success");
          renderCurrentPage();
        } catch (err) {
          toast(err.message, "error");
        }
      };
    });
  }

  /* ================= 7. SPENDING POLICIES ================= */
  async function renderPoliciesPage(el) {
    const [agents] = await Promise.all([API.listAgents()]);
    el.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-heading">Spending Policy Engine</h1>
          <p class="page-subtitle">Deterministic server-side rule evaluator enforcing per-request limits, daily caps, allowed hosts, and available funds.</p>
        </div>
      </div>

      <div class="grid-2">
        <div class="panel">
          <div class="panel-header"><h2 class="panel-title">Policy Decision Simulator</h2></div>
          <form id="pol-eval-form" style="display:flex;flex-direction:column;gap:14px;">
            <div class="form-field">
              <label class="form-label">Select Agent</label>
              <select class="select" name="agent_id">
                ${agents.map((a) => `<option value="${esc(a.id)}">${esc(a.name)} (Max ${fmtUsdc(a.per_request_limit_usdc)}/req)</option>`).join("")}
              </select>
            </div>
            <div class="form-field">
              <label class="form-label">Requested Amount (USDC)</label>
              <input class="input" type="number" step="0.001" name="amount_usdc" value="0.015" required />
            </div>
            <div class="form-field">
              <label class="form-label">Target API Host</label>
              <input class="input mono" name="target_host" value="api.tollrail402.local" required />
            </div>
            <button type="submit" class="btn btn-primary">Evaluate Policy Rules</button>
          </form>
        </div>

        <div class="panel" id="pol-result-panel">
          <div class="panel-header"><h2 class="panel-title">Evaluation Output</h2></div>
          <div class="empty-state">Run an evaluation on the left to inspect all 6 policy checks (active status, challenge expiry, allowed host, per-request cap, daily limit, balance).</div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-header"><h2 class="panel-title">Configured Agent Policy Matrix</h2></div>
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>Agent</th>
                <th class="num-col">Per-Request Cap</th>
                <th class="num-col">Daily Limit</th>
                <th class="num-col">Daily Spent</th>
                <th>Allowed Hosts</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              ${agents.map((a) => `
                <tr>
                  <td><strong>${esc(a.name)}</strong></td>
                  <td class="num-col">${fmtUsdc(a.per_request_limit_usdc)}</td>
                  <td class="num-col">${fmtUsdc(a.daily_limit_usdc)}</td>
                  <td class="num-col">${fmtUsdc(a.daily_spent_usdc)}</td>
                  <td class="mono" style="font-size:12px;">${esc(a.allowed_hosts.join(", "))}</td>
                  <td><span class="status-badge ${a.is_active ? "badge-success" : "badge-error"}">${a.is_active ? "Active" : "Paused"}</span></td>
                </tr>
              `).join("")}
            </tbody>
          </table>
        </div>
      </div>
    `;

    document.getElementById("pol-eval-form").onsubmit = async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      try {
        const res = await API.evaluatePolicy({
          agent_id: fd.get("agent_id"),
          amount_usdc: Number(fd.get("amount_usdc")),
          target_host: fd.get("target_host"),
        });
        document.getElementById("pol-result-panel").innerHTML = `
          <div class="panel-header">
            <h2 class="panel-title">Evaluation Output</h2>
            <span class="status-badge ${res.approved ? "badge-success" : "badge-error"}">${res.approved ? "APPROVED" : "REJECTED"}</span>
          </div>
          <div class="notice ${res.approved ? "notice-success" : "notice-warning"}">${esc(res.reason)}</div>
          <div class="table-wrap">
            <table class="data-table">
              <thead><tr><th>Rule</th><th>Result</th><th>Detail</th></tr></thead>
              <tbody>
                ${res.checks.map((c) => `
                  <tr>
                    <td class="mono">${esc(c.rule)}</td>
                    <td><span class="status-badge ${c.passed ? "badge-success" : "badge-error"}">${c.passed ? "Pass" : "Fail"}</span></td>
                    <td>${esc(c.detail)}</td>
                  </tr>
                `).join("")}
              </tbody>
            </table>
          </div>
        `;
      } catch (err) {
        toast(err.message, "error");
      }
    };
  }

  /* ================= 8. TRANSACTION EXPLORER ================= */
  async function renderExplorerPage(el) {
    const agents = await API.listAgents();
    el.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-heading">Transaction Explorer</h1>
          <p class="page-subtitle">Inspect HTTP 402 payment records, cryptographic nonces, settlement modes, and Algorand TestNet explorer links.</p>
        </div>
      </div>

      <div class="panel" style="margin-bottom:16px;">
        <div class="filter-bar" style="margin-bottom:0;">
          <input id="exp-search" class="input" placeholder="Search TX ID, address, endpoint..." style="max-width:240px;" />
          <select id="exp-agent" class="select" style="max-width:200px;">
            <option value="">All Agents</option>
            ${agents.map((a) => `<option value="${esc(a.id)}">${esc(a.name)}</option>`).join("")}
          </select>
          <select id="exp-mode" class="select" style="max-width:160px;">
            <option value="">All Modes</option>
            <option value="exact">Exact</option>
            <option value="channel">Channel</option>
          </select>
          <select id="exp-status" class="select" style="max-width:160px;">
            <option value="">All Statuses</option>
            <option value="verified">Verified</option>
            <option value="failed">Failed</option>
          </select>
          <input id="exp-from" class="input" type="date" style="max-width:155px;" />
          <button id="exp-filter-btn" class="btn btn-primary btn-sm">Apply Filters</button>
        </div>
      </div>

      <div class="panel" id="exp-table-panel">
        <div class="loading-state">Loading transactions...</div>
      </div>
    `;

    async function loadExplorerRows() {
      const txs = await API.listPayments({
        search: document.getElementById("exp-search").value,
        agent_id: document.getElementById("exp-agent").value,
        settlement_mode: document.getElementById("exp-mode").value,
        status: document.getElementById("exp-status").value,
        date_from: document.getElementById("exp-from").value,
      });
      const panel = document.getElementById("exp-table-panel");
      if (!txs.length) {
        panel.innerHTML = `<div class="empty-state">No matching transactions found.</div>`;
        return;
      }
      panel.innerHTML = `
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>Tx / Ref</th>
                <th>Agent</th>
                <th>Payer → Recipient</th>
                <th>Endpoint</th>
                <th>Mode</th>
                <th class="num-col">Amount (USDC)</th>
                <th>Status</th>
                <th>Timestamp</th>
              </tr>
            </thead>
            <tbody>
              ${txs.map((t) => `
                <tr style="cursor:pointer;" data-tx-detail="${esc(t.id)}">
                  <td>
                    <div class="mono" style="font-weight:600;">${esc(t.blockchain_tx_id || t.local_receipt_ref || t.id)}</div>
                    <div style="font-size:11.5px;color:var(--text-muted);">${t.blockchain_tx_id ? "Algorand TestNet TX" : "Local Demo Reference"}</div>
                  </td>
                  <td>${esc(t.agent_name || t.agent_id)}</td>
                  <td class="mono" style="font-size:11.5px;">${shortAddr(t.payer_address)} → ${shortAddr(t.recipient_address)}</td>
                  <td class="mono">${esc(t.endpoint)}</td>
                  <td style="text-transform:capitalize;">${esc(t.settlement_mode)}</td>
                  <td class="num-col">${fmtUsdcExact(t.amount_usdc)}</td>
                  <td><span class="status-badge ${t.verification_status === "verified" ? "badge-success" : "badge-error"}">${t.verification_status === "verified" ? "Success" : "Failed"}</span></td>
                  <td style="font-size:12px;">${fmtTime(t.created_at)}</td>
                </tr>
              `).join("")}
            </tbody>
          </table>
        </div>
      `;
      panel.querySelectorAll("[data-tx-detail]").forEach((row) => {
        row.onclick = () => showTransactionDrawer(row.dataset.txDetail);
      });
    }

    document.getElementById("exp-filter-btn").onclick = loadExplorerRows;
    await loadExplorerRows();
  }

  async function showTransactionDrawer(txId) {
    try {
      const data = await API.getPaymentDetail(txId);
      const t = data.transaction;
      openDrawer(`Transaction Receipt — ${t.id}`, `
        <div class="kv-row"><span class="kv-key">Status</span><span class="kv-val"><span class="status-badge ${t.verification_status === "verified" ? "badge-success" : "badge-error"}">${esc(t.verification_status.toUpperCase())}</span></span></div>
        <div class="kv-row"><span class="kv-key">Execution Environment</span><span class="kv-val">${t.is_simulated ? "Local Demo Mode (Simulated Settlement)" : "Algorand TestNet (On-Chain)"}</span></div>
        <div class="kv-row"><span class="kv-key">Settlement Mode</span><span class="kv-val">${esc(t.settlement_mode)}</span></div>
        <div class="kv-row"><span class="kv-key">Amount</span><span class="kv-val mono">${fmtUsdcExact(t.amount_usdc)} USDC (ASA ${esc(t.asset_id)})</span></div>
        <div class="kv-row"><span class="kv-key">Endpoint</span><span class="kv-val mono">${esc(t.endpoint)}</span></div>
        <div class="kv-row"><span class="kv-key">Payer Address</span><span class="kv-val mono">${esc(t.payer_address)}</span></div>
        <div class="kv-row"><span class="kv-key">Recipient Address</span><span class="kv-val mono">${esc(t.recipient_address)}</span></div>
        <div class="kv-row"><span class="kv-key">Challenge ID</span><span class="kv-val mono">${esc(t.challenge_id)}</span></div>
        <div class="kv-row"><span class="kv-key">Replay Nonce</span><span class="kv-val mono">${esc(t.nonce)}</span></div>
        ${t.blockchain_tx_id ? `
          <div class="kv-row"><span class="kv-key">Algorand TX ID</span><span class="kv-val mono">${esc(t.blockchain_tx_id)}</span></div>
          <div style="margin-top:10px;"><a class="btn btn-primary btn-sm" href="${esc(t.explorer_url)}" target="_blank" rel="noopener">View on Algorand TestNet Explorer</a></div>
        ` : `<div class="kv-row"><span class="kv-key">Local Demo Ref</span><span class="kv-val mono">${esc(t.local_receipt_ref || "-")}</span></div>`}
        ${t.failure_reason ? `<div class="notice notice-warning" style="margin-top:12px;">${esc(t.failure_reason)}</div>` : ""}
        <div class="divider"></div>
        <h3 style="margin:0 0 10px;font-size:14px;">Audit Timeline</h3>
        ${data.audit_timeline.map((a) => `
          <div style="padding:8px 0;border-bottom:1px solid var(--border-hairline);font-size:12.5px;">
            <div class="mono" style="font-size:11.5px;color:var(--text-muted);">${esc(a.event_type)} · ${fmtTime(a.created_at)}</div>
            <div>${esc(a.message)}</div>
          </div>
        `).join("")}
      `);
    } catch (err) {
      toast(err.message, "error");
    }
  }

  /* ================= 9. AUDIT LOGS ================= */
  async function renderAuditPage(el) {
    const agents = await API.listAgents();
    el.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-heading">Append-Only Audit Ledger</h1>
          <p class="page-subtitle">Immutable chronological log of every HTTP 402 request, challenge, policy decision, verification, and settlement.</p>
        </div>
      </div>

      <div class="panel" style="margin-bottom:16px;">
        <div class="filter-bar" style="margin-bottom:0;">
          <input id="aud-trace" class="input mono" placeholder="Filter by Trace ID..." style="max-width:200px;" />
          <select id="aud-agent" class="select" style="max-width:200px;">
            <option value="">All Agents</option>
            ${agents.map((a) => `<option value="${esc(a.id)}">${esc(a.name)}</option>`).join("")}
          </select>
          <select id="aud-event" class="select" style="max-width:200px;">
            <option value="">All Event Types</option>
            <option value="REQUEST_RECEIVED">REQUEST_RECEIVED</option>
            <option value="PAYMENT_REQUIRED">PAYMENT_REQUIRED</option>
            <option value="POLICY_APPROVED">POLICY_APPROVED</option>
            <option value="POLICY_REJECTED">POLICY_REJECTED</option>
            <option value="PAYMENT_SUBMITTED">PAYMENT_SUBMITTED</option>
            <option value="PAYMENT_VERIFIED">PAYMENT_VERIFIED</option>
            <option value="PAYMENT_FAILED">PAYMENT_FAILED</option>
            <option value="SERVICE_DELIVERED">SERVICE_DELIVERED</option>
            <option value="SETTLED">SETTLED</option>
          </select>
          <button id="aud-filter-btn" class="btn btn-primary btn-sm">Filter Ledger</button>
        </div>
      </div>

      <div class="panel" id="aud-table-panel">
        <div class="loading-state">Loading audit records...</div>
      </div>
    `;

    async function loadAudits() {
      const logs = await API.listAuditLogs({
        trace_id: document.getElementById("aud-trace").value,
        agent_id: document.getElementById("aud-agent").value,
        event_type: document.getElementById("aud-event").value,
      });
      const panel = document.getElementById("aud-table-panel");
      if (!logs.length) {
        panel.innerHTML = `<div class="empty-state">No audit logs matched your filter.</div>`;
        return;
      }
      panel.innerHTML = `
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Trace ID</th>
                <th>Event Type</th>
                <th>Status</th>
                <th>Message</th>
                <th>Timestamp</th>
              </tr>
            </thead>
            <tbody>
              ${logs.map((a) => `
                <tr>
                  <td class="mono">${esc(a.id)}</td>
                  <td class="mono" style="font-size:12px;">${esc(a.trace_id)}</td>
                  <td class="mono" style="font-size:12px;">${esc(a.event_type)}</td>
                  <td><span class="status-badge ${a.status === "success" ? "badge-success" : a.status === "error" ? "badge-error" : a.status === "warning" ? "badge-warning" : "badge-info"}">${esc(a.status)}</span></td>
                  <td>${esc(a.message)}</td>
                  <td style="font-size:12px;white-space:nowrap;">${fmtTime(a.created_at)}</td>
                </tr>
              `).join("")}
            </tbody>
          </table>
        </div>
      `;
    }

    document.getElementById("aud-filter-btn").onclick = loadAudits;
    await loadAudits();
  }

  /* ================= 10. DEVELOPER DOCUMENTATION ================= */
  function renderDocsPage(el) {
    el.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-heading">Developer Documentation</h1>
          <p class="page-subtitle">HTTP 402 header specification, Algorand TestNet USDC configuration, and Autonomous Agent SDK integration guide.</p>
        </div>
      </div>

      <div class="grid-2">
        <div class="panel">
          <div class="panel-header"><h2 class="panel-title">HTTP 402 Protocol Sequence</h2></div>
          <ol style="margin:0;padding-left:18px;display:flex;flex-direction:column;gap:8px;color:var(--text-secondary);">
            <li>Agent calls protected endpoint (e.g., <code class="mono">POST /v1/infer</code>) without payment headers.</li>
            <li>Middleware responds with <strong>HTTP 402 Payment Required</strong> and Base64 JSON <code class="mono">PAYMENT-REQUIRED</code> header.</li>
            <li>Agent SDK evaluates its <code class="mono">PolicyEngine</code> (per-request cap, daily limit, allowed hosts, expiry, balance).</li>
            <li>Agent signs canonical payment payload (Exact mode) or cumulative voucher (Channel mode) with Ed25519.</li>
            <li>In <code class="mono">algorand_testnet</code> mode, agent submits USDC ASA (<code class="mono">10458941</code>) transfer on Algorand TestNet.</li>
            <li>Agent retries the request with <code class="mono">PAYMENT-SIGNATURE</code> header.</li>
            <li>Server verifies signature, nonce replay protection, expiration, and settlement, then returns <strong>HTTP 200</strong> + <code class="mono">PAYMENT-RESPONSE</code>.</li>
          </ol>
        </div>

        <div class="panel">
          <div class="panel-header"><h2 class="panel-title">PAYMENT-REQUIRED Header Schema</h2></div>
          <pre class="code-block">{
  "protocol_version": "x402/1.0",
  "schemes": ["exact", "channel"],
  "network": "algorand:testnet",
  "asset_id": 10458941,
  "asset_symbol": "USDC",
  "amount_micro_usdc": 5000,
  "amount_usdc": "0.005000",
  "recipient_address": "ALGORAND_TESTNET_ADDRESS",
  "resource": "/v1/infer",
  "challenge_id": "chl_...",
  "nonce": "hex_replay_nonce",
  "expires_at": "2026-11-13T14:15:00+00:00"
}</pre>
        </div>
      </div>

      <div class="panel">
        <div class="panel-header"><h2 class="panel-title">Python Agent SDK Quickstart</h2></div>
        <pre class="code-block">from fastapi.testclient import TestClient
from backend.app.database import SessionLocal
from backend.app.main import app
from backend.app.models.models import Agent, ApiService
from backend.app.sdk.agent_client import TollRailAgentClient

with SessionLocal() as db:
    agent = db.query(Agent).filter(Agent.id == "agt_research_01").first()
    service = db.query(ApiService).filter(ApiService.endpoint == "/v1/infer").first()

    sdk = TollRailAgentClient(TestClient(app, base_url="http://api.tollrail402.local"))
    trace = sdk.execute_paid_request(
        db,
        agent=agent,
        service=service,
        request_payload={"prompt": "Summarize Algorand finality", "max_tokens": 100},
    )
    print("Final HTTP Status:", trace["final_http_status"])
    print("Protected Output:", trace["api_response"])</pre>
      </div>
    `;
  }

  /* ================= 11. SETTINGS ================= */
  async function renderSettingsPage(el) {
    const cfg = await API.getSettings();
    const node = cfg.algorand_node_status || {};
    el.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-heading">Platform &amp; Network Settings</h1>
          <p class="page-subtitle">Switch between Local Demo Mode and live Algorand TestNet settlement. TestNet mode never silently falls back to simulation.</p>
        </div>
      </div>

      <div class="grid-2">
        <div class="panel">
          <div class="panel-header"><h2 class="panel-title">Execution &amp; Blockchain Configuration</h2></div>
          <form id="set-form" style="display:flex;flex-direction:column;gap:14px;">
            <div class="form-field">
              <label class="form-label">Operating Mode</label>
              <select class="select" name="tollrail_mode">
                <option value="local_demo" ${cfg.tollrail_mode === "local_demo" ? "selected" : ""}>local_demo (Real HTTP 402 + Ed25519; Local Simulated Settlement)</option>
                <option value="algorand_testnet" ${cfg.tollrail_mode === "algorand_testnet" ? "selected" : ""}>algorand_testnet (Real Algorand TestNet USDC Transactions)</option>
              </select>
            </div>
            <div class="form-field">
              <label class="form-label">Merchant / API Provider Recipient Address</label>
              <input class="input mono" name="merchant_algorand_address" value="${esc(cfg.merchant_algorand_address)}" required />
            </div>
            <div class="form-field">
              <label class="form-label">USDC ASA Asset ID (TestNet Circle USDC = 10458941)</label>
              <input class="input mono" type="number" name="usdc_asset_id" value="${esc(cfg.usdc_asset_id)}" required />
            </div>
            <div class="form-field">
              <label class="form-label">Deployed Escrow Smart Contract App ID (0 = Local Dev Mode)</label>
              <input class="input mono" type="number" name="escrow_app_id" value="${esc(cfg.escrow_app_id)}" required />
            </div>
            <button type="submit" class="btn btn-primary">Save Platform Settings</button>
          </form>
        </div>

        <div class="panel">
          <div class="panel-header"><h2 class="panel-title">Infrastructure Diagnostics</h2></div>
          <div class="kv-row"><span class="kv-key">Database Dialect</span><span class="kv-val mono">${esc(cfg.database_dialect)}</span></div>
          <div class="kv-row"><span class="kv-key">Algorand Network</span><span class="kv-val mono">${esc(cfg.algorand_network)}</span></div>
          <div class="kv-row"><span class="kv-key">Algod Endpoint</span><span class="kv-val mono">${esc(cfg.algod_address)}</span></div>
          <div class="kv-row"><span class="kv-key">Indexer Endpoint</span><span class="kv-val mono">${esc(cfg.indexer_address)}</span></div>
          <div class="kv-row"><span class="kv-key">Algod Status</span><span class="kv-val"><span class="status-badge ${node.connected ? "badge-success" : "badge-error"}">${node.connected ? `Connected (Round #${esc(node.last_round)})` : `Disconnected (${esc(node.error || "timeout")})`}</span></span></div>
          <div class="kv-row"><span class="kv-key">Escrow Contract Status</span><span class="kv-val">${cfg.escrow_deployed ? `App ID ${esc(cfg.escrow_app_id)}` : "Not Deployed (Local Channel Mode)"}</span></div>
        </div>
      </div>
    `;

    document.getElementById("set-form").onsubmit = async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      try {
        await API.updateSettings({
          tollrail_mode: fd.get("tollrail_mode"),
          merchant_algorand_address: fd.get("merchant_algorand_address"),
          usdc_asset_id: Number(fd.get("usdc_asset_id")),
          escrow_app_id: Number(fd.get("escrow_app_id")),
        });
        toast("Settings updated", "success");
        renderCurrentPage();
      } catch (err) {
        toast(err.message, "error");
      }
    };
  }

  /* ================= BOOTSTRAP ================= */
  function init() {
    document.querySelectorAll(".nav-item").forEach((btn) => {
      btn.addEventListener("click", () => navigate(btn.dataset.page));
    });
    document.querySelector("[data-nav='overview']").addEventListener("click", (e) => {
      e.preventDefault();
      navigate("overview");
    });
    document.getElementById("sidebar-demo-promo").addEventListener("click", () => navigate("demo"));
    document.getElementById("topbar-demo-btn").addEventListener("click", () => navigate("demo"));
    document.getElementById("topbar-mode-chip").addEventListener("click", () => navigate("settings"));
    document.getElementById("topbar-wallet-chip").addEventListener("click", async () => {
      const addr = state.settings && state.settings.merchant_algorand_address;
      if (!addr) return;
      try {
        await navigator.clipboard.writeText(addr);
        toast(`Copied merchant address: ${shortAddr(addr)}`, "success");
      } catch (_) {
        toast(addr);
      }
    });
    document.getElementById("drawer-close-btn").addEventListener("click", closeDrawer);
    document.getElementById("drawer-backdrop").addEventListener("click", closeDrawer);
    document.getElementById("mobile-menu-btn").addEventListener("click", () => {
      document.getElementById("sidebar").classList.toggle("open");
    });

    const initialHash = window.location.hash.replace("#", "").trim();
    navigate(PAGE_TITLES[initialHash] ? initialHash : "overview");
  }

  document.addEventListener("DOMContentLoaded", init);
})();
