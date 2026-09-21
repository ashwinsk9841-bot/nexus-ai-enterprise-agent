/* NEXUS admin console page renderer */
(function () {
  async function renderAdmin(section) {
    // Refresh toggle
    const refreshBtn = section.querySelector("[data-action='refresh-admin']");
    if (refreshBtn) refreshBtn.addEventListener("click", () => renderAdmin(section));

    // Load stats
    const statsEl = document.getElementById("admin-stats");
    if (statsEl) statsEl.innerHTML = [0, 1, 2, 3].map(() => UI.skeletonCard().outerHTML).join("");
    try {
      const stats = await NEXUS.adminDashboard();
      if (statsEl) {
        statsEl.innerHTML = "";
        const items = [
          ["Users", stats.total_users, { color: "metric-cyan", sub: `${stats.active_users} active` }],
          ["Agents", stats.total_agents, { color: "metric-violet", sub: "specialist fleet" }],
          ["Audit Events", stats.total_audit_events, { color: "metric-blue", sub: "tracked actions" }],
          ["Open Incidents", stats.open_incidents, { color: "metric-amber", sub: `${stats.total_incidents} total` }],
        ];
        for (const [label, val, opts] of items) statsEl.appendChild(UI.metricsCard(label, val, opts));
      }
    } catch (e) {
      if (statsEl) statsEl.innerHTML = `<div class="empty-state">Admin unavailable — ${fmt.text(e.message)}</div>`;
    }

    bindAdminTabs(section);
    loadUsers(section);
    loadAuditLogs(section);
    loadSecurityEvents(section);
    loadAgentConfigs(section);
    loadSettings(section);
  }

  function bindAdminTabs(section) {
    section.querySelectorAll(".admin-tab").forEach((tab) => {
      tab.addEventListener("click", () => {
        section.querySelectorAll(".admin-tab").forEach((t) => t.classList.remove("active"));
        tab.classList.add("active");
        section.querySelectorAll(".admin-tab-panel").forEach((p) => p.classList.add("hidden"));
        const panel = section.querySelector(`#admin-${tab.dataset.tab}`);
        if (panel) panel.classList.remove("hidden");
      });
    });
  }

  // ---- Users ----
  async function loadUsers(section) {
    const tbody = section.querySelector("#admin-users-table tbody");
    if (!tbody) return;
    tbody.innerHTML = `<tr><td class="muted">Loading users...</td></tr>`;
    try {
      const data = await NEXUS.adminUsers();
      const rows = (data.users || []).map((u) => `
        <tr>
          <td><strong>${fmt.text(u.full_name || u.username)}</strong><br><span class="muted">${fmt.text(u.email)}</span></td>
          <td>
            <select class="input role-select" data-uid="${u.id}" ${u.demo_account ? "disabled title='Demo account'" : ""}>
              ${["VIEWER","ANALYST","MANAGER","ADMIN"].map(r => `<option value="${r}" ${u.role === r ? "selected" : ""}>${r}</option>`).join("")}
            </select>
          </td>
          <td><span class="status-pill ${u.is_active ? "" : "danger"}">${u.is_active ? "Active" : "Disabled"}</span></td>
          <td class="muted">${fmt.time(u.last_login)}</td>
          <td>
            ${u.is_active ? `<button class="btn btn-ghost btn-sm" data-toggle-user="${u.id}" data-active="1">Disable</button>` : `<button class="btn btn-ghost btn-sm" data-toggle-user="${u.id}" data-active="0">Enable</button>`}
          </td>
        </tr>`).join("");
      tbody.innerHTML = rows || `<tr><td class="muted" colspan="5">No users.</td></tr>`;

      tbody.querySelectorAll(".role-select").forEach((sel) => {
        sel.addEventListener("change", async () => {
          try {
            await NEXUS.adminUpdateRole(Number(sel.dataset.uid), sel.value);
            UI.toast("Role updated", "success");
          } catch (err) {
            UI.toast(err.message, "error");
          }
        });
      });
      tbody.querySelectorAll("[data-toggle-user]").forEach((btn) => {
        btn.addEventListener("click", async () => {
          const id = Number(btn.dataset.toggleUser);
          const active = btn.dataset.active === "1" ? false : true;
          try {
            await NEXUS.adminUpdateActive(id, active);
            UI.toast(active ? "User enabled" : "User disabled", "success");
            loadUsers(section);
          } catch (err) {
            UI.toast(err.message, "error");
          }
        });
      });

      const search = section.querySelector("#admin-user-search");
      if (search) {
        search.addEventListener("input", async () => {
          const data = await NEXUS.adminUsers({ search: search.value.trim() });
          const sRows = (data.users || []).map((u) => `
            <tr>
              <td><strong>${fmt.text(u.full_name || u.username)}</strong><br><span class="muted">${fmt.text(u.email)}</span></td>
              <td><span class="status-pill">${u.role}</span></td>
              <td><span class="status-pill ${u.is_active ? "" : "danger"}">${u.is_active ? "Active" : "Disabled"}</span></td>
              <td class="muted">${fmt.time(u.last_login)}</td>
              <td><span class="muted">${u.demo_account ? "demo" : "managed"}</span></td>
            </tr>`).join("");
          tbody.innerHTML = sRows || `<tr><td class="muted" colspan="5">No matches.</td></tr>`;
        });
      }
    } catch (err) {
      tbody.innerHTML = `<tr><td class="muted">Failed to load users — ${fmt.text(err.message)}</td></tr>`;
    }
  }

  // ---- Audit ----
  async function loadAuditLogs(section) {
    const tbody = section.querySelector("#admin-audit-table tbody");
    if (!tbody) return;
    tbody.innerHTML = `<tr><td class="muted">Loading audit log...</td></tr>`;
    try {
      const data = await NEXUS.adminAuditLogs();
      const rows = (data.logs || []).map((l) => `
        <tr>
          <td class="muted">${fmt.time(l.created_at)}</td>
          <td>${fmt.text(l.username) || "system"}</td>
          <td><span class="status-pill">${fmt.text(l.action)}</span></td>
          <td class="muted">${fmt.text(l.resource)}</td>
          <td><span class="status-pill ${l.result === "FAILURE" ? "danger" : ""}">${fmt.text(l.result)}</span></td>
          <td class="muted" title="${fmt.text(l.details)}">${fmt.text(l.details).slice(0, 60)}</td>
        </tr>`).join("");
      tbody.innerHTML = rows || `<tr><td class="muted" colspan="6">No audit entries yet.</td></tr>`;
    } catch (err) {
      tbody.innerHTML = `<tr><td class="muted">Failed — ${fmt.text(err.message)}</td></tr>`;
    }
  }

  // ---- Security events ----
  async function loadSecurityEvents(section) {
    const tbody = section.querySelector("#admin-security-table tbody");
    if (!tbody) return;
    tbody.innerHTML = `<tr><td class="muted">Loading security events...</td></tr>`;
    try {
      const data = await NEXUS.adminSecurityEvents();
      const rows = (data.events || []).map((e) => `
        <tr>
          <td class="muted">${fmt.time(e.timestamp)}</td>
          <td>${fmt.text(e.event_type)}</td>
          <td><span class="risk-pill risk-${String(e.severity).toLowerCase()}">${e.severity}</span></td>
          <td class="muted">${fmt.text(e.source)}</td>
          <td><span class="status-pill">${e.status}</span></td>
        </tr>`).join("");
      tbody.innerHTML = rows || `<tr><td class="muted" colspan="5">No security events.</td></tr>`;
    } catch (err) {
      tbody.innerHTML = `<tr><td class="muted">Failed — ${fmt.text(err.message)}</td></tr>`;
    }
  }

  // ---- Agent configs ----
  async function loadAgentConfigs(section) {
    const tbody = section.querySelector("#admin-agents-table tbody");
    if (!tbody) return;
    tbody.innerHTML = `<tr><td class="muted">Loading agent configs...</td></tr>`;
    try {
      const data = await NEXUS.adminAgents();
      const rows = (data.agents || []).map((a) => `
        <tr>
          <td><strong>${fmt.text(a.name)}</strong><br><span class="muted">${a.key}</span></td>
          <td><input class="input provider-input" data-key="${a.key}" value="${fmt.text(a.provider)}" placeholder="auto (openai)" style="width:110px;" /></td>
          <td><input class="input model-input" data-key="${a.key}" value="${fmt.text(a.model)}" placeholder="default" style="width:130px;" /></td>
          <td><label class="checkbox-label"><input type="checkbox" class="enabled-check" data-key="${a.key}" ${a.enabled ? "checked" : ""} /><span class="checkbox-custom"></span></label></td>
          <td><button class="btn btn-ghost btn-sm" data-save-agent="${a.key}">Save</button></td>
        </tr>`).join("");
      tbody.innerHTML = rows || `<tr><td class="muted" colspan="5">No agents.</td></tr>`;

      tbody.querySelectorAll("[data-save-agent]").forEach((btn) => {
        btn.addEventListener("click", async () => {
          const key = btn.dataset.saveAgent;
          const provider = tbody.querySelector(`.provider-input[data-key="${key}"]`).value.trim();
          const model = tbody.querySelector(`.model-input[data-key="${key}"]`).value.trim();
          const enabled = tbody.querySelector(`.enabled-check[data-key="${key}"]`).checked;
          try {
            await NEXUS.adminUpdateAgent(key, { provider, model, enabled });
            UI.toast(`${key} config updated`, "success");
          } catch (err) {
            UI.toast(err.message, "error");
          }
        });
      });
    } catch (err) {
      tbody.innerHTML = `<tr><td class="muted">Failed — ${fmt.text(err.message)}</td></tr>`;
    }
  }

  // ---- Settings ----
  async function loadSettings(section) {
    const listEl = section.querySelector("#admin-settings-list");
    if (!listEl) return;
    try {
      const data = await NEXUS.adminSettings();
      const settings = data.settings || {};
      const known = Object.keys(settings).length ? settings : { welcome_message: "NEXUS Enterprise AI — welcome to the command center", default_dashboard: "overview" };
      listEl.innerHTML = Object.entries(known).map(([k, v]) => `
        <div class="field-group row-between" style="margin-bottom:12px;">
          <label for="setting-${k}" style="flex:1;"><strong>${fmt.text(k)}</strong><br><span class="muted" style="font-size:11px;">System key/value</span></label>
          <div style="display:flex;gap:8px;align-items:center;">
            <input class="input" id="setting-${k}" value="${fmt.text(v)}" style="min-width:220px;" />
            <button class="btn btn-ghost btn-sm" data-save-setting="${k}">Save</button>
          </div>
        </div>`).join("");
      listEl.querySelectorAll("[data-save-setting]").forEach((btn) => {
        btn.addEventListener("click", async () => {
          const key = btn.dataset.saveSetting;
          const value = listEl.querySelector(`#setting-${key}`).value;
          try {
            await NEXUS.adminUpdateSetting(key, value);
            UI.toast("Setting saved", "success");
          } catch (err) {
            UI.toast(err.message, "error");
          }
        });
      });
    } catch (err) {
      listEl.innerHTML = `<div class="empty-state">Failed — ${fmt.text(err.message)}</div>`;
    }
  }

  setTimeout(() => {
    NEXUS_APP.register("admin", async (section) => {
      await renderAdmin(section);
    });
  }, 0);
})();