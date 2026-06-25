"""
龙虎榜完整回测 (2023-01 ~ 2025-12)
1. 下载龙虎榜 → 提取候选股
2. 下载候选股日线数据
3. 跑12条件回测
"""
import akshare as ak
import pandas as pd
import numpy as np
import time
from datetime import datetime, timedelta
from vnpy.trader.datafeed import get_datafeed
from vnpy.trader.database import get_database
from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.object import HistoryRequest


def step1_download_lhb(start="20230101", end="20251231"):
    """下载龙虎榜，返回满足基础条件的股票列表"""
    print(f"[1/3] 下载龙虎榜 {start[:4]}-{start[4:6]} ~ {end[:4]}-{end[4:6]}...")
    df = ak.stock_lhb_detail_em(start_date=start, end_date=end)

    df["涨跌幅"] = pd.to_numeric(df["涨跌幅"], errors="coerce")
    df["换手率"] = pd.to_numeric(df["换手率"], errors="coerce")
    df["净买额"] = pd.to_numeric(df["龙虎榜净买额"], errors="coerce") / 10000
    df["流通市值"] = pd.to_numeric(df["流通市值"], errors="coerce")
    df["原因"] = df["上榜原因"].astype(str)

    mask = (
        ~df["原因"].str.contains("ST|连续三个|异常波动", na=False)
        & (df["换手率"] >= 3) & (df["换手率"] <= 10)
        & (df["流通市值"] > 30) & (df["净买额"] > 3000)
    )
    base = df[mask].copy()

    # 提取唯一股票
    codes = base["代码"].unique()
    print(f"  龙虎榜总数: {len(df)}")
    print(f"  基础筛选后: {len(base)} 笔")
    print(f"  涉及股票:   {len(codes)} 只")
    return codes, base


def step2_download_stocks(codes):
    """下载缺失的股票日线"""
    print(f"\n[2/3] 检查并下载股票数据...")
    df = get_datafeed()
    db = get_database()
    new = 0
    total = len(codes)

    for i, code in enumerate(codes):
        sym = str(code).zfill(6)
        ex = Exchange.SSE if sym.startswith("6") else Exchange.SZSE

        # 检查是否已有数据
        bars = db.load_bar_data(sym, ex, Interval.DAILY, start="2022-01-01", end="2026-01-01")
        if bars and len(bars) > 100:
            continue

        # 下载
        try:
            req = HistoryRequest(
                symbol=sym, exchange=ex,
                start=datetime(2022, 1, 1), end=datetime(2026, 7, 1),
                interval=Interval.DAILY,
            )
            bars = df.query_bar_history(req)
            if bars:
                db.save_bar_data(bars)
                new += 1
        except Exception:
            pass

        if (i + 1) % 100 == 0:
            print(f"  {i+1}/{total}  新下载 {new} 只")

        time.sleep(0.2)

    print(f"  新下载 {new} 只股票")


def step3_backtest(base):
    """运行12条件回测"""
    print(f"\n[3/3] 回测 {len(base)} 笔候选...")
    db = get_database()
    base["上榜日"] = pd.to_datetime(base["上榜日"])

    trades = []
    passed = 0
    limit_skip = 0
    db_fail = 0

    for _, row in base.iterrows():
        sym = str(row["代码"]).zfill(6)
        ex = Exchange.SSE if sym.startswith("6") else Exchange.SZSE
        d = row["上榜日"]

        bars = db.load_bar_data(sym, ex, Interval.DAILY,
                                start=(d - timedelta(days=150)).strftime("%Y-%m-%d"),
                                end=(d + timedelta(days=1)).strftime("%Y-%m-%d"))
        if bars is None or len(bars) < 60:
            db_fail += 1; continue

        cl = np.array([b.close_price for b in bars])
        hi = np.array([b.high_price for b in bars])
        vo = np.array([b.volume for b in bars])
        idx = next((i for i, b in enumerate(bars) if b.datetime.date() == d.date()), None)
        if idx is None or idx < 20: continue

        c = cl[idx]; tb = bars[idx]; pc = cl[idx - 1]
        if tb.open_price >= pc * 1.098 or tb.low_price >= pc * 1.098: continue
        if c / np.mean(cl[idx - 19:idx + 1]) < 1.02: continue

        g, l2 = [], []
        for i in range(idx - 13, idx + 1):
            dd = cl[i] - cl[i - 1]
            g.append(dd if dd > 0 else 0)
            l2.append(-dd if dd < 0 else 0)
        rsi = 100 - 100 / (1 + np.mean(g) / np.mean(l2)) if np.mean(l2) > 0 else 100
        if rsi < 55 or rsi > 85: continue

        h60 = float(max(hi[idx - 59:idx + 1]))
        if (c - h60) / h60 * 100 < -15: continue
        if (c / cl[idx - 20] - 1) * 100 < 5: continue

        av5 = np.mean(vo[idx - 4:idx + 1])
        av20 = np.mean(vo[idx - 19:idx + 1])
        if av5 / av20 < 1.2 or av5 / av20 > 3.0: continue
        if idx >= 5 and (c / cl[idx - 5] - 1) * 100 >= 15: continue

        ud = 0
        for i in range(idx, 0, -1):
            if cl[i] > cl[i - 1] * 1.095: ud += 1
            else: break
        if ud > 1: continue

        passed += 1

        b2 = db.load_bar_data(sym, ex, Interval.DAILY,
                              start=(d - timedelta(days=1)).strftime("%Y-%m-%d"),
                              end=(d + timedelta(days=5)).strftime("%Y-%m-%d"))
        if b2 is None or len(b2) < 3: continue
        lb = next((b for b in b2 if b.datetime.date() == d.date()), None)
        nb = next((b for b in b2 if b.datetime.date() > d.date()), None)
        sb = next((b for b in b2 if b.datetime.date() > (nb.datetime.date() if nb else d.date())), None)
        if not lb or not nb or not sb: continue
        if nb.open_price >= lb.close_price * 1.098:
            limit_skip += 1; continue

        ret = (sb.open_price - nb.open_price) / nb.open_price * 100
        trades.append(ret)

    return trades, passed, limit_skip, db_fail


def main():
    codes, base = step1_download_lhb("20230101", "20251231")
    step2_download_stocks(codes)
    trades, passed, limit_skip, db_fail = step3_backtest(base)

    print(f"\n{'='*55}")
    print(f"  回测结果 (2023-01 ~ 2025-12)")
    print(f"{'='*55}")
    print(f"  基础候选: {len(base)} 笔")
    print(f"  通过12条件: {passed}")
    print(f"  涨停跳过: {limit_skip}")
    print(f"  数据不足: {db_fail}")
    print(f"  有效交易: {len(trades)} 笔")

    if trades:
        total = sum(trades)
        w = sum(1 for r in trades if r > 0)
        print(f"  总盈亏:    {total:+.1f}%")
        print(f"  均收益:    {total/len(trades):+.2f}%")
        print(f"  胜率:      {w}/{len(trades)} ({w/len(trades)*100:.0f}%)")

        # 按年统计
        print(f"\n  按年统计:")


if __name__ == "__main__":
    main()
