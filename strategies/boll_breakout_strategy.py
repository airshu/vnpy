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


class BollBreakoutStrategy(CtaTemplate):
    """布林带突破策略

    核心逻辑：
    - 价格突破上轨 → 做多
    - 价格突破下轨 → 做空
    - 价格回归中轨 → 平仓

    适合趋势明显的品种，震荡市中会产生较多假突破。
    """
    author = "VeighNa用户"

    # ---- 策略参数（可在 GUI 中编辑）----
    boll_window: int = 20        # 布林带计算窗口
    boll_dev: float = 2.0        # 标准差倍数
    fixed_size: int = 1          # 固定开仓手数

    # ---- 运行时变量（GUI 中显示、自动持久化）----
    boll_mid: float = 0.0        # 布林带中轨
    boll_upper: float = 0.0      # 布林带上轨
    boll_lower: float = 0.0      # 布林带下轨

    parameters = ["boll_window", "boll_dev", "fixed_size"]
    variables = ["boll_mid", "boll_upper", "boll_lower"]

    def on_init(self) -> None:
        """策略初始化"""
        self.write_log("策略初始化")

        # 工具：K 线生成器 + 数组管理器
        self.bg: BarGenerator = BarGenerator(self.on_bar)
        self.am: ArrayManager = ArrayManager()

        # 加载 30 天历史数据，确保布林带指标计算有足够数据
        self.load_bar(30)

    def on_start(self) -> None:
        """策略启动"""
        self.write_log("策略启动")
        self.put_event()

    def on_stop(self) -> None:
        """策略停止"""
        self.write_log("策略停止")
        self.put_event()

    def on_tick(self, tick: TickData) -> None:
        """Tick 推送 → 合成为 K 线"""
        self.bg.update_tick(tick)

    def on_bar(self, bar: BarData) -> None:
        """K 线推送 → 交易逻辑"""
        # 每次新 K 线先撤销未成交委托
        self.cancel_all()

        am: ArrayManager = self.am
        am.update_bar(bar)
        if not am.inited:
            return

        # ---- 1. 计算布林带 ----
        self.boll_mid = am.sma(self.boll_window, array=True)[-1]
        boll_std: float = am.std(self.boll_window, array=True)[-1]
        self.boll_upper = self.boll_mid + self.boll_dev * boll_std
        self.boll_lower = self.boll_mid - self.boll_dev * boll_std

        close: float = bar.close_price

        # ---- 2. 信号判断 ----
        # 向上突破上轨 → 做多
        long_signal: bool = close > self.boll_upper
        # 向下突破下轨 → 做空
        short_signal: bool = close < self.boll_lower
        # 回归中轨 → 平仓
        exit_signal: bool = (
            (self.pos > 0 and close < self.boll_mid) or
            (self.pos < 0 and close > self.boll_mid)
        )

        # ---- 3. 执行交易 ----
        if exit_signal:
            if self.pos > 0:
                self.sell(bar.close_price, abs(self.pos))
            elif self.pos < 0:
                self.cover(bar.close_price, abs(self.pos))

        elif long_signal:
            if self.pos == 0:
                self.buy(bar.close_price, self.fixed_size)
            elif self.pos < 0:
                # 先平空再开多
                self.cover(bar.close_price, abs(self.pos))
                self.buy(bar.close_price, self.fixed_size)

        elif short_signal:
            if self.pos == 0:
                self.short(bar.close_price, self.fixed_size)
            elif self.pos > 0:
                # 先平多再开空
                self.sell(bar.close_price, abs(self.pos))
                self.short(bar.close_price, self.fixed_size)

        # 刷新 GUI 显示
        self.put_event()

    def on_order(self, order: OrderData) -> None:
        """委托回报"""
        pass

    def on_trade(self, trade: TradeData) -> None:
        """成交回报"""
        self.put_event()

    def on_stop_order(self, stop_order: StopOrder) -> None:
        """停止单回报"""
        pass
