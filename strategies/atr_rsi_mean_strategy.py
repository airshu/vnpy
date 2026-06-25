"""
ATR + RSI 震荡策略（短线均值回归）

核心逻辑：
- RSI < oversold 且价格触及 ATR 下轨 → 买入
- RSI > overbought 且价格触及 ATR 上轨 → 卖出
- ATR 动态止损

与海龟互补：海龟做趋势的钱，ATR-RSI 做震荡的钱
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


class AtrRsiMeanStrategy(CtaTemplate):
    """ATR + RSI 震荡策略

    震荡市（价格来回波动）专杀：
    - 价格跌到 ATR 下轨 + RSI 超卖 → 抄底买入
    - 价格涨到 ATR 上轨 + RSI 超买 → 止盈卖出
    - ATR 动态止损：持仓后持续更新止损价

    配合海龟趋势策略：海龟在趋势市赚钱但震荡市磨损，
    本策略在震荡市低吸高抛，两者互补。
    """
    author = "VeighNa用户"

    # ---- 参数 ----
    rsi_window: int = 14         # RSI 计算窗口
    rsi_oversold: int = 30       # RSI 超卖阈值
    rsi_overbought: int = 70     # RSI 超买阈值
    atr_window: int = 20         # ATR 窗口
    atr_mult: float = 2.0        # ATR 通道倍数
    atr_stop: float = 2.0        # 止损 ATR 倍数
    fixed_size: int = 1          # 每次交易手数

    parameters = [
        "rsi_window", "rsi_oversold", "rsi_overbought",
        "atr_window", "atr_mult", "atr_stop", "fixed_size",
    ]

    # ---- 变量 ----
    rsi_value: float = 50.0
    atr_value: float = 0.0
    atr_upper: float = 0.0
    atr_lower: float = 0.0
    stop_price: float = 0.0

    variables = [
        "rsi_value", "atr_value", "atr_upper", "atr_lower", "stop_price",
    ]

    def on_init(self) -> None:
        """初始化"""
        self.write_log("ATR-RSI 震荡策略初始化")

        self.bg = BarGenerator(self.on_bar)

        # 用 deque 存储价格数据
        max_window = max(self.rsi_window, self.atr_window) + 5
        self._highs: deque[float] = deque(maxlen=max_window)
        self._lows: deque[float] = deque(maxlen=max_window)
        self._closes: deque[float] = deque(maxlen=max_window)

        self.load_bar(max_window + 10)

    def on_start(self) -> None:
        """启动"""
        self.write_log("ATR-RSI 策略启动")
        self.put_event()

    def on_stop(self) -> None:
        """停止"""
        self.write_log("策略停止")
        self.put_event()

    def on_tick(self, tick: TickData) -> None:
        """Tick"""
        self.bg.update_tick(tick)

    def on_bar(self, bar: BarData) -> None:
        """K线"""
        self.cancel_all()

        # 累积数据
        self._highs.append(bar.high_price)
        self._lows.append(bar.low_price)
        self._closes.append(bar.close_price)

        close = bar.close_price
        if len(self._closes) < max(self.rsi_window, self.atr_window) + 1:
            return

        # ---- 计算 RSI ----
        closes = list(self._closes)
        gains = []
        losses = []
        for i in range(1, len(closes)):
            diff = closes[i] - closes[i-1]
            if diff > 0:
                gains.append(diff)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(-diff)

        avg_gain = np.mean(gains[-self.rsi_window:])
        avg_loss = np.mean(losses[-self.rsi_window:])
        if avg_loss == 0:
            self.rsi_value = 100.0
        else:
            rs = avg_gain / avg_loss
            self.rsi_value = 100.0 - (100.0 / (1.0 + rs))

        # ---- 计算 ATR ----
        highs = list(self._highs)
        lows = list(self._lows)
        true_ranges = []
        for i in range(1, len(closes)):
            h, l, pc = highs[i], lows[i], closes[i-1]
            tr = max(h - l, abs(h - pc), abs(l - pc))
            true_ranges.append(tr)
        self.atr_value = float(np.mean(true_ranges[-self.atr_window:]))

        # ATR 通道（基于收盘价的滚动均值）
        sma_close = float(np.mean(closes[-self.atr_window:]))
        self.atr_upper = sma_close + self.atr_mult * self.atr_value
        self.atr_lower = sma_close - self.atr_mult * self.atr_value

        # ---- 交易逻辑 ----
        if self.pos == 0:
            # 超卖 + 触及下轨 → 买入
            if self.rsi_value < self.rsi_oversold and close <= self.atr_lower:
                self.buy(close, self.fixed_size)
                self.stop_price = close - self.atr_stop * self.atr_value
                self.write_log(
                    f"买入@{close:.2f} RSI={self.rsi_value:.0f} "
                    f"下轨={self.atr_lower:.2f} 止损={self.stop_price:.2f}"
                )

        elif self.pos > 0:
            # 更新止损（只上移）
            new_stop = close - self.atr_stop * self.atr_value
            if new_stop > self.stop_price:
                self.stop_price = new_stop

            # 止损触发
            if close <= self.stop_price:
                self.sell(close, abs(self.pos))
                self.stop_price = 0.0
                self.write_log(f"止损@{close:.2f}")
                return

            # 止盈：超买 + 触及上轨
            if self.rsi_value > self.rsi_overbought and close >= self.atr_upper:
                self.sell(close, abs(self.pos))
                self.stop_price = 0.0
                self.write_log(
                    f"止盈@{close:.2f} RSI={self.rsi_value:.0f} "
                    f"上轨={self.atr_upper:.2f}"
                )

        self.put_event()

    def on_trade(self, trade: TradeData) -> None:
        """成交"""
        self.put_event()

    def on_order(self, order: OrderData) -> None:
        """委托"""
        pass
