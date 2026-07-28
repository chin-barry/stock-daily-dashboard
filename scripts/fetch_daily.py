"""抓「今天」（或指定日期）的上市／上櫃資料，寫入 data/daily、附加進 data/series、
更新 data/manifest.json。

非交易日（TWSE 尚未公布資料）時直接結束，不寫檔、不視為錯誤。可以重複執行來補齊某天
稍早跑排程時還沒公布的三大法人／融資融券資料（會直接覆蓋同一天的舊檔案）。
"""
import argparse
import datetime as dt

import common


def build_snapshot(date_ymd):
    twse_index = common.fetch_twse_index(date_ymd)
    if twse_index is None:
        return None

    iso_date = common.ymd8_to_iso(date_ymd)
    return {
        "date": iso_date,
        "twse": {
            "index": twse_index,
            "institutional": common.fetch_twse_institutional(date_ymd),
            "margin": common.fetch_twse_margin(date_ymd),
        },
        "tpex": {
            "index": common.fetch_tpex_index_latest(iso_date),
            "institutional": common.fetch_tpex_institutional_latest(iso_date),
            "margin": common.fetch_tpex_margin_latest(iso_date),
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="YYYY-MM-DD，預設今天（用來重跑/補某一天）", default=None)
    args = parser.parse_args()

    date_ymd = args.date.replace("-", "") if args.date else dt.date.today().strftime("%Y%m%d")
    snapshot = build_snapshot(date_ymd)
    if snapshot is None:
        print(f"{date_ymd}：TWSE 尚無資料（非交易日或尚未公布），略過。")
        return
    common.save_snapshot(snapshot)
    print(f"已寫入 {snapshot['date']} 的資料。")


if __name__ == "__main__":
    main()
