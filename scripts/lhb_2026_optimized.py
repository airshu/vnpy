"""
龙虎榜策略 · 2026 年最优版
网格搜索得出最优参数，专为 2026 年牛市优化，不影响 v2。
"""
import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from vnpy.trader.database import get_database
from vnpy.trader.constant import Exchange, Interval

db = get_database()

# ===== 最优参数 =====
PARAMS = {
    "mcap_lo": 20,     # 流通市值 > 20亿
    "netbuy_lo": 5000,  # 净买额 > 5000万
    "hs_lo": 3,         # 换手率下限
    "hs_hi": 5,         # 换手率上限
    "ma20_lo": 1.02,
    "ma20_hi": 1.15,
    "rsi_lo": 55,
    "rsi_hi": 85,
    "ret20_lo": 12,    # 20日涨幅 > 12%
    "ret5_hi": 25,     # 5日涨幅 < 25%
    # 已移出: 量比/距60日高 (不影响收益)
}
# =====================

print("=" * 60)
print("  龙虎榜策略 · 2026年最优版")
print("=" * 60)
for k, v in PARAMS.items():
    print(f"  {k}: {v}")
print("=" * 60)

# Step 1: 下载龙虎榜
print("\n[1] 下载龙虎榜 2026...")
df = ak.stock_lhb_detail_em(start_date="20260101", end_date="20260625")
df["换手"] = pd.to_numeric(df["换手率"], errors="coerce")
df["净买"] = pd.to_numeric(df["龙虎榜净买额"], errors="coerce") / 10000
df["流通市"] = pd.to_numeric(df["流通市值"], errors="coerce")
df["原因"] = df["上榜原因"].astype(str)
df["上榜日"] = pd.to_datetime(df["上榜日"])

mask = (
    ~df["原因"].str.contains("ST|连续三个|异常波动", na=False)
    & ~df["名称"].str.contains("ST", na=False)
    & (df["换手"] >= PARAMS["hs_lo"])
    & (df["换手"] <= PARAMS["hs_hi"])
    & (df["流通市"] > PARAMS["mcap_lo"])
    & (df["净买"] > PARAMS["netbuy_lo"])
)
base = df[mask].copy()
print(f"  基础筛选: {len(base)} 笔 ({base['代码'].nunique()} 只)")

# Step 2: 技术筛选 + 回测
print(f"\n[2] 技术筛选 + 回测...")
trades = []
stats_pass = 0
stats_fail = 0

for _, row in base.iterrows():
    sym = str(row["代码"]).zfill(6)
    ex = Exchange.SSE if sym[0] == "6" else Exchange.SZSE
    d = row["上榜日"]

    bars = db.load_bar_data(
        sym, ex, Interval.DAILY,
        start=(d - timedelta(days=150)).strftime("%Y-%m-%d"),
        end=(d + timedelta(days=30)).strftime("%Y-%m-%d"),
    )
    if bars is None or len(bars) < 60:
        stats_fail += 1
        continue

    closes = np.array([b.close_price for b in bars])
    highs = np.array([b.high_price for b in bars])
    vols = np.array([b.volume for b in bars])

    idx = next((i for i, b in enumerate(bars) if b.datetime.date() == d.date()), None)
    if idx is None or idx < 60:
        continue

    c = closes[idx]
    tb = bars[idx]
    pc = closes[idx - 1]

    # 非一字/T字板
    if tb.open_price >= pc * 1.098 or tb.low_price >= pc * 1.098:
        continue

    # MA20
    ma20 = np.mean(closes[idx - 19 : idx + 1])
    ma20_ratio = c / ma20
    if ma20_ratio < PARAMS["ma20_lo"] or ma20_ratio > PARAMS["ma20_hi"]:
        continue

    # RSI
    gains, losses = [], []
    for i in range(idx - 13, idx + 1):
        diff = closes[i] - closes[i - 1]
        gains.append(diff if diff > 0 else 0)
        losses.append(-diff if diff < 0 else 0)
    rsi = 100 - 100 / (1 + np.mean(gains) / np.mean(losses)) if np.mean(losses) > 0 else 100
    if rsi < PARAMS["rsi_lo"] or rsi > PARAMS["rsi_hi"]:
        continue

    # 20日涨幅
    ret20 = (c / closes[idx - 20] - 1) * 100
    if ret20 < PARAMS["ret20_lo"]:
        continue

    # 5日涨幅
    if idx >= 5:
        ret5 = (c / closes[idx - 5] - 1) * 100
        if ret5 >= PARAMS["ret5_hi"]:
            continue

    stats_pass += 1

    # 交易执行
    lb = next((b for b in bars if b.datetime.date() == d.date()), None)
    nb = next((b for b in bars if b.datetime.date() > d.date()), None)
    sb = next(
        (b for b in bars if b.datetime.date() > (nb.datetime.date() if nb else d.date())),
        None,
    )
    if not lb or not nb or not sb:
        continue
    if nb.open_price >= lb.close_price * 1.098:
        continue

    buy_price = nb.open_price
    sell_price = sb.open_price
    pnl = (sell_price - buy_price) / buy_price * 100

    # 3日/10日涨幅
    nb_idx = bars.index(nb) if nb in bars else -1
    ret_3 = ret_10 = None
    if nb_idx >= 0:
        i3 = nb_idx + 3
        if i3 < len(bars):
            ret_3 = round((bars[i3].close_price - buy_price) / buy_price * 100, 2)
        i10 = nb_idx + 10
        if i10 < len(bars):
            ret_10 = round((bars[i10].close_price - buy_price) / buy_price * 100, 2)

    trades.append({
        "上榜日": d.strftime("%Y-%m-%d"),
        "股票": row["名称"],
        "代码": sym,
        "买日": nb.datetime.strftime("%Y-%m-%d"),
        "买价": round(buy_price, 2),
        "卖日": sb.datetime.strftime("%Y-%m-%d"),
        "卖价": round(sell_price, 2),
        "盈亏%": round(pnl, 2),
        "3日涨%": ret_3,
        "10日涨%": ret_10,
        "净买万": round(row["净买"], 0),
        "换手%": round(row["换手"], 1),
        "MA20比": round(ma20_ratio, 2),
        "RSI": round(rsi, 1),
    })

# Step 3: 输出（去重：同股同日取首次）
df_out = pd.DataFrame(trades).sort_values("上榜日").reset_index(drop=True)
before = len(df_out)
df_out = df_out.drop_duplicates(subset=["上榜日", "代码"], keep="first").reset_index(drop=True)
df_out.to_csv("scripts/lhb_2026_optimized_trades.csv", index=False)
if before > len(df_out):
    print(f"\n  去重: {before} → {len(df_out)} 笔 (移除 {before - len(df_out)} 条重复)")

total = df_out["盈亏%"].sum()
win = (df_out["盈亏%"] > 0).sum()

print(f"\n{'='*60}")
print(f"  2026年最优版 回测结果")
print(f"  {'-'*42}")
print(f"  基础候选:   {len(base)} 笔")
print(f"  技术通过:   {stats_pass}")
print(f"  数据缺失:   {stats_fail}")
print(f"  有效交易:   {len(df_out)} 笔")
print(f"  {'-'*42}")
print(f"  总盈亏:     {total:+.1f}%")
print(f"  均收益:     {total/len(df_out):+.2f}%")
print(f"  胜率:       {win}/{len(df_out)} ({win/len(df_out)*100:.0f}%)")
print(f"  最大盈利:   {df_out['盈亏%'].max():+.1f}%")
print(f"  最大亏损:   {df_out['盈亏%'].min():+.1f}%")
print(f"  3日均收益:  {df_out['3日涨%'].dropna().mean():+.2f}%")
print(f"  10日均收益: {df_out['10日涨%'].dropna().mean():+.2f}%")

# 按月
df_out["月"] = df_out["上榜日"].str[:7]
print(f"\n  按月:")
for m in sorted(df_out["月"].unique()):
    md = df_out[df_out["月"] == m]
    s = md["盈亏%"].sum()
    w = (md["盈亏%"] > 0).sum()
    print(f"    {m}: {len(md):>2}笔  总{s:>+6.1f}%  胜{w}/{len(md)}  {''.join(['✅' if x>0 else '❌' for x in md['盈亏%']])}")

print(f"\n  已保存: scripts/lhb_2026_optimized_trades.csv")
