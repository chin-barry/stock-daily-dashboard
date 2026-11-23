// 分頁切換、今日總覽、全球比較分頁。
// 跟 app.js 共用全域函式 fetchJSON / fetchJSONOrNull / signClass / fmtSigned / fmtIndexValue（app.js 先載入）。

// ---------- 分頁 ----------
const TAB_KEY = "tab_v1";

function showTab(name) {
  if (!document.getElementById(`panel-${name}`)) name = "tw";
  document.querySelectorAll(".tab-panel").forEach((p) => { p.hidden = p.id !== `panel-${name}`; });
  document.querySelectorAll(".tabbar button").forEach((b) => {
    const on = b.dataset.tab === name;
    b.classList.toggle("on", on);
    b.setAttribute("aria-selected", on ? "true" : "false");
  });
  try { localStorage.setItem(TAB_KEY, name); } catch (e) {}
  if (location.hash !== `#${name}`) history.replaceState(null, "", `#${name}`);
}

function initTabs() {
  document.querySelectorAll(".tabbar button").forEach((b) => {
    b.addEventListener("click", () => showTab(b.dataset.tab));
  });
  let start = location.hash.slice(1);
  if (!start) { try { start = localStorage.getItem(TAB_KEY) || "tw"; } catch (e) { start = "tw"; } }
  showTab(start);
}

// ---------- 共用小工具 ----------
const gxFmt = (v) => (v == null ? "—" : (v > 0 ? "+" : "") + v.toFixed(2) + "%");
const gxCls = (v) => (v == null ? "" : v > 0 ? "up" : v < 0 ? "down" : "flat");
const mk = (t, a = {}, ...c) => { const e = document.createElement(t); Object.assign(e, a); e.append(...c); return e; };

function setTile(key, value, valueCls, sub) {
  const tile = document.querySelector(`.sum-tile[data-sum="${key}"]`);
  const v = tile.querySelector(".sum-value");
  v.textContent = value;
  v.className = `sum-value ${valueCls || ""}`;
  tile.querySelector(".sum-sub").textContent = sub;
}

const yi = (n) => `${fmtSigned(n / 1e8, 0)} 億`;

// ---------- 今日總覽 ----------
function renderSummaryTw(day) {
  if (!day) {
    ["twse-index", "tpex-index", "insti", "margin"].forEach((k) => setTile(k, "尚無資料", "flat", ""));
    return;
  }
  document.getElementById("summary-date").textContent = `台股資料日 ${day.date}`;
  for (const m of ["twse", "tpex"]) {
    const idx = day[m] && day[m].index;
    if (idx) {
      const c = signClass(idx.change);
      setTile(`${m}-index`, fmtIndexValue(idx.close), "", `${fmtSigned(idx.change, 2)}（${fmtSigned(idx.changePercent, 2)}%）`);
      document.querySelector(`.sum-tile[data-sum="${m}-index"] .sum-sub`).className = `sum-sub ${c}`;
    } else {
      setTile(`${m}-index`, "尚無資料", "flat", "");
    }
  }

  const net = (m) => { const i = day[m] && day[m].institutional; return i && i.total ? i.total.net : null; };
  const [a, b] = [net("twse"), net("tpex")];
  if (a != null || b != null) {
    const sum = (a || 0) + (b || 0);
    setTile("insti", yi(sum), signClass(sum), `上市 ${a != null ? yi(a) : "—"}｜上櫃 ${b != null ? yi(b) : "—"}`);
  } else {
    setTile("insti", "尚未公布", "flat", "通常傍晚公布");
  }

  const md = (m) => {
    const g = day[m] && day[m].margin;
    return g && g.marginBalance != null && g.marginBalancePrev != null ? g.marginBalance - g.marginBalancePrev : null;
  };
  const [c, d] = [md("twse"), md("tpex")];
  if (c != null || d != null) {
    const sum = (c || 0) + (d || 0);
    setTile("margin", yi(sum), signClass(sum), `上市 ${c != null ? yi(c) : "—"}｜上櫃 ${d != null ? yi(d) : "—"}`);
  } else {
    setTile("margin", "尚未公布", "flat", "通常晚上 9 點後公布");
  }
}

function renderSummaryRank(gx) {
  const rs = gx.rows.filter((r) => r.type === "index" && r.r1M != null).sort((x, y) => y.r1M - x.r1M);
  const i = rs.findIndex((r) => r.symbol === "^TWII");
  if (i < 0) { setTile("rank", "—", "flat", "全球資料不足"); return; }
  const tw = rs[i];
  setTile("rank", `第 ${i + 1}／${rs.length}`, "", `${rs.length} 個指數中（不含個股）｜加權 ${gxFmt(tw.r1M)}`);
  const el = document.getElementById("summary-date");
  el.textContent = `${el.textContent}｜全球更新 ${gx.generated}`;
}

// ---------- 全球比較 ----------
const HIDE_KEY = "gx_hidden_v1";
let gxData = null;
let gxCur = "r1M";
let gxHidden = new Set();
try { gxHidden = new Set(JSON.parse(localStorage.getItem(HIDE_KEY) || "[]")); } catch (e) {}
const gxSave = () => { try { localStorage.setItem(HIDE_KEY, JSON.stringify([...gxHidden])); } catch (e) {} };
const gxShown = () => gxData.rows.filter((r) => !gxHidden.has(r.symbol));
const gxNameCls = (r) => (r.derived ? "est" : r.symbol === "^TWII" ? "tw" : "");

function initGlobal(gx) {
  gxData = gx;
  document.getElementById("gx-sub").textContent = `更新時間 ${gx.generated}（台北）｜共 ${gx.rows.length} 項｜紅漲綠跌`;
  document.getElementById("gx-err").textContent = gx.errors.length ? "抓取失敗：" + gx.errors.join("、") : "";
  document.getElementById("gx-weight").textContent = `${Math.round(gx.tsmcWeight * 100)}%`;

  const regions = [...new Set(gx.rows.map((r) => r.region))];
  const groups = document.getElementById("gx-groups");
  regions.forEach((rg) => {
    const members = gx.rows.filter((r) => r.region === rg);
    const gl = mk("button", { type: "button", className: "gl", textContent: rg, title: "切換整組" });
    gl.onclick = () => {
      const allOn = members.every((r) => !gxHidden.has(r.symbol));
      members.forEach((r) => (allOn ? gxHidden.add(r.symbol) : gxHidden.delete(r.symbol)));
      gxSave(); drawGlobal();
    };
    const chips = members.map((r) => {
      const cb = mk("input", { type: "checkbox" });
      cb.onchange = () => { cb.checked ? gxHidden.delete(r.symbol) : gxHidden.add(r.symbol); gxSave(); drawGlobal(); };
      const lab = mk("label", { className: "chip" }, cb, r.name);
      lab.dataset.sym = r.symbol;
      return lab;
    });
    groups.append(mk("div", { className: "grp" }, gl, ...chips));
  });
  document.getElementById("gx-all").onclick = () => { gxHidden.clear(); gxSave(); drawGlobal(); };
  document.getElementById("gx-none").onclick = () => { gx.rows.forEach((r) => gxHidden.add(r.symbol)); gxSave(); drawGlobal(); };

  gx.periods.forEach(([k, lab]) => {
    const b = mk("button", { type: "button", textContent: lab });
    b.dataset.k = k;
    b.onclick = () => { gxCur = k; drawGlobal(); };
    document.getElementById("gx-periods").append(b);
  });
  drawGlobal();
}

function drawGlobal() {
  const P = gxData.periods;
  document.querySelectorAll("#gx-groups label.chip").forEach((l) => {
    const on = !gxHidden.has(l.dataset.sym);
    l.querySelector("input").checked = on;
    l.classList.toggle("off", !on);
  });
  document.getElementById("gx-count").textContent = `（已選 ${gxShown().length}／${gxData.rows.length}）`;
  document.querySelectorAll("#gx-periods button").forEach((b) => b.classList.toggle("on", b.dataset.k === gxCur));

  const label = P.find((p) => p[0] === gxCur)[1];
  const rs = gxShown().filter((r) => r[gxCur] != null).sort((a, b) => b[gxCur] - a[gxCur]);
  const take = document.getElementById("gx-take");
  if (rs.length >= 2) {
    const best = rs[0], worst = rs[rs.length - 1], tw = rs.find((r) => r.symbol === "^TWII");
    take.replaceChildren(
      `${label}表現最好的是 `, mk("b", { textContent: best.name }), `（${gxFmt(best[gxCur])}），最弱的是 `,
      mk("b", { textContent: worst.name }),
      `（${gxFmt(worst[gxCur])}）` + (tw ? `；台灣加權 ${gxFmt(tw[gxCur])}，排第 ${rs.indexOf(tw) + 1}／${rs.length}` : "") + "。"
    );
  } else {
    take.textContent = rs.length ? `${label}：${rs[0].name} ${gxFmt(rs[0][gxCur])}。` : "";
  }

  const chart = document.getElementById("gx-chart");
  if (!rs.length) {
    chart.replaceChildren(mk("div", { className: "gx-empty", textContent: "請在上方勾選要比較的對象。" }));
  } else {
    const vals = rs.map((r) => r[gxCur]), lo = Math.min(0, ...vals), hi = Math.max(0, ...vals);
    const pad = 15, span = hi - lo || 1, x = (v) => pad + ((v - lo) / span) * (100 - 2 * pad);
    chart.replaceChildren(...rs.map((r) => {
      const v = r[gxCur], a = Math.min(x(0), x(v)), w = Math.max(0.3, Math.abs(x(v) - x(0)));
      const fill = mk("div", { className: `gx-fill ${v >= 0 ? "pos" : "neg"}${r.derived ? " est" : ""}` });
      fill.style.cssText = `left:${a}%;width:${w}%`;
      const val = mk("div", { className: `gx-val ${gxCls(v)}`, textContent: gxFmt(v) });
      val.style.cssText = v >= 0 ? `left:calc(${x(v)}% + 4px)` : `right:calc(${100 - x(v)}% + 4px)`;
      const zero = mk("div", { className: "gx-zero" });
      zero.style.left = `${x(0)}%`;
      return mk("div", { className: "gx-bar" },
        mk("span", { className: gxNameCls(r), textContent: r.name }),
        mk("div", { className: "gx-track" }, zero, fill, val));
    }));
  }

  const heads = ["指數", "資料日期", "收盤", ...P.map((p) => p[1])];
  const thead = mk("tr", {}, ...heads.map((h, i) => mk("th", { textContent: h, className: i >= 3 && P[i - 3][0] === gxCur ? "on" : "" })));
  const body = gxShown().map((r) => mk("tr", {},
    mk("td", { className: gxNameCls(r), textContent: r.name }),
    mk("td", { textContent: r.asof }),
    mk("td", { textContent: r.close == null ? "—" : r.close.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }),
    ...P.map(([k]) => {
      const td = mk("td", { className: `${gxCls(r[k])}${r.derived ? " est" : ""}`, textContent: gxFmt(r[k]) });
      td.title = r[`${k}_base`] ? `期初：${r[`${k}_base`]}` : "";
      return td;
    })
  ));
  document.getElementById("gx-table").replaceChildren(mk("thead", {}, thead), mk("tbody", {}, ...body));
}

// ---------- 啟動 ----------
async function initSummaryAndGlobal() {
  initTabs();
  const [manifest, gx] = await Promise.all([
    fetchJSONOrNull("data/manifest.json"),
    fetchJSONOrNull("data/global/latest.json"),
  ]);
  const latest = manifest && manifest.dates && manifest.dates.length ? [...manifest.dates].sort().pop() : null;
  renderSummaryTw(latest ? await fetchJSONOrNull(`data/daily/${latest}.json`) : null);
  // renderSummaryRank 會在 summary-date 後面接上全球更新時間，所以要在 renderSummaryTw 之後
  if (gx && gx.rows) {
    renderSummaryRank(gx);
    initGlobal(gx);
  } else {
    setTile("rank", "—", "flat", "全球資料尚未產生");
    document.getElementById("gx-err").textContent = "全球指數資料尚未產生（data/global/latest.json）。";
  }
}

initSummaryAndGlobal();
