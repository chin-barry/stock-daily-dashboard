// GitHub Pages 的 CDN／瀏覽器對這些 JSON 檔常常快取超過資料實際更新的頻率，
// 加上一個隨機查詢參數確保每次載入都拿到最新版本。
async function fetchJSON(url) {
  const sep = url.includes("?") ? "&" : "?";
  const res = await fetch(`${url}${sep}_=${Date.now()}`);
  return res.json();
}

function signClass(n) {
  if (n > 0) return "up";
  if (n < 0) return "down";
  return "flat";
}

function fmtIndexValue(n) {
  return n.toLocaleString("zh-TW", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtSigned(n, digits) {
  const s = n.toFixed(digits);
  return n >= 0 ? `+${s}` : s;
}

// 三大法人買賣超金額（元）換算成「億元」比較好讀
function fmtNetYi(yuan) {
  const yi = yuan / 1e8;
  return `${fmtSigned(yi, 2)} 億`;
}

function fmtBalance(value, unit) {
  if (unit === "元") {
    return `${(value / 1e8).toFixed(2)} 億元`;
  }
  return `${Math.round(value).toLocaleString("zh-TW")} 張`;
}

function fmtDelta(curr, prev, unit) {
  const diff = curr - prev;
  if (unit === "元") {
    return `${fmtSigned(diff / 1e8, 2)} 億`;
  }
  return `${fmtSigned(Math.round(diff), 0)} 張`;
}

function renderMarket(market, data) {
  const col = document.querySelector(`.market-column[data-market="${market}"]`);

  const idx = data.index;
  const closeEl = col.querySelector(".close");
  const changeEl = col.querySelector(".change");
  const pctEl = col.querySelector(".change-pct");
  if (idx) {
    closeEl.textContent = fmtIndexValue(idx.close);
    const cls = signClass(idx.change);
    changeEl.textContent = fmtSigned(idx.change, 2);
    pctEl.textContent = `${fmtSigned(idx.changePercent, 2)}%`;
    changeEl.className = `change ${cls}`;
    pctEl.className = `change-pct ${cls}`;
  } else {
    closeEl.textContent = "尚無資料";
    changeEl.textContent = "";
    pctEl.textContent = "";
  }

  const insti = data.institutional;
  col.querySelectorAll(".insti-table .net").forEach((td) => {
    const cat = td.dataset.cat;
    if (insti && insti[cat]) {
      const net = insti[cat].net;
      td.textContent = fmtNetYi(net);
      td.className = `net ${signClass(net)}`;
    } else {
      td.textContent = "尚無資料";
      td.className = "net flat";
    }
  });

  const margin = data.margin;
  const marginBalanceEl = col.querySelector(".margin-balance");
  const marginDeltaEl = col.querySelector(".margin-delta");
  const shortBalanceEl = col.querySelector(".short-balance");
  const shortDeltaEl = col.querySelector(".short-delta");

  // 融資金額只信任官方來源，官方數字還沒出來時 marginBalance 會是 null——這種情況跟
  // margin 整包都還沒有（null）分開處理，因為融券張數（shortBalance）通常還是有的。
  if (margin && margin.marginBalance != null) {
    marginBalanceEl.textContent = fmtBalance(margin.marginBalance, margin.marginUnit);
    marginDeltaEl.textContent = fmtDelta(margin.marginBalance, margin.marginBalancePrev, margin.marginUnit);
  } else {
    marginBalanceEl.textContent = margin ? "尚未公布" : "尚無資料";
    marginDeltaEl.textContent = "";
  }

  if (margin && margin.shortBalance != null) {
    shortBalanceEl.textContent = fmtBalance(margin.shortBalance, margin.shortUnit);
    shortDeltaEl.textContent = fmtDelta(margin.shortBalance, margin.shortBalancePrev, margin.shortUnit);
  } else {
    shortBalanceEl.textContent = "尚無資料";
    shortDeltaEl.textContent = "";
  }
}

async function loadDate(date) {
  const data = await fetchJSON(`data/daily/${date}.json`);
  renderMarket("twse", data.twse);
  renderMarket("tpex", data.tpex);
}

function buildMarketChart(canvasId, indexLabel, indexColor, indexValues, marginLabel, marginColor, marginValues, labels) {
  new Chart(document.getElementById(canvasId), {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: indexLabel,
          data: indexValues,
          borderColor: indexColor,
          yAxisID: "y",
          tension: 0.15,
          pointRadius: 0,
          spanGaps: true,
        },
        {
          label: marginLabel,
          data: marginValues,
          borderColor: marginColor,
          yAxisID: "y1",
          tension: 0.15,
          pointRadius: 0,
          spanGaps: true,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      scales: {
        y: {
          type: "linear",
          position: "left",
          title: { display: true, text: "指數" },
          ticks: { display: true },
        },
        y1: {
          type: "linear",
          position: "right",
          title: { display: true, text: "融資餘額（億元）" },
          ticks: { display: true },
          grid: { drawOnChartArea: false },
        },
      },
    },
  });
}

async function renderCharts() {
  const [indexSeries, marginSeries] = await Promise.all([
    fetchJSON("data/series/index.json"),
    fetchJSON("data/series/margin.json"),
  ]);
  const marginByDate = new Map(marginSeries.map((r) => [r.date, r]));

  const labels = indexSeries.map((r) => r.date);
  const marginYi = (date, market) => {
    const row = marginByDate.get(date);
    const m = row && row[market];
    return m && m.marginBalance != null ? m.marginBalance / 1e8 : null;
  };

  buildMarketChart(
    "twse-chart",
    "加權指數",
    "#2f5fd6",
    indexSeries.map((r) => r.twseClose),
    "融資餘額（億元）",
    "#d5382f",
    labels.map((d) => marginYi(d, "twse")),
    labels
  );

  buildMarketChart(
    "tpex-chart",
    "櫃買指數",
    "#d68c2f",
    indexSeries.map((r) => r.tpexClose),
    "融資餘額（億元）",
    "#d5382f",
    labels.map((d) => marginYi(d, "tpex")),
    labels
  );
}

async function init() {
  const manifest = await fetchJSON("data/manifest.json");
  const select = document.getElementById("date-select");
  const dates = [...manifest.dates].sort().reverse();
  select.innerHTML = dates.map((d) => `<option value="${d}">${d}</option>`).join("");

  const lastUpdatedEl = document.getElementById("last-updated");
  lastUpdatedEl.textContent = manifest.lastUpdated
    ? `最後更新：${new Date(manifest.lastUpdated).toLocaleString("zh-TW")}`
    : "";

  select.addEventListener("change", () => loadDate(select.value));

  if (dates.length) {
    select.value = dates[0];
    await loadDate(dates[0]);
  }

  await renderCharts();
}

init();
