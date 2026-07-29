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

// 指數／融資／三大法人三個 series 檔案在好幾個功能裡都會用到（趨勢圖、區間比較、近一月
// 表格），只在 init() 抓一次，之後都從這幾個 Map 查，避免重複打好幾次網路請求。
let indexByDate = new Map();
let marginByDate = new Map();
let institutionalByDate = new Map();

async function loadAllSeries() {
  const [indexSeries, marginSeries, institutionalSeries] = await Promise.all([
    fetchJSON("data/series/index.json"),
    fetchJSON("data/series/margin.json"),
    fetchJSON("data/series/institutional.json"),
  ]);
  indexByDate = new Map(indexSeries.map((r) => [r.date, r]));
  marginByDate = new Map(marginSeries.map((r) => [r.date, r]));
  institutionalByDate = new Map(institutionalSeries.map((r) => [r.date, r]));
}

// 圖表放大燈箱要能重畫「目前」的圖（尤其區間比較會隨日期選擇器換資料），所以每張圖表
// 除了自己的 Chart 實例，另外存一個「重新產生目前 config」的函式，點擊當下才呼叫，
// 不會拿到開燈箱那一刻已經過期的舊資料快照。
const chartInstances = {}; // canvasId -> Chart 實例
const chartConfigProviders = {}; // canvasId -> () => Chart.js config

function renderChart(canvasId, config) {
  if (chartInstances[canvasId]) {
    chartInstances[canvasId].destroy();
  }
  chartInstances[canvasId] = new Chart(document.getElementById(canvasId), config);
}

function trendChartConfig(labels, indexLabel, indexColor, indexValues, marginLabel, marginColor, marginValues) {
  return {
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
  };
}

function buildMarketChart(canvasId, indexLabel, indexColor, indexValues, marginLabel, marginColor, marginValues, labels) {
  const config = () => trendChartConfig(labels, indexLabel, indexColor, indexValues, marginLabel, marginColor, marginValues);
  chartConfigProviders[canvasId] = config;
  renderChart(canvasId, config());
}

function renderCharts() {
  const labels = [...indexByDate.keys()].sort();
  const marginYi = (date, market) => {
    const row = marginByDate.get(date);
    const m = row && row[market];
    return m && m.marginBalance != null ? m.marginBalance / 1e8 : null;
  };

  buildMarketChart(
    "twse-chart",
    "加權指數",
    "#2f5fd6",
    labels.map((d) => indexByDate.get(d).twseClose),
    "融資餘額（億元）",
    "#d5382f",
    labels.map((d) => marginYi(d, "twse")),
    labels
  );

  buildMarketChart(
    "tpex-chart",
    "櫃買指數",
    "#d68c2f",
    labels.map((d) => indexByDate.get(d).tpexClose),
    "融資餘額（億元）",
    "#d5382f",
    labels.map((d) => marginYi(d, "tpex")),
    labels
  );
}

// ---------- 區間比較 ----------

function rangeChartConfig(labels, indexPct, marginPct, indexLabel, indexColor) {
  return {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: indexLabel,
          data: indexPct,
          borderColor: indexColor,
          tension: 0.15,
          pointRadius: 0,
          spanGaps: true,
        },
        {
          label: "融資餘額 %",
          data: marginPct,
          borderColor: "#d5382f",
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
          title: { display: true, text: "相對起始日變化 %" },
          ticks: { callback: (v) => `${v}%` },
        },
      },
    },
  };
}

function buildRangeChart(canvasId, labels, indexPct, marginPct, indexLabel, indexColor) {
  const config = () => rangeChartConfig(labels, indexPct, marginPct, indexLabel, indexColor);
  chartConfigProviders[canvasId] = config;
  renderChart(canvasId, config());
}

// "2026-07-13" -> "7/13"
function shortDate(iso) {
  const [, mm, dd] = iso.split("-");
  return `${Number(mm)}/${Number(dd)}`;
}

function renderRangeMarket(market, start, end) {
  const panel = document.querySelector(`.range-market[data-market="${market}"]`);
  const closeKey = market === "twse" ? "twseClose" : "tpexClose";
  const highKey = market === "twse" ? "twseHigh" : "tpexHigh";
  const lowKey = market === "twse" ? "twseLow" : "tpexLow";
  const indexLabel = market === "twse" ? "加權指數 %" : "櫃買指數 %";
  const indexColor = market === "twse" ? "#2f5fd6" : "#d68c2f";

  const indexChangeEl = panel.querySelector('[data-field="indexChange"]');
  const indexChangePctEl = panel.querySelector('[data-field="indexChangePct"]');
  const indexDetailEl = panel.querySelector('[data-field="indexDetail"]');
  const marginChangeEl = panel.querySelector('[data-field="marginChange"]');
  const marginChangePctEl = panel.querySelector('[data-field="marginChangePct"]');
  const marginDetailEl = panel.querySelector('[data-field="marginDetail"]');

  // 指數：先用起始/結束日收盤判斷這段區間是漲是跌，決定起點跟搜尋方向——
  // 上漲：起始日「最低點」當起漲點，「最高點」在整個區間裡搜尋（不一定是結束日）；
  // 下跌：起始日「最高點」當起跌點，「最低點」在整個區間裡搜尋（不一定是結束日）。
  // 錨點固定在起始日、搜尋到的極值日期必定 >= 起始日，時間先後已經確定，不用再排序。
  const startIdxRow = indexByDate.get(start);
  const endIdxRow = indexByDate.get(end);
  const startCloseForDir = startIdxRow ? startIdxRow[closeKey] : null;
  const endCloseForDir = endIdxRow ? endIdxRow[closeKey] : null;
  const datesInRangeForIndex = [...indexByDate.keys()].filter((d) => d >= start && d <= end).sort();

  let indexAnchor = null; // { date, value, label }
  let indexExtreme = null;
  if (startIdxRow && startCloseForDir != null && endCloseForDir != null) {
    const isRise = endCloseForDir >= startCloseForDir;
    if (isRise) {
      indexAnchor = { date: start, value: startIdxRow[lowKey], label: "低" };
      for (const d of datesInRangeForIndex) {
        const row = indexByDate.get(d);
        if (row && row[highKey] != null && (!indexExtreme || row[highKey] > indexExtreme.value)) {
          indexExtreme = { date: d, value: row[highKey], label: "高" };
        }
      }
    } else {
      indexAnchor = { date: start, value: startIdxRow[highKey], label: "高" };
      for (const d of datesInRangeForIndex) {
        const row = indexByDate.get(d);
        if (row && row[lowKey] != null && (!indexExtreme || row[lowKey] < indexExtreme.value)) {
          indexExtreme = { date: d, value: row[lowKey], label: "低" };
        }
      }
    }
  }

  if (indexAnchor && indexAnchor.value != null && indexExtreme) {
    const diff = indexExtreme.value - indexAnchor.value;
    const pct = (diff / indexAnchor.value) * 100;
    indexChangeEl.textContent = fmtSigned(diff, 2);
    indexChangeEl.className = `stat-value ${signClass(diff)}`;
    indexChangePctEl.textContent = `${fmtSigned(pct, 2)}%`;
    indexChangePctEl.className = `stat-sub ${signClass(diff)}`;
    indexDetailEl.textContent = `${indexAnchor.label} ${fmtIndexValue(indexAnchor.value)}(${shortDate(indexAnchor.date)}) → ${indexExtreme.label} ${fmtIndexValue(indexExtreme.value)}(${shortDate(indexExtreme.date)})`;
  } else {
    indexChangeEl.textContent = "資料不足";
    indexChangeEl.className = "stat-value flat";
    indexChangePctEl.textContent = "";
    indexDetailEl.textContent = "";
  }

  // 融資：高點、低點都在整個區間裡搜尋（不假設哪一天是高或低）——這樣不管是下跌波段
  // （高點在前、低點在後）還是上漲波段（低點在前、高點在後）都抓得到；顯示時依實際發生
  // 的時間先後排序，較早的一筆當起點、較晚的一筆當終點，正負號才會跟漲跌方向一致。
  const datesInRange = [...indexByDate.keys()].filter((d) => d >= start && d <= end).sort();
  let marginHigh = null; // { date, value }
  let marginLow = null;
  for (const d of datesInRange) {
    const row = marginByDate.get(d);
    const m = row && row[market];
    if (m && m.marginBalance != null) {
      if (!marginHigh || m.marginBalance > marginHigh.value) marginHigh = { date: d, value: m.marginBalance };
      if (!marginLow || m.marginBalance < marginLow.value) marginLow = { date: d, value: m.marginBalance };
    }
  }

  if (marginHigh && marginLow) {
    const [earlier, later] = marginHigh.date <= marginLow.date ? [marginHigh, marginLow] : [marginLow, marginHigh];
    const earlierLabel = earlier === marginHigh ? "高" : "低";
    const laterLabel = later === marginHigh ? "高" : "低";
    const diff = later.value - earlier.value;
    const pct = (diff / earlier.value) * 100;
    marginChangeEl.textContent = `${fmtSigned(diff / 1e8, 2)} 億`;
    marginChangeEl.className = `stat-value ${signClass(diff)}`;
    marginChangePctEl.textContent = `${fmtSigned(pct, 2)}%`;
    marginChangePctEl.className = `stat-sub ${signClass(diff)}`;
    marginDetailEl.textContent = `${earlierLabel} ${(earlier.value / 1e8).toFixed(2)}億(${shortDate(earlier.date)}) → ${laterLabel} ${(later.value / 1e8).toFixed(2)}億(${shortDate(later.date)})`;
  } else {
    marginChangeEl.textContent = "資料不足";
    marginChangeEl.className = "stat-value flat";
    marginChangePctEl.textContent = "";
    marginDetailEl.textContent = "";
  }

  // 走勢圖：區間內每個交易日的收盤，換算成「相對起始日收盤」的變化 %（跟上面 stat tile
  // 用高/低價的算法不同，這裡是為了畫出平滑的逐日走勢，用收盤價當基準比較合理）。
  const startClose = startIdxRow ? startIdxRow[closeKey] : null;
  const startMarginRow = marginByDate.get(start);
  const startMarginValue = startMarginRow && startMarginRow[market] ? startMarginRow[market].marginBalance : null;
  const indexPctSeries = [];
  const marginPctSeries = [];
  for (const d of datesInRange) {
    const row = indexByDate.get(d);
    indexPctSeries.push(
      row && row[closeKey] != null && startClose != null ? ((row[closeKey] - startClose) / startClose) * 100 : null
    );
    const mRow = marginByDate.get(d);
    const mVal = mRow && mRow[market] ? mRow[market].marginBalance : null;
    marginPctSeries.push(
      mVal != null && startMarginValue != null ? ((mVal - startMarginValue) / startMarginValue) * 100 : null
    );
  }
  buildRangeChart(`${market}-range-chart`, datesInRange, indexPctSeries, marginPctSeries, indexLabel, indexColor);

  // 三大法人買賣超區間累計：把區間內每天的 net 加總
  const totals = { foreign: 0, trust: 0, dealer: 0, total: 0 };
  let hasAny = false;
  for (const d of datesInRange) {
    const row = institutionalByDate.get(d);
    const m = row && row[market];
    if (!m) continue;
    for (const cat of ["foreign", "trust", "dealer", "total"]) {
      if (m[cat] && m[cat].net != null) {
        totals[cat] += m[cat].net;
        hasAny = true;
      }
    }
  }
  panel.querySelectorAll(".range-insti-table .net").forEach((td) => {
    const cat = td.dataset.cat;
    if (hasAny) {
      td.textContent = fmtNetYi(totals[cat]);
      td.className = `net ${signClass(totals[cat])}`;
    } else {
      td.textContent = "資料不足";
      td.className = "net flat";
    }
  });
}

function renderRangeComparison() {
  const startSel = document.getElementById("range-start");
  const endSel = document.getElementById("range-end");
  let start = startSel.value;
  let end = endSel.value;
  if (start > end) {
    [start, end] = [end, start];
  }
  renderRangeMarket("twse", start, end);
  renderRangeMarket("tpex", start, end);
}

function initRangeComparison() {
  const dates = [...indexByDate.keys()].sort(); // 舊到新
  const optionsHtml = dates.map((d) => `<option value="${d}">${d}</option>`).join("");
  const startSel = document.getElementById("range-start");
  const endSel = document.getElementById("range-end");
  startSel.innerHTML = optionsHtml;
  endSel.innerHTML = optionsHtml;

  if (!dates.length) return;
  endSel.value = dates[dates.length - 1];
  startSel.value = dates[Math.max(0, dates.length - 21)]; // 預設約近一個月（20 個交易日）

  startSel.addEventListener("change", renderRangeComparison);
  endSel.addEventListener("change", renderRangeComparison);

  renderRangeComparison();
}

// ---------- 近一個月表格 ----------

function marketTableCells(date, market, closeKey) {
  const idxRow = indexByDate.get(date);
  const close = idxRow ? idxRow[closeKey] : null;
  const closeText = close != null ? fmtIndexValue(close) : "--";

  const marginRow = marginByDate.get(date);
  const m = marginRow && marginRow[market];
  let balanceText = "--";
  let deltaText = "--";
  let deltaCls = "flat";
  if (m && m.marginBalance != null) {
    balanceText = (m.marginBalance / 1e8).toFixed(2);
    if (m.marginBalancePrev != null) {
      const diff = m.marginBalance - m.marginBalancePrev;
      deltaText = `${fmtSigned(diff / 1e8, 2)} 億`;
      deltaCls = signClass(diff);
    }
  }
  return `<td>${closeText}</td><td>${balanceText}</td><td class="${deltaCls}">${deltaText}</td>`;
}

function renderMonthlyTable() {
  const RECENT_DAYS = 22; // 約一個月的交易日數
  const dates = [...indexByDate.keys()].sort().slice(-RECENT_DAYS).reverse(); // 近到遠
  const tbody = document.getElementById("monthly-table-body");
  tbody.innerHTML = dates
    .map(
      (d) =>
        `<tr><td>${d}</td>${marketTableCells(d, "twse", "twseClose")}${marketTableCells(d, "tpex", "tpexClose")}</tr>`
    )
    .join("");
}

// ---------- 圖表放大燈箱 ----------

let modalChart = null;

function openChartModal(canvasId, title) {
  const provider = chartConfigProviders[canvasId];
  if (!provider) return;
  document.getElementById("chart-modal-title").textContent = title || "";
  if (modalChart) {
    modalChart.destroy();
  }
  modalChart = new Chart(document.getElementById("modal-chart"), provider());
  document.getElementById("chart-modal").classList.add("open");
}

function closeChartModal() {
  document.getElementById("chart-modal").classList.remove("open");
  if (modalChart) {
    modalChart.destroy();
    modalChart = null;
  }
}

function initChartModal() {
  document.querySelectorAll(".chart-clickable").forEach((el) => {
    el.addEventListener("click", () => {
      const canvas = el.querySelector("canvas");
      if (canvas) openChartModal(canvas.id, el.dataset.title || "");
    });
  });
  document.querySelector(".chart-modal-backdrop").addEventListener("click", closeChartModal);
  document.querySelector(".chart-modal-close").addEventListener("click", closeChartModal);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeChartModal();
  });
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

  await loadAllSeries();

  if (dates.length) {
    select.value = dates[0];
    await loadDate(dates[0]);
  }

  renderCharts();
  initRangeComparison();
  renderMonthlyTable();
  initChartModal();
}

init();
