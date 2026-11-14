/* TollRail402 API Client Wrapper */
window.TollRailAPI = {
  async request(path, options = {}) {
    const config = {
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
      ...options,
    };
    const resp = await fetch(path, config);
    const contentType = resp.headers.get("content-type") || "";
    const data = contentType.includes("application/json") ? await resp.json() : await resp.text();
    if (!resp.ok) {
      const msg = (data && data.detail && (typeof data.detail === "string" ? data.detail : data.detail.message || data.detail.reason)) || `Request failed (${resp.status})`;
      const err = new Error(msg);
      err.status = resp.status;
      err.data = data;
      throw err;
    }
    return data;
  },

  getOverview(days = 7) {
    return this.request(`/api/dashboard/overview?days=${encodeURIComponent(days)}`);
  },

  listAgents(fetchTestnet = false) {
    return this.request(`/api/agents?fetch_testnet=${fetchTestnet ? "true" : "false"}`);
  },
  createAgent(payload) {
    return this.request("/api/agents", { method: "POST", body: JSON.stringify(payload) });
  },
  getAgentBalance(agentId) {
    return this.request(`/api/agents/${encodeURIComponent(agentId)}/balance`);
  },
  updateAgentWallet(agentId, payload) {
    return this.request(`/api/agents/${encodeURIComponent(agentId)}/wallet`, { method: "POST", body: JSON.stringify(payload) });
  },
  updateAgentPolicy(agentId, payload) {
    return this.request(`/api/agents/${encodeURIComponent(agentId)}/policy`, { method: "PATCH", body: JSON.stringify(payload) });
  },
  toggleAgentStatus(agentId, isActive) {
    return this.request(`/api/agents/${encodeURIComponent(agentId)}/status`, { method: "PATCH", body: JSON.stringify({ is_active: isActive }) });
  },
  fundAgentLocal(agentId, amountUsdc) {
    return this.request(`/api/agents/${encodeURIComponent(agentId)}/fund`, { method: "POST", body: JSON.stringify({ amount_usdc: Number(amountUsdc) }) });
  },
  getAgentActivity(agentId) {
    return this.request(`/api/agents/${encodeURIComponent(agentId)}/activity`);
  },

  listServices() {
    return this.request("/api/marketplace/services");
  },

  listPayments(params = {}) {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && String(v).trim() !== "") qs.set(k, v);
    });
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return this.request(`/api/payments${suffix}`);
  },
  getPaymentDetail(txId) {
    return this.request(`/api/payments/${encodeURIComponent(txId)}`);
  },

  listChannels(agentId = "") {
    const suffix = agentId ? `?agent_id=${encodeURIComponent(agentId)}` : "";
    return this.request(`/api/channels${suffix}`);
  },
  getEscrowStatus() {
    return this.request("/api/channels/escrow-status");
  },
  createChannel(payload) {
    return this.request("/api/channels", { method: "POST", body: JSON.stringify(payload) });
  },
  depositChannel(channelId, amountUsdc) {
    return this.request(`/api/channels/${encodeURIComponent(channelId)}/deposit`, { method: "POST", body: JSON.stringify({ amount_usdc: Number(amountUsdc) }) });
  },
  batchSettleChannel(channelId) {
    return this.request(`/api/channels/${encodeURIComponent(channelId)}/batch-settle`, { method: "POST" });
  },
  closeChannel(channelId, reason) {
    return this.request(`/api/channels/${encodeURIComponent(channelId)}/close`, { method: "POST", body: JSON.stringify({ reason }) });
  },

  evaluatePolicy(payload) {
    return this.request("/api/policies/evaluate", { method: "POST", body: JSON.stringify(payload) });
  },

  listAuditLogs(params = {}) {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && String(v).trim() !== "") qs.set(k, v);
    });
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return this.request(`/api/audit${suffix}`);
  },

  runDemo(payload) {
    return this.request("/api/demo/run", { method: "POST", body: JSON.stringify(payload) });
  },

  getSettings() {
    return this.request("/api/settings");
  },
  updateSettings(payload) {
    return this.request("/api/settings", { method: "PATCH", body: JSON.stringify(payload) });
  },
};
