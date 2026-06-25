"""海龟策略 · 20品种组合回测"""
import pandas as pd
import numpy as np
from datetime import datetime
from vnpy.trader.constant import Interval, Exchange
from vnpy_ctastrategy.backtesting import BacktestingEngine
import sys; sys.path.insert(0, __file__.rsplit('/', 2)[0])
from strategies.turtle_trading_strategy import TurtleTradingStrategy

# ---- 合约规格 ----
CONTRACTS = [
    ("RB888",  Exchange.SHFE,  "螺纹钢",  10,   1,     10),
    ("HC888",  Exchange.SHFE,  "热卷",    10,   1,     10),
    ("CU888",  Exchange.SHFE,  "沪铜",     5,  10,      5),
    ("AL888",  Exchange.SHFE,  "沪铝",     5,   5,      5),
    ("ZN888",  Exchange.SHFE,  "沪锌",     5,   5,      5),
    ("AU888",  Exchange.SHFE,  "黄金",  1000, 0.02,  1000),
    ("AG888",  Exchange.SHFE,  "白银",    15,   1,     15),
    ("I888",   Exchange.DCE,   "铁矿石", 100, 0.5,    100),
    ("M888",   Exchange.DCE,   "豆粕",    10,   1,     10),
    ("Y888",   Exchange.DCE,   "豆油",    10,   2,     10),
    ("P888",   Exchange.DCE,   "棕榈油",  10,   2,     10),
    ("JM888",  Exchange.DCE,   "焦煤",    60, 0.5,     60),
    ("J888",   Exchange.DCE,   "焦炭",   100, 0.5,    100),
    ("FG888",  Exchange.CZCE,  "玻璃",    20,   1,     20),
    ("MA888",  Exchange.CZCE,  "甲醇",    10,   1,     10),
    ("TA888",  Exchange.CZCE,  "PTA",      5,   2,      5),
    ("SR888",  Exchange.CZCE,  "白糖",    10,   1,     10),
    ("CF888",  Exchange.CZCE,  "棉花",     5,   5,      5),
    ("SC888",  Exchange.INE,   "原油",  1000, 0.1,   1000),
    ("IF888",  Exchange.CFFEX, "沪深300", 300, 0.2,    300),
]

TOTAL_CAPITAL = 10_000_000   # 总资金 1000 万
PER_SYMBOL = TOTAL_CAPITAL // len(CONTRACTS)  # 每品种 50 万

START = datetime(2021, 6, 23)
END = datetime(2026, 6, 22)

results = {}          # symbol -> daily balance series
trade_summary = []    # 汇总交易统计

for sym, ex, name, size, pricetick, per_point in CONTRACTS:
    vt_sym = f"{sym}.{ex.value}"
    engine = BacktestingEngine()
    engine.set_parameters(
        vt_symbol=vt_sym, interval=Interval.DAILY,
        start=START, end=END,
        rate=1/10000, slippage=pricetick * 2,
        size=size, pricetick=pricetick, capital=PER_SYMBOL,
    )
    engine.add_strategy(TurtleTradingStrategy, {
        "capital": PER_SYMBOL, "per_point_value": per_point,
        "entry_window": 10, "exit_window": 5,
        "atr_window": 20, "atr_stop": 2.0, "max_units": 4,
    })

    try:
        engine.load_data()
        engine.strategy._total_bars = len(engine.history_data)
        engine.run_backtesting()

        s = engine.strategy
        trades = list(engine.trades.values())
        n_trades = len(trades)
        final_pos = s.pos

        df = engine.calculate_result()
        if df is not None and len(df) > 0:
            daily_balance = PER_SYMBOL + df["net_pnl"].cumsum()
        else:
            # 无交易或无结果，资金不变
            daily_balance = pd.Series(PER_SYMBOL, index=pd.DatetimeIndex([], name="datetime"))

        # 如果还有持仓，注入最终平仓盈亏
        if final_pos != 0:
            last_bar = engine.history_data[-1]
            avg_entry = sum(t.price for t in trades if t.offset.value == "开") / max(1, n_trades)
            if final_pos < 0:
                unrealized = abs(final_pos) * (avg_entry - last_bar.close_price) * size
            else:
                unrealized = abs(final_pos) * (last_bar.close_price - avg_entry) * size
            if len(daily_balance) > 0:
                daily_balance.iloc[-1] = daily_balance.iloc[-1] + unrealized

        results[name] = daily_balance
        trade_summary.append({
            "name": name, "trades": n_trades, "pos": final_pos,
            "balance": float(daily_balance.iloc[-1]) if len(daily_balance) > 0 else PER_SYMBOL,
        })
        pos_str = f"末仓{final_pos}手" if final_pos else "已平"
        print(f"✅ {name}: {n_trades}笔 {pos_str} 终资¥{trade_summary[-1]['balance']:,.0f}")

    except Exception as e:
        print(f"❌ {name}: {e}")
        trade_summary.append({"name": name, "trades": 0, "pos": 0, "balance": PER_SYMBOL})
        results[name] = pd.Series(PER_SYMBOL, index=pd.DatetimeIndex([], name="datetime"))

# ---- 组合统计 ----
print(f"\n{'='*60}")
print(f"  海龟交易 · 20品种组合 (2021-06 ~ 2026-06)")

# 汇总日净值
all_balance = pd.DataFrame(results).ffill().fillna(PER_SYMBOL)
portfolio_balance = all_balance.sum(axis=1)
portfolio_return = portfolio_balance / TOTAL_CAPITAL - 1

# 过滤前 100 天（策略初始化期）
if len(portfolio_balance) > 100:
    portfolio_balance = portfolio_balance.iloc[100:]
    portfolio_return = portfolio_return.iloc[100:]

final_balance = portfolio_balance.iloc[-1]
total_return = portfolio_return.iloc[-1] * 100
total_days = len(portfolio_return)
annual_return = ((1 + portfolio_return.iloc[-1]) ** (240 / total_days) - 1) * 100

daily_balance_diff = portfolio_balance.diff().dropna()
daily_ret_pct = daily_balance_diff / portfolio_balance.shift(1).dropna()
dd = (portfolio_balance.cummax() - portfolio_balance) / portfolio_balance.cummax()
max_dd = dd.max() * 100
sharpe = (daily_ret_pct.mean() / daily_ret_pct.std()) * np.sqrt(240) if daily_ret_pct.std() > 0 else 0
win_days = (daily_balance_diff > 0).sum()
loss_days = (daily_balance_diff < 0).sum()
total_pnl = final_balance - TOTAL_CAPITAL

print(f"\n--- 组合绩效 ---")
print(f"  初始资金:      ¥{TOTAL_CAPITAL:,}")
print(f"  最终资金:      ¥{final_balance:,.0f}")
print(f"  总收益率:      {total_return:.2f}%")
print(f"  年化收益:      {annual_return:.2f}%")
print(f"  最大回撤:      {max_dd:.2f}%")
print(f"  夏普比率:      {sharpe:.2f}")
print(f"  净盈亏:        ¥{total_pnl:,.0f}")
print(f"  盈利/亏损天:   {win_days}/{loss_days}")

# ---- 各品种明细 ----
print(f"\n--- 各品种贡献 ---")
total_trades = sum(s["trades"] for s in trade_summary)
trade_summary.sort(key=lambda x: x["balance"], reverse=True)
total_asset = sum(s["balance"] for s in trade_summary)
for s in trade_summary:
    pnl = s["balance"] - PER_SYMBOL
    contrib = (pnl / total_pnl * 100) if total_pnl != 0 else 0
    pct = (s["balance"] / PER_SYMBOL - 1) * 100
    bar = "█" * max(0, int(pnl / 10000)) if pnl > 0 else ("░" * min(20, int(abs(pnl) / 5000)))
    print(f"  {s['name']:<6} {s['trades']:>3}笔  {pct:>+6.1f}%  ¥{s['balance']:>12,.0f}  {bar}")

print(f"\n  总交易次数: {total_trades}")
print(f"  单品种年均: {total_trades/20/5:.1f} 笔")
