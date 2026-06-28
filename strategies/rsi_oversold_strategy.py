"""
RSI 超卖反弹策略 (A股专用)

逻辑:
- RSI ≤ oversold → 超卖恐慌 → 做多（抄底）
- RSI ≥ exit_level → 超卖修复 → 平多止盈
- 价格跌破入场价 × (1 - stop_pct/100) → 止损

A股习惯性超跌反弹，RSI越低反弹概率越大。
不做空，只做多。
"""
import numpy as np

from vnpy_ctastrategy import (
    CtaTemplate,
    StopOrder,
    TickData,
    BarData,
    TradeData,
    OrderData,
    BarGenerator,
    ArrayManager,
)


class RsiOversoldStrategy(CtaTemplate):
    """RSI 超卖反弹策略（A股多头版）"""

    author = "VeighNa用户"

    rsi_window: int = 14           # RSI 周期
    rsi_oversold: int = 35         # 超卖买入阈值
    rsi_exit: int = 65             # 平多止盈阈值
    fixed_size: int = 100          # 每次交易股数
    stop_pct: float = 8.0          # 止损百分比(%)

    rsi_value: float = 50.0
    entry_price: float = 0.0       # 入场价

    parameters = [
        "rsi_window", "rsi_oversold", "rsi_exit",
        "fixed_size", "stop_pct",
    ]
    variables = ["rsi_value", "entry_price"]

    def on_init(self) -> None:
        """策略初始化"""
        self.write_log("RSI超卖反弹策略初始化")
        self.bg: BarGenerator = BarGenerator(self.on_bar)
        self.am: ArrayManager = ArrayManager()
        self.load_bar(30)

    def on_start(self) -> None:
        self.write_log("策略启动")
        self.put_event()

    def on_stop(self) -> None:
        self.write_log("策略停止")
        self.put_event()

    def on_tick(self, tick: TickData) -> None:
        self.bg.update_tick(tick)

    def on_bar(self, bar: BarData) -> None:
        self.cancel_all()
        am: ArrayManager = self.am
        am.update_bar(bar)
        if not am.inited:
            return

        self.rsi_value = am.rsi(self.rsi_window)
        rsi: float = self.rsi_value
        close: float = bar.close_price

        # MA60 趋势过滤
        ma60: float = am.sma(60)

        # 空仓 → 等待入场
        if self.pos == 0:
            if rsi <= self.rsi_oversold and close > ma60:
                # 超卖 + 趋势向上 → 做多
                self.buy(close, self.fixed_size)
                self.entry_price = close

        # 持多仓 → 止盈或止损
        elif self.pos > 0:
            # 止损
            stop_price: float = self.entry_price * (1 - self.stop_pct / 100)
            if close <= stop_price:
                self.sell(close, abs(self.pos))
                self.entry_price = 0.0
            # 止盈: RSI 修复
            elif rsi >= self.rsi_exit:
                self.sell(close, abs(self.pos))
                self.entry_price = 0.0

        self.put_event()

    def on_trade(self, trade: TradeData) -> None:
        self.put_event()

    def on_order(self, order: OrderData) -> None:
        pass

    def on_stop_order(self, stop_order: StopOrder) -> None:
        pass
