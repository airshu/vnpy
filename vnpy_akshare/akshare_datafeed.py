"""
AKShare datafeed plugin for VeighNa (Sina API edition).

通过新浪接口免费获取 A 股 / 期货 / 指数历史日线数据。
无需 Token、无频率限制。

用法:
    1. pip install akshare
    2. datafeed.name = "akshare" in vt_setting.json
    3. 无需 username / password
"""

import time
import akshare as ak
import pandas as pd
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from datetime import datetime, timedelta, date as date_type
from typing import Optional

from vnpy.trader.setting import SETTINGS
from vnpy.trader.datafeed import BaseDatafeed
from vnpy.trader.object import BarData, HistoryRequest, TickData
from vnpy.trader.constant import Exchange, Interval

# ── Exchange → 新浪市场前缀 ─────────────────────────────────
EXCHANGE_SINA_PREFIX = {
    Exchange.SSE: "sh",  # 上海
    Exchange.SZSE: "sz",  # 深圳
}

# ── 常量 ───────────────────────────────────────────────────
MAX_DAYS = 365 * 5  # 单次最多 5 年
SINA_SYMBOL_FMT = "{prefix}{code}"  # 新浪格式: sh600519


class Datafeed(BaseDatafeed):
    """AKShare + 新浪数据源 (免费, 无需 Token)。"""

    REQUEST_TIMEOUT: int = 60
    MAX_RETRIES: int = 3
    RETRY_BACKOFF: float = 2.0

    def __init__(self) -> None:
        self.inited: bool = True
        self._executor: ThreadPoolExecutor = ThreadPoolExecutor(max_workers=1)

    def init(self, output: Callable = print) -> bool:
        output("AKShare 数据服务已就绪 (新浪数据源，免费无需Token)")
        return True

    # ── 带超时 & 重试 ────────────────────────────────────────

    def _call_with_timeout(self, func, *args, **kwargs) -> pd.DataFrame:
        """线程池超时控制 + 指数退避重试。"""
        output: Callable = kwargs.pop("_output", print)
        last_err: Optional[Exception] = None

        for attempt in range(1, self.MAX_RETRIES + 1):
            future = self._executor.submit(func, *args, **kwargs)
            try:
                return future.result(timeout=self.REQUEST_TIMEOUT)
            except FutureTimeout:
                future.cancel()
                last_err = TimeoutError(f"请求超时 (>{self.REQUEST_TIMEOUT}s), 第{attempt}次")
                output(f"[AKShare] {last_err}")
            except Exception as e:
                last_err = e
                output(f"[AKShare] 请求异常 (第{attempt}次): {e}")

            if attempt < self.MAX_RETRIES:
                wait = self.RETRY_BACKOFF ** attempt
                output(f"[AKShare] {wait:.0f}秒后重试...")
                time.sleep(wait)

        raise RuntimeError(f"请求失败 (已重试{self.MAX_RETRIES}次): {last_err}")

    # ── 主查询入口 ──────────────────────────────────────────

    def query_bar_history(self, req: HistoryRequest, output: Callable = print) -> list[BarData]:
        exchange: Exchange = req.exchange
        symbol: str = req.symbol.upper()
        interval: Interval = req.interval
        start: datetime = req.start
        end: datetime = req.end or datetime.now()

        # 仅支持日线/周线
        if interval not in (Interval.DAILY, Interval.WEEKLY):
            output("AKShare 仅支持日线(d)和周线(w)")
            return []

        # 限制时间跨度
        if (end - start).days > MAX_DAYS:
            output(f"时间跨度超过{MAX_DAYS}天, 自动截断")
            start = end - timedelta(days=MAX_DAYS)

        try:
            if self._is_etf(symbol, exchange):
                bars = self._query_sina_etf(symbol, exchange, interval, start, end, output)
            elif exchange in (
                Exchange.CFFEX, Exchange.SHFE, Exchange.DCE,
                Exchange.CZCE, Exchange.INE, Exchange.GFEX,
            ):
                bars = self._query_sina_futures(symbol, exchange, interval, start, end, output)
            elif exchange in (Exchange.SSE, Exchange.SZSE):
                bars = self._query_sina_stock(symbol, exchange, interval, start, end, output)
            else:
                bars = self._query_sina_stock(symbol, exchange, interval, start, end, output)
        except Exception as e:
            output(f"查询失败: {e}")
            return []

        if not bars:
            output(f"未查到 {symbol}.{exchange.value} 的数据")
        else:
            output(f"成功: {symbol}.{exchange.value} K线 {len(bars)} 条")

        return bars

    def query_tick_history(self, req: HistoryRequest, output: Callable = print) -> list[TickData]:
        output("AKShare 不支持 Tick 数据")
        return []

    # ── 股票 / 指数 (新浪) ──────────────────────────────────

    def _query_sina_stock(
        self, symbol: str, exchange: Exchange,
        interval: Interval, start: datetime, end: datetime,
        output: Callable,
    ) -> list[BarData]:
        """通过新浪 stock_zh_a_daily 获取日线。"""
        prefix = EXCHANGE_SINA_PREFIX.get(exchange, "sh")
        sina_symbol = SINA_SYMBOL_FMT.format(prefix=prefix, code=symbol.lower())

        start_date = start.strftime("%Y%m%d")
        end_date = end.strftime("%Y%m%d")

        output(f"新浪获取 {sina_symbol} {interval.value} ({start_date}~{end_date})...")

        df: pd.DataFrame = self._call_with_timeout(
            ak.stock_zh_a_daily,
            symbol=sina_symbol,
            start_date=start_date,
            end_date=end_date,
            adjust="qfq",
            _output=output,
        )

        # 新浪 API 返回英文列: date, open, high, low, close, volume, amount
        return self._df_to_bars_sina(df, symbol, exchange, interval)

    # ── ETF (新浪) ───────────────────────────────────────────

    @staticmethod
    def _is_etf(symbol: str, exchange: Exchange) -> bool:
        """判断是否为 ETF 代码（上交所 5 开头 / 深交所 15-16 开头）。"""
        if exchange == Exchange.SSE and symbol.startswith("5"):
            return True
        if exchange == Exchange.SZSE and len(symbol) >= 2 and symbol[:2] in ("15", "16"):
            return True
        return False

    def _query_sina_etf(
        self, symbol: str, exchange: Exchange,
        interval: Interval, start: datetime, end: datetime,
        output: Callable,
    ) -> list[BarData]:
        """通过新浪 fund_etf_hist_sina 获取 ETF 日线。"""
        prefix = EXCHANGE_SINA_PREFIX.get(exchange, "sh")
        sina_symbol = f"{prefix}{symbol.lower()}"

        output(f"新浪ETF {sina_symbol} {interval.value}...")

        df: pd.DataFrame = self._call_with_timeout(
            ak.fund_etf_hist_sina,
            symbol=sina_symbol,
            _output=output,
        )

        # 按时间范围过滤
        df["date"] = pd.to_datetime(df["date"])
        df = df[
            (df["date"] >= pd.Timestamp(start.replace(tzinfo=None)))
            & (df["date"] <= pd.Timestamp(end.replace(tzinfo=None)))
        ]

        return self._df_to_bars_sina(df, symbol, exchange, interval)

    # ── 期货 (新浪) ─────────────────────────────────────────

    # 新浪主力连续合约映射: vnpy 888 → sina 0
    # 例: I888.DCE → I0, RB888.SHFE → RB0
    _CONTINUOUS_SUFFIX = "888"

    def _query_sina_futures(
        self, symbol: str, exchange: Exchange,
        interval: Interval, start: datetime, end: datetime,
        output: Callable,
    ) -> list[BarData]:
        """通过新浪 futures 接口获取期货日线。支持主力连续合约。"""
        # 主力连续合约: RB888 → RB0 (新浪约定)
        if symbol.endswith(self._CONTINUOUS_SUFFIX):
            base = symbol[:-len(self._CONTINUOUS_SUFFIX)]
            sina_symbol = f"{base}0"
            func = ak.futures_main_sina
        else:
            sina_symbol = symbol
            func = ak.futures_zh_daily_sina

        output(f"新浪期货 {symbol} ({sina_symbol}) {interval.value}...")

        df: pd.DataFrame = self._call_with_timeout(
            func,
            symbol=sina_symbol,
            _output=output,
        )

        # 标准化列名 (新浪期货返回中文列)
        rename_map = {
            "日期": "date", "开盘价": "open", "最高价": "high",
            "最低价": "low", "收盘价": "close", "成交量": "volume",
            "成交额": "amount", "持仓量": "hold",
        }
        # 只重命名存在的列
        rename_map = {k: v for k, v in rename_map.items() if k in df.columns}
        df = df.rename(columns=rename_map)

        # 日期过滤 (strip tz: 新浪数据无时区, start/end 来自 DB_TZ)
        df["date"] = pd.to_datetime(df["date"])
        df = df[
            (df["date"] >= pd.Timestamp(start.replace(tzinfo=None)))
            & (df["date"] <= pd.Timestamp(end.replace(tzinfo=None)))
        ]

        return self._df_to_bars_sina(df, symbol, exchange, interval)

    # ── DataFrame → BarData ─────────────────────────────────

    def _df_to_bars_sina(
        self, df: pd.DataFrame, symbol: str,
        exchange: Exchange, interval: Interval,
    ) -> list[BarData]:
        """新浪 API DataFrame → BarData 列表。"""
        bars: list[BarData] = []

        for _, row in df.iterrows():
            # 日期转换
            date_val = row.get("date")
            if date_val is None:
                continue
            if isinstance(date_val, str):
                dt = datetime.strptime(date_val, "%Y-%m-%d")
            elif isinstance(date_val, date_type):
                dt = datetime.combine(date_val, datetime.min.time())
            else:
                dt = date_val.to_pydatetime()

            bar = BarData(
                symbol=symbol,
                exchange=exchange,
                datetime=dt,
                interval=interval,
                volume=float(row.get("volume") or 0),
                turnover=float(row.get("amount") or row.get("成交额") or 0),
                open_interest=float(row.get("hold") or row.get("持仓量") or 0),
                open_price=float(row.get("open") or row.get("开盘价") or 0),
                high_price=float(row.get("high") or row.get("最高价") or 0),
                low_price=float(row.get("low") or row.get("最低价") or 0),
                close_price=float(row.get("close") or row.get("收盘价") or 0),
                gateway_name="SINA",
            )
            bars.append(bar)

        return bars
