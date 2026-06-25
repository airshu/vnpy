"""
龙虎榜 + 趋势确认策略

基于 K线模式挖掘的规律：
盈利的龙虎榜股票上榜时都在上升趋势中
→ 趋势已经走出来的股票，涨停后继续涨
"""
import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from vnpy.trader.database import get_database
from vnpy.trader.constant import Exchange, Interval


def get_trend_features(sym, ex, date, db):
    """获取上榜日的趋势特征"""
    start = (date - timedelta(days=150)).strftime("%Y-%m-%d")
    end = (date + timedelta(days=1)).strftime("%Y-%m-%d")
    bars = db.load_bar_data(sym, ex, Interval.DAILY, start=start, end=end)

    if bars is None or len(bars) < 60:
        return None

    closes = np.array([b.close_price for b in bars])
    highs = np.array([b.high_price for b in bars])

    idx = next((i for i, b in enumerate(bars) if b.datetime.date() == date.date()), None)
    if idx is None or idx < 20:
        return None

    close = closes[idx]
    prev_close = closes[idx - 1] if idx > 0 else close

    # MA20
    if idx >= 20:
        ma20 = np.mean(closes[idx - 19:idx + 1])
        ma20_ratio = close / ma20
    else:
        return None

    # RSI14
    if idx >= 14:
        gains, losses = [], []
        for i in range(idx - 13, idx + 1):
            d = closes[i] - closes[i - 1]
            gains.append(d if d > 0 else 0)
            losses.append(-d if d < 0 else 0)
        avg_gain = np.mean(gains)
        avg_loss = np.mean(losses)
        rsi = 100 - 100 / (1 + avg_gain / avg_loss) if avg_loss > 0 else 100
    else:
        return None

    # 距60日高
    if idx >= 60:
        h60 = float(max(highs[idx - 59:idx + 1]))
        dist_to_high = (close - h60) / h60 * 100
    else:
        return None

    # 连板天数
    up_days = 0
    for i in range(idx, 0, -1):
        if closes[i] > closes[i - 1] * 1.095:
            up_days += 1
        else:
            break

    # 涨停类型
    today_bar = bars[idx]
    if today_bar.open_price >= prev_close * 1.098:
        board_type = "一字板"
    elif today_bar.low_price >= prev_close * 1.098:
        board_type = "T字板"
    else:
        board_type = "实体涨停"

    return {
        "ma20_ratio": ma20_ratio,
        "rsi": rsi,
        "dist_to_60high": dist_to_high,
        "up_days": up_days,
        "board_type": board_type,
        "price": close,
    }


def run_backtest(start="20250101", end="20260624"):
    """运行策略回测"""
    db = get_database()

    print(f"下载龙虎榜 {start}~{end}...")
    df = ak.stock_lhb_detail_em(start_date=start, end_date=end)

    df["涨跌幅"] = pd.to_numeric(df["涨跌幅"], errors="coerce")
    df["换手率"] = pd.to_numeric(df["换手率"], errors="coerce")
    df["净买额"] = pd.to_numeric(df["龙虎榜净买额"], errors="coerce") / 10000
    df["原因"] = df["上榜原因"].astype(str)
    df["上榜日"] = pd.to_datetime(df["上榜日"])

    # 基础过滤：涨停 + 非ST
    mask = (
        (df["涨跌幅"] >= 9.8) &
        ~df["原因"].str.contains("ST|连续三个|异常波动", na=False)
    )
    candidates = df[mask].copy()

    print(f"基础候选: {len(candidates)} 笔")
    print(f"应用趋势过滤...\n")

    trades = []
    passed = 0
    rejected = {"ma20": 0, "rsi": 0, "high": 0, "up_days": 0, "board": 0, "ok": 0}

    for _, row in candidates.iterrows():
        sym = row["代码"]
        ex = Exchange.SSE if sym.startswith("6") else Exchange.SZSE
        date = row["上榜日"]

        feat = get_trend_features(sym, ex, date, db)
        if feat is None:
            rejected["ma20"] += 1  # 数据不足
            continue

        # === 趋势确认条件 ===
        if feat["ma20_ratio"] < 1.02:
            rejected["ma20"] += 1
            continue
        if feat["rsi"] < 55:
            rejected["rsi"] += 1
            continue
        if feat["dist_to_60high"] < -18:
            rejected["high"] += 1
            continue
        if feat["up_days"] > 1:
            rejected["up_days"] += 1
            continue
        if feat["board_type"] != "实体涨停":
            rejected["board"] += 1
            continue

        rejected["ok"] += 1

        # 计算真实收益
        start_q = (date - timedelta(days=1)).strftime("%Y-%m-%d")
        end_q = (date + timedelta(days=5)).strftime("%Y-%m-%d")
        bars = db.load_bar_data(sym, ex, Interval.DAILY, start=start_q, end=end_q)

        if bars is None or len(bars) < 3:
            continue

        list_bar = next((b for b in bars if b.datetime.date() == date.date()), None)
        next_bar = next((b for b in bars if b.datetime.date() > date.date()), None)
        sell_bar = next((b for b in bars if b.datetime.date() > (next_bar.datetime.date() if next_bar else date.date())), None)

        if not list_bar or not next_bar or not sell_bar:
            continue

        buy_price = next_bar.open_price
        sell_price = sell_bar.open_price

        # 一字板跳过
        if buy_price >= list_bar.close_price * 1.098:
            continue

        ret = (sell_price / buy_price - 1) * 100

        trades.append({
            "date": date.strftime("%Y-%m-%d"),
            "name": row["名称"],
            "code": sym,
            "up_days": feat["up_days"],
            "ma20_ratio": round(feat["ma20_ratio"], 2),
            "rsi": round(feat["rsi"], 1),
            "ret": round(ret, 2),
            "win": ret > 0,
        })

    # 统计
    print(f"  过滤统计:")
    print(f"    MA20<1.02:    {rejected['ma20']} 笔")
    print(f"    RSI<55:       {rejected['rsi']} 笔")
    print(f"    距新高<-18%:  {rejected['high']} 笔")
    print(f"    连板>1:       {rejected['up_days']} 笔")
    print(f"    非实体涨停:   {rejected['board']} 笔")
    print(f"    ✅ 通过:      {rejected['ok']} 笔")
    print(f"    有效交易:     {len(trades)} 笔\n")

    if not trades:
        print("无有效交易")
        return

    rets = [t["ret"] for t in trades]
    wins = sum(1 for t in trades if t["win"])

    print("=" * 55)
    print("  龙虎榜+趋势确认 回测结果")
    print("=" * 55)
    print(f"  总交易:    {len(trades)} 笔")
    print(f"  均收益:    {np.mean(rets):+.2f}%")
    print(f"  中位数:    {np.median(rets):+.2f}%")
    print(f"  胜率:      {wins}/{len(trades)} ({wins/len(trades)*100:.1f}%)")
    print(f"  最大盈利:  {max(rets):+.2f}%")
    print(f"  最大亏损:  {min(rets):+.2f}%")

    # 最近10笔
    print(f"\n  最近10笔:")
    for t in trades[-10:]:
        c = "✅" if t["win"] else "❌"
        print(f"    {c} {t['date']} {t['name']} 连板{t['up_days']}天 MA20={t['ma20_ratio']:.2f} RSI={t['rsi']:.0f}  {t['ret']:+.1f}%")


if __name__ == "__main__":
    run_backtest()
