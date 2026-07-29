"""一次性腳本：幫已經回補的 data/daily/*.json 補上指數的日內最高/最低價（high/low）。

只更新 twse.index / tpex.index（以及 data/series/index.json），不動 margin／institutional
（那些已經是正確的官方資料，不需要重跑）。照月份分組批次抓，同一個月的 TWSE/TPEx 指數
資料都只打一次 API，135 天不會變成 135 次重複請求。
"""
import json
from collections import defaultdict

import common


def main():
    daily_dir = common.DATA_DIR / "daily"
    paths = sorted(daily_dir.glob("*.json"))

    by_month = defaultdict(list)
    for path in paths:
        by_month[path.stem[:7]].append(path)

    updated = 0
    for ym in sorted(by_month):
        year, month = ym.split("-")
        roc_ym = f"{int(year) - 1911}/{month}"
        sample_ymd = f"{year}{month}01"

        twse_high_low = common.fetch_twse_index_month_high_low(sample_ymd)
        tpex_rows = {r["date"]: r for r in common.fetch_tpex_index_month(roc_ym)}

        for path in by_month[ym]:
            with open(path, encoding="utf-8") as f:
                snapshot = json.load(f)
            date = snapshot["date"]

            twse_idx = snapshot.get("twse", {}).get("index")
            if twse_idx and date in twse_high_low:
                twse_idx["high"], twse_idx["low"] = twse_high_low[date]

            tpex_idx = snapshot.get("tpex", {}).get("index")
            tpex_row = tpex_rows.get(date)
            if tpex_idx and tpex_row:
                tpex_idx["high"] = tpex_row["high"]
                tpex_idx["low"] = tpex_row["low"]

            common._dump_json(path, snapshot)
            common._append_series(
                common.DATA_DIR / "series" / "index.json",
                date,
                {
                    "twseClose": twse_idx.get("close") if twse_idx else None,
                    "twseChange": twse_idx.get("change") if twse_idx else None,
                    "twseChangePercent": twse_idx.get("changePercent") if twse_idx else None,
                    "twseHigh": twse_idx.get("high") if twse_idx else None,
                    "twseLow": twse_idx.get("low") if twse_idx else None,
                    "tpexClose": tpex_idx.get("close") if tpex_idx else None,
                    "tpexChange": tpex_idx.get("change") if tpex_idx else None,
                    "tpexChangePercent": tpex_idx.get("changePercent") if tpex_idx else None,
                    "tpexHigh": tpex_idx.get("high") if tpex_idx else None,
                    "tpexLow": tpex_idx.get("low") if tpex_idx else None,
                },
            )
            updated += 1
        print(f"{ym}：{len(by_month[ym])} 天已更新")

    print(f"共更新 {updated} 天。")


if __name__ == "__main__":
    main()
