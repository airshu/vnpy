from vnpy_ctastrategy import (
    CtaTemplate,
    TickData,
    BarData,
    TradeData,
    OrderData,
    BarGenerator,
    ArrayManager,
)


class TurtleTradingStrategy(CtaTemplate):
    """海龟交易策略（完整生产版）

    原版海龟交易法则核心规则：

    1. 双系统独立运行
       - 系统1（短线）：20 日突破进场 / 10 日跌破离场 → 占 50% 资金
       - 系统2（长线）：55 日突破进场 / 20 日跌破离场 → 占 50% 资金
       - 两套系统各自计算仓位、止损、加仓、过滤器

    2. 波动率标准化仓位
       - 1N = ATR(20) × 每点价值
       - 每单位 = 系统资金 × 1% / 1N
       - 单系统最多 4 单位，合计最多 8 单位

    3. 金字塔加仓
       - 持仓后价格朝有利方向每走 0.5 ATR 加 1 单位

    4. 止损（每系统独立）
       - 进场/加仓后止损 = 最新成交价 ∓ 2 × ATR

    5. 过滤器（仅系统1）
       - 上一笔信号亏损 → 跳过下一次同方向信号

    参考：柯蒂斯·费思《海龟交易法则》
    """
    author = "VeighNa用户"

    # ======================== 策略参数 ========================
    capital: int = 500000           # 账户总资金（元）
    per_point_value: int = 10       # 合约每点价值（螺纹钢=10，股指=300）
    entry_window: int = 20          # 系统1进场窗口（系统2自动 +35）
    exit_window: int = 10           # 系统1离场窗口（系统2自动 +10）
    atr_window: int = 20            # ATR 计算窗口
    atr_stop: float = 2.0           # ATR 止损倍数
    max_units: int = 4              # 单系统最大加仓次数

    parameters = [
        "capital", "per_point_value",
        "entry_window", "exit_window", "atr_window",
        "atr_stop", "max_units",
    ]

    # ======================== 运行时变量 ========================
    atr_value: float = 0.0              # 当前 ATR

    # 系统1 状态
    sys1_units: int = 0                 # 持仓单位数（正=多，负=空）
    sys1_entry: float = 0.0             # 进场/最近加仓价
    sys1_stop: float = 0.0              # 当前止损价
    sys1_lost: bool = False             # 过滤器：上笔是否亏损

    # 系统2 状态
    sys2_units: int = 0
    sys2_entry: float = 0.0
    sys2_stop: float = 0.0

    variables = [
        "atr_value",
        "sys1_units", "sys1_entry", "sys1_stop", "sys1_lost",
        "sys2_units", "sys2_entry", "sys2_stop",
    ]

    def on_init(self) -> None:
        """策略初始化"""
        self.write_log("海龟策略初始化")

        self.bg: BarGenerator = BarGenerator(self.on_bar)
        self.am: ArrayManager = ArrayManager()

        # 单位手数缓存
        self._sys1_size: int = 1
        self._sys2_size: int = 1
        self._bar_count: int = 0
        self._total_bars: int = 0

        self.load_bar(max(self.entry_window + 35, self.atr_window) + 10)

    def on_start(self) -> None:
        """策略启动"""
        self._bar_count: int = 0
        # _total_bars 由外部回测脚本注入，不要在此重置
        self.write_log(
            f"策略启动 | 资金={self.capital} | 每点={self.per_point_value}元"
        )
        self.put_event()

    def on_stop(self) -> None:
        """策略停止"""
        self.write_log("策略停止")
        self.put_event()

    def on_tick(self, tick: TickData) -> None:
        """Tick → 合成 K 线"""
        self.bg.update_tick(tick)

    # ======================== 核心逻辑 ========================

    def on_bar(self, bar: BarData) -> None:
        """每根 K 线调一次"""
        self._bar_count += 1
        self.cancel_all()

        am: ArrayManager = self.am
        am.update_bar(bar)
        if not am.inited:
            return

        # ---- 计算指标 ----
        self.atr_value = am.atr(self.atr_window)
        self._calc_unit_sizes()                     # 更新单位手数

        sys1_e_up, sys1_e_dn = am.donchian(self.entry_window)
        sys1_x_up, sys1_x_dn = am.donchian(self.exit_window)

        sys2_e_up, sys2_e_dn = am.donchian(self.entry_window + 35)
        sys2_x_up, sys2_x_dn = am.donchian(self.exit_window + 10)

        close: float = bar.close_price

        # ---- 处理系统1 ----
        self._handle_sys1(close, sys1_e_up, sys1_e_dn, sys1_x_up, sys1_x_dn)

        # ---- 处理系统2 ----
        self._handle_sys2(close, sys2_e_up, sys2_e_dn, sys2_x_up, sys2_x_dn)

        # ---- 自动平仓：回测最后一根 K 线时平掉所有持仓 ----
        if self._total_bars > 0 and self._bar_count >= self._total_bars:
            if self.sys2_units != 0:
                self._sys2_close(close)
            if self.sys1_units != 0:
                self._sys1_close(close)

        self.put_event()

    # ======================== 系统1 ========================

    def _handle_sys1(
        self,
        close: float,
        entry_up: float, entry_dn: float,
        exit_up: float, exit_dn: float,
    ) -> None:
        """系统1 进场/加仓/离场"""
        u = self.sys1_units

        # --- 无仓位：看进场 ---
        if u == 0:
            if not self.sys1_lost:
                if close >= entry_up:
                    self._sys1_open(1, close)
                elif close <= entry_dn:
                    self._sys1_open(-1, close)

        # --- 持多仓 ---
        elif u > 0:
            # 止损检查
            new_stop = close - self.atr_stop * self.atr_value
            if new_stop > self.sys1_stop:
                self.sys1_stop = new_stop
            if close <= self.sys1_stop:
                self._sys1_close(close)
                return

            # 离场
            if close <= exit_dn:
                self._sys1_close(close)
                return

            # 加仓
            if u < self.max_units:
                add_p = self.sys1_entry + 0.5 * self.atr_value * u
                if close >= add_p:
                    self._sys1_add(close)

        # --- 持空仓 ---
        elif u < 0:
            new_stop = close + self.atr_stop * self.atr_value
            if new_stop < self.sys1_stop or self.sys1_stop == 0:
                self.sys1_stop = new_stop
            if close >= self.sys1_stop:
                self._sys1_close(close)
                return

            if close >= exit_up:
                self._sys1_close(close)
                return

            if abs(u) < self.max_units:
                add_p = self.sys1_entry - 0.5 * self.atr_value * abs(u)
                if close <= add_p:
                    self._sys1_add(close)

    # ======================== 系统2 ========================

    def _handle_sys2(
        self,
        close: float,
        entry_up: float, entry_dn: float,
        exit_up: float, exit_dn: float,
    ) -> None:
        """系统2 进场/加仓/离场（无过滤器）"""
        u = self.sys2_units

        if u == 0:
            if close >= entry_up:
                self._sys2_open(1, close)
            elif close <= entry_dn:
                self._sys2_open(-1, close)

        elif u > 0:
            new_stop = close - self.atr_stop * self.atr_value
            if new_stop > self.sys2_stop:
                self.sys2_stop = new_stop
            if close <= self.sys2_stop:
                self._sys2_close(close)
                return

            if close <= exit_dn:
                self._sys2_close(close)
                return

            if u < self.max_units:
                add_p = self.sys2_entry + 0.5 * self.atr_value * u
                if close >= add_p:
                    self._sys2_add(close)

        elif u < 0:
            new_stop = close + self.atr_stop * self.atr_value
            if new_stop < self.sys2_stop or self.sys2_stop == 0:
                self.sys2_stop = new_stop
            if close >= self.sys2_stop:
                self._sys2_close(close)
                return

            if close >= exit_up:
                self._sys2_close(close)
                return

            if abs(u) < self.max_units:
                add_p = self.sys2_entry - 0.5 * self.atr_value * abs(u)
                if close <= add_p:
                    self._sys2_add(close)

    # ======================== 仓位计算 ========================

    def _calc_unit_sizes(self) -> None:
        """根据波动率计算每单位手数（每天更新）

        1N = ATR × 每点价值
        1 单位 = 系统资金 × 1% / 1N
        系统1、系统2 各分一半资金
        """
        if self.atr_value <= 0:
            return

        n_value: float = self.atr_value * self.per_point_value   # 1N

        sys_cap: float = self.capital * 0.5                       # 系统资金
        risk: float = sys_cap * 0.01                              # 每次 1% 风险

        self._sys1_size = max(1, int(risk / n_value))
        self._sys2_size = max(1, int(risk / n_value))

    # ======================== 系统1 操作 ========================

    def _sys1_open(self, direction: int, price: float) -> None:
        """系统1 开仓（direction: 1=多, -1=空）"""
        size: int = self._sys1_size
        self.sys1_entry = price
        self.sys1_units = direction

        if direction == 1:
            self.buy(price, size)
            self.sys1_stop = price - self.atr_stop * self.atr_value
            self.write_log(f"[SYS1] 开多 {size}手@{price:.2f} 止损@{self.sys1_stop:.2f}")
        else:
            self.short(price, size)
            self.sys1_stop = price + self.atr_stop * self.atr_value
            self.write_log(f"[SYS1] 开空 {size}手@{price:.2f} 止损@{self.sys1_stop:.2f}")

        self.put_event()

    def _sys1_add(self, price: float) -> None:
        """系统1 加仓"""
        size: int = self._sys1_size
        self.sys1_entry = price

        if self.sys1_units > 0:
            self.buy(price, size)
            self.sys1_units += 1
            self.sys1_stop = price - self.atr_stop * self.atr_value
            self.write_log(f"[SYS1] 加多 {size}手@{price:.2f} 共{self.sys1_units}单位 止损@{self.sys1_stop:.2f}")
        else:
            self.short(price, size)
            self.sys1_units -= 1
            self.sys1_stop = price + self.atr_stop * self.atr_value
            self.write_log(f"[SYS1] 加空 {size}手@{price:.2f} 共{abs(self.sys1_units)}单位 止损@{self.sys1_stop:.2f}")

        self.put_event()

    def _sys1_close(self, price: float) -> None:
        """系统1 全平"""
        units: int = abs(self.sys1_units)
        size: int = units * self._sys1_size

        if self.sys1_units > 0:
            self.sell(price, size)
            self.sys1_lost = price < self.sys1_entry  # 更新过滤器
        else:
            self.cover(price, size)
            self.sys1_lost = price > self.sys1_entry

        self.write_log(
            f"[SYS1] 平仓 {size}手@{price:.2f} "
            f"({'亏损' if self.sys1_lost else '盈利'})"
        )

        self.sys1_units = 0
        self.sys1_entry = 0.0
        self.sys1_stop = 0.0
        self.put_event()

    # ======================== 系统2 操作 ========================

    def _sys2_open(self, direction: int, price: float) -> None:
        """系统2 开仓"""
        size: int = self._sys2_size
        self.sys2_entry = price
        self.sys2_units = direction

        if direction == 1:
            self.buy(price, size)
            self.sys2_stop = price - self.atr_stop * self.atr_value
            self.write_log(f"[SYS2] 开多 {size}手@{price:.2f} 止损@{self.sys2_stop:.2f}")
        else:
            self.short(price, size)
            self.sys2_stop = price + self.atr_stop * self.atr_value
            self.write_log(f"[SYS2] 开空 {size}手@{price:.2f} 止损@{self.sys2_stop:.2f}")

        self.put_event()

    def _sys2_add(self, price: float) -> None:
        """系统2 加仓"""
        size: int = self._sys2_size
        self.sys2_entry = price

        if self.sys2_units > 0:
            self.buy(price, size)
            self.sys2_units += 1
            self.sys2_stop = price - self.atr_stop * self.atr_value
            self.write_log(f"[SYS2] 加多 {size}手@{price:.2f} 共{self.sys2_units}单位 止损@{self.sys2_stop:.2f}")
        else:
            self.short(price, size)
            self.sys2_units -= 1
            self.sys2_stop = price + self.atr_stop * self.atr_value
            self.write_log(f"[SYS2] 加空 {size}手@{price:.2f} 共{abs(self.sys2_units)}单位 止损@{self.sys2_stop:.2f}")

        self.put_event()

    def _sys2_close(self, price: float) -> None:
        """系统2 全平"""
        units: int = abs(self.sys2_units)
        size: int = units * self._sys2_size

        if self.sys2_units > 0:
            self.sell(price, size)
        else:
            self.cover(price, size)

        self.write_log(f"[SYS2] 平仓 {size}手@{price:.2f}")

        self.sys2_units = 0
        self.sys2_entry = 0.0
        self.sys2_stop = 0.0
        self.put_event()

    # ======================== 回调 ========================

    def on_trade(self, trade: TradeData) -> None:
        """成交回报"""
        self.put_event()

    def on_order(self, order: OrderData) -> None:
        """委托回报"""
        pass
