/* NEXUS page renderers: Overview + AI Command Center */
(function () {
  /* ========================= OVERVIEW ========================= */
  async function renderOverview(scope) {
    const cards = {
      health: document.getElementById("health-cards"),
      biz: document.getElementById("biz-cards"),
      ops: document.getElementById("ops-cards"),
    };

    for (const k of ["health", "biz", "ops"]) {
      if (cards[k]) cards[k].innerHTML = [0, 1, 2, 3].map(() => UI.skeletonCard().outerHTML).join("");
    }

    try {
      const data = await NEXUS.dashboard();

      // Health cards
      if (cards.health) {
        cards.health.innerHTML = "";
        const health = data.health || {};
        const hItems = [
          ["api", "API Health", health.api_health || "HEALTHY", "metric-green"],
          ["db", "Database Health", health.db_health || "HEALTHY", "metric-green"],
          ["srv", "Server Health", health.server_health || "HEALTHY", "metric-green"],
          ["ai", "AI Service Health", health.ai_service_health || "HEALTHY", "metric-green"],
        ];
        for (const [k, label, val, color] of hItems) {
          const state = String(val).toUpperCase();
          const col = state === "HEALTHY" ? "green" : state === "DEGRADED" ? "amber" : "red";
          cards.health.appendChild(
            UI.metricsCard(label, val, { color: "metric-" + col, sub: String(val).toLowerCase() === "healthy" ? "all systems nominal" : "attention required" })
          );
        }
      }

      // Business intelligence
      if (cards.biz) {
        cards.biz.innerHTML = "";
        const biz = data.business || {};
        const threshold = biz.total_revenue >= 5000 ? fmt.currency(biz.total_revenue) : fmt.currency(biz.total_revenue, false);
        const bizItems = [
          ["Revenue", threshold, { color: "metric-cyan", delta: biz.revenue_change, deltaLabel: " vs prev", sub: "period total" }],
          ["Growth", fmt.pct(biz.growth), { color: "metric-green", sub: "customer growth rate" }],
          ["Conversion", biz.conversion + "%", { color: "metric-violet", sub: "lead-to-customer rate" }],
          ["Active Customers", fmt.number(biz.active_customers), { color: "metric-blue", sub: "active accounts", delta: biz.customer_change, deltaLabel: "" }],
        ];
        for (const [label, val, opts] of bizItems) {
          cards.biz.appendChild(UI.metricsCard(label, val, opts));
        }
      }

      // Operational status
      if (cards.ops) {
        cards.ops.innerHTML = "";
        const ops = data.operations || {};
        const opsItems = [
          ["Open Incidents", ops.open_incidents, { color: "metric-amber", sub: "currently tracked" }],
          ["Critical Alerts", ops.critical_alerts, { color: "metric-red", sub: "require immediate attention" }],
          ["Pending Actions", ops.pending_actions, { color: "metric-orange", sub: "awaiting approval" }],
          ["Resolved Issues", ops.resolved_issues, { color: "metric-green", sub: "past 24 hours" }],
        ];
        for (const [label, val, opts] of opsItems) {
          cards.ops.appendChild(UI.metricsCard(label, val, opts));
        }
      }

      // Charts
      renderOverviewCharts(data);

      // Update system status pill
      const statusText = document.getElementById("system-status-text");
      if (statusText) {
        const srv = String((health && health.api_health) || "healthy").toLowerCase();
        statusText.textContent = srv === "healthy" ? "Operational" : "Degraded";
        statusText.parentElement.style.color = srv === "healthy" ? "var(--green)" : "var(--amber)";
      }
    } catch (e) {
      UI.toast("Failed to load dashboard: " + e.message, "error");
      for (const k of ["health", "biz", "ops"]) {
        if (cards[k]) cards[k].innerHTML = `<div class="empty-state">Unavailable — ${fmt.text(e.message)}</div>`;
      }
      return { data: null };
    }
    return { data };
  }

  function renderOverviewCharts(data) {
    const trend = data.trends || {};
    const labels = (trend.labels || []).map((l) => fmt.time(l));

    makeChart("chart-revenue", {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: "Revenue",
            data: trend.revenue || [],
            borderColor: "#22d3ee",
            backgroundColor: fillGradient("#22d3ee"),
            borderWidth: 2,
            pointRadius: 0,
            tension: 0.4,
            fill: true,
          },
        ],
      },
      options: { plugins: { legend: { display: false } } },
    });
    makeChart("chart-customers", {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: "Customers",
            data: trend.customers || [],
            borderColor: "#3b82f6",
            backgroundColor: fillGradient("#3b82f6"),
            borderWidth: 2,
            pointRadius: 0,
            tension: 0.4,
            fill: true,
          },
        ],
      },
      options: { plugins: { legend: { display: false } } },
    });
    makeChart("chart-latency", {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: "Latency (ms)",
            data: trend.latency || [],
            borderColor: "#8b5cf6",
            backgroundColor: fillGradient("#8b5cf6"),
            borderWidth: 2,
            pointRadius: 0,
            tension: 0.3,
            fill: true,
          },
        ],
      },
      options: { plugins: { legend: { display: false } } },
    });
    makeChart("chart-incidents", {
      type: "bar",
      data: {
        labels,
        datasets: [
          {
            label: "Incidents",
            data: trend.incidents || [],
            backgroundColor: "rgba(251,146,60,0.5)",
            borderColor: "#fb923c",
            borderWidth: 1,
            borderRadius: 4,
          },
        ],
      },
      options: {
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { color: ChartTheme.gridColor }, ticks: { color: ChartTheme.tickColor, maxTicksLimit: 8 } },
          y: { grid: { color: ChartTheme.gridColor }, ticks: { color: ChartTheme.tickColor }, beginAtZero: true, } },
      },
    });
  }

  function bindOverviewActions(scope) {
    // The refresh action is wired centrally via window.NexusAction_refresh-dashboard.
  }

  /* ========================= AI COMMAND ========================= */
  async function renderCommand(scope) {
    const input = document.getElementById("command-input");
    const submit = document.getElementById("command-submit");
    const progress = document.getElementById("command-progress");
    const result = document.getElementById("command-result");
    const empty = document.getElementById("command-empty");

    function run(query) {
      if (!query.trim()) {
        UI.toast("Please enter a question first");
        return;
      }
      empty.classList.add("hidden");
      result.classList.add("hidden");
      execute(query);
    }

    submit.addEventListener("click", () => run(input.value));

    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        run(input.value);
      }
    });

    scope.querySelectorAll(".chip").forEach((chip) => {
      chip.addEventListener("click", () => {
        input.value = chip.dataset.query;
        run(chip.dataset.query);
      });
    });

    async function execute(query) {
      // progress placeholders
      progress.innerHTML = `
        <div class="progress-list">
          <div class="progress-item running"><span class="step-ind">1</span><span class="p-label">Selecting agents for: "${query}"</span><span class="p-status">Running</span></div>
        </div>`;
      progress.classList.remove("hidden");

      try {
        const data = await NEXUS.aiAsk(query);
        renderCommandResult(data, query);
      } catch (e) {
        progress.classList.add("hidden");
        result.classList.remove("hidden");
        result.innerHTML = `
          <div class="card result-card">
            <div class="result-query-text" style="color:var(--red)">Analysis failed</div>
            <div class="result-answer">${fmt.text(e.message)}</div>
          </div>`;
      }
    }

    function renderCommandResult(data, query) {
      progress.classList.add("hidden");
      result.classList.remove("hidden");

      const agents = (data.agents_activated || []).map(
        (a) => `<span class="agent-chip-ok"><span class="status-dot"></span>${fmt.text(a.label)}${a.provider && a.provider !== "unconfigured" ? ` <span class="muted">(${fmt.text(a.provider)})</span>` : ""}</span>`
      ).join(" ");

      // Synthesis block
      const synth = data.synthesis || {};
      const synthMeta = synth.provider
        ? `<span class="status-pill">AI · ${fmt.text(synth.provider)} ${fmt.text(synth.model || "")}</span>`
        : `<span class="status-pill ${data.synthetic ? "" : ""}">${data.synthetic ? "Demo-Mode Synthesis" : "Data-Driven"}</span>`;

      // Evidence cards derived from agent findings
      const findings = data.agent_results || [];
      const evidence = findings
        .map((f) => {
          const d = f.details || {};
          const note = f.summary || "";
          let val = "—";
          if (d.change_pct !== undefined) val = fmt.pct(d.change_pct);
          else if (d.risk_level) val = fmt.text(d.risk_level);
          else {
            const first = Object.values(d).find((v) => typeof v === "number");
            if (first !== undefined) val = fmt.number(first);
          }
          return `
          <div class="evidence-card">
            <div class="ev-label">${fmt.text(f.agent)}</div>
            <div class="ev-value">${val}</div>
            <div class="ev-note">${fmt.text(note).slice(0, 110)}</div>
            <div class="ev-meta muted" style="font-size:10px;margin-top:4px;">${f.mode === "ai" ? "AI-analyzed" : "data-driven"} · conf ${Math.round((f.confidence || 0) * 100)}%</div>
          </div>`;
        })
        .join("");

      // Execution trace
      const trace = (data.trace || []).map((t, i) => `
        <div class="progress-item ${i === 0 ? "running" : ""}">
          <span class="step-ind">${i + 1}</span>
          <span class="p-label">${fmt.text(t.step || t.label || "Step")}</span>
          <span class="p-status">${fmt.text(t.status || "OK")}</span>
        </div>
        <div class="trace-detail muted">${fmt.text(t.detail || "")}</div>`).join("");

      // Data gaps
      const gaps = (data.data_gaps || []).map((g) => `<li>${fmt.text(g)}</li>`).join("");
      const gapBlock = gaps ? `<div class="result-block"><h4>Data Gaps</h4><ul>${gaps}</ul></div>` : "";

      // Knowledge
      const kb = data.knowledge || {};
      const kbBlock = kb.used
        ? `<span class="status-pill success">RAG context: ${(kb.sources || []).length} source(s)</span>`
        : `<span class="status-pill neutral">No knowledge context</span>`;

      // Cross-check
      const cc = data.cross_checked || {};
      const ccBlock = `
        <div class="field-group row-between" style="margin:2px 0;">
          <span>Cross-agent corroboration</span>
          <span class="status-pill ${cc.checked ? (cc.conflicts ? "danger" : "success") : "neutral"}">${cc.checked ? (cc.conflicts ? `${cc.conflicts} conflict(s)` : "Consistent") : "Not run"}</span>
        </div>`;

      // Injection guard
      const pkg = data.prompt_injection_guard || {};
      const injBlock = `
        <div class="field-group row-between" style="margin:2px 0;">
          <span>Prompt-injection guard</span>
          <span class="status-pill ${pkg.detected ? "danger" : "success"}">${pkg.detected ? `Blocked (${(pkg.signals || []).length} signal(s))` : "No malicious intent detected"}</span>
        </div>`;

      const recos = buildRecommendations(data);

      result.innerHTML = `
        <div class="card result-card">
          <div class="result-query">Query</div>
          <div class="result-query-text">${fmt.text(query)}</div>
          <div class="result-block">
            <h4>Agents Activated</h4>
            <div class="agents-used">${agents}</div>
          </div>
          <div class="result-block">
            <h4>Executive Synthesis ${synthMeta}</h4>
            <div class="result-answer">${fmt.text(data.result || "No answer produced.")}</div>
            ${synth.note ? `<div class="ev-note muted" style="margin-top:8px;">${fmt.text(synth.note)}</div>` : ""}
          </div>

          <div class="result-block">
            <h4>Evidence</h4>
            <div class="evidence-grid">${evidence || '<div class="empty-state">No evidence captured</div>'}</div>
          </div>

          <div class="result-block">
            <h4>Execution Trace</h4>
            <div class="progress-list">${trace || '<span class="muted">No trace captured</span>'}</div>
          </div>

          <div class="result-block">
            <h4>Guards & Context</h4>
            <div class="guard-list">${injBlock}${ccBlock}<div class="field-group row-between" style="margin:2px 0;"><span>Knowledge base</span>${kbBlock}</div></div>
          </div>

          ${gapBlock}

          <div class="result-block">
            <h4>Root Cause Analysis</h4>
            ${recos.causes}
          </div>

          <div class="result-block">
            <h4>Recommended Actions</h4>
            ${recos.recos || '<div class="empty-state">No recommendations generated</div>'}
          </div>

          <div class="result-meta" style="font-size:11px;color:var(--text-3);margin-top:14px;display:flex;gap:16px;flex-wrap:wrap;">
            <span>Agent runtime: ${fmt.ms(data.duration_ms)}</span>
            <span>Session: ${data.session_id || "—"}</span>
            <span>Synthesis confidence: ${Math.round((synth.confidence || 0) * 100)}%</span>
            ${data.synthetic ? '<span style="color:var(--amber)">Demo-mode synthesis</span>' : ""}
          </div>
        </div>`;
    }

    function buildRecommendations(data) {
      const causes = [];
      const recos = [];

      (data.agent_results || []).forEach((f) => {
        if (f.details && f.details.slo_breaches) {
          const conf = f.details.slo_breaches > 4 ? "high" : "med";
          causes.push(
            `<div class="root-cause-item"><span class="conf ${conf}">${conf === "high" ? "High" : "Medium"} confidence</span><div><div class="rc-title">API latency exceeding SLO</div><div class="rc-detail">${f.details.slo_breaches} windows breached the 300ms target — investigate p95 latency and connection pooling.</div></div></div>`
          );
        }
        if (f.details && f.details.risk_level) {
          causes.push(
            `<div class="root-cause-item"><span class="conf med">Medium confidence</span><div><div class="rc-title">Security risk: ${fmt.text(f.details.risk_level)}</div><div class="rc-detail">Authentication-related anomalies detected in the review window.</div></div></div>`
          );
        }
        if (f.details && f.details.change_pct !== undefined && Math.abs(f.details.change_pct) > 1) {
          const dir = f.details.change_pct < 0 ? "decline" : "increase";
          const conf = Math.abs(f.details.change_pct) > 3 ? "high" : "med";
          causes.push(
            `<div class="root-cause-item"><span class="conf ${conf}">${conf === "high" ? "High" : "Medium"} confidence</span><div><div class="rc-title">Metric ${dir} of ${Math.abs(f.details.change_pct)}%</div><div class="rc-detail">Primary driver is likely a shift in ${fmt.text(f.agent)} activity. Further drill-down recommended.</div></div></div>`
          );
        }
      });

      if (causes.length === 0) {
        causes.push(
          `<div class="root-cause-item"><span class="conf low">Low confidence</span><div><div class="rc-title">Insufficient signal</div><div class="rc-detail">No dominant factor exceeded thresholds in this analysis window. Apply tighter filters for a deeper drill-down.</div></div></div>`
        );
      }

      recos.push(
        `<div class="reco-card">
          <div class="reco-top"><span class="reco-title">Review recent metric trends</span><span class="risk-pill risk-low">Low risk</span></div>
          <div class="reco-desc">Open Analytics to inspect the affected metrics over the last 30 days and confirm the identified shift.</div>
          <div class="reco-meta"><span>Expected impact: Informed decision-making</span><span>Approval: Not required</span></div>
        </div>`
      );

      if (data.query && data.query.toLowerCase().includes("incident") || (data.agent_results || []).find((f) => f.details && (f.details.slo_breaches || f.details.risk_level))) {
        recos.push(
          `<div class="reco-card">
            <div class="reco-top"><span class="reco-title">Dispatch incident response</span><span class="risk-pill risk-medium">Medium risk</span></div>
            <div class="reco-desc">Open a new incident, assign the DevOps agent, and begin investigating the flagged anomaly.</div>
            <div class="reco-meta"><span>Expected impact: Reduced MTTR</span><span>Approval: Manager (optional)</span></div>
            <div class="reco-meta"><button class="btn btn-primary" id="reco-goto-incidents">Open Incidents</button></div>
          </div>`
        );
      }

      recos.push(
        `<div class="reco-card">
          <div class="reco-top"><span class="reco-title">Deeper analysis via RAG knowledge base</span><span class="risk-pill risk-low">Low risk</span></div>
          <div class="reco-desc">Upload runbooks to the Knowledge Center so NEXUS can ground future answers in your documented procedures.</div>
          <div class="reco-meta"><span>Expected impact: Higher-confidence answers</span><span>Approval: Not required</span></div>
        </div>`
      );

      return { causes: causes.join(""), recos: recos.join("") };
    }

    const resultCard = scope.querySelector("#command-result");
    if (resultCard) {
      resultCard.addEventListener("click", (e) => {
        if (e.target.id === "reco-goto-incidents") {
          window.location.hash = "#incidents";
        }
      });
    }
  }

  /* ========================= Registration ========================= */
  window.NexusPage_overview = renderOverview;

  setTimeout(() => {
    NEXUS_APP.register("overview", async (section) => {
      bindOverviewActions(section);
      await renderOverview(section);
    });

    NEXUS_APP.register("command", async (section) => {
      await renderCommand(section);
    });
  }, 0);
})();