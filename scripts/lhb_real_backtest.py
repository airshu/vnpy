"""
龙虎榜真实回测 (2025-01 ~ 2026-06)

逻辑：
1. 筛选当日龙虎榜：涨停 + 换手<5% + 净买入>500万
2. 次日开盘买入（涨停不买）
3. 持1天，第三日开盘卖出
4. 用本地数据库的OHLC算真实收益
"""
import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from vnpy.trader.database import get_database
from vnpy.trader.constant import Exchange, Interval


def get_lhb_candidates(start: str, end: str) -> pd.DataFrame:
    """获取并筛选龙虎榜候选股票"""
    print(f"下载龙虎榜 {start}~{end} ...")
    df = ak.stock_lhb_detail_em(start_date=start, end_date=end)

    df["涨跌幅"] = pd.to_numeric(df["涨跌幅"], errors="coerce")
    df["换手率"] = pd.to_numeric(df["换手率"], errors="coerce")
    df["净买额"] = pd.to_numeric(df["龙虎榜净买额"], errors="coerce") / 10000
    df["原因"] = df["上榜原因"].astype(str)
    df["上榜日"] = pd.to_datetime(df["上榜日"])

    mask = (
        (df["涨跌幅"] >= 9.8) &
        (df["换手率"] < 5) &
        (df["净买额"] > 500) &
        ~df["原因"].str.contains("ST|连续三个|异常波动", na=False)
    )
    return df[mask].copy()


def backtest_with_local_db(candidates: pd.DataFrame):
    """用本地数据库验证真实收益"""
    db = get_database()

    trades = []
    skipped = 0
    for _, row in candidates.iterrows():
        sym = row["代码"]
        name = row["名称"]
        ex = Exchange.SSE if sym.startswith("6") else Exchange.SZSE
        list_date = row["上榜日"]

        # 取上榜日前1天到后5天的数据
        start_q = (list_date - timedelta(days=1)).strftime("%Y-%m-%d")
        end_q = (list_date + timedelta(days=5)).strftime("%Y-%m-%d")
        bars = db.load_bar_data(sym, ex, Interval.DAILY, start=start_q, end=end_q)

        if bars is None or len(bars) < 3:
            skipped += 1
            continue

        # 定位上榜日、次日、第三日
        list_bar = next((b for b in bars if b.datetime.date() == list_date.date()), None)
        next_bar = next((b for b in bars if b.datetime.date() > list_date.date()), None)
        sell_bar = next((b for b in bars if b.datetime.date() > (next_bar.datetime.date() if next_bar else list_date.date())), None)

        if not list_bar or not next_bar or not sell_bar:
            skipped += 1
            continue

        list_close = list_bar.close_price
        buy_price = next_bar.open_price
        sell_price = sell_bar.open_price

        # 检查次日是否一字涨停（买不到）
        if buy_price >= list_close * 1.098:
            skipped += 1
            continue

        ret = (sell_price / buy_price - 1) * 100

        trades.append({
            "date": list_date.strftime("%Y-%m-%d"),
            "code": sym,
            "name": name,
            "list_close": list_close,
            "buy_price": buy_price,
            "sell_price": sell_price,
            "return": ret,
        })

    return trades, skipped


def main():
    print("=" * 55)
    print("  龙虎榜真实回测 (次日开盘买→第三日开盘卖)")
    print("=" * 55)

    # 分月下载
    all_candidates = []
    for y in [2025, 2026]:
        for m in range(1, 13):
            if y == 2026 and m > 6: break
            if y == 2025 and m < 1: continue
            start = f"{y}{m:02d}01"
            end = f"{y}{m:02d}28" if m != 2 else f"{y}{m:02d}29"
            if m == 6 and y == 2026: end = "20260624"
            try:
                cand = get_lhb_candidates(start, end)
                all_candidates.append(cand)
            except:
                continue

    if not all_candidates:
        print("无数据")
        return

    candidates = pd.concat(all_candidates, ignore_index=True)
    print(f"\n原始候选: {len(candidates)} 笔")

    trades, skipped = backtest_with_local_db(candidates)
    print(f"有效交易: {len(trades)} 笔  跳过: {skipped} (无数据/一字板)")

    if not trades:
        print("无有效交易")
        return

    returns = [t["return"] for t in trades]
    win = sum(1 for r in returns if r > 0)
    avg = np.mean(returns)
    med = np.median(returns)

    print(f"\n{'='*55}")
    print(f"  回测结果")
    print(f"{'='*55}")
    print(f"  总交易:      {len(trades)} 笔")
    print(f"  均收益:      {avg:+.2f}%")
    print(f"  中位数收益:  {med:+.2f}%")
    print(f"  胜率:        {win}/{len(trades)} ({win/len(trades)*100:.1f}%)")
    print(f"  最大盈利:    {max(returns):+.2f}%")
    print(f"  最大亏损:    {min(returns):+.2f}%")

    # 按月份
    df_t = pd.DataFrame(trades)
    df_t["月"] = df_t["date"].str[:7]
    monthly = df_t.groupby("月")["return"].agg(["mean", "count", lambda x: (x>0).sum()])
    print(f"\n  月度表现:")
    for idx, row in monthly.iterrows():
        bar = "🟢" if row["mean"] > 1 else ("🟡" if row["mean"] > 0 else "🔴")
        print(f"    {bar} {idx}: {row['mean']:>+5.1f}% W{int(row['<lambda>'])}/{int(row['count'])}")

    # 最近10笔
    print(f"\n  最近10笔交易:")
    for t in trades[-10:]:
        c = "✅" if t["return"] > 0 else "❌"
        print(f"    {c} {t['date']} {t['name']}({t['code']}) 买{t['buy_price']:.2f} 卖{t['sell_price']:.2f} {t['return']:+.1f}%")


if __name__ == "__main__":
    main()
