"""
自动下载历史日线数据到本地数据库 (新浪免费, 默认4年)。

用法:
    python download_data.py

自定义时间:
    python download_data.py --start 2020-01-01
    python download_data.py --years 5
"""
import sys
import time
from datetime import datetime, timedelta

from vnpy.trader.datafeed import get_datafeed
from vnpy.trader.database import get_database, DB_TZ
from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.object import HistoryRequest
from vnpy.trader.utility import extract_vt_symbol
from vnpy.trader.setting import SETTINGS

# ── 默认配置 ──────────────────────────────────────────────
DEFAULT_YEARS = 4                                           # 默认下载最近 N 年
END = datetime.now(tz=DB_TZ)                                # 截止到今天

SYMBOLS: list[str] = [
    # ── A 股蓝筹 ──
    "600519.SSE",    # 贵州茅台
    "000858.SZSE",   # 五粮液
    "601318.SSE",    # 中国平安
    "600036.SSE",    # 招商银行
    "000333.SZSE",   # 美的集团
    "300750.SZSE",   # 宁德时代
    "002594.SZSE",   # 比亚迪
    "601899.SSE",    # 紫金矿业
    "600276.SSE",    # 恒瑞医药
    "601012.SSE",    # 隆基绿能

    # ── 商品期货 (主力连续合约, 888 结尾 = 多年历史) ──
    "RB888.SHFE",   # 螺纹钢主力
    "HC888.SHFE",   # 热卷主力
    "I888.DCE",     # 铁矿石主力
    "J888.DCE",     # 焦炭主力
    "M888.DCE",     # 豆粕主力
    "Y888.DCE",     # 豆油主力

    # ── 金融期货 ──
    "IF888.CFFEX",  # 沪深300股指主力
    "IC888.CFFEX",  # 中证500股指主力
]

# 指数需 tushare (新浪日线不支持), 如需切换:
INDEX_SYMBOLS: list[str] = [
    # "000001.SSE",   # 上证指数
    # "399001.SZSE",  # 深证成指
    # "000300.SSE",   # 沪深300
    # "000016.SSE",   # 上证50
    # "000905.SSE",   # 中证500
]


def parse_args() -> datetime:
    """解析命令行参数, 返回 start 日期. 支持 --start / --years."""
    years = DEFAULT_YEARS
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--start" and i + 1 < len(args):
            return datetime.strptime(args[i + 1], "%Y-%m-%d").replace(tzinfo=DB_TZ)
        elif args[i] == "--years" and i + 1 < len(args):
            years = int(args[i + 1])
        i += 1
    return END - timedelta(days=years * 365)


def download(symbols: list[str], start: datetime) -> tuple[int, list[str]]:
    """下载指定品种列表的日线, 返回 (成功数, 失败列表)."""
    df = get_datafeed()
    db = get_database()
    ok, fail = 0, []

    for i, vs in enumerate(symbols, 1):
        sym, ex = extract_vt_symbol(vs)
        req = HistoryRequest(
            symbol=sym, exchange=ex,
            start=start, end=END,
            interval=Interval.DAILY,
        )
        print(f"\n[{i}/{len(symbols)}] {vs} ", end="", flush=True)
        try:
            bars = df.query_bar_history(req, output=print)
            if bars:
                db.save_bar_data(bars)
                ok += 1
            else:
                fail.append(vs)
        except Exception as e:
            print(f"异常: {e}")
            fail.append(vs)

        if i < len(symbols):
            time.sleep(1.2)
    return ok, fail


def show_db() -> None:
    """打印当前数据库摘要."""
    db = get_database()
    overviews = db.get_bar_overview()
    print(f"\n数据库已有 {len(overviews)} 条记录:")
    for o in overviews:
        print(f"  {o.symbol}.{o.exchange.value}  {o.interval.value}  "
              f"{o.count}条  {o.start.date()}~{o.end.date()}")


def main() -> None:
    start = parse_args()

    print("=" * 58)
    print(f"数据源: {SETTINGS['datafeed.name']} (新浪免费)")
    print(f"数据库: {SETTINGS['database.name']} ({SETTINGS['database.database']})")
    print(f"时间范围: {start.date()} ~ {END.date()}  ({DEFAULT_YEARS}年)")
    print(f"品种数: {len(SYMBOLS)}  (A股{sum(1 for s in SYMBOLS if '.SSE' in s or '.SZSE' in s)}支 + "
          f"期货{sum(1 for s in SYMBOLS if '.SHFE' in s or '.DCE' in s or '.CZCE' in s or '.CFFEX' in s)}支)")
    print("=" * 58)

    ok, fail = download(SYMBOLS, start)

    print(f"\n{'=' * 58}")
    print(f"总结果: 成功 {ok}/{len(SYMBOLS)}, 失败 {len(fail)}")
    if fail:
        print(f"失败品种: {fail}")
    print("=" * 58)

    show_db()


if __name__ == "__main__":
    main()
