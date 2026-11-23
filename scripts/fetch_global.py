# -*- coding: utf-8 -*-
"""全球主要股市漲跌幅比較：抓收盤、算各期間漲跌幅，寫入 data/global/。

由 .github/workflows/fetch-global.yml 排程執行（台北時間 06:30、14:30），也可以本機手動跑：
    python scripts/fetch_global.py

計算邏輯從 01各國指數比較/global_returns.py 搬過來，差別只在輸出：
    data/global/latest.json   網頁讀的計算結果
    data/global/history.csv   每日收盤歷史（每次執行累加、去重）

只用 Python 內建模組。任何一個指數抓失敗不會讓整支程式失敗（會記在 latest.json 的 errors），
全部都失敗才回傳非 0，讓 GitHub Actions 標成失敗並寄信通知。
"""
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from calendar import monthrange
from datetime import datetime, timedelta, timezone

# ---------- 設定 ----------
# (代號, 名稱, 地區, 類型)；類型 stock 是個股，不列入「台股全球排名」
INDICES = [
    ("^TWII", "台灣加權", "台灣", "index"),
    ("TPEx", "台灣櫃買", "台灣", "index"),   # 櫃買指數：Yahoo 沒有，改從 FinMind 抓
    ("2330.TW", "台積電", "台灣", "stock"),
    ("^SOX", "費城半導體", "美國", "index"),
    ("^IXIC", "那斯達克", "美國", "index"),
    ("^GSPC", "標普500", "美國", "index"),
    ("^DJI", "道瓊工業", "美國", "index"),
    ("^N225", "日經225", "亞洲", "index"),
    ("^KS11", "韓國綜合", "亞洲", "index"),
    ("^HSI", "香港恒生", "亞洲", "index"),
    ("000001.SS", "上證綜合", "亞洲", "index"),
    ("^STOXX50E", "歐洲斯托克50", "歐洲", "index"),
    ("^GDAXI", "德國DAX", "歐洲", "index"),
]
PERIODS = [("r1W", "近一週", "7d"), ("r1M", "近一月", 1), ("r3M", "近一季", 3),
           ("r6M", "近半年", 6), ("r1Y", "近一年", 12), ("rYTD", "今年以來", 0)]
# 「加權不含台積電」推估用的台積電權重（期末）。證交所每月底公布權值比重，可每月更新一次。
TSMC_WEIGHT = 0.42
EX_TSMC = ("EX_TSMC", "加權不含台積電(推估)", "台灣")
LOOKBACK_DAYS = 420  # 約 13~14 個月，足夠算近一年與今年以來
FINMIND_IDS = {"TPEx"}

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "data", "global")
OUT_LATEST = os.path.join(OUT_DIR, "latest.json")
OUT_HISTORY = os.path.join(OUT_DIR, "history.csv")
TPE = timezone(timedelta(hours=8))
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
}

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def _get_json(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _retry(fn):
    last_err = None
    for attempt in range(3):
        try:
            return fn()
        except (urllib.error.URLError, urllib.error.HTTPError, KeyError, IndexError,
                TypeError, ValueError, TimeoutError, ConnectionError) as e:
            last_err = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"{last_err}")


def fetch_finmind(data_id):
    start = (datetime.now(TPE) - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    url = ("https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockPrice&data_id="
           + urllib.parse.quote(data_id) + "&start_date=" + start)

    def go():
        data = _get_json(url)
        if data.get("status") != 200:
            raise ValueError(data.get("msg", "FinMind 回傳錯誤"))
        out = {r["date"]: float(r["close"]) for r in data.get("data", []) if r.get("close") is not None}
        return sorted(out.items())
    return _retry(go)


def fetch_yahoo(symbol):
    now = int(time.time())
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
           + urllib.parse.quote(symbol, safe="")
           + f"?period1={now - LOOKBACK_DAYS * 86400}&period2={now}&interval=1d")

    def go():
        res = _get_json(url)["chart"]["result"][0]
        off = res["meta"].get("gmtoffset", 0) or 0
        closes = res["indicators"]["quote"][0]["close"]
        out = {}
        for t, c in zip(res["timestamp"], closes):
            if c is not None:  # 同一天若有重複，留最後一筆
                out[datetime.fromtimestamp(t + off, tz=timezone.utc).strftime("%Y-%m-%d")] = float(c)
        return sorted(out.items())
    return _retry(go)


def fetch_closes(symbol):
    return fetch_finmind(symbol) if symbol in FINMIND_IDS else fetch_yahoo(symbol)


def minus_months(ds, m):
    y, mo, d = map(int, ds.split("-"))
    ny, nm = divmod(y * 12 + (mo - 1) - m, 12)
    nm += 1
    return f"{ny:04d}-{nm:02d}-{min(d, monthrange(ny, nm)[1]):02d}"


def close_on_or_before(series, ds):
    hit = None
    for d, c in series:
        if d > ds:
            break
        hit = (d, c)
    return hit


def period_target(last_d, m):
    if isinstance(m, str) and m.endswith("d"):
        return (datetime.strptime(last_d, "%Y-%m-%d") - timedelta(days=int(m[:-1]))).strftime("%Y-%m-%d")
    if m:
        return minus_months(last_d, m)
    return f"{int(last_d[:4]) - 1}-12-31"


def compute(series):
    last_d, last_c = series[-1]
    row = {"asof": last_d, "close": round(last_c, 2)}
    for key, _label, m in PERIODS:
        base = close_on_or_before(series, period_target(last_d, m))
        row[key] = round((last_c / base[1] - 1) * 100, 2) if base else None
        row[key + "_base"] = base[0] if base else ""
    return row


def compute_ex_tsmc(tw, ts, w_end=TSMC_WEIGHT):
    """用加權指數與台積電推估「加權不含台積電」的漲跌幅。
    R_idx = w0*R_tsmc + (1-w0)*R_rest，期初權重 w0 由期末權重反推：w0 = w_end*(1+R_idx)/(1+R_tsmc)。"""
    last_d, last_i = tw[-1]
    end_t = close_on_or_before(ts, last_d)
    row = {"asof": last_d, "close": None}
    for key, _label, m in PERIODS:
        bi = close_on_or_before(tw, period_target(last_d, m))
        bt = close_on_or_before(ts, bi[0]) if bi else None
        if not (bi and bt and end_t):
            row[key], row[key + "_base"] = None, ""
            continue
        ri = last_i / bi[1] - 1
        rt = end_t[1] / bt[1] - 1
        w0 = w_end * (1 + ri) / (1 + rt)
        row[key] = round((ri - w0 * rt) / (1 - w0) * 100, 2)
        row[key + "_base"] = bi[0]
    return row


def save_history(all_series):
    hist = {}
    if os.path.exists(OUT_HISTORY):
        with open(OUT_HISTORY, newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                hist[(r["date"], r["symbol"])] = r
    names = {s: n for s, n, _, _ in INDICES}
    for sym, series in all_series.items():
        for d, c in series:
            hist[(d, sym)] = {"date": d, "symbol": sym, "name": names[sym], "close": f"{c:.4f}"}
    with open(OUT_HISTORY, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["date", "symbol", "name", "close"])
        w.writeheader()
        for k in sorted(hist):
            w.writerow(hist[k])
    return len(hist)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    rows, errors, all_series = [], [], {}
    pct = lambda v: "—" if v is None else f"{v:+.2f}%"
    for sym, name, region, kind in INDICES:
        try:
            series = fetch_closes(sym)
            if not series:
                raise RuntimeError("沒有資料")
            all_series[sym] = series
            r = compute(series)
            r.update({"symbol": sym, "name": name, "region": region, "type": kind})
            rows.append(r)
            print(f"  ✓ {name:<8} {r['asof']}  收盤 {r['close']:>12,.2f}  近一月 {pct(r['r1M'])}")
        except Exception as e:
            errors.append(f"{name}（{sym}）")
            print(f"  ✗ {name}（{sym}）失敗：{e}")
        time.sleep(0.3)

    if "^TWII" in all_series and "2330.TW" in all_series:
        r = compute_ex_tsmc(all_series["^TWII"], all_series["2330.TW"])
        r.update({"symbol": EX_TSMC[0], "name": EX_TSMC[1], "region": EX_TSMC[2], "type": "derived", "derived": True})
        pos = next((i for i, x in enumerate(rows) if x["symbol"] == "2330.TW"), len(rows) - 1) + 1
        rows.insert(pos, r)
    else:
        errors.append(EX_TSMC[1] + "（需要加權與台積電資料）")

    if not rows:
        print("全部抓取失敗，不更新檔案。")
        return 1

    payload = {
        "generated": datetime.now(TPE).strftime("%Y-%m-%d %H:%M"),
        "tsmcWeight": TSMC_WEIGHT,
        "periods": [[k, lab] for k, lab, _ in PERIODS],
        "rows": rows,
        "errors": errors,
    }
    with open(OUT_LATEST, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    n = save_history(all_series)
    print(f"完成：成功 {len(rows)} 項、失敗 {len(errors)} 項；收盤歷史累計 {n} 筆")
    return 0


if __name__ == "__main__":
    sys.exit(main())
