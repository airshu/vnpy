"""
龙虎榜趋势股筛选 (最近3个月)

条件:
1. 价格 > MA20 (1.02 ~ 1.18)
2. 距60日高 < 15%
3. RSI 55-85
4. 换手率 3-10%
5. 流通市值 > 30亿
6. 净买额 > 3000万
7. 20日涨幅 > 15%
8. 量比 1.2-3.0
9. 5日涨幅 < 15%
(涨跌幅不限，K线趋势自会筛选)

v2: MA20上界1.18, 删连板条件(冗余)
"""
import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from vnpy.trader.database import get_database
from vnpy.trader.constant import Exchange, Interval


def get_features(sym, ex, date, db):
    """提取上榜日K线特征"""
    start = (date - timedelta(days=150)).strftime("%Y-%m-%d")
    end = (date + timedelta(days=1)).strftime("%Y-%m-%d")
    bars = db.load_bar_data(sym, ex, Interval.DAILY, start=start, end=end)

    if bars is None or len(bars) < 60:
        return None

    closes = np.array([b.close_price for b in bars])
    highs = np.array([b.high_price for b in bars])
    vols = np.array([b.volume for b in bars])

    idx = next((i for i, b in enumerate(bars) if b.datetime.date() == date.date()), None)
    if idx is None or idx < 20:
        return None

    close = closes[idx]
    today_bar = bars[idx]
    prev_close = closes[idx - 1]

    # MA20
    ma20 = np.mean(closes[idx - 19:idx + 1])
    ma20_ratio = close / ma20

    # RSI14
    gains, losses = [], []
    for i in range(idx - 13, idx + 1):
        d = closes[i] - closes[i - 1]
        gains.append(d if d > 0 else 0)
        losses.append(-d if d < 0 else 0)
    avg_gain = np.mean(gains)
    avg_loss = np.mean(losses)
    rsi = 100 - 100 / (1 + avg_gain / avg_loss) if avg_loss > 0 else 100

    # 距60日高
    h60 = float(max(highs[idx - 59:idx + 1]))
    dist_high = (close - h60) / h60 * 100

    # 5日涨幅
    ret5 = (close / closes[idx - 5] - 1) * 100 if idx >= 5 else 0
    
    # 20日涨幅
    ret20 = (close / closes[idx - 20] - 1) * 100 if idx >= 20 else 0

    # 量比 (5日均量 / 20日均量)
    avg_vol5 = np.mean(vols[idx - 4:idx + 1]) if idx >= 5 else 0
    avg_vol20 = np.mean(vols[idx - 19:idx + 1]) if idx >= 20 else 0
    vol_ratio = avg_vol5 / avg_vol20 if avg_vol20 > 0 else 0

    # 连板天数
    up_days = 0
    for i in range(idx, 0, -1):
        if closes[i] > closes[i - 1] * 1.095:
            up_days += 1
        else:
            break

    # 涨停类型
    if today_bar.open_price >= prev_close * 1.098:
        board_type = "一字板"
    elif today_bar.low_price >= prev_close * 1.098:
        board_type = "T字板"
    else:
        board_type = "实体涨停"

    return {
        "ma20_ratio": ma20_ratio,
        "rsi": rsi,
        "dist_high": dist_high,
        "ret5": ret5,
        "ret20": ret20,
        "vol_ratio": vol_ratio,
        "up_days": up_days,
        "board_type": board_type,
    }


def main():
    end = datetime(2026, 6, 24)
    start = end - timedelta(days=92)  # 约3个月

    print(f"龙虎榜 {start.strftime('%Y-%m-%d')} ~ {end.strftime('%Y-%m-%d')}")
    print("=" * 60)

    # 下载龙虎榜
    df = ak.stock_lhb_detail_em(
        start_date=start.strftime("%Y%m%d"),
        end_date=end.strftime("%Y%m%d"),
    )

    df["涨跌幅"] = pd.to_numeric(df["涨跌幅"], errors="coerce")
    df["换手率"] = pd.to_numeric(df["换手率"], errors="coerce")
    df["净买额"] = pd.to_numeric(df["龙虎榜净买额"], errors="coerce") / 10000
    df["流通市值"] = pd.to_numeric(df["流通市值"], errors="coerce")
    df["原因"] = df["上榜原因"].astype(str)
    df["上榜日"] = pd.to_datetime(df["上榜日"])

    # === 基础过滤 ===
    mask = (
        ~df["原因"].str.contains("ST|连续三个|异常波动", na=False) &
        ~df["名称"].str.contains("ST", na=False) &
        (df["换手率"] >= 3) & (df["换手率"] <= 10) &
        (df["流通市值"] > 30) &
        (df["净买额"] > 3000)
    )
    base = df[mask].copy()
    print(f"基础过滤后: {len(base)} 笔 ({base['代码'].nunique()} 只股票)")

    # === K线特征过滤 ===
    db = get_database()
    results = []
    stats = {"total": 0, "nodata": 0, "ma20": 0, "rsi": 0, "high": 0,
             "ret5": 0, "ret20": 0, "vol": 0, "board": 0, "pass": 0}

    for _, row in base.iterrows():
        stats["total"] += 1
        sym = str(row["代码"]).zfill(6)
        ex = Exchange.SSE if sym.startswith("6") else Exchange.SZSE
        date = row["上榜日"]

        feat = get_features(sym, ex, date, db)
        if feat is None:
            stats["nodata"] += 1
            continue

        # 逐一检查
        if feat["board_type"] != "实体涨停":
            stats["board"] += 1; continue
        if feat["ma20_ratio"] < 1.02 or feat["ma20_ratio"] > 1.18:
            stats["ma20"] += 1; continue
        if feat["rsi"] < 55 or feat["rsi"] > 85:
            stats["rsi"] += 1; continue
        if feat["dist_high"] < -15:
            stats["high"] += 1; continue
        if feat["ret20"] < 15:
            stats["ret20"] += 1; continue
        if feat["vol_ratio"] < 1.2 or feat["vol_ratio"] > 3.0:
            stats["vol"] += 1; continue
        if feat["ret5"] >= 15:
            stats["ret5"] += 1; continue

        stats["pass"] += 1
        results.append({
            "上榜日": date.strftime("%Y-%m-%d"),
            "代码": sym,
            "名称": row["名称"],
            "涨停%": f"{row['涨跌幅']:.1f}",
            "连板": feat["up_days"],
            "换手%": f"{row['换手率']:.1f}",
            "净买(万)": f"{row['净买额']:.0f}",
            "市值(亿)": f"{row['流通市值']:.0f}",
            "MA20比": f"{feat['ma20_ratio']:.2f}",
            "RSI": f"{feat['rsi']:.0f}",
            "20日涨%": f"{feat['ret20']:.0f}",
            "量比": f"{feat['vol_ratio']:.1f}",
        })

    # 输出结果
    print(f"\n  过滤统计:")
    print(f"    总候选:      {stats['total']}")
    print(f"    无K线数据:   {stats['nodata']}")
    print(f"    非实体涨停:  {stats['board']}")
    print(f"    MA20<1.02:   {stats['ma20']}")
    print(f"    RSI超标:     {stats['rsi']}")
    print(f"    距新高<-15%: {stats['high']}")
    print(f"    20日涨<5%:   {stats['ret20']}")
    print(f"    量比超标:    {stats['vol']}")
    print(f"    ✅ 通过:     {stats['pass']}")

    if results:
        df_out = pd.DataFrame(results).sort_values("上榜日", ascending=False)
        print(f"\n{'='*90}")
        print(f"  通过筛选的股票 ({len(results)} 只)")
        print(f"{'='*90}")
        print(f"  {'上榜日':<12} {'代码':<8} {'名称':<8} {'涨停':>5} {'连板':>3} {'换手':>5} {'净买':>8} {'市值':>8} {'MA20':>5} {'RSI':>4} {'20日涨':>6} {'量比':>4}")
        print(f"  {'-'*86}")
        for _, r in df_out.iterrows():
            print(f"  {r['上榜日']} {r['代码']:<8} {r['名称']:<8} {r['涨停%']:>4}% {r['连板']:>2}天 {r['换手%']:>4}% {r['净买(万)']:>7} {r['市值(亿)']:>7} {r['MA20比']:>4} {r['RSI']:>3} {r['20日涨%']:>5}% {r['量比']:>3}")

        # 按日期分组
        print(f"\n  每日候选数:")
        daily = df_out.groupby("上榜日").size()
        for d, cnt in daily.items():
            print(f"    {d}: {cnt} 只")

        # 出现最多的
        print(f"\n  出现次数最多的:")
        top = df_out["名称"].value_counts().head(10)
        for name, cnt in top.items():
            print(f"    {name}: {cnt} 次")
    else:
        print(f"\n  ⚠ 没有股票通过全部条件")


if __name__ == "__main__":
    main()
