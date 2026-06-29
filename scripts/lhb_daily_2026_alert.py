"""
龙虎榜 2026 优化版 · 每日筛选 + 飞书通知
参数：换手3-5%, 净买>5000万, 流通>20亿, MA20比1.02-1.15, RSI 55-85, 20日涨>12%, 5日涨<25%
"""
import akshare as ak
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta
from vnpy.trader.database import get_database
from vnpy.trader.constant import Exchange, Interval

FEISHU_WEBHOOK = "https://open.feishu.cn/open-apis/bot/v2/hook/84efb9e0-1af9-4a3c-9fa3-4d9f8b5ecc5d"

PARAMS = {
    "mcap_lo": 20,
    "netbuy_lo": 5000,
    "hs_lo": 3,
    "hs_hi": 5,
    "ma20_lo": 1.02,
    "ma20_hi": 1.15,
    "rsi_lo": 55,
    "rsi_hi": 85,
    "ret20_lo": 12,
    "ret5_hi": 25,
}


def screen_lhb(date_str, db):
    """按2026优化参数筛选"""
    try:
        df = ak.stock_lhb_detail_em(start_date=date_str, end_date=date_str)
    except Exception as e:
        return None, f"下载失败: {e}"
    if len(df) == 0:
        return [], "无数据"

    df["换"] = pd.to_numeric(df["换手率"], errors="coerce")
    df["净"] = pd.to_numeric(df["龙虎榜净买额"], errors="coerce") / 10000
    df["市"] = pd.to_numeric(df["流通市值"], errors="coerce")
    df["因"] = df["上榜原因"].astype(str)
    df["日"] = pd.to_datetime(df["上榜日"])

    mask = (
        ~df["因"].str.contains("ST|连续|异常", na=False)
        & ~df["名称"].str.contains("ST", na=False)
        & ~df["代码"].str.startswith("688")  # 排除科创板
        & (df["换"] >= PARAMS["hs_lo"])
        & (df["换"] <= PARAMS["hs_hi"])
        & (df["市"] > PARAMS["mcap_lo"])
        & (df["净"] > PARAMS["netbuy_lo"])
    )
    base = df[mask].copy()
    stats = {"base": len(base), "nodb": 0}
    results = []

    for _, row in base.iterrows():
        sym = str(row["代码"]).zfill(6)
        ex = Exchange.SSE if sym[0] == "6" else Exchange.SZSE
        d = row["日"]

        bars = db.load_bar_data(
            sym, ex, Interval.DAILY,
            start=(d - timedelta(days=150)).strftime("%Y-%m-%d"),
            end=(d + timedelta(days=1)).strftime("%Y-%m-%d"),
        )
        if bars is None or len(bars) < 60:
            stats["nodb"] += 1
            continue

        closes = np.array([b.close_price for b in bars])
        highs = np.array([b.high_price for b in bars])
        idx = next((i for i, b in enumerate(bars) if b.datetime.date() == d.date()), None)
        if idx is None or idx < 60:
            continue

        c = closes[idx]
        tb = bars[idx]
        pc = closes[idx - 1]

        # 非一字板/T字板
        if tb.open_price >= pc * 1.098 or tb.low_price >= pc * 1.098:
            continue

        # MA20
        ma20 = np.mean(closes[idx - 19 : idx + 1])
        ma20_ratio = c / ma20
        if ma20_ratio < PARAMS["ma20_lo"] or ma20_ratio > PARAMS["ma20_hi"]:
            continue

        # RSI
        gains, losses = [], []
        for i in range(idx - 13, idx + 1):
            diff = closes[i] - closes[i - 1]
            gains.append(diff if diff > 0 else 0)
            losses.append(-diff if diff < 0 else 0)
        rsi = 100 - 100 / (1 + np.mean(gains) / np.mean(losses)) if np.mean(losses) > 0 else 100
        if rsi < PARAMS["rsi_lo"] or rsi > PARAMS["rsi_hi"]:
            continue

        # 20日涨幅
        ret20 = (c / closes[idx - 20] - 1) * 100
        if ret20 < PARAMS["ret20_lo"]:
            continue

        # 5日涨幅
        if idx >= 5:
            ret5 = (c / closes[idx - 5] - 1) * 100
            if ret5 >= PARAMS["ret5_hi"]:
                continue

        results.append({
            "名称": row["名称"],
            "代码": sym,
            "涨幅": f"{row.get('涨跌幅', '?')}%",
            "换手": f"{row['换']:.1f}%",
            "净买万": f"{row['净']:.0f}",
            "MA20比": f"{ma20_ratio:.2f}",
            "RSI": f"{rsi:.0f}",
            "20日涨": f"{ret20:.0f}%",
        })

    return results, stats


def send_feishu(text):
    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": "🐲 龙虎榜 2026 优化版"},
                "template": "blue",
            },
            "elements": [
                {"tag": "markdown", "content": text},
            ],
        },
    }
    try:
        r = requests.post(FEISHU_WEBHOOK, json=payload, timeout=10)
        return r.status_code == 200
    except Exception as e:
        print(f"飞书发送失败: {e}", flush=True)
        return False


def main():
    db = get_database()

    # 找最近有数据的交易日
    today = datetime.now()
    check_date = today if today.hour >= 17 else today - timedelta(days=1)
    while check_date.weekday() >= 5:
        check_date -= timedelta(days=1)

    date_str = check_date.strftime("%Y%m%d")

    # 试下载，如果当天没数据就往前翻
    for _ in range(7):
        print(f"尝试: {date_str}", flush=True)
        results, info = screen_lhb(date_str, db)
        if results is not None:
            break
        check_date -= timedelta(days=1)
        while check_date.weekday() >= 5:
            check_date -= timedelta(days=1)
        date_str = check_date.strftime("%Y%m%d")

    if results is None:
        print(f"最近7天无龙虎榜数据")
        return

    print(f"日期: {date_str}  基础: {info.get('base', 0)}笔  命中: {len(results)}只", flush=True)

    if len(results) == 0:
        return

    # 构造飞书消息
    lines = [
        f"📅 {check_date.strftime('%Y-%m-%d')}",
        f"龙虎榜 {info.get('base', '?')} 笔 → 命中 **{len(results)} 只**",
        "",
    ]
    for i, r in enumerate(results, 1):
        lines.append(
            f"**{i}. {r['名称']}**（{r['代码']}）\n"
            f"　涨幅{r['涨幅']}　换手{r['换手']}　净买{r['净买万']}万\n"
            f"　MA20比{r['MA20比']}　RSI{r['RSI']}　20日涨{r['20日涨']}\n"
            f"　→ 明日开盘买入，后日开盘卖出"
        )
    lines.append("")
    lines.append("⚠ 以上为策略筛选结果，不构成投资建议")

    ok = send_feishu("\n".join(lines))
    print(f"飞书: {'✅' if ok else '❌'}", flush=True)


if __name__ == "__main__":
    main()
