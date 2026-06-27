"""
用 baostock 补全 2018-2020 数据
"""
import sqlite3, sys, time
from datetime import datetime
import baostock as bs
from vnpy.trader.database import get_database
from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.object import BarData

def log(msg):
    print(msg, flush=True)

conn = sqlite3.connect(".vntrader/database.db")
stocks = conn.execute(
    "SELECT symbol, exchange FROM dbbaroverview WHERE interval='d' AND start>'2021-01-01'"
).fetchall()
conn.close()

db = get_database()
bs.login()
log(f"需补全: {len(stocks)} 只")

success = 0
fail = 0
t0 = time.time()

for i, (sym, ex_str) in enumerate(stocks):
    bs_code = f"{'sh' if ex_str=='SSE' else 'sz'}.{sym}"
    ex = Exchange(ex_str)

    # 跳过已有
    existing = db.load_bar_data(sym, ex, Interval.DAILY, start="2018-01-01", end="2018-01-10")
    if existing and len(existing) >= 3:
        success += 1
        continue

    try:
        rs = bs.query_history_k_data_plus(
            bs_code, "date,open,high,low,close,volume,amount",
            start_date="2018-01-01", end_date="2020-12-31",
            frequency="d", adjustflag="2",
        )
        rows = []
        while rs.next():
            rows.append(rs.get_row_data())

        if rows:
            bars = []
            for row in rows:
                if row[0] == "" or row[1] == "0.000000":
                    continue
                bar = BarData(
                    gateway_name="BS", symbol=sym, exchange=ex,
                    datetime=datetime.strptime(row[0], "%Y-%m-%d"),
                    interval=Interval.DAILY,
                    open_price=float(row[1]), high_price=float(row[2]),
                    low_price=float(row[3]), close_price=float(row[4]),
                    volume=float(row[5]), turnover=float(row[6]),
                )
                bars.append(bar)
            db.save_bar_data(bars)
            success += 1
        else:
            fail += 1
    except Exception as e:
        fail += 1

    if (i + 1) % 200 == 0:
        elapsed = time.time() - t0
        log(f"  {i+1}/{len(stocks)}  ok={success}  fail={fail}  {elapsed:.0f}s")

bs.logout()

# 验证
conn = sqlite3.connect(".vntrader/database.db")
cnt = conn.execute(
    "SELECT COUNT(DISTINCT symbol) FROM dbbaroverview WHERE interval='d' AND start<='2019-01-01'"
).fetchone()[0]
conn.close()
elapsed = time.time() - t0
log(f"\n完成: {success}成功 {fail}失败  耗时{elapsed:.0f}s")
log(f"2018年前有数据: {cnt} 只 / {len(stocks)}")
