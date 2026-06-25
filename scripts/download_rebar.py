"""下载螺纹钢期货历史日线数据"""
from datetime import datetime, timedelta
from vnpy.trader.datafeed import get_datafeed
from vnpy.trader.database import get_database
from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.object import HistoryRequest

# 尝试多个螺纹钢主力合约代码
symbols = ["RB888", "RB99", "RB000", "RB"]
exchange = Exchange.SHFE

df = get_datafeed()
db = get_database()

start = datetime(2018, 1, 1)
end = datetime(2026, 6, 22)

for sym in symbols:
    print(f"尝试 {sym}.{exchange.value}...")
    try:
        req = HistoryRequest(
            symbol=sym,
            exchange=exchange,
            start=start,
            end=end,
            interval=Interval.DAILY,
        )
        bars = df.query_bar_history(req)
        if bars and len(bars) > 0:
            print(f"  ✅ 成功！{len(bars)} 根K线，{bars[0].datetime} ~ {bars[-1].datetime}")
            db.save_bar_data(bars)
            print(f"  已保存到数据库")
            break
        else:
            print(f"  ❌ 无数据")
    except Exception as e:
        print(f"  ❌ 错误: {e}")
