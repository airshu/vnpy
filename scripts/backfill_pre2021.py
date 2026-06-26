"""用东方财富API补全2018-2020年数据"""
import akshare as ak
import pandas as pd
import sqlite3
import time
from datetime import datetime
from vnpy.trader.database import get_database
from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.object import BarData

db = get_database()

# 获取需要补的股票(数据早于2021年的)
conn = sqlite3.connect('.vntrader/database.db')
rows = conn.execute(
    "SELECT symbol, exchange FROM dbbaroverview WHERE interval='d' GROUP BY symbol, exchange"
).fetchall()
conn.close()

print(f"总股票数: {len(rows)}")
new = 0
skip = 0

for i, (sym, ex_str) in enumerate(rows):
    ex = Exchange(ex_str)

    # 检查是否已有2020年之前的数据
    bars = db.load_bar_data(sym, ex, Interval.DAILY, start="2018-01-01", end="2018-03-01")
    if bars and len(bars) > 10:
        skip += 1
        continue

    try:
        # 东方财富API - 无5年限制
        df = ak.stock_zh_a_hist(symbol=sym, period="daily",
                                start_date="20180101", end_date="20201231",
                                adjust="qfq")
        if df is None or len(df) == 0:
            continue

        df["日期"] = pd.to_datetime(df["日期"])

        bars = []
        for _, row in df.iterrows():
            bars.append(BarData(
                gateway_name="AK", symbol=sym, exchange=ex,
                datetime=row["日期"].to_pydatetime(),
                interval=Interval.DAILY,
                open_price=row["开盘"], high_price=row["最高"],
                low_price=row["最低"], close_price=row["收盘"],
                volume=row["成交量"], open_interest=0,
            ))
        db.save_bar_data(bars)
        new += 1
    except Exception as e:
        pass

    if (i + 1) % 200 == 0:
        print(f"  {i+1}/{len(rows)}  已补 {new} 只")

    time.sleep(0.3)  # 控制频率

print(f"\n完成: 已补 {new} 只, 已有 {skip} 只")
