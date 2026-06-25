"""
龙虎榜模式挖掘：
1. 回测所有LHB股票 → 标注盈亏
2. 提取特征 → 找盈利交易的共性
3. 生成策略规则
"""
import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from vnpy.trader.database import get_database
from vnpy.trader.constant import Exchange, Interval

# ============ Step 1: 数据收集 ============

def collect_all_trades():
    """收集全部龙虎榜候选，标注真实盈亏"""
    print("Step 1: 收集龙虎榜数据...")
    df = ak.stock_lhb_detail_em(start_date="20250101", end_date="20260624")

    # 基础特征
    df["涨跌幅"] = pd.to_numeric(df["涨跌幅"], errors="coerce")
    df["换手率"] = pd.to_numeric(df["换手率"], errors="coerce")
    df["净买额"] = pd.to_numeric(df["龙虎榜净买额"], errors="coerce") / 10000
    df["成交额"] = pd.to_numeric(df["龙虎榜成交额"], errors="coerce") / 10000
    df["总成交"] = pd.to_numeric(df["市场总成交额"], errors="coerce") / 100000000
    df["流通市值"] = pd.to_numeric(df["流通市值"], errors="coerce")
    df["上榜日"] = pd.to_datetime(df["上榜日"])
    df["原因"] = df["上榜原因"].astype(str)

    # 衍生特征
    df["买占比"] = (df["净买额"] * 10000 + pd.to_numeric(df["龙虎榜卖出额"], errors="coerce")) / pd.to_numeric(df["龙虎榜成交额"], errors="coerce")
    df["净买占成交"] = df["净买额"] * 10000 / (df["总成交"] * 1e8) * 100
    df["龙虎额占市场"] = df["成交额"] / (df["总成交"] * 100) * 100

    # 过滤ST
    df = df[~df["原因"].str.contains("ST", na=False)]

    print(f"  原始数据: {len(df)} 条")

    # ============ Step 2: 标注真实盈亏 ============
    print("Step 2: 标注真实盈亏...")
    db = get_database()
    trades = []
    skipped = 0

    for _, row in df.iterrows():
        sym = row["代码"]
        ex = Exchange.SSE if sym.startswith("6") else Exchange.SZSE
        list_date = row["上榜日"]

        start_q = (list_date - timedelta(days=1)).strftime("%Y-%m-%d")
        end_q = (list_date + timedelta(days=5)).strftime("%Y-%m-%d")
        bars = db.load_bar_data(sym, ex, Interval.DAILY, start=start_q, end=end_q)

        if bars is None or len(bars) < 3:
            skipped += 1; continue

        list_bar = next((b for b in bars if b.datetime.date() == list_date.date()), None)
        next_bar = next((b for b in bars if b.datetime.date() > list_date.date()), None)
        sell_bar = next((b for b in bars if b.datetime.date() > (next_bar.datetime.date() if next_bar else list_date.date())), None)

        if not list_bar or not next_bar or not sell_bar:
            skipped += 1; continue

        buy_price = next_bar.open_price
        sell_price = sell_bar.open_price

        # 一字涨停跳过
        if buy_price >= list_bar.close_price * 1.098:
            skipped += 1; continue

        ret = (sell_price / buy_price - 1) * 100

        trades.append({
            "代码": sym,
            "名称": row["名称"],
            "上榜日": list_date,
            "涨跌幅": row["涨跌幅"],
            "换手率": row["换手率"],
            "净买额": row["净买额"],
            "净买占成交": row["净买占成交"],
            "龙虎额占市场": row["龙虎额占市场"],
            "流通市值": row["流通市值"],
            "买占比": row["买占比"],
            "收益": ret,
            "盈利": ret > 0,
        })

    print(f"  有效交易: {len(trades)} 笔  跳过: {skipped}")
    return pd.DataFrame(trades)


# ============ Step 3: 特征分析 ============

def analyze_features(df: pd.DataFrame):
    """分析盈利 vs 亏损交易的共性"""
    win = df[df["盈利"]]
    lose = df[~df["盈利"]]

    features = ["涨跌幅", "换手率", "净买额", "净买占成交", "龙虎额占市场", "流通市值", "买占比"]

    print(f"\n{'='*60}")
    print(f"  特征分析: 盈利{len(win)}笔 vs 亏损{len(lose)}笔")
    print(f"{'='*60}")
    print(f"  {'特征':<14} {'盈利均值':>10} {'亏损均值':>10} {'差值':>8} {'盈利中位':>10} {'亏损中位':>10}")
    print(f"  {'-'*58}")

    insights = []
    for f in features:
        wm = win[f].dropna().mean()
        lm = lose[f].dropna().mean()
        wmd = win[f].dropna().median()
        lmd = lose[f].dropna().median()
        diff = wm - lm
        marker = "★" if abs(diff) > (wm + lm) / 2 * 0.1 else " "
        print(f"  {marker} {f:<12} {wm:>10.2f} {lm:>10.2f} {diff:>+8.2f} {wmd:>10.2f} {lmd:>10.2f}")
        if abs(diff) > 0:
            insights.append((f, diff))

    # 按特征分段看胜率
    print(f"\n  分段胜率分析:")
    for f in ["换手率", "净买额", "涨跌幅", "流通市值"]:
        if f not in df.columns: continue
        valid = df[f].dropna()
        if len(valid) == 0: continue
        bins = pd.qcut(valid, 5, duplicates="drop")
        print(f"  {f}:")
        for interval, group in df.groupby(bins, observed=False):
            wr = group["盈利"].sum() / len(group) * 100 if len(group) > 0 else 0
            bar = "🟢" if wr > 50 else ("🟡" if wr > 40 else "🔴")
            print(f"    {bar} {interval}: 胜率{wr:.0f}% (N={len(group)})")

    return insights


# ============ Step 4: 生成策略规则 ============

def generate_rules(df: pd.DataFrame):
    """从盈利交易中提炼策略规则"""
    win = df[df["盈利"]]

    rules = {
        "换手率_max": win["换手率"].quantile(0.75),
        "净买额_min": win["净买额"].quantile(0.25),
        "涨跌幅_min": win["涨跌幅"].min(),
        "流通市值_min": win["流通市值"].quantile(0.1),
    }

    print(f"\n{'='*60}")
    print(f"  策略规则 (基于盈利交易的P25-P75范围)")
    print(f"{'='*60}")
    print(f"  换手率 < {rules['换手率_max']:.1f}%")
    print(f"  净买额 > {rules['净买额_min']:.0f}万")
    print(f"  涨跌幅 > {rules['涨跌幅_min']:.1f}%")
    print(f"  流通市值 > {rules['流通市值_min']:.0f}亿")

    # 应用规则看过滤效果
    mask = (
        (df["换手率"] < rules["换手率_max"]) &
        (df["净买额"] > rules["净买额_min"]) &
        (df["涨跌幅"] > rules["涨跌幅_min"]) &
        (df["流通市值"] > rules["流通市值_min"])
    )
    filtered = df[mask]
    wr = filtered["盈利"].sum() / len(filtered) * 100 if len(filtered) > 0 else 0
    avg_ret = filtered["收益"].mean()

    print(f"\n  规则过滤后: {len(filtered)}笔 胜率{wr:.1f}% 均收益{avg_ret:+.2f}%")
    print(f"  过滤前:    {len(df)}笔 胜率{df['盈利'].sum()/len(df)*100:.1f}% 均收益{df['收益'].mean():+.2f}%")

    return rules


if __name__ == "__main__":
    df = collect_all_trades()
    if len(df) > 0:
        analyze_features(df)
        rules = generate_rules(df)

        # 保存结果
        df.to_csv("scripts/lhb_trades.csv", index=False)
        print(f"\n交易明细已保存至 scripts/lhb_trades.csv")
