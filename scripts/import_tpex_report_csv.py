"""一次性腳本：用 TPEx 官方報表 Report.csv（使用者從官網下載）補齊上櫃融資融券與三大法人的
歷史資料。CSV 涵蓋 2026-01-02 ~ 2026-07-27，跟目前 data/ 回補的範圍一致，是官方逐日數字，
取代原本「張數 x 收盤價」的市值估算，也補上原本完全空白的歷史三大法人資料。

CSV 只有三大法人的「買賣超淨額」，沒有個別買進/賣出金額，所以匯入後 institutional 的
buy/sell 欄位會是 null，只有 net 有值（前端本來就只顯示 net，不受影響）。

執行前會先印出覆蓋前後的比對報告。
"""
import csv
import json

import common

CSV_PATH = common.ROOT / "Report.csv"


def _num(s):
    s = s.replace(",", "").strip()
    if s in ("", "-", "--"):
        return 0.0
    return float(s)


def _parse_date(s):
    # "'26/07/27" -> "2026-07-27"
    s = s.lstrip("'")
    yy, mm, dd = s.split("/")
    return f"20{yy}-{mm}-{dd}"


def load_csv_rows():
    with open(CSV_PATH, encoding="big5") as f:
        reader = csv.reader(f, delimiter="\t")
        next(reader)  # header
        rows = [row for row in reader if row and row[0].strip()]
    rows.reverse()  # CSV 是新到舊排序，反轉成舊到新，方便鏈接「前一個交易日」

    parsed = []
    prev_margin = prev_short = None
    for row in rows:
        margin_balance = _num(row[6]) * 1e8  # 融資餘額（億元）
        short_balance = _num(row[8])  # 融卷餘額（張）
        margin_prev = prev_margin if prev_margin is not None else margin_balance - _num(row[5]) * 1e8
        short_prev = prev_short if prev_short is not None else short_balance - _num(row[7])
        parsed.append(
            {
                "date": _parse_date(row[0]),
                "marginBalance": margin_balance,
                "marginBalancePrev": margin_prev,
                "shortBalance": short_balance,
                "shortBalancePrev": short_prev,
                "foreignNet": _num(row[9]) * 1e8,
                "trustNet": _num(row[10]) * 1e8,
                "dealerNet": _num(row[11]) * 1e8,
                "totalNet": _num(row[12]) * 1e8,
            }
        )
        prev_margin, prev_short = margin_balance, short_balance
    return parsed


def main():
    csv_rows = load_csv_rows()
    print(f"CSV 涵蓋 {csv_rows[0]['date']} ~ {csv_rows[-1]['date']}，共 {len(csv_rows)} 個交易日。\n")

    print(f"{'日期':<12}{'原融資(億)':>12}{'CSV融資(億)':>13}{'差異%':>9}   三大法人")
    diffs = []
    targets = []
    for row in csv_rows:
        daily_path = common.DATA_DIR / "daily" / f"{row['date']}.json"
        if not daily_path.exists():
            continue
        with open(daily_path, encoding="utf-8") as f:
            snapshot = json.load(f)
        current_margin = snapshot.get("tpex", {}).get("margin")
        had_institutional = snapshot.get("tpex", {}).get("institutional") is not None

        if current_margin:
            cur_yi = current_margin["marginBalance"] / 1e8
            new_yi = row["marginBalance"] / 1e8
            diff_pct = ((new_yi - cur_yi) / cur_yi * 100) if cur_yi else 0.0
            diffs.append(diff_pct)
            insti_note = "已有資料，改用 CSV" if had_institutional else "原本空值 -> 補上"
            print(f"{row['date']:<12}{cur_yi:>12.2f}{new_yi:>13.2f}{diff_pct:>8.1f}%   {insti_note}")
        targets.append((row, snapshot))

    if diffs:
        print(f"\n融資餘額差異：最小 {min(diffs):.1f}%，最大 {max(diffs):.1f}%，平均 {sum(diffs)/len(diffs):.1f}%")
    print(f"\n共 {len(targets)} 天有對應的 data/daily 檔案，準備覆蓋...")

    for row, snapshot in targets:
        snapshot["tpex"]["margin"] = {
            "marginBalance": row["marginBalance"],
            "marginBalancePrev": row["marginBalancePrev"],
            "marginUnit": "元",
            "source": "tpex_official",
            "shortBalance": row["shortBalance"],
            "shortBalancePrev": row["shortBalancePrev"],
            "shortUnit": "張",
        }
        snapshot["tpex"]["institutional"] = {
            "foreign": {"buy": None, "sell": None, "net": row["foreignNet"]},
            "trust": {"buy": None, "sell": None, "net": row["trustNet"]},
            "dealer": {"buy": None, "sell": None, "net": row["dealerNet"]},
            "total": {"buy": None, "sell": None, "net": row["totalNet"]},
        }
        common._dump_json(common.DATA_DIR / "daily" / f"{row['date']}.json", snapshot)
        common._append_series(
            common.DATA_DIR / "series" / "margin.json",
            row["date"],
            {"twse": snapshot["twse"]["margin"], "tpex": snapshot["tpex"]["margin"]},
        )
        common._append_series(
            common.DATA_DIR / "series" / "institutional.json",
            row["date"],
            {"twse": snapshot["twse"]["institutional"], "tpex": snapshot["tpex"]["institutional"]},
        )

    print(f"已覆蓋 {len(targets)} 天的 data/daily/{{date}}.json 與 data/series/*.json。")


if __name__ == "__main__":
    main()
