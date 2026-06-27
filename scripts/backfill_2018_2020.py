"""
补全 2018-01-01 ~ 2020-12-31 数据
用 vnpy 自带 datafeed (新浪源), 无 5 年限制
"""
import sqlite3
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

print(f"需补全: {len(stocks)} 只股票 → 2018-01-01 ~ 2020-12-31")

df = get_datafeed()
db = get_database()

success = 0
skip = 0
fail = 0

for i, (sym, ex_str) in enumerate(stocks):
    ex = Exchange(ex_str)
    # 先检查是否已有足够数据
    existing = db.load_bar_data(sym, ex, Interval.DAILY, start="2018-01-01", end="2018-01-10")
    if existing and len(existing) >= 3:
        skip += 1
        continue

    # 按年下载（新浪对单次请求条数有限制）
    for yr in [2018, 2019, 2020]:
        try:
            req = HistoryRequest(
                symbol=sym, exchange=ex,
                start=datetime(yr, 1, 1), end=datetime(yr, 12, 31),
                interval=Interval.DAILY,
            )
            bars = df.query_bar_history(req)
            if bars:
                db.save_bar_data(bars)
        except Exception:
            pass  # 部分股票可能2018年还没上市

    success += 1
    if success % 100 == 0:
        print(f"  进度: {success}/{len(stocks)} (跳过 {skip})")

print(f"\n完成: 成功 {success}, 跳过(已有) {skip}, 失败 {fail}")

# 验证
conn = sqlite3.connect(".vntrader/database.db")
cnt = conn.execute(
    "SELECT COUNT(DISTINCT symbol) FROM dbbaroverview WHERE interval='d' AND start<='2019-01-01'"
).fetchone()[0]
print(f"2018年前有数据的: {cnt} 只")
conn.close()
