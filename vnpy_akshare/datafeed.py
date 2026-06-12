"""
VeighNa datafeed adapter for AKShare (free & open-source financial data API).

Supports:
  - A-share stocks (SSE / SZSE / BSE)
  - Stock indices (SSE / CFFEX)
  - Commodity futures (SHFE / DCE / CZCE / CFFEX / INE / GFEX)
  - ETFs / LOFs
  - Daily / Weekly bar data

Usage:
  1. pip install akshare
  2. Set vt_setting.json: {"datafeed.name": "akshare", "datafeed.password": ""}
"""

from collections.abc import Callable
from datetime import datetime, timedelta

from vnpy.trader.object import BarData, HistoryRequest, TickData
from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.setting import SETTINGS


# ── helper: one-time akshare import ──────────────────────────────
try:
    import akshare as ak
except ImportError:
    ak = None


# ── interval → akshare period ────────────────────────────────────
_INTERVAL_MAP: dict[Interval, str] = {
    Interval.DAILY: "daily",
    Interval.WEEKLY: "weekly",
}

# ── exchange → akshare function ──────────────────────────────────
_STOCK_EXCHANGES: set[Exchange] = {Exchange.SSE, Exchange.SZSE, Exchange.BSE}
_FUTURES_EXCHANGES: set[Exchange] = {
    Exchange.SHFE,
    Exchange.DCE,
    Exchange.CZCE,
    Exchange.CFFEX,
    Exchange.INE,
    Exchange.GFEX,
}


def _map_index_symbol(symbol: str, exchange: Exchange) -> str:
    """Map vnpy index symbol to akshare index symbol."""
    if exchange == Exchange.SSE:
        return f"sh{symbol}"
    if exchange == Exchange.SZSE:
        return f"sz{symbol}"
    return symbol  # CFFEX / 其他指数直接用原始代码


class Datafeed:
    """AKShare datafeed adapter implementing VeighNa BaseDatafeed protocol."""

    def __init__(self) -> None:
        self._inited: bool = False

    # ── init ─────────────────────────────────────────────────────
    def init(self, output: Callable[[str], None] = print) -> bool:
        if ak is None:
            output("AKShare 未安装，请执行: pip install akshare")
            return False
        try:
            # 预热：取一次交易日历确认网络连通
            ak.tool_trade_date_hist_sina()
            self._inited = True
            output("AKShare 数据服务初始化成功（免费，无频率限制）")
            return True
        except Exception as e:
            output(f"AKShare 初始化失败: {e}")
            return False

    # ── query_bar_history ────────────────────────────────────────
    def query_bar_history(
        self, req: HistoryRequest, output: Callable[[str], None] = print
    ) -> list[BarData]:
        """Download historical K-line bars."""
        if not self._inited:
            self.init(output)

        symbol: str = req.symbol
        exchange: Exchange = req.exchange
        interval: Interval = req.interval or Interval.DAILY
        start: datetime = req.start
        end: datetime = req.end or datetime.now()

        if interval not in _INTERVAL_MAP:
            output(f"AKShare 暂不支持 K线周期: {interval.value}")
            return []

        try:
            df = self._download(symbol, exchange, interval, start, end)
            bars: list[BarData] = self._to_bars(df, symbol, exchange, interval)
            output(f"{symbol}.{exchange.value} 下载完成，共 {len(bars)} 条K线")
            return bars
        except Exception as e:
            output(f"下载失败 {symbol}.{exchange.value}: {e}")
            return []

    # ── query_tick_history (not supported) ────────────────────────
    def query_tick_history(
        self, req: HistoryRequest, output: Callable[[str], None] = print
    ) -> list[TickData]:
        output("AKShare 暂不支持 Tick 数据")
        return []

    # ── internal download logic ───────────────────────────────────
    def _download(
        self,
        symbol: str,
        exchange: Exchange,
        interval: Interval,
        start: datetime,
        end: datetime,
    ):
        """Route to correct akshare API based on exchange type."""
        period: str = _INTERVAL_MAP[interval]
        start_str: str = start.strftime("%Y%m%d")
        end_str: str = end.strftime("%Y%m%d")

        # ── stocks ────────────────────────────────────────────────
        if exchange in _STOCK_EXCHANGES:
            df = ak.stock_zh_a_hist(
                symbol=symbol,
                period=period,
                start_date=start_str,
                end_date=end_str,
                adjust="qfq",  # 前复权
            )
            return df

        # ── futures ───────────────────────────────────────────────
        if exchange in _FUTURES_EXCHANGES:
            # 兼容 CFFEX 的 IF / IC / IH 等指数期货
            code: str = symbol
            # akshare 期货日线接口用新浪源
            df = ak.futures_zh_daily_sina(symbol=code)
            if df is None or df.empty:
                # 尝试用主力连续（去掉数字部分）
                # 例如 IF2506 → IF (但是 akshare 支持原始代码)
                raise RuntimeError(f"未获取到期货数据: {code}，请确认合约代码是否正确")

            # 按日期过滤
            df = df.rename(columns={"date": "日期"})
            df["日期"] = pd.to_datetime(df["日期"])
            df = df[(df["日期"] >= start) & (df["日期"] <= end)]
            return df

        # ── indices ───────────────────────────────────────────────
        try:
            ak_symbol: str = _map_index_symbol(symbol, exchange)
            df = ak.index_zh_a_hist(
                symbol=ak_symbol,
                period=period,
                start_date=start_str,
                end_date=end_str,
            )
            return df
        except Exception:
            # fallback: stock_zh_index_daily
            idx_code: str = f"sh{symbol}" if exchange == Exchange.SSE else f"sz{symbol}"
            df = ak.stock_zh_index_daily(symbol=idx_code)
            df = df.rename(columns={"date": "日期"})
            df["日期"] = pd.to_datetime(df["日期"])
            df = df[(df["日期"] >= start) & (df["日期"] <= end)]
            return df

    # ── DataFrame → BarData ───────────────────────────────────────
    def _to_bars(
        self,
        df,
        symbol: str,
        exchange: Exchange,
        interval: Interval,
    ) -> list[BarData]:
        """Convert akshare DataFrame to vnpy BarData list."""
        bars: list[BarData] = []

        for _, row in df.iterrows():
            # 统一日期字段
            if "日期" in row:
                dt = pd.Timestamp(row["日期"]).to_pydatetime()
            elif "date" in row:
                dt = pd.Timestamp(row["date"]).to_pydatetime()
            else:
                continue

            bar = BarData(
                symbol=symbol,
                exchange=exchange,
                datetime=dt,
                interval=interval,
                gateway_name="AKSHARE",
                open_price=float(row.get("开盘", row.get("open", 0))),
                high_price=float(row.get("最高", row.get("high", 0))),
                low_price=float(row.get("最低", row.get("low", 0))),
                close_price=float(row.get("收盘", row.get("close", 0))),
                volume=float(row.get("成交量", row.get("volume", 0))),
                turnover=float(row.get("成交额", row.get("turnover", 0))),
                open_interest=float(row.get("持仓量", row.get("hold", 0))),
            )
            bars.append(bar)

        return bars


# ── lazy pandas import ───────────────────────────────────────────
import pandas as pd
