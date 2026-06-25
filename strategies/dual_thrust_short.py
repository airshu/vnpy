"""
Dual Thrust 双轨突破策略（短线经典）

发明者：Michael Chalek (1980s)
原理：前N日最高价/最低价/收盘价计算上下轨，突破即入场。

A股用法（T+1限制）：
- 建议用 ETF 或可转债（T+0品种）
- 或用于日间持仓：尾盘入场，次日离场
- 期货/股指期货效果最佳（T+0，流动性好）

核心参数：
- k1/k2: 上轨/下轨的扩张系数（默认 0.5/0.5）
- window: 计算轨道的回溯天数（默认 4 天）
"""
from collections import deque
import numpy as np

from vnpy_ctastrategy import (
    CtaTemplate,
    TickData,
    BarData,
    TradeData,
    OrderData,
    BarGenerator,
)


class DualThrustShortStrategy(CtaTemplate):
    """Dual Thrust 短线版本

    规则：
    - Range = Max(HH - LC, HC - LL)
    - 上轨 = Open + k1 × Range
    - 下轨 = Open - k2 × Range
    - 价格 > 上轨 → 做多
    - 价格 < 下轨 → 做空（期货）/ 平多离场（股票）
    """
    author = "VeighNa用户"

    window: int = 4             # 计算区间天数
    k1: float = 0.5             # 上轨扩张系数
    k2: float = 0.5             # 下轨扩张系数
    fixed_size: int = 1         # 每次交易手数

    parameters = ["window", "k1", "k2", "fixed_size"]

    upper_bound: float = 0.0    # 上轨
    lower_bound: float = 0.0    # 下轨

    variables = ["upper_bound", "lower_bound"]

    def on_init(self) -> None:
        """初始化"""
        self.write_log("Dual Thrust 短线策略初始化")
        self.bg = BarGenerator(self.on_bar)

        # 缓存 K 线数据（开盘高开低收）
        self._bars: deque[tuple] = deque(maxlen=self.window + 1)
        self.load_bar(self.window + 20)

    def on_start(self) -> None:
        """策略启动"""
        self.write_log("Dual Thrust 策略启动")
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

        # 缓存当前 bar
        self._bars.append((bar.open_price, bar.high_price, bar.low_price, bar.close_price))
        if len(self._bars) < self.window:
            return

        bars_list = list(self._bars)
        close = bar.close_price

        # 计算 Range（不含当日）
        prev_bars = bars_list[:-1]
        hh = max(b[1] for b in prev_bars)  # N日最高
        hc = max(b[3] for b in prev_bars)  # N日最高收盘
        ll = min(b[2] for b in prev_bars)  # N日最低
        lc = min(b[3] for b in prev_bars)  # N日最低收盘

        rng = max(hh - lc, hc - ll)        # Range

        # 上下轨（基于当日开盘价）
        today_open = bar.open_price
        self.upper_bound = today_open + self.k1 * rng
        self.lower_bound = today_open - self.k2 * rng

        # ---- 交易逻辑 ----
        if self.pos == 0:
            if close >= self.upper_bound:
                self.buy(close, self.fixed_size)
            elif close <= self.lower_bound:
                self.short(close, self.fixed_size)

        elif self.pos > 0:
            if close <= self.lower_bound:
                self.sell(close, abs(self.pos))
                self.short(close, self.fixed_size)  # 反手做空

        elif self.pos < 0:
            if close >= self.upper_bound:
                self.cover(close, abs(self.pos))
                self.buy(close, self.fixed_size)    # 反手做多

        self.put_event()

    def on_trade(self, trade: TradeData) -> None:
        """成交回报"""
        self.put_event()

    def on_order(self, order: OrderData) -> None:
        """委托回报"""
        pass
