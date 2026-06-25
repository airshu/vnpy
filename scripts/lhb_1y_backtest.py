"""
龙虎榜11条件策略 · 一年回测 (2025-06 ~ 2026-06)
"""
import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from vnpy.trader.database import get_database
from vnpy.trader.constant import Exchange, Interval


def get_trade(sym, ex, date, db):
    """获取单笔交易的真实收益"""
    start = (date - timedelta(days=1)).strftime("%Y-%m-%d")
    end = (date + timedelta(days=5)).strftime("%Y-%m-%d")
    bars = db.load_bar_data(sym, ex, Interval.DAILY, start=start, end=end)
    if bars is None or len(bars) < 3:
        return None

    list_bar = next((b for b in bars if b.datetime.date() == date.date()), None)
    next_bar = next((b for b in bars if b.datetime.date() > date.date()), None)
    sell_bar = next(
        (b for b in bars if b.datetime.date() > (next_bar.datetime.date() if next_bar else date.date())),
        None,
    )

    if not list_bar or not next_bar or not sell_bar:
        return None

    buy_price = next_bar.open_price
    sell_price = sell_bar.open_price

    # 次日一字板跳过
    if buy_price >= list_bar.close_price * 1.098:
        return None

    ret = (sell_price / buy_price - 1) * 100
    return {
        "name": None,
        "code": sym,
        "date": date.strftime("%Y-%m-%d"),
        "buy": buy_price,
        "sell": sell_price,
        "ret": ret,
        "win": ret > 0,
    }


def check_features(sym, ex, date, db):
    """检查11个条件"""
    start = (date - timedelta(days=150)).strftime("%Y-%m-%d")
    end = (date + timedelta(days=1)).strftime("%Y-%m-%d")
    bars = db.load_bar_data(sym, ex, Interval.DAILY, start=start, end=end)

    if bars is None or len(bars) < 60:
        return False

    closes = np.array([b.close_price for b in bars])
    highs = np.array([b.high_price for b in bars])
    vols = np.array([b.volume for b in bars])

    idx = next((i for i, b in enumerate(bars) if b.datetime.date() == date.date()), None)
    if idx is None or idx < 20:
        return False

    close = closes[idx]
    today_bar = bars[idx]
    prev_close = closes[idx - 1]

    # 1. 非一字板/T字板
    if today_bar.open_price >= prev_close * 1.098:
        return False
    if today_bar.low_price >= prev_close * 1.098:
        return False

    # 2. MA20
    ma20 = np.mean(closes[idx - 19 : idx + 1])
    if close / ma20 < 1.02:
        return False

    # 3. RSI 55-85
    gains, losses = [], []
    for i in range(idx - 13, idx + 1):
        d = closes[i] - closes[i - 1]
        gains.append(d if d > 0 else 0)
        losses.append(-d if d < 0 else 0)
    avg_gain = np.mean(gains)
    avg_loss = np.mean(losses)
    rsi = 100 - 100 / (1 + avg_gain / avg_loss) if avg_loss > 0 else 100
    if rsi < 55 or rsi > 85:
        return False

    # 4. 距60日高 < 15%
    h60 = float(max(highs[idx - 59 : idx + 1]))
    if (close - h60) / h60 * 100 < -15:
        return False

    # 5. 20日涨幅 > 5%
    if (close / closes[idx - 20] - 1) * 100 < 5:
        return False

    # 6. 量比 1.2-3.0
    avg_vol5 = np.mean(vols[idx - 4 : idx + 1])
    avg_vol20 = np.mean(vols[idx - 19 : idx + 1])
    vol_ratio = avg_vol5 / avg_vol20 if avg_vol20 > 0 else 0
    if vol_ratio < 1.2 or vol_ratio > 3.0:
        return False

    # 7. 5日涨幅 < 15%
    if (close / closes[idx - 5] - 1) * 100 >= 15:
        return False

    # 8. 连板 <= 1
    up_days = 0
    for i in range(idx, 0, -1):
        if closes[i] > closes[i - 1] * 1.095:
            up_days += 1
        else:
            break
    if up_days > 1:
        return False

    return True


def main():
    end = datetime(2026, 6, 24)
    start = end - timedelta(days=365)

    print(f"龙虎榜 {start.strftime('%Y-%m-%d')} ~ {end.strftime('%Y-%m-%d')}\n")

    # 下载龙虎榜
    df = ak.stock_lhb_detail_em(
        start_date=start.strftime("%Y%m%d"), end_date=end.strftime("%Y%m%d"),
    )

    df["涨跌幅"] = pd.to_numeric(df["涨跌幅"], errors="coerce")
    df["换手率"] = pd.to_numeric(df["换手率"], errors="coerce")
    df["净买额"] = pd.to_numeric(df["龙虎榜净买额"], errors="coerce") / 10000
    df["流通市值"] = pd.to_numeric(df["流通市值"], errors="coerce")
    df["原因"] = df["上榜原因"].astype(str)
    df["上榜日"] = pd.to_datetime(df["上榜日"])

    mask = (
        (df["涨跌幅"] >= 9.8)
        & ~df["原因"].str.contains("ST|连续三个|异常波动", na=False)
        & (df["换手率"] >= 3)
        & (df["换手率"] <= 10)
        & (df["流通市值"] > 30)
        & (df["净买额"] > 1000)
    )
    base = df[mask].copy()
    print(f"基础过滤: {len(base)} 笔 ({base['代码'].nunique()} 只)")

    db = get_database()
    trades = []
    checked = 0

    for _, row in base.iterrows():
        checked += 1
        sym = str(row["代码"]).zfill(6)
        ex = Exchange.SSE if sym.startswith("6") else Exchange.SZSE
        date = row["上榜日"]

        if not check_features(sym, ex, date, db):
            continue

        trade = get_trade(sym, ex, date, db)
        if trade:
            trade["name"] = row["名称"]
            trades.append(trade)

        if len(trades) > 0 and len(trades) % 20 == 0:
            print(f"  有效交易: {len(trades)}...")

    print(f"\n{'='*55}")
    print(f"  一年回测结果")
    print(f"{'='*55}")
    print(f"  基础候选: {len(base)} 笔")
    print(f"  通过筛选: {len(trades)} 笔")

    if not trades:
        print("  无有效交易")
        return

    rets = [t["ret"] for t in trades]
    wins = sum(1 for t in trades if t["win"])

    print(f"  均收益:    {np.mean(rets):+.2f}%")
    print(f"  中位数:    {np.median(rets):+.2f}%")
    print(f"  胜率:      {wins}/{len(trades)} ({wins/len(trades)*100:.1f}%)")
    print(f"  最大盈利:  +{max(rets):.2f}%")
    print(f"  最大亏损:  {min(rets):+.2f}%")

    # 月度表现
    df_t = pd.DataFrame(trades)
    df_t["月"] = df_t["date"].str[:7]
    monthly = df_t.groupby("月")["ret"].agg(["mean", "count", lambda x: (x > 0).sum()])
    monthly.columns = ["均收益", "笔数", "胜"]

    print(f"\n  月度表现:")
    for idx, row in monthly.iterrows():
        bar = "🟢" if row["均收益"] > 2 else ("🟡" if row["均收益"] > 0 else "🔴")
        print(f"    {bar} {idx}: {row['均收益']:>+5.1f}%  W{int(row['胜'])}/{int(row['笔数'])}")

    # 最近10笔
    print(f"\n  最近10笔:")
    for t in trades[-10:]:
        c = "✅" if t["win"] else "❌"
        print(f"    {c} {t['date']} {t['name']:<8} {t['ret']:+.1f}%")

    # 净值曲线概要
    cum = np.cumprod([1 + r / 100 for r in rets])
    print(f"\n  累计净值: {cum[-1]:.3f}  ({'+' if cum[-1] > 1 else ''}{(cum[-1]-1)*100:.1f}%)")


if __name__ == "__main__":
    main()
