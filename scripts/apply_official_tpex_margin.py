"""一次性腳本：把 data/daily/ 裡最近幾個交易日的 TPEx 融資估算值換成官方數字。

TPEx 內部 API（dayChart.json）只回溯約 10 個交易日，所以只會動到這個範圍內、且本地已經
有 data/daily/{date}.json 的日期；更久以前的歷史資料維持原本的估算值不動。

執行前會先印出「目前估算 vs 官方」的差異報告，再動手覆蓋。
"""
import json

import common


def main():
    official = common.fetch_tpex_margin_value_official()
    if not official:
        print("抓不到官方資料（dayChart.json 失敗或格式跑掉），沒有東西可以覆蓋。")
        return

    print(f"{'日期':<12}{'目前估算(億)':>14}{'官方(億)':>12}{'差異(億)':>12}{'差異%':>10}")
    targets = []
    for date in sorted(official):
        daily_path = common.DATA_DIR / "daily" / f"{date}.json"
        if not daily_path.exists():
            continue
        with open(daily_path, encoding="utf-8") as f:
            snapshot = json.load(f)
        current = snapshot.get("tpex", {}).get("margin")
        if current:
            cur_yi = current["marginBalance"] / 1e8
            off_yi = official[date]["marginBalance"] / 1e8
            diff_yi = off_yi - cur_yi
            diff_pct = (diff_yi / cur_yi * 100) if cur_yi else 0.0
            print(f"{date:<12}{cur_yi:>14.2f}{off_yi:>12.2f}{diff_yi:>12.2f}{diff_pct:>9.1f}%")
        else:
            print(f"{date:<12}（目前沒有 tpex.margin 資料，直接補上官方值）")
        targets.append((date, snapshot))

    if not targets:
        print("data/daily/ 裡沒有任何日期落在官方資料回溯範圍內，沒有東西可以覆蓋。")
        return

    for date, snapshot in targets:
        margin = snapshot["tpex"].get("margin") or {"shortBalance": 0.0, "shortBalancePrev": 0.0}
        margin.update(
            {
                "marginBalance": official[date]["marginBalance"],
                "marginBalancePrev": official[date]["marginBalancePrev"],
                "marginUnit": "元",
                "source": "tpex_official",
            }
        )
        snapshot["tpex"]["margin"] = margin
        common._dump_json(common.DATA_DIR / "daily" / f"{date}.json", snapshot)
        common._append_series(
            common.DATA_DIR / "series" / "margin.json",
            date,
            {"twse": snapshot["twse"]["margin"], "tpex": margin},
        )

    print(f"\n已覆蓋 {len(targets)} 天的 data/daily/{{date}}.json 與 data/series/margin.json。")


if __name__ == "__main__":
    main()
