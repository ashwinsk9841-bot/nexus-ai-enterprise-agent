/* NEXUS API client */
const API_BASE = (window.NEXUS_API_BASE || "").replace(/\/$/, "") || "/api";

const NEXUS = {
  token: localStorage.getItem("nexus_token") || null,
  user: JSON.parse(localStorage.getItem("nexus_user") || "null"),

  setAuth(token, user) {
    this.token = token;
    this.user = user;
    localStorage.setItem("nexus_token", token || "");
    if (user) localStorage.setItem("nexus_user", JSON.stringify(user));
    else localStorage.removeItem("nexus_user");
  },

  clearAuth() {
    this.token = null;
    this.user = null;
    localStorage.removeItem("nexus_token");
    localStorage.removeItem("nexus_user");
  },

  async request(method, path, body, opts = {}) {
    const headers = {};
    if (this.token) headers["Authorization"] = `Bearer ${this.token}`;
    let payload = body;
    if (body instanceof FormData) {
      payload = body;
    } else if (body !== undefined && body !== null) {
      headers["Content-Type"] = "application/json";
      payload = JSON.stringify(body);
    }

    const controller = new AbortController();
    const timeoutMs = opts.timeout || 60000;
    const t = setTimeout(() => controller.abort(), timeoutMs);

    try {
      const res = await fetch(`${API_BASE}${path}`, {
        method,
        headers,
        body: payload,
        signal: controller.signal,
      });
      clearTimeout(t);

      let data = null;
      const contentType = res.headers.get("content-type") || "";
      if (contentType.includes("application/json")) {
        data = await res.json();
      }

      if (!res.ok) {
        // FastAPI returns `detail` as an array for 422 validation errors;
        // surface those as readable messages instead of "Request failed".
        let msg = (data && data.detail) || res.statusText || "Request failed";
        if (Array.isArray(msg)) {
          const parts = msg.map((v) => {
            const loc = (v.loc || []).slice(1).join(".");
            const reason = typeof v.msg === "string" ? v.msg : "invalid value";
            return loc ? `${loc}: ${reason}` : reason;
          });
          msg = "Invalid request: " + parts.join("; ");
        }
        const err = new Error(typeof msg === "string" ? msg : "Request failed");
        err.status = res.status;
        err.data = data;
        throw err;
      }
      return data;
    } catch (e) {
      clearTimeout(t);
      if (e.name === "AbortError") {
        const err = new Error("Request timed out. Please try again.");
        err.status = 408;
        throw err;
      }
      throw e;
    }
  },

  // --- Auth ---
  login(email, password, remember) {
    return this.request("POST", "/auth/login", { email, password, remember: !!remember });
  },
  demoLogin() {
    return this.request("POST", "/auth/login", { email: "demo@nexus.io", password: "demo1234" });
  },
  register(email, username, fullName, password, confirmPassword) {
    return this.request("POST", "/auth/register", {
      email,
      username,
      full_name: fullName,
      password,
      confirm_password: confirmPassword || password,
    });
  },
  authConfig() {
    return this.request("GET", "/auth/config");
  },
  logout() {
    return this.request("POST", "/auth/logout", {});
  },
  me() {
    return this.request("GET", "/auth/me");
  },

  // --- Dashboard ---
  dashboard(query = "") {
    return this.request("GET", `/dashboard/overview?${query}`);
  },

  // --- Agents ---
  agents() {
    return this.request("GET", "/agents");
  },
  agentDetail(id) {
    return this.request("GET", `/agents/${id}`);
  },

  // --- Analytics ---
  analytics(params) {
    const q = new URLSearchParams(params || {}).toString();
    return this.request("GET", `/analytics/metrics?${q}`);
  },
  analyticsExplain(params) {
    return this.request("POST", "/analytics/explain", params);
  },
  analyticsExport(params) {
    return this.request("POST", "/analytics/export", params, { timeout: 15000 });
  },

  // --- Security ---
  security(params) {
    const q = new URLSearchParams(params || {}).toString();
    return this.request("GET", `/security/summary?${q}`);
  },
  securityEvents(params) {
    const q = new URLSearchParams(params || {}).toString();
    return this.request("GET", `/security/events?${q}`);
  },

  // --- Operations ---
  operations(params) {
    const q = new URLSearchParams(params || {}).toString();
    return this.request("GET", `/operations/metrics?${q}`);
  },

  // --- Incidents ---
  incidents(params) {
    const q = new URLSearchParams(params || {}).toString();
    return this.request("GET", `/incidents?${q}`);
  },
  incidentDetail(id) {
    return this.request("GET", `/incidents/${id}`);
  },
  createIncident(data) {
    return this.request("POST", "/incidents", data);
  },
  updateIncident(id, data) {
    return this.request("PATCH", `/incidents/${id}`, data);
  },

  // --- Knowledge / RAG ---
  knowledgeDocs() {
    return this.request("GET", "/knowledge/documents");
  },
  uploadKnowledge(formData) {
    return this.request("POST", "/knowledge/upload", formData, { timeout: 120000 });
  },
  kbAsk(query) {
    return this.request("POST", "/knowledge/ask", { query });
  },

  // --- Reports ---
  reports() {
    return this.request("GET", "/reports");
  },
  generateReport(type, range) {
    return this.request("POST", "/reports/generate", { report_type: type, date_range: range }, { timeout: 120000 });
  },
  exportReport(id) {
    return this.request("POST", `/reports/${id}/export`, {});
  },

  // --- AI ---
  aiAsk(query) {
    return this.request("POST", "/ai/command", { query }, { timeout: 120000 });
  },

  // --- Notifications ---
  notifications() {
    return this.request("GET", "/notifications");
  },
  markNotification(id) {
    return this.request("POST", `/notifications/${id}/read`, {});
  },
  markAllRead() {
    return this.request("POST", "/notifications/read-all", {});
  },

  // --- Profile/settings ---
  profile() {
    return this.request("GET", "/auth/me");
  },

  // --- Admin ---
  adminDashboard() {
    return this.request("GET", "/admin/dashboard");
  },
  adminUsers(params) {
    const q = new URLSearchParams(params || {}).toString();
    return this.request("GET", `/admin/users?${q}`);
  },
  adminUserDetail(id) {
    return this.request("GET", `/admin/users/${id}`);
  },
  adminUpdateRole(userId, role) {
    return this.request("PUT", `/admin/users/${userId}/role`, { role });
  },
  adminUpdateActive(userId, isActive) {
    return this.request("PUT", `/admin/users/${userId}/active`, { is_active: isActive });
  },
  adminAuditLogs(params) {
    const q = new URLSearchParams(params || {}).toString();
    return this.request("GET", `/admin/audit?${q}`);
  },
  adminAgents() {
    return this.request("GET", "/admin/agents");
  },
  adminUpdateAgent(key, body) {
    return this.request("PUT", `/admin/agents/${key}`, body);
  },
  adminSettings() {
    return this.request("GET", "/admin/settings");
  },
  adminUpdateSetting(key, value) {
    return this.request("PUT", `/admin/settings/${key}`, { value });
  },
  adminProviders() {
    return this.request("GET", "/admin/providers");
  },
  adminKnowledge() {
    return this.request("GET", "/admin/knowledge");
  },
  adminSecurityEvents(params) {
    const q = new URLSearchParams(params || {}).toString();
    return this.request("GET", `/admin/security-events?${q}`);
  },
  adminHealth() {
    return this.request("GET", "/admin/health");
  },
};

// Formatting helpers
const fmt = {
  currency(v, compact = true) {
    const n = Number(v || 0);
    if (compact && Math.abs(n) >= 1000) {
      return new Intl.NumberFormat("en-US", {
        style: "currency", currency: "USD", notation: "compact", maximumFractionDigits: 1,
      }).format(n);
    }
    return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(n);
  },
  number(v) {
    return new Intl.NumberFormat("en-US").format(Number(v || 0));
  },
  pct(v, d = 1) {
    const n = Number(v || 0);
    const sign = n > 0 ? "+" : "";
    return `${sign}${n.toFixed(d)}%`;
  },
  time(iso) {
    if (!iso) return "—";
    try {
      return new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
    } catch { return iso; }
  },
  date(daysAgo = 0) {
    const d = new Date();
    d.setDate(d.getDate() - daysAgo);
    return d.toISOString();
  },
  ms(ms) {
    const n = Number(ms || 0);
    if (n >= 1000) return `${(n / 1000).toFixed(1)}s`;
    return `${n}ms`;
  },
  text(html) {
    const div = document.createElement("div");
    div.innerHTML = html || "";
    return div.textContent || div.innerText || "";
  },
};