"""同步 A 股日线数据到最新交易日

用法: python scripts/sync_data.py
输出: 更新 database.db 中所有 A 股日线到最新交易日
"""
import sqlite3
from datetime import datetime, timedelta
from vnpy.trader.datafeed import get_datafeed
from vnpy.trader.database import get_database, DB_TZ
from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.object import HistoryRequest


DB_PATH = ".vntrader/database.db"

# 只同步 A 股（沪深交易所）
STOCK_EXCHANGES = {"SSE", "SZSE"}


def main():
    db = get_database()

    # 1. 只读 A 股日线
    conn = sqlite3.connect(DB_PATH)
    overviews = conn.execute(
        "SELECT symbol, exchange, interval FROM dbbaroverview "
        "WHERE exchange IN ('SSE','SZSE') AND interval='d'"
    ).fetchall()
    conn.close()

    df = get_datafeed()
    today = datetime.now(DB_TZ).replace(hour=23, minute=59, second=59)
    updated = 0

    print(f"A 股共 {len(overviews)} 只，开始同步...\n")

    for symbol, exchange_str, interval_str in overviews:
        exchange = Exchange(exchange_str)

        # 获取最新日期
        bars = db.load_bar_data(
            symbol, exchange, Interval.DAILY,
            start=datetime(2000, 1, 1), end=today
        )
        if not bars:
            continue

        latest_date = bars[-1].datetime
        if (today - latest_date).days <= 1:
            continue  # 已是最新

        # 下载新数据
        try:
            req = HistoryRequest(
                symbol=symbol, exchange=exchange,
                start=latest_date + timedelta(seconds=1),
                end=today, interval=Interval.DAILY,
            )
            new_bars = df.query_bar_history(req) or []
        except Exception:
            continue

        if new_bars:
            db.save_bar_data(new_bars)
            updated += 1
            print(f"  ✅ {symbol}.{exchange_str} +{len(new_bars)}根 "
                  f"{new_bars[0].datetime.date()}~{new_bars[-1].datetime.date()}")
            if updated % 100 == 0:
                print(f"  ... {updated} 只已更新")

    print(f"\n同步完成: 更新 {updated} 只")


if __name__ == "__main__":
    main()
