# 股市資訊網站 — 架構文件

每日呈現上市（TWSE）／上櫃（TPEx）大盤漲跌、三大法人買賣超、融資融券狀況的靜態網站。

## 方案

零維運靜態架構：GitHub Actions 排程抓資料 → 整理成 JSON commit 回 repo → GitHub Pages 直接讀 JSON 呈現，不需要自建伺服器。資料量小（一天一筆快照），這個方案完全免費、幾乎不用維運。

歷史資料回補範圍：2026-01-01 至今。

## 資料來源

**TWSE 上市：**（`scripts/common.py`，`fetch_twse_*`，每日排程與回補共用同一組端點，只差 `date` 參數）

| 項目 | 端點 | 說明 |
|---|---|---|
| 大盤指數（收盤／漲跌） | `https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?response=json&date=YYYYMMDD&type=ALL` | 從 `tables` 裡找列名為「發行量加權股價指數」的那一列。⚠️「漲跌點數」欄只給量值（要配合顏色 `color:red`/`color:green` 判斷正負），但「漲跌百分比」欄有時已經自帶負號——兩欄簽名慣例不一致，程式裡分開處理 |
| 大盤指數（日內最高／最低） | `https://www.twse.com.tw/rwd/zh/TAIEX/MI_5MINS_HIST?response=json&date=YYYYMMDD` | 帶任一天的日期會回傳「整個月」每個交易日的開高低收（`fields: 日期,開盤指數,最高指數,最低指數,收盤指數`，日期格式民國年 `115/06/23`）。已用 6/23 實測數字（最高 48218.87）驗證。`fetch_twse_index()` 內部會另外呼叫這支端點取得 `high`／`low`，`MI_INDEX` 只提供收盤／漲跌，兩支合併成完整的 index 物件；`fetch_twse_index_month_high_low()` 是月批次版本，backfill 情境用來避免同一個月重複打好幾次 |
| 三大法人買賣金額（全市場合計） | `https://www.twse.com.tw/rwd/zh/fund/BFI82U?response=json&dayDate=YYYYMMDD&type=day` | 回傳自營商(自行買賣)／自營商(避險)／投信／外資及陸資／外資自營商／合計 六列的買進、賣出、買賣差額。⚠️「外資及陸資」這列名稱偶爾會帶「(不含外資自營商)」字尾，比對時用前綴比對而非完全相等；「外資自營商」金額官方已經算進自營商合計裡了，不能再另外加總一次 |
| 融資融券餘額（全市場合計） | `https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?response=json&date=YYYYMMDD&selectType=ALL` | 回傳的 `tables[0]`「信用交易統計」就是全市場彙總，不用自己加總個股：`融資金額(仟元)` 列有前日/今日餘額（程式裡換算成「元」存，跟 TPEx 那邊單位統一），`融券(交易單位)` 列有前日/今日餘額（張）；這份資料**沒有**融券金額的仟元合計，只有張數 |

⚠️ 實測發現的兩個 TWSE 限制：(1) 每日 13:30–13:45（台北時間）尖峰時段會暫停「整批查詢」，改回傳提示訊息，程式遇到會自動 sleep 後重試；(2) 請求太密集（回補歷史時連續打很多天）偶爾會回傳空白內容（非合法 JSON），一樣視為暫時性錯誤、短暫等待後重試，回補腳本每個請求之間也加了 0.3 秒間隔。

⚠️ **三大法人／融資融券的「今天」資料常常比大盤指數晚公布**——實測在台北時間下午跑排程時，大盤指數已經有今天的收盤資料，但三大法人與融資融券還停留在前一天，要到傍晚才會更新。這是把每日排程時間訂在台北時間 18:00 的原因；如果那個時間點資料還沒出來，`fetch_daily.py` 會把該欄位存成 `null`，之後可以用 `workflow_dispatch` 手動重跑同一天來補齊（重跑會覆蓋同一天的舊檔案）。

**TPEx 上櫃：**（`scripts/common.py`，分「近期資料」與「歷史回補」兩組函式，因為新版 OpenAPI 不支援指定日期）

*每日排程用（`fetch_tpex_*_latest`，新版 OpenAPI，已用 Python `requests` + 瀏覽器標頭實測）：*

| 項目 | 端點 | 說明 |
|---|---|---|
| 大盤指數 | `https://www.tpex.org.tw/openapi/v1/tpex_index` | 欄位 `Date, Open, High, Low, Close, Change`，`High`／`Low` 就是當天日內最高/最低價，直接取用。只回傳近期滾動資料（實測回傳當月 1 日至今），不支援日期參數 |
| 三大法人買賣超（全市場合計） | `https://www.tpex.org.tw/openapi/v1/tpex_3insti_summary` | 欄位 `Date, Investor, PurchaseAmount, SaleAmount, Net`；`Investor` 用到的三個精確字串是「外資及陸資合計」「投信」「自營商合計」，另外有現成的「三大法人合計*」總計列可以直接用，不用自己加總 |
| 融資融券餘額 | `https://www.tpex.org.tw/openapi/v1/tpex_mainboard_margin_balance` | 欄位 `MarginPurchaseBalance, MarginPurchaseBalancePreviousDay, ShortSaleBalance, ShortSaleBalancePreviousDay`（張），是逐檔個股資料，腳本裡加總全部個股 |
| 收盤價（換算融資金額用） | `https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes` | 逐檔個股收盤價，跟上面融資融券資料用同一個 `SecuritiesCompanyCode` 欄位對應股票代號 |

因為這幾個端點沒有日期參數，程式會核對回傳資料裡的 `Date` 是不是真的等於目標日期，對不上（代表當天還沒公布）就回傳 `null`，避免把前一天的資料誤標成今天。

⚠️ **TPEx 逐檔融資融券資料只有張數，沒有官方金額**（不像 TWSE 有現成的「融資金額(仟元)」）。原本用「張數 × 1000股 × 收盤價」自行換算金額，但這只是**市值**，不是實際融資金額（沒扣掉融資成數，一般股票只借得到市值 6 成），比真實數字高了約 40%。後來找到下面這支官方端點可以直接拿到正確金額：

| 項目 | 端點 | 說明 |
|---|---|---|
| 融資融券（官方，唯一來源） | `https://www.tpex.org.tw/data/home/dayChart.json` | TPEx 首頁走勢圖 widget 用的內部 API，**沒有出現在 `openapi/swagger.json` 裡，非正式文件化端點**，沒有官方保證長期可用。`dataDate`（民國年）是最新一筆的日期；`marginPurchaseValue10Days` 是最近約 10 個交易日的融資餘額 `{date:"MM-DD", amt(億元), dif(億元)}` 陣列；`shortSell10Days` 是同樣天數的融券張數 `{date, bal(千張), dif(千張)}` 陣列（無年份，程式用 `dataDate` 的年份推回去、月份比 `dataDate` 大時代表跨年、要退一年）。融資已用 wantgoo 網站的公開數字交叉驗證，07/27 兩邊都是 1883.47 億，完全一致；融券已用 `Report.csv` 的官方數字交叉驗證 |

`fetch_tpex_credit_official()`（`common.py`）呼叫這支端點，**一次拿到融資金額和融券張數**，回傳 `{iso_date: {marginBalance, marginBalancePrev, shortBalance, shortBalancePrev}}`（元／張）。`fetch_tpex_margin_latest()`（每日排程用）只信任這個來源：當天有資料就用，標記 `"source": "tpex_official"`；沒有就整包回傳 `None`——**不會**再退回去用「張數 × 收盤價」估算（早期版本會這樣 fallback，估算值沒扣融資成數、容易誤導，出過一次狀況後改掉）。

⚠️ 早期版本融資金額用這支端點、融券張數改用另一支逐檔資料（`tpex_mainboard_margin_balance`）加總，實測發現**兩者公布時間不同步**——某天融資金額已經更新、逐檔張數卻還停在前一天，導致融資明明已經公布卻被融券拖累顯示不出來。後來發現 `dayChart.json` 本身就同時有 `marginPurchaseValue10Days`（融資）跟 `shortSell10Days`（融券），是同一次呼叫、同一個 `dataDate`，兩個數字保證同步，才改成兩者都從這支端點拿，不再需要 `tpex_mainboard_margin_balance`。

**這支端點只回溯約 10 個交易日**，所以只能用在「今天」之後的每日排程；更久的歷史資料改用下面「用 Report.csv 補齊」那段的方式一次性匯入，不是靠這支端點回補。

*回補歷史用（`fetch_tpex_index_month` / `fetch_tpex_margin_by_date`，legacy 網頁端點，民國年日期格式，已實測）：*

| 項目 | 端點 | 說明 |
|---|---|---|
| 大盤指數 | `https://www.tpex.org.tw/web/stock/iNdex_info/inxh/Inx_result.php?l=zh-tw&d=115/07&o=json` | 帶「民國年/月」（不含日）一次回傳整個月每個交易日的開高低收與漲跌，`high`／`low` 直接取用，回補時用月份迴圈抓，比逐日呼叫有效率 |
| 融資融券餘額 | `https://www.tpex.org.tw/web/stock/margin_trading/margin_balance/margin_bal_result.php?l=zh-tw&d=115/07/27&o=json` | 逐檔個股資料，欄位有清楚命名（`前資餘額(張)`、`資餘額`、`前券餘額(張)`、`券餘額`…）；金額換算跟每日排程一樣，另外用 `stk_wn1430_result.php?l=zh-tw&d=115/07/27&se=EW&o=json`（同一天的收盤價，legacy 版）做 join |
| ~~三大法人買賣超~~ | ~~`3itrade_hedge_result.php`~~ | **沒有用這支端點做歷史回補**：這支 legacy 端點雖然存在（`/web/stock/3insti/daily_trade/3itrade_hedge_result.php`），但回傳的是逐檔個股、7 組買賣超股數，7 組欄位沒有標名稱、分類順序沒有官方文件佐證，貿然假設順序去加總誤植的風險太高，所以選擇不做。歷史三大法人資料後來改用下面「用 Report.csv 補齊」的方式一次性匯入 |

### 用 Report.csv 補齊歷史融資融券與三大法人（一次性匯入，已完成）

`dayChart.json` 只回溯 10 個交易日，沒辦法補更久以前的歷史；歷史三大法人也一直沒有可靠端點。後來使用者直接從 TPEx 官網下載了官方報表 `Report.csv`，涵蓋 2026-01-02 ~ 2026-07-27（跟這個專案回補的範圍完全吻合），裡面同時有**融資餘額（億元）**與**三大法人買賣超淨額（億元）**的官方逐日數字，比估算或係數修正準確得多，直接拿來取代。

- 格式：Big5 編碼、**Tab 分隔**（雖然副檔名是 `.csv`）；日期欄格式 `'26/07/27`（民國年 2 碼），千分位逗號的欄位有雙引號包住。欄位順序：期別／收盤／漲跌／漲跌(%)／成交量(億元)／融資增減／**融資餘額**／融卷增減／**融卷餘額**／**外資買賣超(億元)**／**投信買賣超(億元)**／**自營商買賣超(億元)**／**三大法人合計**。
- `scripts/import_tpex_report_csv.py`（一次性，已執行）：解析 CSV，`marginBalancePrev`／`shortBalancePrev` 用「前一個交易日自己那列的餘額」串出來（不是用「增減」欄位反推，避免捨入誤差累積），覆蓋對應日期 `data/daily/{date}.json` 的 `tpex.margin`（標記 `source: "tpex_official"`）與 `tpex.institutional`。
- ⚠️ CSV 只有三大法人的**買賣超淨額**，沒有個別買進／賣出金額，所以這段歷史資料的 `tpex.institutional.{foreign,trust,dealer,total}.buy` / `.sell` 是 `null`，只有 `.net` 有值——前端本來就只顯示 `net`，不受影響。
- 這個匯入只覆蓋 CSV 涵蓋到的日期（到 2026-07-27 為止）；再更新的日期還是由 `fetch_daily.py` 每天即時抓取（含 `dayChart.json` 官方融資來源），跟這次匯入無關，不會被覆蓋。

⚠️ `www.tpex.org.tw` 對沒有瀏覽器標頭的請求會回 403（WAF 擋爬蟲），抓取時務必帶上 `User-Agent`（設成常見瀏覽器字串）與 `Referer: https://www.tpex.org.tw/`。

⚠️ 這台開發機的 Python（3.14 + 新版 OpenSSL）對 `tpex.org.tw` 的憑證驗證預設會失敗（`Missing Subject Key Identifier`——瀏覽器與舊版 OpenSSL 都能接受，只有較新版 OpenSSL 的嚴格模式會拒絕）。`common.py` 用一個自訂的 `requests` `HTTPAdapter` 關掉 `ssl.VERIFY_X509_STRICT` 這個嚴格旗標解決，憑證鏈與主機名稱仍然正常驗證，不影響安全性。GitHub Actions 的 Ubuntu runner 未必會踩到這個問題，但兩邊統一用同一個 session 比較保險。

## 檔案結構

```
股市資訊/
├── .github/workflows/
│   └── fetch-daily.yml        # 排程：平日 18:00 台北時間跑，另開 workflow_dispatch 手動觸發（可帶 date 參數補特定一天）
├── scripts/
│   ├── common.py                       # 共用：呼叫 API、正規化 schema、寫入 data/ 的邏輯
│   ├── fetch_daily.py                  # 抓「今天」資料，寫入 daily + 附加進 series
│   ├── backfill.py                     # 一次性：迴圈 2026-01-01 至今的交易日，補齊 data/
│   ├── apply_official_tpex_margin.py   # 一次性：把最近 10 個交易日的 TPEx 融資估算值換成 dayChart.json 官方值
│   ├── import_tpex_report_csv.py       # 一次性：用 Report.csv 補齊 TPEx 歷史融資融券與三大法人（見下方說明）
│   └── backfill_index_high_low.py      # 一次性：幫已回補的 data/daily 補上指數日內最高/最低價
├── data/
│   ├── daily/{date}.json      # 當日完整快照（index / institutional / margin，各分 twse、tpex）
│   ├── series/index.json      # 逐日累積的指數時間序列，前端畫趨勢圖用，避免要抓幾百個 daily 檔案
│   ├── series/institutional.json
│   ├── series/margin.json
│   └── manifest.json          # 有資料的日期清單 + lastUpdated，前端用來設定日期選擇的可選範圍
├── index.html                 # 靜態前端：今日卡片 + Chart.js 趨勢圖 + 歷史日期選擇
├── assets/style.css
├── assets/app.js
└── README.md
```

`fetch_daily.py` 與 `backfill.py` 共用 `common.py` 裡的抓取／正規化函式，差別只在日期迴圈範圍，避免兩份重複邏輯。

## 排程邏輯

- Cron：兩個時段，平日各跑一次，UTC 08:30／13:30 = 台北時間 **16:30**／**21:30**。每次都是全量抓取（`fetch_daily.py` 對同一天重跑是安全的），16:30 這次主要是讓三大法人買賣超（通常較早公布）進 repo；21:30 這次主要是補上融資融券（實測約 21:10 前後才公布，比三大法人晚很多）。哪個時段實際抓到哪些欄位取決於當天官方公布時間，不是寫死的，兩個時段互補、有缺就等下一次補上。
- 另外開 `workflow_dispatch`，可帶一個 `date`（YYYY-MM-DD）輸入手動重跑或補資料；不帶就抓今天。`fetch_daily.py` 對同一天重跑是安全的，會直接覆蓋舊檔案。
- 若當天不是交易日（TWSE 回傳空值），腳本直接結束，不寫檔、不 commit，維持 repo 乾淨、可重複執行（idempotent）。
- 抓完資料後：`git add data/ && git commit && git push`，用 workflow 內建的 `GITHUB_TOKEN`（需開 `permissions: contents: write`）。

## 前端

純靜態頁面，讀取 `data/manifest.json` 取得可選日期，預設顯示最新一天：

- 今日卡片：大盤指數（含漲跌／漲跌%）、三大法人買賣超金額、融資融券餘額（含較前日增減），上市／上櫃分開顯示
- **區間比較**：兩個日期選擇器（起始／結束，內容來自 `manifest.dates`，預設抓最近約 20 個交易日），上市／上櫃各自顯示：
  - 指數漲跌：先比較起始／結束日收盤判斷這段是漲是跌（結束 ≥ 起始視為上漲），再決定起點跟搜尋方向——**上漲**：起始日的「最低點」當起漲點，「最高點」在整個區間裡搜尋（不一定是結束日）；**下跌**：起始日的「最高點」當起跌點，「最低點」在整個區間裡搜尋（不一定是結束日）。因為起點固定在起始日、搜尋到的極值日期必定晚於或等於起始日，不需要再判斷時間先後。
  - 融資餘額變化：高點、低點都在整個區間裡搜尋最大/最小值（不假設哪一天是高或低，融資部位的高低點常常跟指數不同天）。顯示時依實際發生的時間先後排序——較早的一筆當起點、較晚的一筆當終點，這樣下跌波段（高點在前、低點在後）跟上漲波段（低點在前、高點在後）都能正確顯示、正負號跟漲跌方向一致。兩個 stat tile 底下都有小字動態標示實際取用的日期和數值（例如「高 X億(日期) → 低 Y億(日期)」或反過來），方便核對。
  - 三大法人買賣超區間累計（把區間內每天的 `net` 加總）。
  - 一張「相對起始日變化 %」的走勢圖（指數與融資餘額都換算成 % 疊在同一張圖，方便看兩者是不是同向；這張圖的基準點固定用起始日，跟上面融資 stat tile 用「區間最高點」當基準不同，圖表著重看整段走勢、stat tile 著重抓最大變化量）。

  全部在前端算，資料來源是已經載入的 `data/series/{index,margin,institutional}.json`，換區間不用重新打 API。
- **近一個月表格**：兩張趨勢圖下方，抓最近 22 個交易日（約一個月），欄位是日期＋上市／上櫃各自的指數、融資餘額（億）、融資增減，增減用紅漲綠跌上色。
- 趨勢圖（Chart.js）：兩張獨立圖表（上市一張、上櫃一張），各自疊加「指數」與「融資餘額（億元）」雙 Y 軸
- 日期選擇：頂部日期、區間比較的起始／結束都是原生 `<input type="date">`（月曆式選擇，不是下拉選單，避免資料累積後選單太長），`min`/`max` 設成 `manifest.dates` 的範圍。原生 date input 沒辦法把範圍內個別沒資料的日子（週末、假日）標成不可選，選到這種日子時前端會優雅顯示「尚無資料」（`loadDate()` 改用 `fetchJSONOrNull()`，404 時回傳 `null` 而不是丟例外）。
- **圖表放大燈箱**：4 張圖表（2 張區間比較走勢圖 + 2 張長期趨勢圖）的外層容器都有 `.chart-clickable`，點擊會跳出置中的彈出視窗，用同一份資料重畫一張大圖。做法是每個 `buildMarketChart()`／`buildRangeChart()` 呼叫時，把「重新產生目前 config」的函式存進 `chartConfigProviders[canvasId]`，點擊當下才呼叫這個函式建立 modal 圖表——這樣區間比較換日期後再點放大，看到的一定是當下選的區間，不是開燈箱那一刻的舊快照。關閉方式：點背景遮罩、點右上角關閉鈕、按 Esc。

`assets/app.js` 的 `init()` 只在頁面載入時打一次 `data/series/{index,margin,institutional}.json`，存成三個 `Map`（`indexByDate`／`marginByDate`／`institutionalByDate`），區間比較、近一月表格、趨勢圖都共用這三個 Map，不會每個功能各自重複 fetch。

## 實作步驟

0. **（本文件）** 先產出這份架構文件，確認方向後才開始寫程式／建 repo。
1. **使用者手動**：在 GitHub 開一個新的 public repo，本機資料夾 `git init` 並加上 remote。
2. 撰寫 `scripts/common.py` + `scripts/fetch_daily.py`，本機測試，確認能產生 `data/daily/{today}.json` 且假日會自動跳過。
3. ~~用 Python `requests` 實測 TPEx 對應端點~~ 已於規劃階段驗證完成（見上表），`common.py` 直接依驗證結果實作上櫃抓取邏輯即可。
4. 撰寫 `scripts/backfill.py`，本機執行一次回補 2026-01-01 至今的資料。
5. 撰寫 `index.html` / `assets/app.js`，本機用 `python -m http.server` 測試畫面。
6. 撰寫 `.github/workflows/fetch-daily.yml`。
7. commit 全部檔案，push 到 GitHub repo（push 前會先確認）。
8. Repo Settings → Pages，設定 Deploy from branch：`main` / `(root)`。
9. 手動觸發一次 `workflow_dispatch`，確認 Actions 能成功寫入新 commit，GitHub Pages 網址能看到資料。

## 上線後的修正紀錄

網站上線、GitHub Pages 打得開之後，陸續修正的問題與新增的功能（依時間順序）：

1. **TPEx 融資餘額單位跟 TWSE 對不起來**：原本 TPEx 顯示張數、TWSE 顯示金額，改成用張數×收盤價換算法，統一都用「元」，前端統一用「億元」呈現。因為這個改動影響所有歷史資料的 schema，`data/` 整批清空後用新版 `common.py` 重新跑過一次 `backfill.py`。
2. **趨勢圖 Y 軸太短、沒刻度，且要求拆成上市／上櫃各一張**：原因是 canvas 寫死了 `height="90"` 又沒設 `maintainAspectRatio: false`，改成外層 `.chart-wrap` 給固定高度（320px）＋ `maintainAspectRatio: false`；並把單一圖表拆成 `#twse-chart` / `#tpex-chart` 兩張，各自疊加指數（左軸）與融資餘額（右軸）。
3. **TPEx 融資金額（張數×收盤價換算法）比外部網站（wantgoo）高了約 40%**：漏乘融資成數，換算的其實是市值不是融資金額。找到 `data/home/dayChart.json` 這支非正式端點可以拿到官方正確數字後，一開始改成「官方優先、估算 fallback」（見上面「資料來源」段落），並寫了一次性腳本 `scripts/apply_official_tpex_margin.py` 把已經回補的最近 10 個交易日換成官方值。
4. **10 天以前的 TPEx 融資餘額仍是市值估算、櫃買三大法人歷史資料整片空白**：`dayChart.json` 只能回溯 10 天，原本打算用融資成數 0.6 當係數修正舊資料。後來使用者直接從 TPEx 官網下載官方報表 `Report.csv`（涵蓋 2026-01-02 ~ 2026-07-27），改用 `scripts/import_tpex_report_csv.py` 一次性匯入真正的官方逐日數字，取代係數修正的做法，同時把整片空白的歷史三大法人資料補齊（見上面「用 Report.csv 補齊」段落）。匯入後全部 134 天的 `tpex.margin.source` 都是 `"tpex_official"`；`tpex.institutional` 的 `buy`／`sell` 是 `null`（CSV 只有淨額）。
5. **看到的資料是舊的，但部署內容其實是對的（發生兩次）**：GitHub Pages 的 CDN／瀏覽器對 `data/*.json` 快取的時間比資料實際更新頻率長。前端所有抓 JSON 的地方統一改用 `assets/app.js` 裡的 `fetchJSON()` helper，自動加上時間戳記查詢參數避免快取。
6. **拿掉「官方優先、估算 fallback」，改成「只信任官方，沒有就顯示尚未公布」**：item 3 那個 fallback 邏輯有個縫隙——`dayChart.json`（官方金額）跟逐檔張數資料（`tpex_mainboard_margin_balance`）不是同時更新，如果張數先出來、官方金額還沒出來，`fetch_tpex_margin_latest()` 會退回去用估算值，顯示沒扣融資成數、偏高的市值當融資餘額，跟 item 3 修的問題一樣會誤導人。改成 `fetch_tpex_margin_latest()` 只信任 `fetch_tpex_margin_value_official()`：官方數字還沒出來時 `marginBalance`／`marginBalancePrev` 是 `null`、`source` 是 `"pending"`，前端顯示「尚未公布」而不是錯誤的估算數字；融券張數不受影響（一律用逐檔資料加總，本來就準確，沒有估算問題，跟融資金額是否公布無關）。因為「latest」路徑不再需要估算邏輯，順手刪掉了已經沒人呼叫的 `_build_tpex_margin()` 與 `fetch_tpex_close_prices_latest()`（`fetch_tpex_margin_by_date()` 那條 backfill 專用路徑不受影響，繼續保留自己的估算邏輯，只用在 CSV 涵蓋不到的未來回補情境）。
7. **上櫃融資金額跟融券張數公布時間不同步，導致有資料也顯示不出來**：item 6 修完後，實測發現融資金額（`dayChart.json`）跟融券張數（原本用另一支逐檔資料 `tpex_mainboard_margin_balance` 加總）公布時間常常對不上，某天融資金額已經出來、逐檔張數卻還停在前一天，而 `fetch_tpex_margin_latest()` 是用「張數資料的日期」當進入判斷的關卡，張數沒到就連已經公布的融資金額也一起被吃掉、整包回傳 `None`。後來發現 `dayChart.json` 本身同時有 `marginPurchaseValue10Days`（融資）跟 `shortSell10Days`（融券張數），是同一次呼叫拿到的，`dataDate` 保證一致——改成兩個數字都從 `dayChart.json` 拿（新的 `fetch_tpex_credit_official()`），不再需要 `tpex_mainboard_margin_balance`，從根本解決同步問題，而不是讓兩邊各自判斷日期去繞過它。
8. **單一排程時間抓不齊三大法人跟融資融券**：兩者公布時間差很多（三大法人較早、融資融券實測約 21:10 前後才出來），單一個 18:00 的排程沒辦法兩個都保證抓到。改成兩個時段：台北時間 16:30（主要抓三大法人）與 21:30（主要補融資融券），`fetch-daily.yml` 的 `on.schedule` 加了第二筆 cron。兩次執行都是全量抓取，沒有互相依賴，缺的欄位由較晚那次自然補上。
9. **區間比較的指數「高/低」補上真正的日內最高/最低價**：一開始 TWSE 端點（`MI_INDEX`）沒有加權指數的日內高低價，只能先用收盤價代替上線（見上一版本紀錄）。後來找到 `MI_5MINS_HIST` 這支端點（用 6/23 實測驗證：收盤 47100.65、真正最高 48218.87，兩者換算跌幅差了 2.37 個百分點，證實有必要修正），`fetch_twse_index()` 改成同時打 `MI_INDEX`（收盤/漲跌）跟 `MI_5MINS_HIST`（高/低）合併成完整的 index 物件；TPEx 那邊的資料來源本來就有 High/Low，只是補上兩個欄位。寫了一次性腳本 `scripts/backfill_index_high_low.py`，只更新已回補 135 天的 `index.high`／`index.low`（照月份批次抓，不會同一個月重複打好幾次），不動 margin／institutional。前端當時改成「起始日最高 → 結束日最低」——這個算法後來在 item 11 又被修正過，見下方。
10. **區間比較的融資餘額高低點都改成區間內搜尋，不再固定用結束日**：原本融資低點固定用結束日的實際餘額，分析下跌波段沒問題，但上漲波段（融資低點通常在區間中段偏前，不是結束日）比較不出來。改成高點、低點都在區間內搜尋，依實際發生的時間先後排序決定起訖點與正負號方向，兩種波段都驗證過（1/2~1/28 上漲、6/23~7/28 下跌）。
11. **區間比較的指數改成依漲跌方向決定起點與搜尋方式**：item 9 那版「起始日最高 → 結束日最低」只適用於使用者刻意選「波段最高那天當起始日」的下跌分析情境，遇到上漲區間（例如 1/2~7/28，指數從約 29000 漲到 41600）會把方向跟數字都搞反。改成先用起始/結束日收盤判斷這段是漲是跌：上漲時起始日最低點當起漲點、最高點在整個區間裡搜尋（不一定是結束日）；下跌時起始日最高點當起跌點、最低點在區間裡搜尋。因為錨點固定在起始日，搜尋到的極值日期必定不早於起始日，不用再額外判斷時間先後。
12. **四張圖表加上點擊放大功能**：兩張區間比較走勢圖與兩張長期趨勢圖的外層容器都加上 `.chart-clickable`，點擊會跳出置中的彈出視窗（`#chart-modal`），用同一份資料重畫一張大圖。每個 `buildMarketChart()`／`buildRangeChart()` 呼叫時會把「重新產生目前 config」的函式存進 `chartConfigProviders[canvasId]`，點擊當下才呼叫，確保換過日期的區間比較圖表放大時顯示的是當下資料，不是舊快照。關閉方式：背景遮罩、右上角關閉鈕、Esc。
13. **三個日期選擇改成月曆式**：原本用 `<select>` 塞滿 `manifest.dates` 全部日期，資料累積後下拉選單會越來越長。改成原生 `<input type="date">`，`min`/`max` 限制在資料範圍內。原生 date input 沒辦法把範圍內個別沒資料的日子（週末、假日）標成不可選，選到這種日子時 `loadDate()` 改用新增的 `fetchJSONOrNull()`（404 時回傳 `null` 而不是丟例外），前端優雅顯示「尚無資料」。

## 驗證方式

- 本機執行 `python scripts/fetch_daily.py`，檢查 `data/daily/{today}.json` 內容與欄位。
- 本機執行 `python scripts/backfill.py`，抽查幾個日期（含週末、國定假日應自動跳過）。
- 本機起 `python -m http.server` 開 `index.html`，確認畫面讀得到 `data/`、圖表與卡片正確、切換日期資料會變。
- push 後檢查 GitHub repo 的 Actions 分頁 workflow 是否綠勾、`data/` 是否有新 commit。
- 開啟 GitHub Pages 網址，確認能正常顯示當天資料。
