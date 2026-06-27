"""
续补 2018-2020 数据 (只补缺失的, 带延迟防限流)
"""
import sqlite3, time
from datetime import datetime
from vnpy.trader.datafeed import get_datafeed
from vnpy.trader.database import get_database
from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.object import HistoryRequest

conn = sqlite3.connect(".vntrader/database.db")
stocks = conn.execute(
    "SELECT symbol, exchange FROM dbbaroverview WHERE interval='d' AND start>'2021-01-01'"
).fetchall()
conn.close()

db = get_database()
dfeed = get_datafeed()

# 跳过已有2018数据的
need = []
for sym, ex_str in stocks:
    ex = Exchange(ex_str)
    existing = db.load_bar_data(sym, ex, Interval.DAILY, start="2018-01-01", end="2018-01-10")
    if not existing or len(existing) < 3:
        need.append((sym, ex))

print(f"需补全: {len(need)} 只 (已有 347 只)")

for i, (sym, ex) in enumerate(need):
    for yr in [2018, 2019, 2020]:
        try:
            req = HistoryRequest(
                symbol=sym, exchange=ex,
                start=datetime(yr, 1, 1), end=datetime(yr, 12, 31),
                interval=Interval.DAILY,
            )
            bars = dfeed.query_bar_history(req)
            if bars:
                db.save_bar_data(bars)
            time.sleep(0.3)  # 防限流
        except Exception:
            pass
    if (i + 1) % 50 == 0:
        print(f"  进度: {i+1}/{len(need)}")
        # 验证
        cnt = db.load_bar_data("600519", Exchange.SSE, Interval.DAILY, "2018-01-01", "2018-01-10")
        exist_ok = cnt and len(cnt) >= 3
        print(f"  (验证: 茅台2018={'OK' if exist_ok else 'FAIL'})")
    time.sleep(0.2)

# 最终验证
conn = sqlite3.connect(".vntrader/database.db")
cnt = conn.execute(
    "SELECT COUNT(DISTINCT symbol) FROM dbbaroverview WHERE interval='d' AND start<='2019-01-01'"
).fetchone()[0]
conn.close()
print(f"\n完成! 2018年前有数据的: {cnt} 只")
