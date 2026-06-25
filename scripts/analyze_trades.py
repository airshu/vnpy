"""查看海龟策略回测的多空方向分布"""
from datetime import datetime
from vnpy.trader.constant import Interval
from vnpy_ctastrategy.backtesting import BacktestingEngine

import sys
sys.path.insert(0, __file__.rsplit('/', 2)[0])
from strategies.turtle_trading_strategy import TurtleTradingStrategy

engine = BacktestingEngine()
engine.set_parameters(
    vt_symbol="600519.SSE",
    interval=Interval.DAILY,
    start=datetime(2022, 6, 13),
    end=datetime(2026, 6, 18),
    rate=0.5 / 10000,
    slippage=0.01,
    size=1,
    pricetick=0.01,
    capital=500_000,
)

setting = {
    "capital": 500_000, "per_point_value": 1,
    "entry_window": 20, "exit_window": 10,
    "atr_window": 20, "atr_stop": 2.0, "max_units": 2,
}
engine.add_strategy(TurtleTradingStrategy, setting)
engine.load_data()
engine.run_backtesting()

# 分析交易记录
trades = engine.trades
print(f"\n总成交: {len(trades)} 笔")
long_trades = [t for t in trades if t.direction.value == "多"]
short_trades = [t for t in trades if t.direction.value == "空"]
print(f"做多: {len(long_trades)} 笔, 做空: {len(short_trades)} 笔")

# 按系统分组
for label, sys_filter in [("系统1(S1)", "[SYS1]"), ("系统2(S2)", "[SYS2]")]:
    sys_count = 0
    for t in trades:
        # 检查交易日志
        pass
    print(f"{label}: 通过日志识别需要修改策略才能获取")

print("\n--- 最近10笔交易 ---")
for i, t in enumerate(trades[-10:]):
    direction = "多" if t.direction.value == "多" else "空"
    offset = "开" if "开" in str(t.offset.value) else "平"
    print(f"  {t.datetime.date()} {direction}{offset} {t.volume}股@{t.price:.2f}")

# 计算统计
df = engine.calculate_result()
print(f"\n净值曲线样本（每100天）:")
print(df.iloc[::100][['balance']].to_string())
