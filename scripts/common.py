"""共用的資料抓取與正規化邏輯，供 fetch_daily.py 與 backfill.py 共用。"""
import datetime as dt
import json
import ssl
import time
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
TWSE_HEADERS = {"User-Agent": USER_AGENT, "Referer": "https://www.twse.com.tw/"}
TPEX_HEADERS = {"User-Agent": USER_AGENT, "Referer": "https://www.tpex.org.tw/"}


class _LenientTLSAdapter(HTTPAdapter):
    """部分政府網站（如 tpex.org.tw）的憑證缺少 Subject Key Identifier 擴充欄位，
    在較新版 OpenSSL 的預設嚴格模式下會被拒絕（瀏覽器與舊版 OpenSSL 都能接受）。
    這裡只關掉那個嚴格旗標，憑證鏈與主機名稱仍然正常驗證。
    """

    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(*args, **kwargs)


SESSION = requests.Session()
SESSION.mount("https://", _LenientTLSAdapter())


def _num(s):
    if s is None:
        return 0.0
    s = str(s).replace(",", "").strip()
    if s in ("", "--", "-", "N/A"):
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def _signed(value_str, sign):
    """套用正負號，但如果原始字串已經帶負號就直接信任它，不重複套用。"""
    value = _num(value_str)
    if str(value_str).strip().startswith("-"):
        return value
    return sign * value


def roc7_to_iso(s):
    """民國年日期字串（如 '1150727'）轉成 'YYYY-MM-DD'。"""
    s = str(s)
    year = int(s[:-4]) + 1911
    return f"{year}-{s[-4:-2]}-{s[-2:]}"


def ymd8_to_iso(s):
    """西元 8 碼日期字串（如 '20260727'）轉成 'YYYY-MM-DD'。"""
    s = str(s)
    return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"


def iso_to_roc_date(iso_date):
    """'2026-07-27' -> '115/07/27'。"""
    y, m, d = iso_date.split("-")
    return f"{int(y) - 1911}/{m}/{d}"


# ---------- 資料落地（daily / series / manifest 共用邏輯）----------


def _load_json(path, default):
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def _dump_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def _append_series(path, date, values):
    series = _load_json(path, [])
    series = [row for row in series if row.get("date") != date]
    series.append({"date": date, **values})
    series.sort(key=lambda r: r["date"])
    _dump_json(path, series)


def save_snapshot(snapshot):
    """寫入 data/daily/{date}.json、附加進 data/series/*.json、更新 data/manifest.json。"""
    date = snapshot["date"]

    _dump_json(DATA_DIR / "daily" / f"{date}.json", snapshot)

    twse_idx = snapshot["twse"]["index"] or {}
    tpex_idx = snapshot["tpex"]["index"] or {}
    _append_series(
        DATA_DIR / "series" / "index.json",
        date,
        {
            "twseClose": twse_idx.get("close"),
            "twseChange": twse_idx.get("change"),
            "twseChangePercent": twse_idx.get("changePercent"),
            "tpexClose": tpex_idx.get("close"),
            "tpexChange": tpex_idx.get("change"),
            "tpexChangePercent": tpex_idx.get("changePercent"),
        },
    )
    _append_series(
        DATA_DIR / "series" / "institutional.json",
        date,
        {"twse": snapshot["twse"]["institutional"], "tpex": snapshot["tpex"]["institutional"]},
    )
    _append_series(
        DATA_DIR / "series" / "margin.json",
        date,
        {"twse": snapshot["twse"]["margin"], "tpex": snapshot["tpex"]["margin"]},
    )

    manifest = _load_json(DATA_DIR / "manifest.json", {"dates": []})
    if date not in manifest["dates"]:
        manifest["dates"].append(date)
        manifest["dates"].sort()
    manifest["lastUpdated"] = dt.datetime.now(dt.timezone.utc).isoformat()
    _dump_json(DATA_DIR / "manifest.json", manifest)


def fetch_twse_legacy(url, params, max_retries=3, retry_wait=120):
    """呼叫 www.twse.com.tw 的 legacy JSON 端點。

    TWSE 每日 13:30-13:45 尖峰時段會暫停整批查詢、改回傳提示訊息，遇到時 sleep 後重試；
    請求太密集時偶爾會回傳空白內容（非合法 JSON），視為暫時性錯誤、短暫等待後重試；
    非交易日或查無資料則回傳 None（呼叫端應視為「當天略過」，不是錯誤）。
    """
    for attempt in range(max_retries):
        r = SESSION.get(url, params=params, headers=TWSE_HEADERS, timeout=20)
        r.raise_for_status()
        try:
            data = r.json()
        except ValueError:
            if attempt < max_retries - 1:
                time.sleep(5)
                continue
            return None
        stat = data.get("stat") if isinstance(data, dict) else None
        if stat == "OK":
            return data
        if stat and "尖峰" in stat and attempt < max_retries - 1:
            time.sleep(retry_wait)
            continue
        return None
    return None


def fetch_tpex_openapi(path):
    """呼叫 TPEx 新版 OpenAPI（僅回傳近期滾動資料，不支援指定歷史日期）。"""
    r = SESSION.get(
        f"https://www.tpex.org.tw/openapi/v1/{path}", headers=TPEX_HEADERS, timeout=20
    )
    r.raise_for_status()
    return r.json()


# ---------- TWSE 上市 ----------


def fetch_twse_index(date_ymd):
    """date_ymd: 西元 'YYYYMMDD'。回傳 None 表示當天非交易日。"""
    data = fetch_twse_legacy(
        "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX",
        {"response": "json", "date": date_ymd, "type": "ALL"},
    )
    if not data:
        return None
    result = None
    for table in data.get("tables", []):
        for row in table.get("data") or []:
            if row and row[0] == "發行量加權股價指數":
                # TWSE 的「漲跌點數」欄只給量值（要靠顏色判斷正負），但「漲跌百分比」欄
                # 有時已經自帶負號——兩欄的簽名慣例不一致，所以分開判斷、已有負號的直接信任。
                sign = -1 if "green" in row[2] else 1
                result = {
                    "close": _num(row[1]),
                    "change": _signed(row[3], sign),
                    "changePercent": _signed(row[4], sign),
                }
                break
        if result:
            break
    if not result:
        return None

    # MI_INDEX 沒有日內最高/最低，另外從 MI_5MINS_HIST 撈（同樣是整個月一次回來，這裡只挑
    # 目標那一天）。抓不到就用收盤價頂著，不讓整個 index 因為這個次要欄位變成 None。
    month_high_low = fetch_twse_index_month_high_low(date_ymd)
    high, low = month_high_low.get(ymd8_to_iso(date_ymd), (None, None))
    result["high"] = high if high is not None else result["close"]
    result["low"] = low if low is not None else result["close"]
    return result


def fetch_twse_index_month_high_low(date_ymd):
    """date_ymd: 西元 'YYYYMMDD'（月份內任一天皆可，端點本身是照月份回傳整批）。
    回傳 {iso_date: (high, low)}，查無資料時回傳 {}。獨立成月批次函式方便 backfill
    情境重複使用同一個月的資料，不用每天都重打一次同一個月的請求。
    """
    data = fetch_twse_legacy(
        "https://www.twse.com.tw/rwd/zh/TAIEX/MI_5MINS_HIST",
        {"response": "json", "date": date_ymd},
    )
    if not data:
        return {}
    result = {}
    for row in data.get("data", []):
        roc_y, m, d = row[0].split("/")
        result[f"{int(roc_y) + 1911}-{m}-{d}"] = (_num(row[2]), _num(row[3]))
    return result


def fetch_twse_institutional(date_ymd):
    data = fetch_twse_legacy(
        "https://www.twse.com.tw/rwd/zh/fund/BFI82U",
        {"response": "json", "dayDate": date_ymd, "type": "day"},
    )
    if not data:
        return None
    rows = data.get("data", [])

    def combine(*name_prefixes):
        # TWSE 的「外資及陸資」列名有時會帶「(不含外資自營商)」等註記字尾，用前綴比對比較保險。
        # 「外資自營商」這列的金額官方已經算進自營商合計裡了，不能再另外加一次，所以不列入比對前綴。
        buy = sell = net = 0.0
        for row in rows:
            if any(row[0].startswith(prefix) for prefix in name_prefixes):
                buy += _num(row[1])
                sell += _num(row[2])
                net += _num(row[3])
        return {"buy": buy, "sell": sell, "net": net}

    return {
        "foreign": combine("外資及陸資"),
        "trust": combine("投信"),
        "dealer": combine("自營商(自行買賣)", "自營商(避險)"),
        "total": combine("合計"),
    }


def fetch_twse_margin(date_ymd):
    data = fetch_twse_legacy(
        "https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN",
        {"response": "json", "date": date_ymd, "selectType": "ALL"},
    )
    if not data or not data.get("tables"):
        return None
    rows = {r[0]: r for r in data["tables"][0].get("data", [])}
    margin_row = rows.get("融資金額(仟元)")
    short_row = rows.get("融券(交易單位)")
    if not margin_row or not short_row:
        return None
    return {
        "marginBalance": _num(margin_row[5]) * 1000,  # 仟元 -> 元，跟 TPEx 那邊統一單位
        "marginBalancePrev": _num(margin_row[4]) * 1000,
        "marginUnit": "元",
        "shortBalance": _num(short_row[5]),
        "shortBalancePrev": _num(short_row[4]),
        "shortUnit": "張",
    }


# ---------- TPEx 上櫃（近期資料，僅供每日排程使用）----------


def fetch_tpex_index_latest(target_date_iso):
    """target_date_iso: 'YYYY-MM-DD'。這幾個 TPEx 端點只回傳近期滾動資料、沒有日期參數，
    所以要自己核對回傳的最新一筆是不是真的等於目標日期——三大法人／融資融券常常會比
    指數晚一天才公布，如果直接拿「最新一筆」硬塞進目標日期的快照，會把前一天的資料誤標成當天。
    日期對不上就回傳 None（視為當天尚未公布）。
    """
    data = fetch_tpex_openapi("tpex_index")
    if not data:
        return None
    last = data[-1]
    if ymd8_to_iso(last["Date"]) != target_date_iso:
        return None
    close = _num(last["Close"])
    change = _num(last["Change"])
    prev_close = close - change
    change_pct = (change / prev_close * 100) if prev_close else 0.0
    return {
        "close": close,
        "change": change,
        "changePercent": change_pct,
        "high": _num(last["High"]),
        "low": _num(last["Low"]),
    }


def fetch_tpex_institutional_latest(target_date_iso):
    data = fetch_tpex_openapi("tpex_3insti_summary")
    if not data or roc7_to_iso(data[0]["Date"]) != target_date_iso:
        return None
    by_investor = {row["Investor"]: row for row in data}

    def cat(name):
        row = by_investor.get(name)
        if not row:
            return {"buy": 0.0, "sell": 0.0, "net": 0.0}
        return {
            "buy": _num(row["PurchaseAmount"]),
            "sell": _num(row["SaleAmount"]),
            "net": _num(row["Net"]),
        }

    return {
        "foreign": cat("外資及陸資合計"),
        "trust": cat("投信"),
        "dealer": cat("自營商合計"),
        "total": cat("三大法人合計*"),
    }


def fetch_tpex_close_prices_by_date(roc_date):
    """roc_date: 民國年日期，如 '115/07/27'。回傳 {股票代號: 收盤價}，legacy 端點，供回補使用。"""
    r = SESSION.get(
        "https://www.tpex.org.tw/web/stock/aftertrading/otc_quotes_no1430/stk_wn1430_result.php",
        params={"l": "zh-tw", "d": roc_date, "se": "EW", "o": "json"},
        headers=TPEX_HEADERS,
        timeout=20,
    )
    r.raise_for_status()
    data = r.json()
    tables = data.get("tables") or []
    rows = tables[0].get("data") if tables else None
    if not rows:
        return {}
    # row: [代號, 名稱, 收盤, 漲跌, 開盤, 最高, 最低, ...]
    return {row[0]: _num(row[2]) for row in rows}


def fetch_tpex_credit_official():
    """呼叫 TPEx 首頁走勢圖 widget 用的內部 API，一次拿到融資金額與融券張數的官方數字。

    ⚠️ 這不是 openapi/swagger.json 裡正式文件化的端點，沒有官方保證長期可用；
    只回溯最近約 10 個交易日，不能拿來回補更久以前的歷史，只能當「今天」或
    「最近幾天」的權威資料來源。

    融資金額（`marginPurchaseValue10Days`，億元）跟融券張數（`shortSell10Days`，千張）
    是同一次 API 呼叫、同一個 `dataDate` 出來的，保證兩者同步更新，不會有「融資出來了但
    融券還沒出來」（或反過來）的情況——早期版本融資用這支端點、融券用另一支逐檔資料
    （`tpex_mainboard_margin_balance`）湊出來，結果兩邊實測公布時間不同步，一邊有資料
    就會被另一邊還沒出來拖累。改成兩個數字都從這支端點拿，從根本解決同步問題。

    回傳 {iso_date: {"marginBalance", "marginBalancePrev", "shortBalance", "shortBalancePrev"}}
    （元／張），失敗時回傳 {}。
    """
    try:
        r = SESSION.get(
            "https://www.tpex.org.tw/data/home/dayChart.json", headers=TPEX_HEADERS, timeout=20
        )
        r.raise_for_status()
        data = r.json()
        latest_iso = roc7_to_iso(data["dataDate"])
        margin_rows = data["marginPurchaseValue10Days"]
        short_rows = data["shortSell10Days"]
    except (requests.RequestException, ValueError, KeyError):
        return {}

    latest_year, latest_month = int(latest_iso[:4]), int(latest_iso[5:7])

    def date_key(mmdd):
        mm, dd = mmdd.split("-")
        # 10 天內若跨年（例如現在 1 月、列表裡有去年 12 月），月份會比最新一筆大，要退一年。
        year = latest_year - 1 if int(mm) > latest_month else latest_year
        return f"{year}-{mm}-{dd}"

    result = {}
    for row in margin_rows:
        amt_yuan = row["amt"] * 1e8
        entry = result.setdefault(date_key(row["date"]), {})
        entry["marginBalance"] = amt_yuan
        entry["marginBalancePrev"] = amt_yuan - row["dif"] * 1e8
    for row in short_rows:
        bal_zhang = row["bal"] * 1000
        entry = result.setdefault(date_key(row["date"]), {})
        entry["shortBalance"] = bal_zhang
        entry["shortBalancePrev"] = bal_zhang - row["dif"] * 1000
    return result


def fetch_tpex_margin_latest(target_date_iso):
    """融資融券只信任 fetch_tpex_credit_official() 這個官方來源，沒有當天資料就整包回傳
    None——寧可顯示「尚無資料」，也不要退回去用「張數 x 收盤價」這種沒扣融資成數、可能
    誤導的估算金額（之前吃過這個虧）。
    """
    official = fetch_tpex_credit_official().get(target_date_iso)
    if not official:
        return None
    return {
        "marginBalance": official.get("marginBalance"),
        "marginBalancePrev": official.get("marginBalancePrev"),
        "marginUnit": "元",
        "source": "tpex_official",
        "shortBalance": official.get("shortBalance"),
        "shortBalancePrev": official.get("shortBalancePrev"),
        "shortUnit": "張",
    }


# ---------- TPEx 上櫃（歷史資料，僅供 backfill 使用）----------
#
# TPEx 新版 OpenAPI（tpex_index / tpex_3insti_summary / tpex_mainboard_margin_balance）
# 不接受日期參數，只能拿到近期滾動資料，回補歷史要改走 legacy 網頁端點（民國年日期格式）。
#
# 三大法人（3itrade_hedge_result.php）目前只找到「逐檔個股、7 組買賣超股數」的版本，
# 但 7 組欄位沒有標名稱、順序未經官方文件證實，貿然假設順序去加總風險太高，所以「不」
# 實作 TPEx 歷史三大法人回補——這段期間的 TPEx 三大法人資料留白，只能從程式開始每日
# 排程執行之後才有（用 fetch_tpex_institutional_latest 那組乾淨的彙總端點）。
#
# 融資融券（margin_bal_result.php）逐檔個股欄位都有清楚命名，張數可以安全加總；金額則另外
# 用同一天的收盤價（stk_wn1430_result.php）換算成市值估算（沒有官方金額可用時的次選）。
# 這條路徑只用在 Report.csv 涵蓋不到、且 dayChart.json 也回溯不到的更久以前歷史，
# 「今天」的每日排程改用 fetch_tpex_margin_latest（只信任 dayChart.json 官方數字）。


def fetch_tpex_index_month(roc_year_month):
    """roc_year_month: 民國年/月，如 '115/07'。回傳整個月每個交易日的指數資料 list。"""
    r = SESSION.get(
        "https://www.tpex.org.tw/web/stock/iNdex_info/inxh/Inx_result.php",
        params={"l": "zh-tw", "d": roc_year_month, "o": "json"},
        headers=TPEX_HEADERS,
        timeout=20,
    )
    r.raise_for_status()
    data = r.json()
    tables = data.get("tables") or []
    if not tables:
        return []
    result = []
    for row in tables[0].get("data") or []:
        # row: [日期('2026/07/01'), 開市, 最高, 最低, 收市, 漲/跌]
        close = _num(row[4])
        change = _num(row[5])
        prev_close = close - change
        change_pct = (change / prev_close * 100) if prev_close else 0.0
        result.append(
            {
                "date": row[0].replace("/", "-"),
                "close": close,
                "change": change,
                "changePercent": change_pct,
                "high": _num(row[2]),
                "low": _num(row[3]),
            }
        )
    return result


def fetch_tpex_margin_by_date(roc_date):
    """roc_date: 民國年日期，如 '115/07/27'。回傳 None 表示當天查無資料。

    融資金額一樣用「張數 × 1000股 × 當天收盤價」換算成新台幣（估算值，見 _build_tpex_margin）。
    """
    r = SESSION.get(
        "https://www.tpex.org.tw/web/stock/margin_trading/margin_balance/margin_bal_result.php",
        params={"l": "zh-tw", "d": roc_date, "o": "json"},
        headers=TPEX_HEADERS,
        timeout=20,
    )
    r.raise_for_status()
    data = r.json()
    tables = data.get("tables") or []
    rows = tables[0].get("data") if tables else None
    if not rows:
        return None
    # fields: 代號,名稱,前資餘額(張),資買,資賣,現償,資餘額,資屬證金,資使用率(%),資限額,
    #         前券餘額(張),券賣,券買,券償,券餘額,券屬證金,券使用率(%),券限額,資券相抵(張),備註
    prices = fetch_tpex_close_prices_by_date(roc_date)
    margin_yuan = margin_prev_yuan = 0.0
    short_today = short_prev = 0.0
    for row in rows:
        price = prices.get(row[0], 0.0)
        margin_yuan += _num(row[6]) * 1000 * price
        margin_prev_yuan += _num(row[2]) * 1000 * price
        short_today += _num(row[14])
        short_prev += _num(row[10])
    return {
        "marginBalance": margin_yuan,
        "marginBalancePrev": margin_prev_yuan,
        "marginUnit": "元",
        "source": "estimated",
        "shortBalance": short_today,
        "shortBalancePrev": short_prev,
        "shortUnit": "張",
    }
