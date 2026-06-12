"""
AKShare datafeed plugin for VeighNa.

Provides historical bar data for Chinese stocks, futures, and indices
via the free AKShare library.

Usage:
    1. pip install akshare
    2. Set datafeed.name = "akshare" in vt_setting.json
    3. No username/password required
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
from vnpy.trader.utility import round_to

# ── Exchange → AKShare symbol mapping ────────────────────────────
# Map vnpy Exchange enum to AKShare market prefix
EXCHANGE_TO_AK = {
    Exchange.SSE: "sh",       # 上海证券交易所
    Exchange.SZSE: "sz",      # 深圳证券交易所
    Exchange.CFFEX: "cffex",  # 中国金融期货交易所
    Exchange.SHFE: "shfe",    # 上海期货交易所
    Exchange.DCE: "dce",      # 大连商品交易所
    Exchange.CZCE: "czce",    # 郑州商品交易所
    Exchange.INE: "ine",      # 上海国际能源交易中心
    Exchange.GFEX: "gfex",    # 广州期货交易所
}

# Interval → AKShare period string
INTERVAL_TO_AK = {
    Interval.MINUTE: "1",     # 1分钟K线
    Interval.HOUR: "60",      # 1小时K线
    Interval.DAILY: "daily",  # 日K线
    Interval.WEEKLY: "weekly", # 周K线
    # Tick is not supported by AKShare historical API
}

# ── 时间范围限制（避免一次下载过多数据）────────────────────────
MAX_DAYS_PER_REQUEST = 365 * 5  # 单次最多5年


class Datafeed(BaseDatafeed):
    """AKShare datafeed implementation for VeighNa."""

    # ── 超时 & 重试配置 ────────────────────────────────────────
    REQUEST_TIMEOUT: int = 45         # 单次请求最长等待秒数
    MAX_RETRIES: int = 3              # 最多重试次数
    RETRY_BACKOFF: float = 2.0        # 重试退避倍数（指数增长）

    def __init__(self) -> None:
        self.inited: bool = True                                   # 无需认证
        self._executor: ThreadPoolExecutor = ThreadPoolExecutor(max_workers=1)

    # ── 带超时的请求包装器 ─────────────────────────────────────

    def _call_with_timeout(self, func, *args, **kwargs) -> pd.DataFrame:
        """
        Execute an AKShare API call with timeout and retry.

        AKShare底层调用东方财富API，网络不稳定时可能挂起无响应。
        这里用线程池实现超时控制，并在失败后指数退避重试。
        """
        output: Callable = kwargs.pop("_output", print)
        last_err: Optional[Exception] = None

        for attempt in range(1, self.MAX_RETRIES + 1):
            future = self._executor.submit(func, *args, **kwargs)
            try:
                df: pd.DataFrame = future.result(timeout=self.REQUEST_TIMEOUT)
                return df  # 成功
            except FutureTimeout:
                future.cancel()
                last_err = TimeoutError(
                    f"请求超时（>{self.REQUEST_TIMEOUT}s），第{attempt}次尝试失败"
                )
                output(f"[AKShare] {last_err}")
            except Exception as e:
                last_err = e
                output(f"[AKShare] 请求异常（第{attempt}次）: {e}")

            if attempt < self.MAX_RETRIES:
                wait = self.RETRY_BACKOFF ** attempt
                output(f"[AKShare] {wait:.0f}秒后重试...")
                time.sleep(wait)

        raise RuntimeError(
            f"AKShare请求失败（已重试{self.MAX_RETRIES}次）: {last_err}"
        )

    def init(self, output: Callable = print) -> bool:
        """Initialize AKShare datafeed (no auth required)."""
        output("AKShare 数据服务已就绪（免费开源，无需Token）")
        return True

    # ── 主查询接口 ──────────────────────────────────────────────

    def query_bar_history(self, req: HistoryRequest, output: Callable = print) -> list[BarData]:
        """
        Query historical K-line bar data from AKShare.

        Supported:
          - 股票（上证/深证）日线/周线
          - 指数（上证指数/深证成指）日线
          - 期货主力连续合约日线

        Parameters:
            req: HistoryRequest with symbol, exchange, interval, start, end.
            output: Logging callback.

        Returns:
            List of BarData objects.
        """
        exchange: Exchange = req.exchange
        symbol: str = req.symbol.upper()
        interval: Interval = req.interval
        start: datetime = req.start
        end: datetime = req.end or datetime.now()

        # Limit date range to avoid huge downloads
        if (end - start).days > MAX_DAYS_PER_REQUEST:
            output(
                f"查询时间跨度超过{MAX_DAYS_PER_REQUEST * 5}天，自动截断至最近{MAX_DAYS_PER_REQUEST * 5}天"
            )
            start = end - timedelta(days=MAX_DAYS_PER_REQUEST * 5)

        try:
            if exchange in (Exchange.SSE, Exchange.SZSE):
                bars = self._query_stock_bars(symbol, exchange, interval, start, end, output)
            elif exchange in (
                Exchange.CFFEX, Exchange.SHFE, Exchange.DCE,
                Exchange.CZCE, Exchange.INE, Exchange.GFEX,
            ):
                bars = self._query_futures_bars(symbol, exchange, interval, start, end, output)
            else:
                bars = self._query_stock_bars(symbol, exchange, interval, start, end, output)
        except Exception as e:
            output(f"AKShare查询K线数据失败：{e}")
            return []

        if not bars:
            output(f"未查询到 {symbol}.{exchange.value} 的K线数据，请检查品种代码是否正确")
        else:
            output(f"成功获取 {symbol}.{exchange.value} K线数据，共 {len(bars)} 条")

        return bars

    def query_tick_history(self, req: HistoryRequest, output: Callable = print) -> list[TickData]:
        """
        AKShare does not provide historical tick data.
        """
        output("AKShare 暂不支持历史Tick数据查询")
        return []

    # ── 股票K线 ─────────────────────────────────────────────────

    def _query_stock_bars(
        self,
        symbol: str,
        exchange: Exchange,
        interval: Interval,
        start: datetime,
        end: datetime,
        output: Callable,
    ) -> list[BarData]:
        """Query stock daily/weekly bars via AKShare."""

        period: str = INTERVAL_TO_AK.get(interval, "daily")
        if interval not in (Interval.DAILY, Interval.WEEKLY):
            output("AKShare 股票数据仅支持日线(d)和周线(w)，其他周期请升级tushare积分")
            return []

        # AKShare expects date strings like "20240101"
        start_date: str = start.strftime("%Y%m%d")
        end_date: str = end.strftime("%Y%m%d")

        output(f"正在从AKShare获取 {symbol} 的{period}K线数据 ({start_date} ~ {end_date})...")

        try:
            df: pd.DataFrame = self._call_with_timeout(
                ak.stock_zh_a_hist,
                symbol=symbol,
                period=period,
                start_date=start_date,
                end_date=end_date,
                adjust="qfq",
                _output=output,
            )
        except Exception as e1:
            # Fallback: try as index (e.g. 上证指数sh000001, 深证成指sz399001)
            try:
                market: str = EXCHANGE_TO_AK.get(exchange, "sh")
                index_code: str = f"{market}{symbol}"
                output(f"股票API失败({e1})，尝试按指数查询 {index_code}...")
                df = self._call_with_timeout(
                    ak.stock_zh_index_daily,
                    symbol=index_code,
                    _output=output,
                )
                df["date"] = pd.to_datetime(df["date"])
                df = df[
                    (df["date"] >= pd.Timestamp(start))
                    & (df["date"] <= pd.Timestamp(end))
                ]
            except Exception as e2:
                raise RuntimeError(f"无法获取 {symbol} 的数据: {e2}")

        return self._df_to_bars(df, symbol, exchange, interval)

    # ── 期货K线 ─────────────────────────────────────────────────

    def _query_futures_bars(
        self,
        symbol: str,
        exchange: Exchange,
        interval: Interval,
        start: datetime,
        end: datetime,
        output: Callable,
    ) -> list[BarData]:
        """Query futures daily bars via AKShare."""

        if interval not in (Interval.DAILY, Interval.WEEKLY):
            output("AKShare 期货数据目前主要支持日线(d)")
            return []

        output(f"正在从AKShare获取期货 {symbol} 的{interval.value}K线数据...")

        try:
            # Try futures daily API (contract code, e.g. "RB2505")
            # First try specific contract
            try:
                df: pd.DataFrame = ak.futures_zh_daily_sina(symbol=symbol)
            except Exception:
                # Fallback: try main continuous contract
                df = ak.futures_main_sina(symbol=symbol)

            # Standardize column names
            df = df.rename(columns={
                "日期": "date",
                "开盘价": "open",
                "最高价": "high",
                "最低价": "low",
                "收盘价": "close",
                "成交量": "volume",
                "成交额": "amount",
                "持仓量": "hold",
                "涨跌幅": "pct_chg",
            })

            # Filter date range
            df["date"] = pd.to_datetime(df["date"])
            df = df[
                (df["date"] >= pd.Timestamp(start))
                & (df["date"] <= pd.Timestamp(end))
            ]

            return self._df_to_bars(df, symbol, exchange, interval)

        except Exception as e:
            raise RuntimeError(f"期货数据获取失败 {symbol}: {e}")

    # ── DataFrame → BarData ─────────────────────────────────────

    def _df_to_bars(
        self,
        df: pd.DataFrame,
        symbol: str,
        exchange: Exchange,
        interval: Interval,
    ) -> list[BarData]:
        """Convert AKShare DataFrame to VeighNa BarData list."""

        bars: list[BarData] = []

        for _, row in df.iterrows():
            # Handle date column
            date_val = row.get("日期") or row.get("date")
            if date_val is None:
                continue

            if isinstance(date_val, str):
                dt = datetime.strptime(date_val, "%Y-%m-%d")
            elif isinstance(date_val, date_type):
                dt = datetime.combine(date_val, datetime.min.time())
            else:
                dt = date_val.to_pydatetime()

            # Normalize field names (AKShare may return Chinese or English columns)
            open_price: float = float(row.get("开盘") or row.get("open") or 0)
            high_price: float = float(row.get("最高") or row.get("high") or 0)
            low_price: float = float(row.get("最低") or row.get("low") or 0)
            close_price: float = float(row.get("收盘") or row.get("close") or 0)
            volume: float = float(row.get("成交量") or row.get("volume") or 0)
            turnover: float = float(row.get("成交额") or row.get("amount") or 0)
            open_interest: float = float(row.get("持仓量") or row.get("hold") or 0)

            bar = BarData(
                symbol=symbol,
                exchange=exchange,
                datetime=dt,
                interval=interval,
                volume=volume,
                turnover=turnover,
                open_interest=open_interest,
                open_price=open_price,
                high_price=high_price,
                low_price=low_price,
                close_price=close_price,
                gateway_name="AK",
            )
            bars.append(bar)

        return bars
