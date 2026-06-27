"""
用 baostock 补全 2018-2020 股票日线数据 (推荐版本)

用法: python scripts/backfill_baostock_v3.py
依赖: baostock, sqlite3
输出: 直接写入 database.db，跳过已有数据不重复下载
"""
import sqlite3, sys, time
from datetime import datetime
import baostock as bs
from vnpy.trader.database import get_database
from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.object import BarData

def log(msg):
    print(msg, flush=True)

db = get_database()
bs.login()
log("baostock login ok")

# 一次性查出所有需要补的
conn = sqlite3.connect(".vntrader/database.db")
all_symbols = conn.execute(
    "SELECT DISTINCT symbol, exchange FROM dbbaroverview WHERE interval='d'"
).fetchall()
conn.close()

# 查出已有2018数据的
conn = sqlite3.connect(".vntrader/database.db")
existing_2018 = set()
for row in conn.execute(
    "SELECT DISTINCT symbol FROM dbbaroverview WHERE interval='d' AND start<='2019-01-01'"
).fetchall():
    existing_2018.add(row[0])
conn.close()

need = [(s, e) for s, e in all_symbols if s not in existing_2018]
log(f"总计: {len(all_symbols)} 只  已有2018: {len(existing_2018)}  需补: {len(need)}")

success = 0
fail = 0
t0 = time.time()

for i, (sym, ex_str) in enumerate(need):
    bs_code = f"{'sh' if ex_str == 'SSE' else 'sz'}.{sym}"
    ex = Exchange(ex_str)

    try:
        rs = bs.query_history_k_data_plus(
            bs_code,
            "date,open,high,low,close,volume,amount",
            start_date="2018-01-01",
            end_date="2020-12-31",
            frequency="d",
            adjustflag="2",
        )
        if rs.error_code != "0":
            fail += 1
            continue

        rows = []
        while rs.next():
            rows.append(rs.get_row_data())

        if not rows:
            fail += 1
            continue

        bars = []
        for row in rows:
            if row[0] == "" or row[1] == "0.000000":
                continue
            bar = BarData(
                gateway_name="BS",
                symbol=sym,
                exchange=ex,
                datetime=datetime.strptime(row[0], "%Y-%m-%d"),
                interval=Interval.DAILY,
                open_price=float(row[1]),
                high_price=float(row[2]),
                low_price=float(row[3]),
                close_price=float(row[4]),
                volume=float(row[5]),
                turnover=float(row[6]),
            )
            bars.append(bar)

        if bars:
            db.save_bar_data(bars)
            success += 1
        else:
            fail += 1
    except Exception:
        fail += 1

    if (i + 1) % 200 == 0:
        elapsed = time.time() - t0
        log(f"  [{i+1}/{len(need)}] ok={success} fail={fail}  {elapsed:.0f}s")

bs.logout()

# 验证
conn = sqlite3.connect(".vntrader/database.db")
cnt = conn.execute(
    "SELECT COUNT(DISTINCT symbol) FROM dbbaroverview WHERE interval='d' AND start<='2019-01-01'"
).fetchone()[0]
conn.close()
elapsed = time.time() - t0
log(f"\n完成: ok={success} fail={fail}  耗时{elapsed:.0f}s")
log(f"2018年前有数据: {cnt}/{len(all_symbols)} 只")
