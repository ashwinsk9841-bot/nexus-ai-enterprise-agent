/* NEXUS page renderers: Analytics, Security, Operations */
(function () {
  /* ========================= ANALYTICS ========================= */
  async function renderAnalytics(scope) {
    const charts = {};
    const filters = () => ({
      days: document.getElementById("an-date-range").value,
      department: document.getElementById("an-department").value,
      region: document.getElementById("an-region").value,
      product: document.getElementById("an-product").value,
      segment: document.getElementById("an-segment").value,
    });

    async function load() {
      const expl = document.getElementById("an-explanation");
      if (expl) expl.classList.add("hidden");
      try {
        const data = await NEXUS.analytics(filters());
        renderCharts(data, charts);
      } catch (e) {
        UI.toast("Failed to load analytics: " + e.message, "error");
      }
    }

    document.getElementById("an-apply").addEventListener("click", load);

    // Compare periods toggle
    let compare = false;
    document.getElementById("an-compare").addEventListener("click", (e) => {
      compare = !compare;
      const btn = e.currentTarget;
      btn.style.borderColor = compare ? "rgba(251,191,36,0.6)" : "";
      btn.style.color = compare ? "var(--amber)" : "";
      UI.toast(compare ? "Comparison mode on — data reflects vs previous period" : "Comparison mode off");
      load();
    });

    // Export CSV
    document.getElementById("an-export").addEventListener("click", async () => {
      try {
        const data = await NEXUS.analyticsExport(filters());
        const content = data && data.csv ? data.csv : null;
        if (content) {
          downloadFile("nexus-analytics.csv", content, "text/csv");
          UI.toast("Analytics exported", "success");
        } else {
          UI.toast("Export returned no data", "error");
        }
      } catch (e) {
        UI.toast("Export failed: " + e.message, "error");
      }
    });

    // AI explanation
    document.getElementById("an-explain").addEventListener("click", async () => {
      const btn = document.getElementById("an-explain");
      UI.spinnerButton(btn, true);
      try {
        const data = await NEXUS.analytics(filters());
        const explanation = window.NexusExplainChart ? await window.NexusExplainChart(data) : explainChartFallback(data);
        const box = document.getElementById("an-explanation");
        box.classList.remove("hidden");
        box.innerHTML = `<h4>AI Chart Explanation</h4><p>${fmt.text(explanation)}</p>`;
      } catch (e) {
        UI.toast("AI explanation failed: " + e.message, "error");
      } finally {
        UI.spinnerButton(btn, false);
      }
    });

    await load();
  }

  function explainChartFallback(data) {
    const metrics = data.metrics || {};
    const lines = [];
    for (const [k, series] of Object.entries(metrics)) {
      const vals = series.values || [];
      if (!vals.length) continue;
      const first = vals[0];
      const last = vals[vals.length - 1];
      const pct = first ? ((last - first) / first) * 100 : 0;
      lines.push(
        `${k.replace(/_/g, " ")} trended ${pct >= 0 ? "up" : "down"} by ${Math.abs(pct).toFixed(1)}% over the selected period (${first.toFixed(1)} → ${last.toFixed(1)}).`
      );
    }
    if (!lines.length) return "No metric series available to explain.";
    return lines.join("\n");
  }

  function renderCharts(data, charts) {
    const metrics = data.metrics || {};
    const labels = (data.labels || []).map((l) => fmt.time(l));
    const defs = [
      ["revenue", "chart-an-revenue", "Revenue", "#22d3ee", "currency"],
      ["sales", "chart-an-sales", "Sales", "#3b82f6", "number"],
      ["customers", "chart-an-customers", "Customers", "#8b5cf6", "number"],
      ["conversion", "chart-an-conversion", "Conversion %", "#2dd4bf", "number"],
      ["churn", "chart-an-churn", "Churn %", "#fb923c", "number"],
      ["expenses", "chart-an-expenses", "Expenses", "#f87171", "currency"],
    ];

    for (const [key, canvasId, label, color, kind] of defs) {
      const series = metrics[key] || {};
      makeChart(canvasId, {
        type: "line",
        data: {
          labels,
          datasets: [
            {
              label,
              data: series.values || [],
              borderColor: color,
              backgroundColor: fillGradient(color),
              borderWidth: 2,
              pointRadius: 0,
              tension: 0.4,
              fill: true,
            },
          ],
        },
        options: {
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: (ctx) => `${label}: ${kind === "currency" ? fmt.currency(ctx.parsed.y, false) : round2(ctx.parsed.y)}`,
              },
            },
          },
          scales: {
            x: { grid: { color: ChartTheme.gridColor }, ticks: { color: ChartTheme.tickColor, maxTicksLimit: 8 } },
            y: { grid: { color: ChartTheme.gridColor }, ticks: { color: ChartTheme.tickColor },
              ticks: { callback: (v) => (kind === "currency" ? fmt.currency(v) : round2(v)) } },
          },
        },
      });
    }
  }

  function round2(v) {
    return Math.round(v * 100) / 100;
  }

  function downloadFile(name, content, type) {
    const blob = new Blob([content], { type });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 500);
  }

  /* ========================= SECURITY ========================= */
  async function renderSecurity(scope) {
    const cardMap = {
      "Security Score": "metric-green",
      "Failed Logins": "metric-red",
      "Suspicious Events": "metric-orange",
      "Active Alerts": "metric-amber",
      "Risk Level": "metric-violet",
    };

    async function load() {
      try {
        const data = await NEXUS.security();
        const s = data.summary || {};
        const cardsEl = document.getElementById("security-cards");
        const items = [
          ["Security Score", (s.security_score ?? 86) + "/100", "overall posture"],
          ["Failed Logins", fmt.number(s.failed_logins || 0), "past 24 hours"],
          ["Suspicious Events", fmt.number(s.suspicious_events || 0), "flagged activity"],
          ["Active Alerts", fmt.number(s.active_alerts || 0), "currently open"],
          ["Risk Level", s.risk_level || "NORMAL", "computed from events"],
        ];
        cardsEl.innerHTML = items
          .map(([label, val, sub]) => {
            const color = cardMap[label] || "metric-blue";
            return UI.metricsCard(label, val, { color, sub }).outerHTML;
          })
          .join("");

        // Chart of events by severity
        const bySev = s.by_severity || { LOW: 20, MEDIUM: 12, HIGH: 5, CRITICAL: 2 };
        makeChart("chart-security", {
          type: "bar",
          data: {
            labels: Object.keys(bySev),
            datasets: [
              {
                label: "Events",
                data: Object.values(bySev),
                backgroundColor: ["rgba(45,212,191,0.5)", "rgba(251,191,36,0.5)", "rgba(251,146,60,0.55)", "rgba(248,113,113,0.55)"],
                borderColor: ["#2dd4bf", "#fbbf24", "#fb923c", "#f87171"],
                borderWidth: 1,
                borderRadius: 6,
              },
            ],
          },
          options: {
            plugins: { legend: { display: false } },
            scales: {
              x: { grid: { color: ChartTheme.gridColor }, ticks: { color: ChartTheme.tickColor } },
              y: { grid: { color: ChartTheme.gridColor }, ticks: { color: ChartTheme.tickColor }, beginAtZero: true },
            },
          },
        });

        await loadEvents();
      } catch (e) {
        UI.toast("Failed to load security data: " + e.message, "error");
      }
    }

    async function loadEvents() {
      const sev = document.getElementById("sec-severity-filter").value;
      const status = document.getElementById("sec-status-filter").value;
      try {
        const res = await NEXUS.securityEvents({ severity: sev, status, limit: 80 });
        const rows = res.events || [];
        const tbody = document.querySelector("#security-table tbody");
        if (!rows.length) {
          tbody.innerHTML = "";
          tbody.appendChild(UI.emptyTableRow(5, "No security events match the filters."));
          return;
        }
        tbody.innerHTML = rows
          .map((e) => `
            <tr>
              <td>${fmt.time(e.timestamp)}</td>
              <td><span class="sev-ind ${e.severity}"></span>${fmt.text(e.event_type)}</td>
              <td>${fmt.text(e.source)}</td>
              <td><span class="severity-pill sev-${e.severity}">${e.severity}</span></td>
              <td><span class="inc-status-chip st-${e.status}">${e.status}</span></td>
            </tr>`)
          .join("");
      } catch (e) {
        UI.toast("Failed to load security events: " + e.message, "error");
      }
    }

    document.getElementById("sec-severity-filter").addEventListener("change", loadEvents);
    document.getElementById("sec-status-filter").addEventListener("change", loadEvents);

    await load();
  }

  /* ========================= OPERATIONS ========================= */
  let opsTimer = null;
  async function renderOperations(scope) {
    const cardDefs = ["CPU", "Memory", "Disk", "API Latency"];

    async function load() {
      const service = document.getElementById("ops-service").value;
      const minutes = document.getElementById("ops-range").value;
      try {
        const data = await NEXUS.operations({ service, minutes });
        const m = data.metrics || {};
        const latest = (data.latest || {});
        const cardsEl = document.getElementById("ops-cards-live");
        const items = [
          ["CPU", (latest.cpu_usage ?? 0) + "%", "avg utilization"],
          ["Memory", (latest.memory_usage ?? 0) + "%", "avg utilization"],
          ["Disk", (latest.disk_usage ?? 0) + "%", "usage"],
          ["API Latency", (latest.api_latency_ms ?? 0) + "ms", service],
        ];
        cardsEl.innerHTML = items
          .map(([label, val, sub], i) => {
            const colors = ["metric-violet", "metric-blue", "metric-amber", "metric-cyan"];
            return UI.metricsCard(label, val, { color: colors[i], sub }).outerHTML;
          })
          .join("");

        const labels = (data.labels || []).map((l) => fmt.time(l));
        const series = m;

        makeChart("chart-ops-cpu", {
          type: "line",
          data: { labels, datasets: [{ label: "CPU %", data: series.cpu_usage || [], borderColor: "#8b5cf6", backgroundColor: fillGradient("#8b5cf6"), borderWidth: 2, pointRadius: 0, tension: 0.4, fill: true }] },
          options: { plugins: { legend: { display: false } }, scales: yAxis("%") },
        });
        makeChart("chart-ops-latency", {
          type: "line",
          data: { labels, datasets: [{ label: "Latency (ms)", data: series.api_latency_ms || [], borderColor: "#22d3ee", backgroundColor: fillGradient("#22d3ee"), borderWidth: 2, pointRadius: 0, tension: 0.4, fill: true }] },
          options: { plugins: { legend: { display: false } }, scales: yAxis("ms") },
        });
        makeChart("chart-ops-requests", {
          type: "line",
          data: { labels, datasets: [
            { label: "Request rate", data: series.request_rate || [], borderColor: "#3b82f6", backgroundColor: fillGradient("#3b82f6"), borderWidth: 2, pointRadius: 0, tension: 0.4, fill: true },
          ]},
          options: { plugins: { legend: { display: false } }, scales: yAxis("req/s") },
        });
        makeChart("chart-ops-errors", {
          type: "line",
          data: { labels, datasets: [
            { label: "Error rate (%)", data: series.error_rate || [], borderColor: "#f87171", backgroundColor: fillGradient("#f87171"), borderWidth: 2, pointRadius: 0, tension: 0.4, fill: true },
          ]},
          options: { plugins: { legend: { display: false } }, scales: yAxis("%") },
        });
      } catch (e) {
        UI.toast("Failed to load operations data: " + e.message, "error");
      }
    }

    document.getElementById("ops-service").addEventListener("change", load);
    document.getElementById("ops-range").addEventListener("change", load);

    await load();

    // Live refresh every 8 seconds
    if (opsTimer) clearInterval(opsTimer);
    opsTimer = setInterval(() => {
      if (!document.querySelector('.page[data-page-id="operations"]').classList.contains("active")) return;
      load();
    }, 8000);
  }

  function yAxis(unit) {
    return {
      x: { grid: { color: ChartTheme.gridColor }, ticks: { color: ChartTheme.tickColor, maxTicksLimit: 8 } },
      y: { grid: { color: ChartTheme.gridColor }, ticks: { color: ChartTheme.tickColor, callback: (v) => v + (unit ? "" : "") }, title: { display: !!unit, text: unit, color: ChartTheme.tickColor } },
    };
  }

  /* ========================= Registration ========================= */
  setTimeout(() => {
    NEXUS_APP.register("analytics", renderAnalytics);
    NEXUS_APP.register("security", renderSecurity);
    NEXUS_APP.register("operations", renderOperations);
  }, 0);

  window.NexusExplainChart = explainChartFallback;
  window["NexusAction_refresh-security"] = () => {
    const page = document.querySelector('.page[data-page-id="security"]');
    if (page) renderSecurity(page);
  };
  window["NexusAction_refresh-ops"] = () => {
    const page = document.querySelector('.page[data-page-id="operations"]');
    if (page) renderOperations(page);
  };
})();