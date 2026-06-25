"""
动量轮动策略（A股短线 · T+1 兼容）

核心逻辑：
- 每天尾盘（日线）计算过去 N 日的涨跌幅
- 买入涨幅最大的股票
- 次日尾盘卖出，换仓到新动量最强的股票

原理：短期动量效应（Jegadeesh & Titman, 1993）
A股市场 5-20 日动量效果显著（存在显著的散户动量效应）

用法：
1. 在多个股票上各跑一个策略实例
2. 通过外部排分选出最强的 3-5 只
3. 或者直接给定一个已筛选的股票池
"""
import numpy as np
from collections import deque

from vnpy_ctastrategy import (
    CtaTemplate,
    TickData,
    BarData,
    TradeData,
    OrderData,
    BarGenerator,
)


class MomentumRotationStrategy(CtaTemplate):
    """日间动量轮动（单品种）

    每个品种独立运行：
    - 5日涨跌幅 > 阈值 → 尾盘买入
    - 持有 1 天 → 次日出掉
    - 继续监测动量，循环

    配合多品种一起跑效果最佳
    """
    author = "VeighNa用户"

    # ---- 参数 ----
    momentum_window: int = 5       # 动量计算窗口（天）
    mom_threshold: float = 0.02   # 动量阈值（涨超2%才买）
    fixed_size: int = 100         # 每次交易股数
    hold_days: int = 1            # 持仓天数

    parameters = [
        "momentum_window", "mom_threshold",
        "fixed_size", "hold_days",
    ]

    # ---- 变量 ----
    momentum: float = 0.0          # 当前动量
    hold_counter: int = 0          # 已持有天数

    variables = ["momentum", "hold_counter"]

    def on_init(self) -> None:
        """初始化"""
        self.write_log("动量轮动策略初始化")
        self.bg = BarGenerator(self.on_bar)
        self._close_deque: deque[float] = deque(maxlen=self.momentum_window + 5)
        self.load_bar(self.momentum_window + 20)

    def on_start(self) -> None:
        """策略启动"""
        self.write_log(f"动量轮动启动 | 窗口={self.momentum_window}天 阈值={self.mom_threshold*100}%")
        self.put_event()

    def on_stop(self) -> None:
        """策略停止"""
        self.write_log("策略停止")
        self.put_event()

    def on_tick(self, tick: TickData) -> None:
        """Tick 推送"""
        self.bg.update_tick(tick)

    def on_bar(self, bar: BarData) -> None:
        """K线推送 - 日线级别"""
        self.cancel_all()
        close = bar.close_price

        # 累积收盘价
        self._close_deque.append(close)
        if len(self._close_deque) < self.momentum_window + 1:
            return

        closes = list(self._close_deque)

        # 计算 N 日动量
        self.momentum = (close - closes[-(self.momentum_window + 1)]) / closes[-(self.momentum_window + 1)]

        # ---- 交易逻辑 ----
        if self.pos == 0:
            # 空仓：动量足够强则买入
            if self.momentum >= self.mom_threshold:
                self.buy(close, self.fixed_size)
                self.hold_counter = 0
                self.write_log(
                    f"买入 {self.fixed_size}股@{close:.2f} 动量{self.momentum*100:.1f}%"
                )

        elif self.pos > 0:
            self.hold_counter += 1

            # 持仓到期 或 动量转负 → 卖出
            if self.hold_counter >= self.hold_days or self.momentum <= 0:
                self.sell(close, abs(self.pos))
                self.hold_counter = 0
                reason = "到期" if self.hold_counter >= self.hold_days else "动量转负"
                self.write_log(f"卖出 {abs(self.pos)}股@{close:.2f} ({reason})")

        self.put_event()

    def on_trade(self, trade: TradeData) -> None:
        """成交回报"""
        self.put_event()

    def on_order(self, order: OrderData) -> None:
        """委托回报"""
        pass
