/* NEXUS page renderers: Agents, Knowledge, Incidents, Reports */
(function () {
  const AGENT_ICONS = { data: "⇅", analytics: "∿", finance: "$", security: "⬡", devops: "⌘", support: "◎", report: "▤" };
  const AGENT_COLORS = {
    data: "59,130,246", analytics: "34,211,238", finance: "45,212,191", security: "248,113,113",
    devops: "139,92,246", support: "251,146,60", report: "251,191,36",
  };

  /* ========================= AGENTS ========================= */
  async function renderAgents(scope) {
    const grid = document.getElementById("agents-grid");
    grid.innerHTML = [0, 1, 2, 3, 4, 5, 6].map(() => UI.skeletonCard().outerHTML).join("");

    try {
      const res = await NEXUS.agents();
      const agents = res.agents || [];
      grid.innerHTML = "";

      agents.forEach((a, i) => {
        const status = (a.status || "IDLE").toUpperCase();
        const stCls = status.toLowerCase();
        const rgb = AGENT_COLORS[a.key] || "59,130,246";
        const icon = AGENT_ICONS[a.key] || "◆";
        const card = UI.el("div", { class: "card agent-card", style: `--ac:${AGENT_COLORS[a.key] || "#3b82f6"};--ac-rgb:${rgb};animation-delay:${i * 60}ms` });
        card.innerHTML = `
          <div class="agent-head">
            <div class="agent-icon">${icon}</div>
            <span class="status-badge ${stCls}"><span class="pulsing"></span>${status}</span>
          </div>
          <div class="agent-name">${fmt.text(a.name)}</div>
          <div class="agent-desc">${fmt.text(a.description)}</div>
          <div class="agent-stats">
            <div class="agent-stat"><div class="as-label">Success rate</div><div class="as-value">${a.success_rate ?? 0}%</div></div>
            <div class="agent-stat"><div class="as-label">Avg response</div><div class="as-value">${fmt.ms(a.avg_response_ms)}</div></div>
            <div class="agent-stat"><div class="as-label">Total runs</div><div class="as-value">${fmt.number(a.executions_total)}</div></div>
            <div class="agent-stat"><div class="as-label">Last run</div><div class="as-value">${fmt.time(a.last_execution)}</div></div>
          </div>
          <div class="agent-provider" style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin:8px 0 0;">
            <span class="status-pill" style="font-size:10px;">${a.provider || "auto"}</span>
            ${a.model ? `<span class="status-pill" style="font-size:10px;">${fmt.text(a.model)}</span>` : ""}
            <span class="status-pill" style="font-size:10px;">${a.enabled ? "enabled" : "disabled"}</span>
          </div>
          <div class="agent-task-bar">Task: ${fmt.text(a.current_task || "Idle")}</div>`;
        card.addEventListener("click", () => openAgentDetail(a));
        grid.appendChild(card);
      });
    } catch (e) {
      grid.innerHTML = `<div class="empty-state">Failed to load agents: ${fmt.text(e.message)}</div>`;
    }
  }

  async function openAgentDetail(agent) {
    const detail = document.getElementById("agent-detail");
    detail.classList.remove("hidden");
    document.getElementById("agent-detail-name").textContent = agent.name;
    document.getElementById("agent-detail-desc").textContent = agent.description;
    const statusEl = document.getElementById("agent-detail-status");
    statusEl.className = "status-pill";
    statusEl.innerHTML = `<span class="status-dot"></span>${agent.status}`;

    // Stats
    const stats = document.getElementById("agent-detail-stats");
    const items = [
      ["Success rate", agent.success_rate + "%"],
      ["Avg response", fmt.ms(agent.avg_response_ms)],
      ["Total runs", fmt.number(agent.executions_total)],
      ["Succeeded", fmt.number(agent.executions_success)],
    ];
    stats.innerHTML = items.map(([l, v]) => UI.metricsCard(l, v, { color: "metric-blue" }).outerHTML).join("");

    // Load runs
    const tbody = document.querySelector("#agent-runs-table tbody");
    tbody.innerHTML = `<tr><td colspan="4">Loading execution history...</td></tr>`;
    try {
      const res = await NEXUS.agentDetail(agent.id);
      const runs = (res.runs || []).slice(0, 25);
      tbody.innerHTML = runs.length
        ? runs.map((r) => `
            <tr>
              <td>${fmt.time(r.started_at)}</td>
              <td>${fmt.text((r.task || r.query || "").slice(0, 70))}</td>
              <td><span class="inc-status-chip ${r.status === "SUCCESS" ? "st-Resolved" : r.status === "FAILED" ? "st-CRITICAL" : "st-Detected"}">${r.status}</span></td>
              <td>${fmt.ms(r.duration_ms)}</td>
            </tr>`).join("")
        : `<tr><td colspan="4">No execution history.</td></tr>`;
    } catch (e) {
      tbody.innerHTML = `<tr><td colspan="4">${fmt.text(e.message)}</td></tr>`;
    }

    detail.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  /* ========================= KNOWLEDGE ========================= */
  async function renderKnowledge(scope) {
    await loadDocs();

    const drop = document.getElementById("drop-zone");
    const fileInput = document.getElementById("knowledge-file-input");

    drop.addEventListener("click", () => fileInput.click());
    drop.querySelector("#file-picker-btn").addEventListener("click", (e) => {
      e.stopPropagation();
      fileInput.click();
    });

    ["dragover", "dragenter"].forEach((ev) =>
      drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("dragging"); })
    );
    ["dragleave", "drop"].forEach((ev) =>
      drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("dragging"); })
    );
    drop.addEventListener("drop", (e) => {
      const files = e.dataTransfer.files;
      if (files.length) uploadFiles(files);
    });
    fileInput.addEventListener("change", () => {
      if (fileInput.files.length) uploadFiles(fileInput.files);
    });

    // KB ask
    document.getElementById("kb-ask").addEventListener("click", kbAsk);
    document.getElementById("kb-question").addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        kbAsk();
      }
    });

    async function kbAsk() {
      const q = document.getElementById("kb-question").value.trim();
      if (!q) { UI.toast("Enter a question first"); return; }
      const btn = document.getElementById("kb-ask");
      UI.spinnerButton(btn, true);
      document.getElementById("kb-answer").classList.add("hidden");
      try {
        const res = await NEXUS.kbAsk(q);
        const box = document.getElementById("kb-answer");
        document.getElementById("kb-answer-text").textContent = res.answer || "No answer.";
        const sources = res.sources || [];
        document.getElementById("kb-sources").innerHTML = sources.length
          ? sources.map((s) => `<span class="source-chip">📄 ${fmt.text(s.document_title)} <span class="sc-score">${(s.score * 100).toFixed(0)}%</span></span>`).join("")
          : `<span class="empty-state small">No knowledge sources matched.</span>`;
        box.classList.remove("hidden");
      } catch (e) {
        UI.toast("Knowledge query failed: " + e.message, "error");
      } finally {
        UI.spinnerButton(btn, false);
      }
    }
  }

  async function loadDocs() {
    const list = document.getElementById("knowledge-docs");
    try {
      const res = await NEXUS.knowledgeDocs();
      const docs = res.documents || [];
      if (!docs.length) {
        list.innerHTML = `<div class="empty-state small">No documents uploaded yet. Upload runbooks or policies to enable RAG answers.</div>`;
        return;
      }
      list.innerHTML = docs.map((d) => `
        <div class="doc-item">
          <div class="doc-icon">${(d.doc_type || "txt").toUpperCase().slice(0, 4)}</div>
          <div class="doc-info">
            <div class="doc-title">${fmt.text(d.title)}</div>
            <div class="doc-meta">${fmt.text(d.filename)} · ${Math.round((d.size_bytes || 0) / 1024)} KB · ${d.chunk_count} chunks · ${fmt.time(d.created_at)}</div>
          </div>
          <span class="doc-status ${d.status || "PROCESSING"}">${d.status || "PROCESSING"}</span>
        </div>`).join("");
    } catch (e) {
      list.innerHTML = `<div class="empty-state small">Failed to load documents: ${fmt.text(e.message)}</div>`;
    }
  }

  async function uploadFiles(fileList) {
    const files = Array.from(fileList);
    const progress = document.getElementById("upload-progress");
    progress.classList.remove("hidden");
    progress.innerHTML = "";

    for (const file of files) {
      const item = document.createElement("div");
      item.className = "upload-progress-item";
      item.innerHTML = `<span style="flex:1">${fmt.text(file.name)}</span><span class="p-status" style="color:var(--amber)">Uploading...</span>`;
      progress.appendChild(item);
      const fd = new FormData();
      fd.append("files", file);
      fd.append("title", file.name.replace(/\.[^.]+$/, ""));
      try {
        await NEXUS.uploadKnowledge(fd);
        item.querySelector(".p-status").textContent = "✓ Done";
        item.querySelector(".p-status").style.color = "var(--green)";
      } catch (e) {
        item.querySelector(".p-status").textContent = "Failed";
        item.querySelector(".p-status").style.color = "var(--red)";
        item.title = e.message;
      }
    }
    UI.toast(`Uploaded ${files.length} document${files.length > 1 ? "s" : ""}`, "success");
    await loadDocs();
  }

  /* ========================= INCIDENTS ========================= */
  let currentIncidentList = [];

  async function renderIncidents(scope) {
    const filters = () => ({
      status: document.getElementById("inc-status-filter").value,
      severity: document.getElementById("inc-severity-filter").value,
    });

    async function load() {
      try {
        const res = await NEXUS.incidents(filters());
        currentIncidentList = res.incidents || [];
        renderList();
      } catch (e) {
        document.getElementById("incidents-list").innerHTML = `<div class="empty-state">Failed to load incidents: ${fmt.text(e.message)}</div>`;
      }
    }

    function renderList() {
      const list = document.getElementById("incidents-list");
      if (!currentIncidentList.length) {
        list.innerHTML = `<div class="empty-state">No incidents match the current filters.</div>`;
        return;
      }
      list.innerHTML = currentIncidentList.map((inc, i) => {
        const stCls = (inc.status || "").replace(/\s+/g, "");
        return `
        <div class="card incident-card" data-inc="${inc.id}" style="animation-delay:${i * 40}ms">
          <div class="inc-top">
            <span class="inc-id">${fmt.text(inc.incident_id)}</span>
            <span class="severity-pill sev-${inc.severity}">${inc.severity}</span>
            <span class="inc-status-chip st-${stCls}">${inc.status}</span>
          </div>
          <div class="inc-title">${fmt.text(inc.title)}</div>
          <div class="inc-desc">${fmt.text(inc.description)}</div>
          <div class="inc-meta">
            <span>Created ${fmt.time(inc.created_at)}</span>
            <span>Agent: ${fmt.text(inc.assigned_agent)}</span>
            <span>${fmt.text(inc.assignee || "Unassigned")}</span>
          </div>
        </div>`;
      }).join("");

      list.querySelectorAll(".incident-card").forEach((card) => {
        card.addEventListener("click", () => openIncidentDetail(card.dataset.inc));
      });
    }

    document.getElementById("inc-status-filter").addEventListener("change", load);
    document.getElementById("inc-severity-filter").addEventListener("change", load);

    await load();

    // New incident modal
    const newBtn = document.getElementById("inc-new-btn");
    newBtn.addEventListener("click", () => openIncidentModal());

    const form = document.getElementById("incident-form");
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const id = document.getElementById("inc-id").value;
      const payload = {
        title: document.getElementById("inc-title").value,
        description: document.getElementById("inc-desc").value,
        severity: document.getElementById("inc-severity").value,
        status: document.getElementById("inc-status").value,
        assigned_agent: document.getElementById("inc-agent").value,
        assignee: document.getElementById("inc-assignee").value,
        root_cause: document.getElementById("inc-rootcause").value,
        resolution: document.getElementById("inc-resolution").value,
      };
      const btn = e.target.querySelector('button[type="submit"]');
      UI.spinnerButton(btn, true);
      try {
        if (id) {
          await NEXUS.updateIncident(id, payload);
          UI.toast("Incident updated", "success");
        } else {
          await NEXUS.createIncident(payload);
          UI.toast("Incident created", "success");
        }
        closeAllModalsLocal();
        await load();
      } catch (err) {
        UI.toast("Save failed: " + err.message, "error");
      } finally {
        UI.spinnerButton(btn, false);
      }
    });

    // Detail actions
    document.getElementById("inc-detail-close").addEventListener("click", () => {
      document.getElementById("incident-detail").classList.add("hidden");
    });
    document.getElementById("inc-add-note-btn").addEventListener("click", async () => {
      const note = prompt("Add a timeline note:");
      if (note && note.trim()) {
        try {
          const inc = document.getElementById("incident-detail").dataset.incId;
          await NEXUS.updateIncident(inc, { note: note.trim(), event_type: "note" });
          UI.toast("Note added", "success");
          await openIncidentDetail(inc);
        } catch (e) { UI.toast("Failed: " + e.message, "error"); }
      }
    });
    document.getElementById("inc-update-status-btn").addEventListener("click", () => {
      const inc = document.getElementById("incident-detail").dataset.incId;
      const current = document.querySelector("#inc-detail-meta [data-field=status]");
      openIncidentModal(current ? current.textContent : undefined, inc);
    });

    function closeAllModalsLocal() {
      document.querySelectorAll(".modal").forEach((m) => m.classList.add("hidden"));
    }
    scope.querySelectorAll("[data-close-modal]").forEach((el) => el.addEventListener("click", closeAllModalsLocal));
  }

  function openIncidentModal(status, id) {
    const modal = document.getElementById("incident-modal");
    document.getElementById("inc-modal-title").textContent = id || !id ? "Edit Incident" : "New Incident";
    if (!id) {
      document.getElementById("incident-form").reset();
      document.getElementById("inc-id").value = "";
      if (status) document.getElementById("inc-status").value = status;
    }
    modal.classList.remove("hidden");
  }

  async function openIncidentDetail(id) {
    try {
      const inc = await NEXUS.incidentDetail(id);
      const detail = document.getElementById("incident-detail");
      detail.dataset.incId = inc.id;
      detail.classList.remove("hidden");
      document.getElementById("inc-detail-title").textContent = inc.title + " — " + inc.incident_id;
      const sevEl = document.getElementById("inc-detail-sev");
      sevEl.className = `severity-pill sev-${inc.severity}`;
      sevEl.textContent = inc.severity;
      document.getElementById("inc-detail-desc").textContent = inc.description || "";

      const meta = document.getElementById("inc-detail-meta");
      const items = [
        ["Status", inc.status, "metric-amber"],
        ["Assigned agent", inc.assigned_agent, "metric-blue"],
        ["Assignee", inc.assignee || "Unassigned", "metric-violet"],
        ["Created", fmt.time(inc.created_at), "metric-green"],
      ];
      meta.innerHTML = items.map(([l, v, c]) => UI.metricsCard(l, v, { color: c }).outerHTML).join("");

      const timeline = document.getElementById("inc-timeline");
      const events = inc.events || [];
      timeline.innerHTML = events.length
        ? events.map((ev) => `
            <div class="tl-item ${ev.event_type || "note"}">
              <div class="tl-msg">${fmt.text(ev.message)}</div>
              <div class="tl-meta">${fmt.time(ev.timestamp)} · ${fmt.text(ev.actor)}</div>
            </div>`).join("")
        : `<div class="empty-state small">No timeline events.</div>`;

      detail.scrollIntoView({ behavior: "smooth", block: "nearest" });
    } catch (e) {
      UI.toast("Failed to load incident: " + e.message, "error");
    }
  }

  /* ========================= REPORTS ========================= */
  async function renderReports(scope) {
    await loadReports();

    document.getElementById("rep-generate").addEventListener("click", async () => {
      const type = document.getElementById("rep-type").value;
      const range = document.getElementById("rep-range").value;
      const btn = document.getElementById("rep-generate");
      UI.spinnerButton(btn, true);
      try {
        const res = await NEXUS.generateReport(type, range);
        UI.toast("Report generated", "success");
        await loadReports();
        if (res.report && res.report.id) viewReport(res.report);
      } catch (e) {
        UI.toast("Report generation failed: " + e.message, "error");
      } finally {
        UI.spinnerButton(btn, false);
      }
    });

    document.getElementById("report-print").addEventListener("click", () => {
      const body = document.getElementById("report-view-body");
      if (!body) return;
      const win = window.open("", "_blank");
      win.document.write(`<html><head><title>NEXUS Report</title><style>body{font-family:Inter,sans-serif;padding:32px;max-width:800px;margin:auto;color:#111} h1{font-size:22px} h4{margin-top:20px;text-transform:uppercase;letter-spacing:1px;font-size:12px;color:#555}</style></head><body>${body.innerHTML}</body></html>`);
      win.document.close();
      win.print();
    });
  }

  async function loadReports() {
    const list = document.getElementById("reports-list");
    try {
      const res = await NEXUS.reports();
      const reports = res.reports || [];
      if (!reports.length) {
        list.innerHTML = `<div class="empty-state">No reports generated yet. Create one above.</div>`;
        return;
      }
      list.innerHTML = reports.map((r, i) => `
        <div class="card report-item" data-report="${r.id}" style="animation-delay:${i * 50}ms">
          <div class="report-ico">🗎</div>
          <div class="report-info">
            <div class="report-title">${fmt.text(r.title)}</div>
            <div class="report-meta">${fmt.text(r.report_type)} · ${fmt.time(r.created_at)} · by ${fmt.text(r.created_by)}</div>
          </div>
          <span class="inc-status-chip st-Resolved">open</span>
        </div>`).join("");

      list.querySelectorAll(".report-item").forEach((el) => el.addEventListener("click", async () => {
        try {
          const res = await NEXUS.reports();
          const report = res.reports.find((r) => String(r.id) === String(el.dataset.report));
          if (report) viewReport(report);
        } catch (e) { UI.toast("Failed: " + e.message, "error"); }
      }));
    } catch (e) {
      list.innerHTML = `<div class="empty-state">Failed to load reports: ${fmt.text(e.message)}</div>`;
    }
  }

  function viewReport(report) {
    const view = document.getElementById("report-view");
    view.classList.remove("hidden");
    document.getElementById("report-view-title").textContent = report.title;
    let content = report.content;
    let parsed = null;
    try { parsed = JSON.parse(content); } catch {}
    const body = document.getElementById("report-view-body");

    if (parsed) {
      body.innerHTML = `
        <h4>Executive Summary</h4>
        <p>${fmt.text(parsed.summary)}</p>
        ${parsed.key_metrics ? `<h4>Key Metrics</h4><div class="report-metric-inline">${parsed.key_metrics.map((m) => `<span>${fmt.text(m)}</span>`).join("")}</div>` : ""}
        ${parsed.changes && parsed.changes.length ? `<h4>Important Changes</h4><ul>${parsed.changes.map((c) => `<li>${fmt.text(c)}</li>`).join("")}</ul>` : ""}
        ${parsed.incidents && parsed.incidents.length ? `<h4>Incidents</h4><ul>${parsed.incidents.map((c) => `<li>${fmt.text(c)}</li>`).join("")}</ul>` : ""}
        ${parsed.root_causes && parsed.root_causes.length ? `<h4>Root Causes</h4><ul>${parsed.root_causes.map((c) => `<li>${fmt.text(c)}</li>`).join("")}</ul>` : ""}
        ${parsed.recommendations && parsed.recommendations.length ? `<h4>Recommendations</h4><ul>${parsed.recommendations.map((c) => `<li>${fmt.text(c)}</li>`).join("")}</ul>` : ""}`;
    } else {
      body.innerHTML = `<p>${fmt.text(content)}</p>`;
    }
    view.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  /* ========================= Registration ========================= */
  setTimeout(() => {
    NEXUS_APP.register("agents", renderAgents);
    NEXUS_APP.register("knowledge", renderKnowledge);
    NEXUS_APP.register("incidents", renderIncidents);
    NEXUS_APP.register("reports", renderReports);
  }, 0);

  window["NexusAction_refresh-agents"] = () => {
    const page = document.querySelector('.page[data-page-id="agents"]');
    if (page) renderAgents(page);
  };
  window["NexusAction_refresh-dashboard"] = () => {
    const page = document.querySelector('.page[data-page-id="overview"]');
    if (window.NexusPage_overview) {
      window.NexusPage_overview(page);
      if (window.NEXUS_APP && NEXUS_APP.rebind) NEXUS_APP.rebind(page);
      UI.toast("Dashboard refreshed", "success");
    } else {
      UI.toast("Dashboard unavailable right now", "error");
    }
  };
})();