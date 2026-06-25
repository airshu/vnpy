"""下载更多期货 1 小时 K 线"""
import akshare as ak
import pandas as pd
from vnpy.trader.database import get_database
from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.object import BarData

db = get_database()

FUTURES = [
    ("RB888", Exchange.SHFE, "RB0", "螺纹钢"),
    ("HC888", Exchange.SHFE, "HC0", "热卷"),
    ("AL888", Exchange.SHFE, "AL0", "沪铝"),
    ("ZN888", Exchange.SHFE, "ZN0", "沪锌"),
    ("FG888", Exchange.CZCE, "FG0", "玻璃"),
    ("TA888", Exchange.CZCE, "TA0", "PTA"),
    ("SR888", Exchange.CZCE, "SR0", "白糖"),
    ("Y888",  Exchange.DCE,  "Y0",  "豆油"),
    ("JM888", Exchange.DCE,  "JM0", "焦煤"),
    ("J888",  Exchange.DCE,  "J0",  "焦炭"),
    ("SC888", Exchange.INE,  "SC0", "原油"),
    ("CF888", Exchange.CZCE, "CF0", "棉花"),
]

for vnpy_sym, ex, ak_sym, name in FUTURES:
    try:
        df = ak.futures_zh_minute_sina(symbol=ak_sym, period="60")
        df["datetime"] = pd.to_datetime(df["datetime"]).dt.tz_localize("Asia/Shanghai")
        bars = []
        for _, row in df.iterrows():
            dt = row["datetime"].to_pydatetime()
            bars.append(BarData(
                gateway_name="AK", symbol=vnpy_sym, exchange=ex,
                datetime=dt, interval=Interval.HOUR,
                open_price=row["open"], high_price=row["high"],
                low_price=row["low"], close_price=row["close"],
                volume=row["volume"], open_interest=row["hold"],
            ))
        db.save_bar_data(bars)
        print(f"✅ {name}: {len(bars)}根  {bars[0].datetime.date()} ~ {bars[-1].datetime.date()}")
    except Exception as e:
        print(f"❌ {name}: {e}")
