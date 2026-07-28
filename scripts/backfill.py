"""回補歷史資料到 data/。預設回補 2026-01-01 到昨天（今天由 fetch_daily.py 負責）。

已經存在 data/daily/{date}.json 的日期會直接跳過，所以這支腳本可以放心重複執行、
中斷後重跑也只會補齊還沒抓到的日子。TPEx 三大法人歷史資料因為找不到可靠的官方彙總
端點，這段期間會留空（見 common.py 開頭「TPEx 上櫃（歷史資料）」段落的說明）。
"""
import argparse
import datetime as dt
import time

import common

DEFAULT_START = "2026-01-01"
POLITE_DELAY_SECONDS = 0.3


def daterange(start, end):
    d = start
    while d <= end:
        yield d
        d += dt.timedelta(days=1)


def load_tpex_index_map(start, end):
    """依月份批次抓 TPEx 指數，回傳 {iso_date: {close, change, changePercent}}。"""
    index_map = {}
    month = start.replace(day=1)
    while month <= end:
        roc_ym = f"{month.year - 1911}/{month.month:02d}"
        for row in common.fetch_tpex_index_month(roc_ym):
            index_map[row["date"]] = {
                "close": row["close"],
                "change": row["change"],
                "changePercent": row["changePercent"],
            }
        time.sleep(POLITE_DELAY_SECONDS)
        if month.month == 12:
            month = month.replace(year=month.year + 1, month=1)
        else:
            month = month.replace(month=month.month + 1)
    return index_map


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default=DEFAULT_START, help="YYYY-MM-DD，預設 2026-01-01")
    parser.add_argument("--end", default=None, help="YYYY-MM-DD，預設昨天")
    args = parser.parse_args()

    start = dt.date.fromisoformat(args.start)
    end = dt.date.fromisoformat(args.end) if args.end else dt.date.today() - dt.timedelta(days=1)

    print(f"回補範圍：{start} ~ {end}")
    tpex_index_map = load_tpex_index_map(start, end)
    print(f"已取得 TPEx 指數月資料，共 {len(tpex_index_map)} 個交易日")

    written = skipped_existing = skipped_holiday = 0

    for date in daterange(start, end):
        if date.weekday() >= 5:  # 週六、週日
            continue

        iso_date = date.isoformat()
        if (common.DATA_DIR / "daily" / f"{iso_date}.json").exists():
            skipped_existing += 1
            continue

        ymd = date.strftime("%Y%m%d")
        twse_index = common.fetch_twse_index(ymd)
        if twse_index is None:
            print(f"{iso_date}：非交易日或查無資料，略過")
            skipped_holiday += 1
            continue
        time.sleep(POLITE_DELAY_SECONDS)
        twse_institutional = common.fetch_twse_institutional(ymd)
        time.sleep(POLITE_DELAY_SECONDS)
        twse_margin = common.fetch_twse_margin(ymd)
        time.sleep(POLITE_DELAY_SECONDS)
        tpex_margin = common.fetch_tpex_margin_by_date(common.iso_to_roc_date(iso_date))

        snapshot = {
            "date": iso_date,
            "twse": {
                "index": twse_index,
                "institutional": twse_institutional,
                "margin": twse_margin,
            },
            "tpex": {
                "index": tpex_index_map.get(iso_date),
                "institutional": None,  # 見檔案開頭說明：歷史資料無可靠來源
                "margin": tpex_margin,
            },
        }
        common.save_snapshot(snapshot)
        written += 1
        print(f"{iso_date}：已寫入")
        time.sleep(POLITE_DELAY_SECONDS)

    print(
        f"完成。新寫入 {written} 天，已存在略過 {skipped_existing} 天，"
        f"非交易日略過 {skipped_holiday} 天。"
    )


if __name__ == "__main__":
    main()
