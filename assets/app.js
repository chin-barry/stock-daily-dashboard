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
  if (unit === "仟元") {
    const yi = (value * 1000) / 1e8;
    return `${yi.toFixed(2)} 億元`;
  }
  return `${Math.round(value).toLocaleString("zh-TW")} 張`;
}

function fmtDelta(curr, prev, unit) {
  const diff = curr - prev;
  if (unit === "仟元") {
    const yi = (diff * 1000) / 1e8;
    return `${fmtSigned(yi, 2)} 億`;
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
  if (margin) {
    marginBalanceEl.textContent = fmtBalance(margin.marginBalance, margin.marginUnit);
    marginDeltaEl.textContent = fmtDelta(margin.marginBalance, margin.marginBalancePrev, margin.marginUnit);
    shortBalanceEl.textContent = fmtBalance(margin.shortBalance, margin.shortUnit);
    shortDeltaEl.textContent = fmtDelta(margin.shortBalance, margin.shortBalancePrev, margin.shortUnit);
  } else {
    marginBalanceEl.textContent = "尚無資料";
    marginDeltaEl.textContent = "";
    shortBalanceEl.textContent = "尚無資料";
    shortDeltaEl.textContent = "";
  }
}

async function loadDate(date) {
  const res = await fetch(`data/daily/${date}.json`);
  const data = await res.json();
  renderMarket("twse", data.twse);
  renderMarket("tpex", data.tpex);
}

async function renderChart() {
  const res = await fetch("data/series/index.json");
  const series = await res.json();
  const ctx = document.getElementById("index-chart");
  new Chart(ctx, {
    type: "line",
    data: {
      labels: series.map((r) => r.date),
      datasets: [
        {
          label: "加權指數（上市）",
          data: series.map((r) => r.twseClose),
          borderColor: "#2f5fd6",
          yAxisID: "y",
          tension: 0.15,
          pointRadius: 0,
        },
        {
          label: "櫃買指數（上櫃）",
          data: series.map((r) => r.tpexClose),
          borderColor: "#d68c2f",
          yAxisID: "y1",
          tension: 0.15,
          pointRadius: 0,
        },
      ],
    },
    options: {
      responsive: true,
      interaction: { mode: "index", intersect: false },
      scales: {
        y: { type: "linear", position: "left", title: { display: true, text: "加權指數" } },
        y1: {
          type: "linear",
          position: "right",
          title: { display: true, text: "櫃買指數" },
          grid: { drawOnChartArea: false },
        },
      },
    },
  });
}

async function init() {
  const res = await fetch("data/manifest.json");
  const manifest = await res.json();
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

  await renderChart();
}

init();
