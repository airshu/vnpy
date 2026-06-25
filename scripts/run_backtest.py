"""海龟交易策略回测脚本"""
from datetime import datetime
from vnpy.trader.constant import Interval
from vnpy_ctastrategy.backtesting import BacktestingEngine

# 导入自定义海龟策略
import sys
sys.path.insert(0, __file__.rsplit('/', 2)[0])
from strategies.turtle_trading_strategy import TurtleTradingStrategy

# ---- 要测试的品种列表 ----
SYMBOLS = [
    ("600519", "SSE", "贵州茅台", 1500),
    ("002594", "SZSE", "比亚迪", 250),
    ("300750", "SZSE", "宁德时代", 200),
    ("510050", "SSE", "上证50ETF", 2.5),
    ("510300", "SSE", "沪深300ETF", 4.0),
    ("002230", "SZSE", "科大讯飞", 50),
]


def run(symbol: str, exchange: str, name: str, approx_price: float):
    """运行单个品种的回测"""
    vt_symbol = f"{symbol}.{exchange}"
    print(f"\n{'='*60}")
    print(f"  {name} ({vt_symbol})")
    print(f"{'='*60}")

    engine = BacktestingEngine()

    engine.set_parameters(
        vt_symbol=vt_symbol,
        interval=Interval.DAILY,        # 日线
        start=datetime(2022, 6, 13),
        end=datetime(2026, 6, 18),
        rate=0.5 / 10000,               # 万五佣金（含印花税）
        slippage=0.01,                  # 1 分钱滑点
        size=1,                         # 股票每手 = 1（P&L 按股计算）
        pricetick=0.01,                 # 最小变动 1 分
        capital=500_000,                # 50 万初始资金
    )

    # 策略参数：per_point_value=1（按股计算），max_units=2 控制仓位
    setting = {
        "capital": 500_000,
        "per_point_value": 1,
        "entry_window": 20,
        "exit_window": 10,
        "atr_window": 20,
        "atr_stop": 2.0,
        "max_units": 2,             # 最多加仓2次，控制总仓位
    }

    engine.add_strategy(TurtleTradingStrategy, setting)
    engine.load_data()
    engine.strategy._total_bars = len(engine.history_data)  # 告诉策略K线总数
    engine.run_backtesting()

    df = engine.calculate_result()
    stats = engine.calculate_statistics()

    if stats is None:
        print("  ⚠ 回测无交易数据")
        return

    # 关键指标
    print(f"  最终资金:      {stats.get('end_balance', 0):,.0f} 元")
    print(f"  总收益率:      {stats.get('total_return', 0):.2f}%")
    print(f"  年化收益率:    {stats.get('annual_return', 0):.2f}%")
    print(f"  最大回撤:      {stats.get('max_ddpercent', 0):.2f}%")
    print(f"  夏普比率:      {stats.get('sharpe_ratio', 0):.2f}")
    print(f"  收益回撤比:    {stats.get('return_drawdown_ratio', 0):.2f}")
    print(f"  总交易次数:    {stats.get('total_trade_count', 0)}")
    print(f"  盈利天数:      {stats.get('profit_days', 0)} / {stats.get('total_days', 1)}")
    print(f"  日均盈亏:      {stats.get('daily_net_pnl', 0):.0f} 元")
    print(f"  总手续费:      {stats.get('total_commission', 0):.0f} 元")
    print(f"  总滑点:        {stats.get('total_slippage', 0):.0f} 元")


if __name__ == "__main__":
    for sym, ex, name, price in SYMBOLS:
        try:
            run(sym, ex, name, price)
        except Exception as e:
            print(f"\n  ❌ {name} 回测失败: {e}")

    print("\n" + "=" * 60)
    print("  回测完成！")
    print("=" * 60)
