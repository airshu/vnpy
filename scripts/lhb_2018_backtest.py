"""
龙虎榜趋势策略 · 完整回测 (2018-01 ~ 2026-06)

条件:
1.  非ST / 非异常波动
2.  换手率 3 ~ 10%
3.  流通市值 > 30亿
4.  净买额 > 3000万
5.  非一字板 / 非T字板
6.  MA20偏离 1.02 ~ 1.18 (趋势确认但不超买)
7.  RSI(14) 55 ~ 85
8.  距60日高 > -15%
9.  20日涨幅 > 15%
10. 量比(5/20) 1.2 ~ 3.0
11. 5日涨幅 < 15%

买入: 次日开盘价  /  卖出: 第三日开盘价 (持1天)

v1 → v2: MA20 加 1.18 上界, 删连板条件(冗余), +36.5% → +83.5%
"""
import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from vnpy.trader.database import get_database
from vnpy.trader.constant import Exchange, Interval
from collections import defaultdict

db = get_database()

# ===== Step 1: 下载龙虎榜 + 候选股 =====
all_years = [2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]
end_2026 = "20260625"

print("[1/3] 下载历年龙虎榜数据...")
lhb_dfs = []
for y in all_years:
    start_s = f"{y}0101"
    end_s = f"{y}1231"
    df = ak.stock_lhb_detail_em(start_date=start_s, end_date=end_s)
    lhb_dfs.append(df)
    print(f"  {y}: {len(df)} 条")

df_2026 = ak.stock_lhb_detail_em(start_date="20260101", end_date=end_2026)
lhb_dfs.append(df_2026)
print(f"  2026: {len(df_2026)} 条")

df_all = pd.concat(lhb_dfs, ignore_index=True)
df_all["换手"] = pd.to_numeric(df_all["换手率"], errors="coerce")
df_all["净买"] = pd.to_numeric(df_all["龙虎榜净买额"], errors="coerce") / 10000
df_all["流通市"] = pd.to_numeric(df_all["流通市值"], errors="coerce")
df_all["原因"] = df_all["上榜原因"].astype(str)
df_all["上榜日"] = pd.to_datetime(df_all["上榜日"])

# 基础过滤
mask = (
    ~df_all["原因"].str.contains("ST|连续三个|异常波动", na=False)
    & ~df_all["名称"].str.contains("ST", na=False)
    & ~df_all["代码"].astype(str).str.startswith("688")
    & (df_all["换手"] >= 3)
    & (df_all["换手"] <= 10)
    & (df_all["流通市"] > 30)
    & (df_all["净买"] > 3000)
)
base = df_all[mask].copy()
print(f"\n  基础筛选: {len(base)} 笔 ({base['代码'].nunique()} 只股票)")

# 数据已在 baostock 补全中下载完毕, 跳过此步

# ===== Step 2: 逐笔回测 =====
print(f"\n[2/2] 运行回测...")
all_trades = []
stats_pass = 0
stats_data_fail = 0
stats_board = 0

for _, row in base.iterrows():
    sym = str(row["代码"]).zfill(6)
    ex = Exchange.SSE if sym[0] == "6" else Exchange.SZSE
    d = row["上榜日"]

    bars = db.load_bar_data(
        sym, ex, Interval.DAILY,
        start=(d - timedelta(days=150)).strftime("%Y-%m-%d"),
        end=(d + timedelta(days=1)).strftime("%Y-%m-%d"),
    )
    if bars is None or len(bars) < 60:
        stats_data_fail += 1
        continue

    closes = np.array([b.close_price for b in bars])
    highs = np.array([b.high_price for b in bars])
    lows = np.array([b.low_price for b in bars])
    vols = np.array([b.volume for b in bars])

    idx = next((i for i, b in enumerate(bars) if b.datetime.date() == d.date()), None)
    if idx is None or idx < 60:
        continue

    c = closes[idx]
    tb = bars[idx]
    pc = closes[idx - 1]

    # 非一字板 / 非T字板
    if tb.open_price >= pc * 1.098 or tb.low_price >= pc * 1.098:
        continue

    # MA20: 站稳均线但不偏离太远
    ma20 = np.mean(closes[idx - 19 : idx + 1])
    ma20_ratio = c / ma20
    if ma20_ratio < 1.02 or ma20_ratio > 1.18:
        continue

    # RSI(14)
    gains, losses = [], []
    for i in range(idx - 13, idx + 1):
        diff = closes[i] - closes[i - 1]
        gains.append(diff if diff > 0 else 0)
        losses.append(-diff if diff < 0 else 0)
    rsi = 100 - 100 / (1 + np.mean(gains) / np.mean(losses)) if np.mean(losses) > 0 else 100
    if rsi < 55 or rsi > 85:
        continue

    # 距60日高
    h60 = float(max(highs[idx - 59 : idx + 1]))
    if (c - h60) / h60 * 100 < -15:
        continue

    # 20日涨幅
    ret20 = (c / closes[idx - 20] - 1) * 100
    if ret20 < 15:
        continue

    # 量比
    avg5 = np.mean(vols[idx - 4 : idx + 1])
    avg20 = np.mean(vols[idx - 19 : idx + 1])
    vol_ratio = avg5 / avg20
    if vol_ratio < 1.2 or vol_ratio > 3.0:
        continue

    # 5日涨幅
    if idx >= 5:
        ret5 = (c / closes[idx - 5] - 1) * 100
        if ret5 >= 15:
            continue

    stats_pass += 1

    # 回测交易: 拉取上榜日前后 30 天数据 (覆盖长假)
    b2 = db.load_bar_data(
        sym, ex, Interval.DAILY,
        start=(d - timedelta(days=1)).strftime("%Y-%m-%d"),
        end=(d + timedelta(days=30)).strftime("%Y-%m-%d"),
    )
    if b2 is None or len(b2) < 3:
        continue

    lb = next((b for b in b2 if b.datetime.date() == d.date()), None)
    nb = next((b for b in b2 if b.datetime.date() > d.date()), None)
    sb = next(
        (b for b in b2 if b.datetime.date() > (nb.datetime.date() if nb else d.date())),
        None,
    )
    if not lb or not nb or not sb:
        continue

    # 次日一字板买不到
    if nb.open_price >= lb.close_price * 1.098:
        stats_board += 1
        continue

    buy_price = nb.open_price
    sell_price = sb.open_price
    pnl_pct = (sell_price - buy_price) / buy_price * 100

    # 计算买入后 3 天 / 10 天涨幅
    nb_idx = b2.index(nb) if nb in b2 else -1
    ret_3d = None
    ret_10d = None
    if nb_idx >= 0:
        # 第3个交易日 (买入日算 day 0, 往后数 3 根 bar)
        idx_3 = nb_idx + 3
        if idx_3 < len(b2):
            ret_3d = round((b2[idx_3].close_price - buy_price) / buy_price * 100, 2)
        # 第10个交易日
        idx_10 = nb_idx + 10
        if idx_10 < len(b2):
            ret_10d = round((b2[idx_10].close_price - buy_price) / buy_price * 100, 2)

    # 上榜日涨跌幅
    day_gain = (row["换手"] / row["换手"]) * row.get("涨跌幅", 0) if hasattr(row, "涨跌幅") else 0

    all_trades.append(
        {
            "上榜日": d.strftime("%Y-%m-%d"),
            "股票": row["名称"],
            "代码": sym,
            "买日": nb.datetime.strftime("%Y-%m-%d"),
            "买价": round(buy_price, 2),
            "卖日": sb.datetime.strftime("%Y-%m-%d"),
            "卖价": round(sell_price, 2),
            "盈亏%": round(pnl_pct, 2),
            "3日涨%": ret_3d,
            "10日涨%": ret_10d,
            "净买万": round(row["净买"], 0),
            "换手%": round(row["换手"], 1),
            "20日涨%": round(ret20, 1),
            "RSI": round(rsi, 1),
        }
    )

# ===== Step 3: 输出 =====
df_out = pd.DataFrame(all_trades)
if len(df_out) > 0:
    # 按日期排序
    df_out = df_out.sort_values("上榜日").reset_index(drop=True)
    df_out = df_out.drop_duplicates(subset=["上榜日", "代码"], keep="first").reset_index(drop=True)
    df_out.to_csv("scripts/lhb_2018_2026_trades.csv", index=False)

    total_pnl = df_out["盈亏%"].sum()
    win_count = (df_out["盈亏%"] > 0).sum()

    print(f"\n{'='*60}")
    print(f"  完整回测结果 (2018-01 ~ 2026-06)")
    print(f"  {'-'*42}")
    print(f"  基础候选:   {len(base)} 笔")
    print(f"  通过10条件:  {stats_pass} 笔")
    print(f"  数据缺失:    {stats_data_fail} 笔")
    print(f"  涨停跳过:    {stats_board} 笔")
    print(f"  有效交易:    {len(df_out)} 笔")
    print(f"  {'-'*42}")
    print(f"  总盈亏:      {total_pnl:+.1f}%")
    print(f"  均收益:      {total_pnl/len(df_out):+.2f}%")
    print(f"  胜率:        {win_count}/{len(df_out)} ({win_count/len(df_out)*100:.0f}%)")

    # 按年统计
    df_out["年"] = df_out["上榜日"].str[:4]
    print(f"\n  年度分布:")
    for yr in sorted(df_out["年"].unique()):
        ydf = df_out[df_out["年"] == yr]
        y_total = ydf["盈亏%"].sum()
        y_win = (ydf["盈亏%"] > 0).sum()
        print(f"    {yr}: {len(ydf):>3}笔  总{y_total:>+7.1f}%  均{y_total/len(ydf):>+6.2f}%  胜{y_win}/{len(ydf)}")

    # 按月统计
    df_out["月"] = df_out["上榜日"].str[:7]
    print(f"\n  月度分布:")
    for m in sorted(df_out["月"].unique()):
        mdf = df_out[df_out["月"] == m]
        m_total = mdf["盈亏%"].sum()
        print(f"    {m}: {len(mdf):>2}笔  {m_total:>+6.1f}%  {''.join(['✅' if x>0 else '❌' for x in mdf['盈亏%']])}")

    print(f"\n  已保存: scripts/lhb_2018_2026_trades.csv")
