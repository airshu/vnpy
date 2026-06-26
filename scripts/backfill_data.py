"""补全数据库到 2020-01-01"""
import sqlite3
import time
from datetime import datetime
from vnpy.trader.datafeed import get_datafeed
from vnpy.trader.database import get_database
from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.object import HistoryRequest

db = get_database()
df = get_datafeed()

# 获取所有需要补的股票
conn = sqlite3.connect('.vntrader/database.db')
rows = conn.execute(
    "SELECT symbol, exchange FROM dbbaroverview WHERE interval='d' AND start > '2020-01-01'"
).fetchall()
conn.close()

print(f"需要补全: {len(rows)} 只股票")
updated = 0

for i, (sym, ex_str) in enumerate(rows):
    ex = Exchange(ex_str)
    # 下载2020-01-01到已有数据起始日之间的数据
    try:
        req = HistoryRequest(
            symbol=sym, exchange=ex,
            start=datetime(2020, 1, 1), end=datetime(2026, 7, 1),
            interval=Interval.DAILY,
        )
        bars = df.query_bar_history(req)
        if bars:
            db.save_bar_data(bars)
            updated += 1
    except:
        pass

    if (i + 1) % 100 == 0:
        print(f"  {i+1}/{len(rows)}  已更新 {updated} 只")

    time.sleep(0.15)  # 控制频率

print(f"\n补全完成: {updated}/{len(rows)} 只")
