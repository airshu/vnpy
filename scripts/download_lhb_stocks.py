"""下载龙虎榜候选股票的日线数据"""
import akshare as ak
import pandas as pd
import time
from datetime import datetime
from vnpy.trader.datafeed import get_datafeed
from vnpy.trader.database import get_database
from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.object import HistoryRequest


def get_required_symbols() -> list:
    """获取龙虎榜中符合条件的股票代码"""
    print("获取龙虎榜候选...")
    df = ak.stock_lhb_detail_em(start_date="20250101", end_date="20260624")

    df["涨跌幅"] = pd.to_numeric(df["涨跌幅"], errors="coerce")
    df["换手率"] = pd.to_numeric(df["换手率"], errors="coerce")
    df["净买额"] = pd.to_numeric(df["龙虎榜净买额"], errors="coerce") / 10000
    df["原因"] = df["上榜原因"].astype(str)

    mask = (
        (df["涨跌幅"] >= 9.8)
        & (df["换手率"] < 5)
        & (df["净买额"] > 500)
        & ~df["原因"].str.contains("ST|连续三个|异常波动", na=False)
    )
    cand = df[mask]
    symbols = cand[["代码", "名称"]].drop_duplicates(subset="代码")
    print(f"需要下载 {len(symbols)} 只股票")
    return symbols


def download_one(symbol: str, df, db) -> bool:
    """下载一只股票的日线数据"""
    exchange = Exchange.SSE if symbol.startswith("6") else Exchange.SZSE
    try:
        req = HistoryRequest(
            symbol=symbol,
            exchange=exchange,
            start=datetime(2024, 1, 1),
            end=datetime(2026, 6, 24),
            interval=Interval.DAILY,
        )
        bars = df.query_bar_history(req)
        if bars:
            db.save_bar_data(bars)
            return True
    except Exception:
        pass
    return False


def main():
    symbols = get_required_symbols()
    df = get_datafeed()
    db = get_database()

    success = 0
    fail = 0
    total = len(symbols)
    start_time = time.time()

    print(f"\n开始下载 {total} 只股票...")
    for i, (_, row) in enumerate(symbols.iterrows()):
        sym = row["代码"]
        name = row["名称"]

        ok = download_one(sym, df, db)
        if ok:
            success += 1
        else:
            fail += 1

        # 每 50 只汇报
        if (i + 1) % 50 == 0:
            elapsed = time.time() - start_time
            eta = elapsed / (i + 1) * (total - i - 1)
            print(f"  {i+1}/{total} ({((i+1)/total)*100:.0f}%) "
                  f"✅{success} ❌{fail}  ETA:{eta/60:.0f}min")

        # 控制频率，避免被封
        time.sleep(0.3)

    elapsed = time.time() - start_time
    print(f"\n下载完成! 耗时 {elapsed/60:.0f} 分钟")
    print(f"成功: {success}  失败: {fail}")


if __name__ == "__main__":
    main()
