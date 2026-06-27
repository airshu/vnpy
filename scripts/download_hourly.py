"""下载期货 1 小时 K 线数据到数据库"""
import akshare as ak
import pandas as pd
from datetime import datetime
from vnpy.trader.database import get_database
from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.object import BarData

db = get_database()

# 主力连续合约 -> akshare符号映射
FUTURES = [
    ("RB888", Exchange.SHFE, "RB0", "螺纹钢"),
    ("CU888", Exchange.SHFE, "CU0", "沪铜"),
    ("AG888", Exchange.SHFE, "AG0", "白银"),
    ("M888",  Exchange.DCE,  "M0",  "豆粕"),
    ("MA888", Exchange.CZCE, "MA0", "甲醇"),
    ("P888",  Exchange.DCE,  "P0",  "棕榈油"),
]

for vnpy_sym, ex, ak_sym, name in FUTURES:
    try:
        df = ak.futures_zh_minute_sina(symbol=ak_sym, period="60")
        df["datetime"] = pd.to_datetime(df["datetime"]).dt.tz_localize("Asia/Shanghai")
        bars = []
        for _, row in df.iterrows():
            dt = row["datetime"].to_pydatetime()
            bar = BarData(
                gateway_name="AK",
                symbol=vnpy_sym,
                exchange=ex,
                datetime=dt,
                interval=Interval.HOUR,
                open_price=row["open"],
                high_price=row["high"],
                low_price=row["low"],
                close_price=row["close"],
                volume=row["volume"],
                open_interest=row["hold"],
            )
            bars.append(bar)
        db.save_bar_data(bars)
        print(f"✅ {name}: {len(bars)} 根 1h K线, {bars[0].datetime} ~ {bars[-1].datetime}")
    except Exception as e:
        print(f"❌ {name}: {e}")
