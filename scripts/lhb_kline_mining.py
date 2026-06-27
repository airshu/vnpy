"""
龙虎榜 K线模式挖掘
分析盈利交易上榜时的技术指标共性
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from collections import Counter
from vnpy.trader.database import get_database
from vnpy.trader.constant import Exchange, Interval


def get_kline_features(symbol, exchange, date, db, lookback=120):
    """获取上榜日前后的K线特征"""
    start = (date - timedelta(days=lookback + 30)).strftime("%Y-%m-%d")
    end = (date + timedelta(days=5)).strftime("%Y-%m-%d")
    bars = db.load_bar_data(symbol, exchange, Interval.DAILY, start=start, end=end)

    if bars is None or len(bars) < 30:
        return None

    closes = np.array([b.close_price for b in bars])
    highs = np.array([b.high_price for b in bars])
    lows = np.array([b.low_price for b in bars])
    volumes = np.array([b.volume for b in bars])

    # 找上榜日在 bars 中的位置
    idx = next((i for i, b in enumerate(bars) if b.datetime.date() == date.date()), None)
    if idx is None or idx < 20:
        return None

    close = closes[idx]
    vol = volumes[idx]

    features = {}

    # 1. 均线位置
    for n in [5, 10, 20, 60]:
        if idx >= n:
            ma = np.mean(closes[idx - n + 1:idx + 1])
            features[f"ma{n}_ratio"] = close / ma

    # 2. 连板天数
    up_days = 0
    for i in range(idx, 0, -1):
        if closes[i] > closes[i-1] * 1.095:
            up_days += 1
        else:
            break
    features["连续涨停天"] = up_days

    # 3. N日涨跌幅
    for n in [3, 5, 10, 20]:
        if idx >= n:
            features[f"{n}日涨幅"] = (close / closes[idx - n] - 1) * 100

    # 4. 量比
    if idx >= 5:
        avg_vol_5 = np.mean(volumes[idx - 4:idx + 1])
        if idx >= 20:
            avg_vol_20 = np.mean(volumes[idx - 19:idx + 1])
            features["量比"] = avg_vol_5 / avg_vol_20 if avg_vol_20 > 0 else 0

    # 5. 波动率
    if idx >= 20:
        rets = np.diff(closes[idx - 20:idx + 1]) / closes[idx - 20:idx]
        features["20日波动率"] = np.std(rets) * 100

    # 6. 距60日新高/低
    if idx >= 60:
        h60 = max(highs[idx - 59:idx + 1])
        l60 = min(lows[idx - 59:idx + 1])
        features["距60日高%"] = (close - h60) / h60 * 100
        features["距60日低%"] = (close - l60) / l60 * 100

    # 7. RSI
    if idx >= 14:
        gains, losses = [], []
        for i in range(idx - 13, idx + 1):
            d = closes[i] - closes[i-1]
            gains.append(d if d > 0 else 0)
            losses.append(-d if d < 0 else 0)
        avg_gain = np.mean(gains)
        avg_loss = np.mean(losses)
        if avg_loss == 0:
            features["RSI"] = 100
        else:
            features["RSI"] = 100 - 100 / (1 + avg_gain / avg_loss)

    # 8. 涨停板类型: T字/一字/实体
    if idx >= 1:
        prev_close = closes[idx-1]
        open_p = bars[idx].open_price
        high_p = bars[idx].high_price
        low_p = bars[idx].low_price
        if open_p >= prev_close * 1.098:
            features["涨停类型"] = "一字板"
        elif low_p >= prev_close * 1.098:
            features["涨停类型"] = "T字板"
        elif open_p > low_p:
            features["涨停类型"] = "实体涨停"
        else:
            features["涨停类型"] = "其他"

    # 9. 成交额级别
    amount = bars[idx].turnover if hasattr(bars[idx], 'turnover') and bars[idx].turnover else 0
    if amount == 0:
        amount = vol * close
    features["成交额(亿)"] = amount / 1e8

    features["上榜日"] = date.strftime("%Y-%m-%d")
    features["代码"] = symbol
    features["收益"] = None  # 稍后从trades数据填充

    return features


def main():
    # 加载之前保存的交易数据
    try:
        trades = pd.read_csv("scripts/lhb_trades.csv")
    except:
        print("请先运行 lhb_pattern_mining.py 生成交易数据")
        return

    wins = trades[trades["盈利"] == True]
    print(f"盈利交易: {len(wins)} 笔")
    print(f"提取K线特征中...\n")

    db = get_database()
    all_features = []
    done = 0

    for _, row in wins.iterrows():
        sym = str(row["代码"])
        if len(sym) != 6: continue
        ex = Exchange.SSE if sym.startswith("6") else Exchange.SZSE
        date = pd.to_datetime(row["上榜日"])

        feat = get_kline_features(sym, ex, date, db)
        if feat:
            feat["收益"] = row["收益"]
            all_features.append(feat)
            done += 1

        if done % 100 == 0:
            print(f"  {done}/{len(wins)}...")

    if not all_features:
        print("无有效数据")
        return

    df = pd.DataFrame(all_features)
    print(f"\n有效样本: {len(df)} 笔\n")
    print("=" * 55)
    print("  盈利交易 K线特征分析")
    print("=" * 55)

    # 数值特征
    num_cols = [c for c in df.columns if c not in ["代码", "上榜日", "涨停类型", "收益"]]
    print(f"\n{'特征':<16} {'均值':>8} {'中位':>8} {'P25':>8} {'P75':>8} {'分布':>20}")
    print("-" * 70)

    for col in num_cols:
        valid = df[col].dropna()
        if len(valid) == 0: continue
        m = valid.mean(); md = valid.median()
        p25 = valid.quantile(0.25); p75 = valid.quantile(0.75)
        spread = p75 - p25
        bar = "█" * min(20, int(spread * 20 / (p75 + 0.01)))
        print(f"  {col:<16} {m:>8.2f} {md:>8.2f} {p25:>8.2f} {p75:>8.2f} {bar}")

    # 涨停类型分布
    if "涨停类型" in df.columns:
        print(f"\n  涨停类型:")
        for t, cnt in df["涨停类型"].value_counts().items():
            avg_ret = df[df["涨停类型"] == t]["收益"].mean()
            print(f"    {t}: {cnt}笔 均收益{avg_ret:+.1f}%")

    # 连续涨停天
    if "连续涨停天" in df.columns:
        print(f"\n  连续涨停天:")
        for n in sorted(df["连续涨停天"].unique()):
            sub = df[df["连续涨停天"] == n]
            print(f"    {int(n)}天: {len(sub)}笔 均收益{sub['收益'].mean():+.1f}%")

    # 均线位置分段胜率
    for ma_col in ["ma5_ratio", "ma20_ratio", "ma60_ratio"]:
        if ma_col not in df.columns: continue
        valid = df[ma_col].dropna()
        if len(valid) == 0: continue
        ma_name = ma_col.replace("_ratio", "").upper()
        print(f"\n  {ma_name}位置:")
        for label, lo, hi in [("贴MA", 0.95, 1.05), ("高于MA", 1.05, 1.9), ("远高于MA", 1.9, 99)]:
            sub = df[(valid >= lo) & (valid < hi)]
            if len(sub) == 0: continue
            print(f"    {label}({lo}-{hi}): {len(sub)}笔 均收益{sub['收益'].mean():+.1f}%")


if __name__ == "__main__":
    main()
