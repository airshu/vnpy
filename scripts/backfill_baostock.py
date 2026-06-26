"""
用 baostock 补全 2018-2020 数据 (无限制, 无延迟)
"""
import sqlite3
import pandas as pd
from datetime import datetime
import baostock as bs
from vnpy.trader.database import get_database
from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.object import BarData

conn = sqlite3.connect(".vntrader/database.db")
stocks = conn.execute(
    "SELECT symbol, exchange FROM dbbaroverview WHERE interval='d' AND start>'2021-01-01'"
).fetchall()
conn.close()

db = get_database()

# 跳过已有2018数据的
need = []
for sym, ex_str in stocks:
    ex = Exchange(ex_str)
    existing = db.load_bar_data(sym, ex, Interval.DAILY, start="2018-01-01", end="2018-01-10")
    if not existing or len(existing) < 3:
        need.append((sym, ex_str))

print(f"需补全: {len(need)} 只")

# baostock 登录
lg = bs.login()
print(f"登录: {lg.error_msg}")

success = 0
fail = 0

for i, (sym, ex_str) in enumerate(need):
    # baostock 代码格式: sh.600519 或 sz.000858
    bs_code = f"{'sh' if ex_str=='SSE' else 'sz'}.{sym}"
    ex = Exchange(ex_str)

    for yr in [2018, 2019, 2020]:
        try:
            rs = bs.query_history_k_data_plus(
                bs_code,
                "date,open,high,low,close,volume,amount",
                start_date=f"{yr}-01-01",
                end_date=f"{yr}-12-31",
                frequency="d",
                adjustflag="2",  # 前复权
            )
            rows = []
            while rs.next():
                rows.append(rs.get_row_data())

            if not rows:
                continue

            bars = []
            for row in rows:
                if row[0] == "" or row[1] == "0.000000":
                    continue
                dt = datetime.strptime(row[0], "%Y-%m-%d")
                bar = BarData(
                    gateway_name="BS",
                    symbol=sym,
                    exchange=ex,
                    datetime=dt,
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

        except Exception:
            pass

    success += 1
    if success % 200 == 0:
        print(f"  进度: {success}/{len(need)}")

bs.logout()

# 验证
conn = sqlite3.connect(".vntrader/database.db")
cnt = conn.execute(
    "SELECT COUNT(DISTINCT symbol) FROM dbbaroverview WHERE interval='d' AND start<='2019-01-01'"
).fetchone()[0]
conn.close()
print(f"\n完成! 成功 {success}, 失败 {fail}")
print(f"2018年前有数据: {cnt} 只")
