"""同步数据库已有品种的最新数据

用法: python scripts/sync_data.py
依赖: tushare
输出: 更新 database.db 中已有品种到最新交易日
"""
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from vnpy.trader.datafeed import get_datafeed
from vnpy.trader.database import get_database, DB_TZ
from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.object import HistoryRequest, BarData


DB_PATH = ".vntrader/database.db"

# akshare 的1h/1m数据需要用新浪API直接获取
def download_hourly_bars(symbol: str, exchange: Exchange, ak_symbol: str):
    """用 akshare 新浪API 下载小时线"""
    try:
        import akshare as ak
        df = ak.futures_zh_minute_sina(symbol=ak_symbol, period="60")
        df["datetime"] = pd.to_datetime(df["datetime"]).dt.tz_localize("Asia/Shanghai")
        bars = []
        for _, row in df.iterrows():
            dt = row["datetime"].to_pydatetime()
            bars.append(BarData(
                gateway_name="AK", symbol=symbol, exchange=exchange,
                datetime=dt, interval=Interval.HOUR,
                open_price=row["open"], high_price=row["high"],
                low_price=row["low"], close_price=row["close"],
                volume=row["volume"], open_interest=row["hold"],
            ))
        return bars
    except Exception:
        return []


# 期货 vnpy代码 → akshare新浪代码 映射
SYMBOL_MAP = {
    "RB888": "RB0", "HC888": "HC0", "CU888": "CU0", "AL888": "AL0",
    "ZN888": "ZN0", "AU888": "AU0", "AG888": "AG0", "I888": "I0",
    "M888": "M0", "Y888": "Y0", "P888": "P0", "JM888": "JM0",
    "J888": "J0", "FG888": "FG0", "MA888": "MA0", "TA888": "TA0",
    "SR888": "SR0", "CF888": "CF0", "SC888": "SC0", "IF888": "IF0",
}


def main():
    db = get_database()

    # 1. 读取所有已存在的品种
    conn = sqlite3.connect(DB_PATH)
    overviews = conn.execute(
        "SELECT symbol, exchange, interval FROM dbbaroverview"
    ).fetchall()
    conn.close()

    df = get_datafeed()  # 日线用标准datafeed
    today = datetime.now(DB_TZ).replace(hour=23, minute=59, second=59)
    updated = 0
    skipped = 0

    print(f"数据库共 {len(overviews)} 个品种，开始同步...\n")

    for symbol, exchange_str, interval_str in overviews:
        exchange = Exchange(exchange_str)
        interval = Interval(interval_str)

        # 获取最新日期
        bars = db.load_bar_data(
            symbol, exchange, interval,
            start=datetime(2000, 1, 1), end=today
        )

        if not bars:
            print(f"  ⚠ {symbol}.{exchange_str} 无数据，跳过")
            skipped += 1
            continue

        latest_bar = bars[-1]
        latest_date = latest_bar.datetime

        # 判断是否需要更新（日线：距今>1天，小时线：距今>2小时）
        if interval == Interval.DAILY:
            if (today - latest_date).days <= 1:
                continue  # 已是最新
        elif interval == Interval.HOUR:
            if (today - latest_date).total_seconds() < 7200:
                continue

        # 下载新数据
        start = latest_date + timedelta(seconds=1)
        new_bars = []

        if interval == Interval.HOUR:
            # 小时线用新浪API
            ak_sym = SYMBOL_MAP.get(symbol, None)
            if ak_sym:
                new_bars = download_hourly_bars(symbol, exchange, ak_sym)
                # 过滤出更新的
                new_bars = [b for b in new_bars if b.datetime > latest_date]
        else:
            # 日线用标准datafeed
            try:
                req = HistoryRequest(
                    symbol=symbol, exchange=exchange,
                    start=start, end=today, interval=interval,
                )
                new_bars = df.query_bar_history(req) or []
            except Exception:
                pass

        if new_bars:
            db.save_bar_data(new_bars)
            updated += 1
            print(f"  ✅ {symbol}.{exchange_str} [{interval_str}] "
                  f"+{len(new_bars)}根 {new_bars[0].datetime.date()}~{new_bars[-1].datetime.date()}")
        else:
            continue  # 无新数据，不打印

    print(f"\n同步完成: 更新 {updated} 个，跳过 {skipped} 个")


if __name__ == "__main__":
    main()
