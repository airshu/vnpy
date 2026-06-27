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
    "300866.SZSE",   # 安克创新
    "600519.SSE",    # 贵州茅台
    "000858.SZSE",   # 五粮液
    "600887.SSE",    # 伊利股份

    # ── 金融 ──
    "601318.SSE",    # 中国平安
    "600036.SSE",    # 招商银行
    "601166.SSE",    # 兴业银行

    # ── 新能源 + 制造业 ──
    "300750.SZSE",   # 宁德时代
    "002594.SZSE",   # 比亚迪
    "000333.SZSE",   # 美的集团
    "601012.SSE",    # 隆基绿能

    # ── 资源有色 ──
    "601899.SSE",    # 紫金矿业

    # ── 医药科技 ──
    "600276.SSE",    # 恒瑞医药
    "002415.SZSE",   # 海康威视

    # ── 地产 ──
    "000002.SZSE",   # 万科A

    # ── AI + 半导体 ──
    "002230.SZSE",   # 科大讯飞（AI 语音/NLP）
    "000063.SZSE",   # 中兴通讯（AI 算力/通信）
    "603501.SSE",    # 韦尔股份（图像传感器/芯片）
    "688256.SSE",    # 寒武纪（AI 芯片）
    "688981.SSE",    # 中芯国际（晶圆代工/芯片制造）

    # ── 主流行业 ETF ──
    "510050.SSE",    # 上证50ETF
    "510300.SSE",    # 沪深300ETF
    "510500.SSE",    # 中证500ETF
    "159915.SZSE",   # 创业板ETF
    "588000.SSE",    # 科创50ETF
    "512880.SSE",    # 证券ETF
    "512010.SSE",    # 医药ETF
    "159995.SZSE",   # 芯片ETF
    "512690.SSE",    # 酒ETF
    "512660.SSE",    # 军工ETF
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


def download(symbols: list[str], start: datetime, force: bool = False) -> tuple[int, int, int]:
    """下载品种日线, 返回 (新增, 跳过, 失败列表). 默认增量: 已存在的跳过."""
    df = get_datafeed()
    db = get_database()

    # 查已有品种
    existing = {(o.symbol, o.exchange.value) for o in db.get_bar_overview()}

    ok, skip, fail = 0, 0, []

    for i, vs in enumerate(symbols, 1):
        sym, ex = extract_vt_symbol(vs)
        key = (sym, ex.value)

        if not force and key in existing:
            print(f"\n[{i}/{len(symbols)}] {vs} 已存在, 跳过")
            skip += 1
            continue

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
    return ok, skip, fail


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
    print(f"品种数: {len(SYMBOLS)} 支 (A股+ETF)")
    print("=" * 58)

    ok, skip, fail = download(SYMBOLS, start)

    print(f"\n{'=' * 58}")
    print(f"总结果: 新增 {ok}, 跳过 {skip}, 失败 {len(fail)} / 共 {len(SYMBOLS)}")
    if fail:
        print(f"失败品种: {fail}")
    print("=" * 58)

    show_db()


if __name__ == "__main__":
    main()
