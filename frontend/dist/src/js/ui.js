/* NEXUS shared UI helpers */

const UI = {
  toast(message, type = "info", duration = 3800) {
    const container = document.getElementById("toast-container");
    if (!container) return;
    const t = document.createElement("div");
    t.className = `toast ${type}`;
    t.textContent = message;
    container.appendChild(t);
    setTimeout(() => {
      t.classList.add("out");
      setTimeout(() => t.remove(), 400);
    }, duration);
  },

  el(tag, attrs = {}, children = []) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") node.className = v;
      else if (k === "html") node.innerHTML = v;
      else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
      else if (k === "dataset") Object.assign(node.dataset, v);
      else node.setAttribute(k, v);
    }
    for (const c of [].concat(children)) {
      if (c) node.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    }
    return node;
  },

  metricsCard(label, value, opts = {}) {
    const { sub = "", delta = null, deltaLabel = "", color = "metric-blue", suffix = "" } = opts;
    let deltaHtml = "";
    if (delta !== null) {
      const cls = delta > 0 ? "up" : delta < 0 ? "down" : "flat";
      const arrow = delta > 0 ? "▲" : delta < 0 ? "▼" : "•";
      deltaHtml = `<span class="metric-delta ${cls}">${arrow} ${fmt.pct(Math.abs(delta))}${deltaLabel}</span>`;
    }
    const card = UI.el("div", { class: `card metric-card ${color}` });
    card.innerHTML = `
      <div class="metric-label">${label}</div>
      <div class="metric-value" data-counter="true">${value}<span class="suffix">${suffix}</span></div>
      <div class="metric-sub">${deltaHtml} ${sub}</div>`;
    return card;
  },

  skeletonCard() {
    const c = UI.el("div", { class: "card metric-card skeleton-card" });
    c.innerHTML = `<div class="skeleton-line"></div><div class="skeleton-line short"></div>`;
    return c;
  },

  emptyTableRow(cols, text = "No data available") {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = cols;
    td.className = "empty-state";
    td.textContent = text;
    tr.appendChild(td);
    return tr;
  },

  spinnerButton(btn, on) {
    if (!btn) return;
    if (on) {
      btn.disabled = true;
      btn.classList.add("loading");
      btn.dataset.label = btn.innerHTML;
      btn.innerHTML = `<span class="btn-spinner"></span> Working...`;
    } else {
      btn.disabled = false;
      btn.classList.remove("loading");
      if (btn.dataset.label) btn.innerHTML = btn.dataset.label;
    }
  },
};

/* Chart theme + factory */
const ChartTheme = {
  gridColor: "rgba(107,122,147,0.12)",
  tickColor: "#6b7a93",
  font: { family: "Inter", size: 11 },
};

function makeChart(canvasId, config) {
  const cv = document.getElementById(canvasId);
  if (!cv) return null;
  if (cv._chart) cv._chart.destroy();

  const base = {
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 600, easing: "easeOutQuart" },
    interaction: { mode: "index", intersect: false },
    plugins: {
      legend: {
        labels: {
          color: "#a7b4c9",
          boxWidth: 10,
          boxHeight: 10,
          usePointStyle: true,
          font: ChartTheme.font,
        },
      },
      tooltip: {
        backgroundColor: "rgba(13,17,27,0.95)",
        borderColor: "rgba(96,140,220,0.35)",
        borderWidth: 1,
        titleColor: "#e7edf7",
        bodyColor: "#a7b4c9",
        padding: 10,
        cornerRadius: 8,
      },
    },
    scales: baseScales(config.horizontal),
  };

  const cfg = Object.assign({}, config, {
    options: Object.assign({}, base, config.options || {}),
    data: config.data,
  });
  const chart = new Chart(cv, cfg);
  cv._chart = chart;
  return chart;

  function baseScales(horizontal) {
    const s = {
      x: {
        grid: { color: ChartTheme.gridColor },
        ticks: { color: ChartTheme.tickColor, maxTicksLimit: 8, font: ChartTheme.font },
      },
      y: {
        grid: { color: ChartTheme.gridColor },
        ticks: { color: ChartTheme.tickColor, font: ChartTheme.font },
        beginAtZero: false,
      },
    };
    if (horizontal) {
      s.y.reverse = true;
    }
    return s;
  }
}

const gradients = {
  cyan: (b, g) => g.createLinearGradient(0, 0, 0, b),
  blue: (b, g) => g.createLinearGradient(0, 0, 0, b),
  violet: (b, g) => g.createLinearGradient(0, 0, 0, b),
  green: (b, g) => g.createLinearGradient(0, 0, 0, b),
};

function fillGradient(color, a = { top: 0.35, bottom: 0.02 }) {
  return (context) => {
    const { chart } = context;
    const { ctx, chartArea } = chart;
    if (!chartArea) return "rgba(59,130,246,0.2)";
    const g = ctx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
    g.addColorStop(0, withAlpha(color, a.top));
    g.addColorStop(1, withAlpha(color, a.bottom));
    return g;
  };
}

function withAlpha(hex, a) {
  if (hex.startsWith("rgba")) return hex;
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r},${g},${b},${a})`;
}

const PALETTE = ["#22d3ee", "#3b82f6", "#8b5cf6", "#2dd4bf", "#fbbf24", "#fb923c", "#f87171", "#d946ef"];