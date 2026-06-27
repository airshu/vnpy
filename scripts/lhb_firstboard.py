"""
首板低换手策略 · 龙虎榜回测

逻辑：涨停首日换手率低 → 抛压小 → 次日大概率继续涨
"""
import akshare as ak
import pandas as pd
import numpy as np


def run_first_board_backtest(start="20240101", end="20260623"):
    df = ak.stock_lhb_detail_em(start_date=start, end_date=end)
    df["净买额"] = pd.to_numeric(df["龙虎榜净买额"], errors="coerce") / 10000
    df["涨跌幅"] = pd.to_numeric(df["涨跌幅"], errors="coerce")
    df["换手"] = pd.to_numeric(df["换手率"], errors="coerce")
    df["流通市值"] = pd.to_numeric(df["流通市值"], errors="coerce")
    df["原因"] = df["上榜原因"].astype(str)

    # 分步看
    masks = {
        "原始数据": slice(None),
        "涨停(≥9.8%)": df["涨跌幅"] >= 9.8,
        "+低换手(<5%)": (df["涨跌幅"] >= 9.8) & (df["换手"] < 5),
        "+净买入>500万": (df["涨跌幅"] >= 9.8) & (df["换手"] < 5) & (df["净买额"] > 500),
        "+非ST/异常": (df["涨跌幅"] >= 9.8) & (df["换手"] < 5) & (df["净买额"] > 500) &
                      ~df["原因"].str.contains("ST|连续三个|异常波动", na=False),
        "+市值>30亿": (df["涨跌幅"] >= 9.8) & (df["换手"] < 5) & (df["净买额"] > 500) &
                      ~df["原因"].str.contains("ST|连续三个|异常波动", na=False) &
                      (df["流通市值"] > 30),
    }

    print(f"\n{'='*60}")
    print(f"  首板低换手策略 ({start} ~ {end})")
    print(f"{'='*60}")

    prev = 99999
    for label, mask in masks.items():
        cand = df[mask]
        n = len(cand)
        removed = prev - n if prev != 99999 else 0
        for hold in [1, 2, 5]:
            col = f"上榜后{hold}日"
            valid = cand[col].dropna()
            if len(valid) == 0: continue
            avg = valid.mean()
            win = (valid > 0).sum() / len(valid) * 100
            if hold == 1:
                print(f"\n  {label}: {n}笔 (砍掉{removed}笔)")
                print(f"   持1日: {avg:+.2f}%  胜率{win:.0f}%  |  持2日: ", end="")
            elif hold == 2:
                print(f"{avg:+.2f}%  胜率{win:.0f}%  |  持5日: ", end="")
            elif hold == 5:
                print(f"{avg:+.2f}%  胜率{win:.0f}%")
        prev = n

    # 按月份统计
    final_mask = masks["+市值>30亿"]
    final = df[final_mask]
    final["月份"] = pd.to_datetime(final["上榜日"]).dt.strftime("%Y-%m")
    monthly = final.groupby("月份")["上榜后1日"].agg(["mean", "count", lambda x: (x>0).sum()/len(x)*100])
    monthly.columns = ["均收益", "笔数", "胜率"]

    print(f"\n  月度表现:")
    for idx, row in monthly.iterrows():
        bar = "#" * max(1, int(row["均收益"])) if row["均收益"] > 0 else "-" * max(1, int(abs(row["均收益"])))
        print(f"    {idx}:  {row['均收益']:>+5.1f}%  {row['胜率']:>4.0f}%  {int(row['笔数']):>3}笔  {bar}")


if __name__ == "__main__":
    run_first_board_backtest()
