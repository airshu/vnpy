"""
点金术选股法 · 量化版本

规则（基于：奥特之父 点金术选股法）：

基本面筛选（外部完成）：
- PE < 20
- 股息率 > 3%
- ROE > 10%
- 市值 > 50 亿

技术面交易（本策略）：
- 股价 < MA120 × 88% → 分批买入
- 股价 > MA120 × 112% → 卖出
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


class DianJinValueStrategy(CtaTemplate):
    """点金术选股法 - MA120 均值回归

    适用于：已通过基本面筛选的低估值高股息股票
    """
    author = "VeighNa用户"

    # ---- 策略参数 ----
    ma_window: int = 120          # 均线周期
    buy_threshold: float = 0.88   # 买入阈值 (MA120 × 88%)
    sell_threshold: float = 1.12  # 卖出阈值 (MA120 × 112%)
    fixed_size: int = 100         # 每次交易股数（仅capital_pct=0时生效）
    max_lots: int = 10            # 最大买入批次
    capital_pct: float = 0.10     # 每次买入占总资金比例（0=用fixed_size）

    parameters = [
        "ma_window", "buy_threshold", "sell_threshold",
        "fixed_size", "max_lots", "capital_pct",
    ]

    # ---- 运行时变量 ----
    ma_value: float = 0.0
    buy_line: float = 0.0
    sell_line: float = 0.0
    lot_count: int = 0            # 已买入批次

    variables = ["ma_value", "buy_line", "sell_line", "lot_count"]

    def on_init(self) -> None:
        """策略初始化"""
        self.write_log("点金术策略初始化")

        self.bg = BarGenerator(self.on_bar)

        # 用 deque 保存最近 N 根收盘价
        self._close_window: deque[float] = deque(maxlen=self.ma_window + 1)

        self.load_bar(self.ma_window + 30)

    def on_start(self) -> None:
        """策略启动"""
        self.write_log("点金术策略启动 | MA120 均值回归")
        self.put_event()

    def on_stop(self) -> None:
        """策略停止"""
        self.write_log("策略停止")
        self.put_event()

    def on_tick(self, tick: TickData) -> None:
        """Tick 推送"""
        self.bg.update_tick(tick)

    def on_bar(self, bar: BarData) -> None:
        """K线推送"""
        self.cancel_all()

        close = bar.close_price

        # 累积收盘价
        self._close_window.append(close)
        if len(self._close_window) < self.ma_window:
            return

        # 计算 MA120
        closes = np.array(self._close_window)[-self.ma_window:]
        self.ma_value = float(np.mean(closes))

        self.buy_line = self.ma_value * self.buy_threshold
        self.sell_line = self.ma_value * self.sell_threshold

        # 计算每次交易股数（按资金比例，100股起）
        if self.capital_pct > 0 and close > 0:
            self.fixed_size = max(100, int(500000 * self.capital_pct / close / 100) * 100)

        # ---- 交易逻辑 ----
        if self.pos == 0:
            if close <= self.buy_line:
                self.buy(close, self.fixed_size)
                self.lot_count = 1
                self.write_log(
                    f"买入1 {self.fixed_size}股@{close:.2f} "
                    f"(MA120:{self.ma_value:.2f} 买入线:{self.buy_line:.2f})"
                )

        elif self.pos > 0:
            # 卖出
            if close >= self.sell_line:
                self.sell(close, abs(self.pos))
                self.lot_count = 0
                self.write_log(
                    f"卖出 {abs(self.pos)}股@{close:.2f} "
                    f"(MA120:{self.ma_value:.2f} 卖出线:{self.sell_line:.2f})"
                )
                return

            # 越跌越买：每跌 3%，加仓一次
            if self.lot_count < self.max_lots:
                next_buy = self.buy_line * (1 - 0.03 * self.lot_count)
                if close <= next_buy:
                    self.buy(close, self.fixed_size)
                    self.lot_count += 1
                    self.write_log(
                        f"加仓{self.lot_count} {self.fixed_size}股@{close:.2f}"
                    )

        self.put_event()

    def on_trade(self, trade: TradeData) -> None:
        """成交回报"""
        self.put_event()

    def on_order(self, order: OrderData) -> None:
        """委托回报"""
        pass
