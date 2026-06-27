"""下载多个期货品种的日线数据"""
from datetime import datetime
from vnpy.trader.datafeed import get_datafeed
from vnpy.trader.database import get_database
from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.object import HistoryRequest

# 主力连续合约代码
FUTURES = [
    ("RB888", Exchange.SHFE, "螺纹钢"),
    ("HC888", Exchange.SHFE, "热卷"),
    ("CU888", Exchange.SHFE, "沪铜"),
    ("AL888", Exchange.SHFE, "沪铝"),
    ("ZN888", Exchange.SHFE, "沪锌"),
    ("AU888", Exchange.SHFE, "黄金"),
    ("AG888", Exchange.SHFE, "白银"),
    ("I888", Exchange.DCE, "铁矿石"),
    ("M888", Exchange.DCE, "豆粕"),
    ("Y888", Exchange.DCE, "豆油"),
    ("P888", Exchange.DCE, "棕榈油"),
    ("JM888", Exchange.DCE, "焦煤"),
    ("J888", Exchange.DCE, "焦炭"),
    ("FG888", Exchange.CZCE, "玻璃"),
    ("MA888", Exchange.CZCE, "甲醇"),
    ("TA888", Exchange.CZCE, "PTA"),
    ("SR888", Exchange.CZCE, "白糖"),
    ("CF888", Exchange.CZCE, "棉花"),
    ("SC888", Exchange.INE, "原油"),
    ("IF888", Exchange.CFFEX, "沪深300股指"),
]

df = get_datafeed()
db = get_database()
start = datetime(2021, 1, 1)
end = datetime(2026, 6, 22)

total = 0
success = 0

for symbol, ex, name in FUTURES:
    try:
        req = HistoryRequest(
            symbol=symbol, exchange=ex,
            start=start, end=end,
            interval=Interval.DAILY,
        )
        bars = df.query_bar_history(req)
        if bars:
            db.save_bar_data(bars)
            print(f"✅ {name}({symbol}) {len(bars)}根K线 {bars[0].datetime.date()} ~ {bars[-1].datetime.date()}")
            total += len(bars)
            success += 1
        else:
            print(f"❌ {name}({symbol}) 无数据")
    except Exception as e:
        print(f"❌ {name}({symbol}) 错误: {e}")

print(f"\n总计: {success}/20 品种, {total} 根K线")
