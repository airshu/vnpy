"""海龟策略 · 螺纹钢期货回测"""
from datetime import datetime
from copy import copy
from vnpy.trader.constant import Interval, Direction, Offset, Exchange
from vnpy.trader.object import TradeData
from vnpy_ctastrategy.backtesting import BacktestingEngine
import sys
sys.path.insert(0, __file__.rsplit('/', 2)[0])
from strategies.turtle_trading_strategy import TurtleTradingStrategy

# ---- 回测参数 ----
engine = BacktestingEngine()
engine.set_parameters(
    vt_symbol="RB888.SHFE",
    interval=Interval.DAILY,
    start=datetime(2021, 6, 23),
    end=datetime(2026, 6, 22),
    rate=1 / 10000,       # 万一手续费
    slippage=1,            # 1 个点滑点
    size=10,               # 合约乘数 10 吨/手
    pricetick=1,           # 最小跳动 1 元
    capital=500_000,
)

engine.add_strategy(TurtleTradingStrategy, {
    "capital": 500_000,
    "per_point_value": 10,
    "entry_window": 20,
    "exit_window": 10,
    "atr_window": 20,
    "atr_stop": 2.0,
    "max_units": 4,
})

engine.load_data()
engine.strategy._total_bars = len(engine.history_data)
engine.run_backtesting()

# ---- 回测结束后，手动平掉未平仓（注入最终成交）----
last_bar = copy(engine.history_data[-1])
last_close = last_bar.close_price
pos = engine.strategy.pos

if pos != 0:
    close_dir = Direction.LONG if pos < 0 else Direction.SHORT
    close_vol = abs(pos)

    # 注入平仓成交记录
    close_trade = TradeData(
        gateway_name="BACKTESTING",
        symbol="RB888",
        exchange=Exchange.SHFE,
        orderid="terminal_close",
        tradeid="terminal_close",
        direction=close_dir,
        offset=Offset.CLOSE,
        price=last_close,
        volume=close_vol,
        datetime=last_bar.datetime,
    )
    engine.trades[close_trade.tradeid] = close_trade
    engine.strategy.pos = 0

# ---- 结果分析 ----
trades = list(engine.trades.values())
longs = [t for t in trades if t.direction == Direction.LONG]
shorts = [t for t in trades if t.direction == Direction.SHORT]

print(f"\n{'='*60}")
print(f"  螺纹钢(RB888) · 海龟交易回测")
print(f"{'='*60}")
print(f"\n--- 交易明细 ({len(trades)} 笔) ---")
for t in trades:
    d = "多" if t.direction == Direction.LONG else "空"
    o = "开" if t.offset == Offset.OPEN else "平"
    flag = " ⭐ 终平" if t.tradeid == "terminal_close" else ""
    print(f"  {t.datetime.date()} {d}{o} {t.volume}手 @{t.price:.0f}{flag}")

stats = engine.calculate_statistics()
if stats:
    print(f"\n--- 绩效统计 ---")
    print(f"  回测区间:    {stats['start_date']} ~ {stats['end_date']}")
    print(f"  交易天数:    {stats['total_days']}")
    print(f"  初始资金:    ¥500,000")
    print(f"  最终资金:    ¥{stats['end_balance']:,.0f}")
    print(f"  总收益率:    {stats['total_return']:.2f}%")
    print(f"  年化收益:    {stats['annual_return']:.2f}%")
    print(f"  最大回撤:    {stats['max_ddpercent']:.2f}%")
    print(f"  夏普比率:    {stats['sharpe_ratio']:.2f}")
    print(f"  收益回撤比:  {stats['return_drawdown_ratio']:.2f}")
    print(f"  总交易次数:  {stats['total_trade_count']}")
    print(f"  净盈亏:      ¥{stats['total_net_pnl']:,.0f}")
    print(f"  总手续费:    ¥{stats['total_commission']:,.0f}")
    print(f"  滑点成本:    ¥{stats['total_slippage']:,.0f}")
    print(f"  盈/亏天数:   {stats['profit_days']}/{stats['loss_days']}")

print()
