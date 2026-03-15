/* app.js - YouTube Automation Dashboard */

const PALETTE = [
  "#6c63ff", "#e040fb", "#26c6da", "#66bb6a",
  "#ffa726", "#ef5350", "#ab47bc", "#42a5f5",
];

const RANK_EMOJI = { 1: "🥇", 2: "🥈", 3: "🥉" };

/* ── Fetch summary.json ───────────────────────────────── */
async function loadData() {
  const resp = await fetch("summary.json?" + Date.now());
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

/* ── Format helpers ───────────────────────────────────── */
const fmt = (n, digits = 0) =>
  typeof n === "number" ? n.toLocaleString("ja-JP", { maximumFractionDigits: digits }) : "—";

const fmtCtr = (v) => (typeof v === "number" ? (v * 100).toFixed(1) + "%" : "—");
const fmtHours = (mins) => fmt(Math.round(mins / 60));
const fmtScore = (v) => (typeof v === "number" ? v.toFixed(4) : "0.0000");

/* ── Account cards ────────────────────────────────────── */
function renderCards(accounts) {
  const grid = document.getElementById("account-cards");
  grid.innerHTML = "";

  accounts.forEach((a, i) => {
    const rank = a.score_rank ?? (i + 1);
    const m7 = a.metrics_7d ?? {};
    const priority = a.priority ?? "low";
    const rankEmoji = RANK_EMOJI[rank] ?? `#${rank}`;

    const card = document.createElement("div");
    card.className = `account-card${rank <= 3 ? " rank-" + rank : ""}`;
    card.innerHTML = `
      <span class="card-rank">${rankEmoji}</span>
      <div class="card-name">${a.display_name ?? a.account_id}</div>
      <div class="card-genre">${a.genre ?? ""}</div>
      <div class="card-score">${fmtScore(a.score)}</div>
      <div class="card-score-label">Performance Score</div>
      <div class="card-stats">
        <div class="card-stat">
          <span class="card-stat-label">視聴数(7d)</span>
          <span class="card-stat-value">${fmt(m7.views)}</span>
        </div>
        <div class="card-stat">
          <span class="card-stat-label">登録者増(7d)</span>
          <span class="card-stat-value">${fmt(m7.subscribersNet, 0)}</span>
        </div>
        <div class="card-stat">
          <span class="card-stat-label">CTR(7d)</span>
          <span class="card-stat-value">${fmtCtr(m7.impressionsClickThroughRate)}</span>
        </div>
        <div class="card-stat">
          <span class="card-stat-label">投稿頻度</span>
          <span class="card-stat-value">${a.videos_per_week ?? "—"}本/週</span>
        </div>
      </div>
      <span class="pill pill-${priority}">${priority}</span>
    `;
    grid.appendChild(card);
  });
}

/* ── Bar chart helper ─────────────────────────────────── */
function barChart(canvasId, labels, datasets, unit = "") {
  const ctx = document.getElementById(canvasId).getContext("2d");
  new Chart(ctx, {
    type: "bar",
    data: { labels, datasets },
    options: {
      responsive: true,
      plugins: {
        legend: { labels: { color: "#aaa", font: { size: 11 } } },
        tooltip: {
          callbacks: {
            label: (c) => ` ${c.dataset.label}: ${c.formattedValue}${unit}`,
          },
        },
      },
      scales: {
        x: { ticks: { color: "#888" }, grid: { color: "#2a2a3a" } },
        y: { ticks: { color: "#888" }, grid: { color: "#2a2a3a" } },
      },
    },
  });
}

/* ── Bar charts ───────────────────────────────────────── */
function renderBarCharts(accounts) {
  const labels = accounts.map((a) => a.display_name ?? a.account_id);
  const colors = accounts.map((_, i) => PALETTE[i % PALETTE.length]);

  // Views
  barChart("chart-views", labels, [{
    label: "視聴数",
    data: accounts.map((a) => a.metrics_7d?.views ?? 0),
    backgroundColor: colors,
    borderRadius: 6,
  }]);

  // Subscribers net
  barChart("chart-subs", labels, [{
    label: "登録者増減",
    data: accounts.map((a) => a.metrics_7d?.subscribersNet ?? 0),
    backgroundColor: accounts.map((a) => (a.metrics_7d?.subscribersNet ?? 0) >= 0 ? "#4caf50" : "#ef5350"),
    borderRadius: 6,
  }]);

  // CTR
  barChart("chart-ctr", labels, [{
    label: "CTR (%)",
    data: accounts.map((a) => parseFloat(((a.metrics_7d?.impressionsClickThroughRate ?? 0) * 100).toFixed(2))),
    backgroundColor: colors,
    borderRadius: 6,
  }], "%");
}

/* ── Trend line chart ─────────────────────────────────── */
function renderTrendChart(accounts) {
  const ctx = document.getElementById("chart-trend").getContext("2d");

  // 全アカウントの日付ユニオンを取得
  const dateSet = new Set();
  accounts.forEach((a) => (a.daily_trend ?? []).forEach((d) => dateSet.add(d.date)));
  const labels = [...dateSet].sort();

  const datasets = accounts.map((a, i) => {
    const map = {};
    (a.daily_trend ?? []).forEach((d) => { map[d.date] = d.views; });
    return {
      label: a.display_name ?? a.account_id,
      data: labels.map((d) => map[d] ?? null),
      borderColor: PALETTE[i % PALETTE.length],
      backgroundColor: "transparent",
      tension: 0.3,
      pointRadius: 2,
      spanGaps: true,
    };
  });

  new Chart(ctx, {
    type: "line",
    data: { labels, datasets },
    options: {
      responsive: true,
      plugins: {
        legend: { labels: { color: "#aaa", font: { size: 11 } } },
      },
      scales: {
        x: { ticks: { color: "#888", maxTicksLimit: 10 }, grid: { color: "#2a2a3a" } },
        y: { ticks: { color: "#888" }, grid: { color: "#2a2a3a" } },
      },
    },
  });
}

/* ── Metrics table ────────────────────────────────────── */
function renderTable(accounts) {
  const tbody = document.getElementById("metrics-tbody");
  tbody.innerHTML = "";

  accounts.forEach((a, i) => {
    const rank = a.score_rank ?? (i + 1);
    const m7 = a.metrics_7d ?? {};
    const badgeClass = rank <= 3 ? `rank-${rank}-bg` : "";
    const rankBadge = `<span class="rank-badge ${badgeClass}">${rank}</span>`;
    const priorityPill = `<span class="pill pill-${a.priority ?? "low"}">${a.priority ?? "low"}</span>`;

    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${rankBadge}</td>
      <td>${a.display_name ?? a.account_id}</td>
      <td>${a.genre ?? ""}</td>
      <td>${fmtScore(a.score)}</td>
      <td>${fmt(m7.views)}</td>
      <td>${fmtHours(m7.estimatedMinutesWatched)}</td>
      <td>${fmt(m7.subscribersNet, 0)}</td>
      <td>${fmtCtr(m7.impressionsClickThroughRate)}</td>
      <td>${fmt(m7.averageViewPercentage, 1)}%</td>
      <td>${a.videos_per_week ?? "—"}本/週</td>
      <td>${priorityPill}</td>
    `;
    tbody.appendChild(tr);
  });
}

/* ── Main ─────────────────────────────────────────────── */
(async () => {
  try {
    const data = await loadData();
    const accounts = data.accounts ?? [];

    document.getElementById("last-updated").textContent = data.generated_at ?? "不明";
    document.getElementById("loading").style.display = "none";
    document.getElementById("main-content").style.display = "block";

    if (accounts.length === 0) {
      document.getElementById("main-content").innerHTML =
        '<p class="message">まだデータがありません。最初の Analytics 収集後に表示されます。</p>';
      return;
    }

    renderCards(accounts);
    renderBarCharts(accounts);
    renderTrendChart(accounts);
    renderTable(accounts);
  } catch (err) {
    console.error(err);
    document.getElementById("loading").style.display = "none";
    document.getElementById("error").style.display = "block";
    document.getElementById("error").textContent =
      `データの読み込みに失敗しました: ${err.message}`;
  }
})();
