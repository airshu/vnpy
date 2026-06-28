"""
布林带均值回归策略 (A股专用)

逻辑:
- 价格跌破下轨 → 做多（超跌反弹）
- 价格回升到中轨 → 平多止盈
- 价格跌破买入价 × (1 - stop_pct) → 止损
- A股不做空，只做多

适合震荡行情。
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


class BollingerMeanRevertStrategy(CtaTemplate):
    """布林带均值回归策略（A股多头版）"""

    author = "VeighNa用户"

    boll_window: int = 20          # 布林带周期
    boll_dev: float = 2.5          # 标准差倍数（越大越少交易）
    fixed_size: int = 100           # 每次交易股数
    stop_pct: float = 5.0           # 止损百分比(%)

    boll_mid: float = 0.0
    boll_up: float = 0.0
    boll_down: float = 0.0
    entry_price: float = 0.0        # 入场价（用于止损计算）

    parameters = ["boll_window", "boll_dev", "fixed_size", "stop_pct"]
    variables = ["boll_mid", "boll_up", "boll_down", "entry_price"]

    def on_init(self) -> None:
        """策略初始化"""
        self.write_log("布林带均值回归策略初始化")
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

        self.boll_up, self.boll_down = am.boll(self.boll_window, self.boll_dev)
        self.boll_mid = (self.boll_up + self.boll_down) / 2
        close: float = bar.close_price

        # 空仓 → 触及下轨做多
        if self.pos == 0:
            if close <= self.boll_down:
                self.buy(bar.close_price, self.fixed_size)
                self.entry_price = bar.close_price

        # 持多仓 → 止盈或止损
        elif self.pos > 0:
            stop_price: float = self.entry_price * (1 - self.stop_pct / 100)
            if close <= stop_price:
                self.sell(bar.close_price, abs(self.pos))
                self.entry_price = 0.0
            elif close >= self.boll_mid:
                self.sell(bar.close_price, abs(self.pos))
                self.entry_price = 0.0

        self.put_event()

    def on_trade(self, trade: TradeData) -> None:
        self.put_event()

    def on_order(self, order: OrderData) -> None:
        pass

    def on_stop_order(self, stop_order: StopOrder) -> None:
        pass
