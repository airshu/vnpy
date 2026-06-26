"""
龙虎榜每日筛选 + 飞书通知
用法: python scripts/lhb_daily_alert.py
"""
import akshare as ak
import pandas as pd
import numpy as np
import requests
import json
from datetime import datetime, timedelta
from vnpy.trader.database import get_database
from vnpy.trader.constant import Exchange, Interval

FEISHU_WEBHOOK = "https://open.feishu.cn/open-apis/bot/v2/hook/84efb9e0-1af9-4a3c-9fa3-4d9f8b5ecc5d"

# ===== 10 条件筛选函数 =====
def screen_lhb(date_str, db):
    """筛选指定日期龙虎榜中满足条件的股票"""
    try:
        df = ak.stock_lhb_detail_em(start_date=date_str, end_date=date_str)
    except Exception as e:
        return None, f"下载龙虎榜失败: {e}"

    if len(df) == 0:
        return [], f"{date_str} 无龙虎榜数据"

    df["换"] = pd.to_numeric(df["换手率"], errors="coerce")
    df["净"] = pd.to_numeric(df["龙虎榜净买额"], errors="coerce") / 10000
    df["市"] = pd.to_numeric(df["流通市值"], errors="coerce")
    df["因"] = df["上榜原因"].astype(str)
    df["日"] = pd.to_datetime(df["上榜日"])

    mask = (
        ~df["因"].str.contains("ST|连续|异常", na=False)
        & ~df["名称"].str.contains("ST", na=False)
        & (df["换"] >= 3)
        & (df["换"] <= 10)
        & (df["市"] > 30)
        & (df["净"] > 3000)
    )
    base = df[mask].copy()

    results = []
    stats = {"base": len(base), "nodata": 0}

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
            stats["nodata"] += 1
            continue

        closes = np.array([b.close_price for b in bars])
        highs = np.array([b.high_price for b in bars])
        vols = np.array([b.volume for b in bars])
        idx = next((i for i, b in enumerate(bars) if b.datetime.date() == d.date()), None)
        if idx is None or idx < 60:
            continue

        c = closes[idx]
        tb = bars[idx]
        pc = closes[idx - 1]

        # 非一字板/T字板
        if tb.open_price >= pc * 1.098 or tb.low_price >= pc * 1.098:
            continue

        # MA20 > 1.02
        ma20 = np.mean(closes[idx - 19 : idx + 1])
        if c / ma20 < 1.02:
            continue

        # RSI 55-85
        gains, losses = [], []
        for i in range(idx - 13, idx + 1):
            diff = closes[i] - closes[i - 1]
            gains.append(diff if diff > 0 else 0)
            losses.append(-diff if diff < 0 else 0)
        rsi = 100 - 100 / (1 + np.mean(gains) / np.mean(losses)) if np.mean(losses) > 0 else 100
        if rsi < 55 or rsi > 85:
            continue

        # 距60日高 < 15%
        h60 = float(max(highs[idx - 59 : idx + 1]))
        if (c - h60) / h60 * 100 < -15:
            continue

        # 20日涨幅 > 15%
        ret20 = (c / closes[idx - 20] - 1) * 100
        if ret20 < 15:
            continue

        # 量比 1.2-3.0
        avg5 = np.mean(vols[idx - 4 : idx + 1])
        avg20 = np.mean(vols[idx - 19 : idx + 1])
        vol_ratio = avg5 / avg20
        if vol_ratio < 1.2 or vol_ratio > 3.0:
            continue

        # 5日涨幅 < 15%
        if idx >= 5:
            ret5 = (c / closes[idx - 5] - 1) * 100
            if ret5 >= 15:
                continue

        # 连板 ≤ 1
        up_days = 0
        for i in range(idx, 0, -1):
            if closes[i] > closes[i - 1] * 1.095:
                up_days += 1
            else:
                break
        if up_days > 1:
            continue

        results.append({
            "名称": row["名称"],
            "代码": sym,
            "涨幅": f"{row.get('涨跌幅', '?')}%",
            "换手": f"{row['换']:.1f}%",
            "净买万": f"{row['净']:.0f}",
            "20日涨": f"{ret20:.0f}%",
            "RSI": f"{rsi:.0f}",
        })

    return results, stats


# ===== 飞书消息发送 =====
def send_feishu(text):
    """发送文本消息到飞书群"""
    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": "🐲 龙虎榜趋势股筛选"},
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
        print(f"飞书发送失败: {e}")
        return False


# ===== 主流程 =====
def main():
    db = get_database()

    # 找最新交易日
    today = datetime.now()
    if today.hour < 17:
        # 今天还没收盘，用昨天的数据
        check_date = today - timedelta(days=1)
    else:
        check_date = today

    # 跳过周末
    while check_date.weekday() >= 5:
        check_date -= timedelta(days=1)

    date_str = check_date.strftime("%Y%m%d")
    print(f"检查日期: {check_date.strftime('%Y-%m-%d')}")

    # 检查数据库是否已有该日数据（抽样验证一只股票即可）
    results, info = screen_lhb(date_str, db)
    if results is None:
        # 下载失败，发通知
        send_feishu(f"❌ {date_str} 龙虎榜数据下载失败: {info}")
        return

    if len(results) == 0:
        # 无信号，不推送，只记日志
        print(f"{date_str}: 基础{info.get('base',0)}笔  无符合条件")
        return

    # === 有符合条件的股票 ===
    print(f"\n🎉 选出 {len(results)} 只:")
    for r in results:
        print(f"  {r['名称']}({r['代码']}) 换{r['换手']} RSI{r['RSI']}")

    # 构造飞书消息
    lines = [
        f"📅 {check_date.strftime('%Y-%m-%d')}",
        f"龙虎榜 {info.get('base', '?')} 笔 → 筛选出 **{len(results)} 只**",
        "",
    ]
    for i, r in enumerate(results, 1):
        lines.append(
            f"**{i}. {r['名称']}**（{r['代码']}）\n"
            f"　涨幅{r['涨幅']}　换手{r['换手']}　净买{r['净买万']}万\n"
            f"　20日涨{r['20日涨']}　RSI{r['RSI']}\n"
            f"　→ 明日开盘买入，后日开盘卖出"
        )

    lines.append("")
    lines.append("⚠ 以上为策略筛选结果，不构成投资建议")

    text = "\n".join(lines)
    ok = send_feishu(text)
    print(f"\n飞书通知: {'✅ 已发送' if ok else '❌ 发送失败'}")


if __name__ == "__main__":
    main()
