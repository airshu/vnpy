"""
龙虎榜每日筛选 + 飞书通知

用法:
  python scripts/lhb_daily_alert.py              # 检测今天
  python scripts/lhb_daily_alert.py 20260630     # 检测指定日期

流程: 下载龙虎榜 → 缺数据则同步 → 基础版+优化版双策略筛选 → 命中推飞书
"""
import sys
import time
import akshare as ak
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta
from vnpy.trader.database import get_database
from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.datafeed import get_datafeed
from vnpy.trader.object import HistoryRequest

FEISHU_WEBHOOK = "https://open.feishu.cn/open-apis/bot/v2/hook/84efb9e0-1af9-4a3c-9fa3-4d9f8b5ecc5d"

# 基础版: 换手3-10%, 净买>3000万, 流通>30亿
BASE_PARAMS = {
    "hs_lo": 3, "hs_hi": 10, "mcap_lo": 30, "netbuy_lo": 3000,
    "ma20_lo": 1.02, "rsi_lo": 55, "rsi_hi": 85,
    "ret20_lo": 15, "ret5_hi": 15,
}
# 优化版: 换手3-5%, 净买>5000万, 流通>20亿
OPT_PARAMS = {
    "hs_lo": 3, "hs_hi": 5, "mcap_lo": 20, "netbuy_lo": 5000,
    "ma20_lo": 1.02, "ma20_hi": 1.15,
    "rsi_lo": 55, "rsi_hi": 85, "ret20_lo": 12, "ret5_hi": 25,
}


def get_date():
    if len(sys.argv) > 1:
        return datetime.strptime(sys.argv[1], "%Y%m%d")
    t = datetime.now()
    d = t if t.hour >= 17 else t - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def ensure_data(candidates, db, date):
    """确保候选股K线数据已同步到本地(增量补缺)"""
    missing = []
    for _, row in candidates.iterrows():
        sym = str(row["代码"]).zfill(6)
        ex = Exchange.SSE if sym[0] == "6" else Exchange.SZSE
        bars = db.load_bar_data(sym, ex, Interval.DAILY,
            start=(date - timedelta(days=150)).strftime("%Y-%m-%d"),
            end=(date + timedelta(days=1)).strftime("%Y-%m-%d"))
        if bars is None or len(bars) < 60:
            missing.append((sym, ex))
    if not missing:
        return 0

    print(f"  缺 {len(missing)} 只，同步中...", flush=True)
    synced = 0
    for sym, ex in missing:
        # 先试 vnpy datafeed(新浪)
        bars = _download_vnpy(sym, ex, date, db)
        if not bars:
            # 失败则换 baostock
            bars = _download_baostock(sym, ex)
        if bars:
            db.save_bar_data(bars)
            synced += 1
    print(f"  同步完成: {synced}/{len(missing)}", flush=True)
    return synced


def _download_vnpy(sym, ex, date, db):
    try:
        existing = db.load_bar_data(sym, ex, Interval.DAILY,
            start=(date - timedelta(days=200)).strftime("%Y-%m-%d"),
            end=date.strftime("%Y-%m-%d"))
        if existing and len(existing) > 0:
            last_dt = existing[-1].datetime
            if (date - last_dt).days <= 1:
                return existing
            start = last_dt + timedelta(seconds=1)
        else:
            start = date - timedelta(days=730)
        dfeed = get_datafeed()
        req = HistoryRequest(symbol=sym, exchange=ex, start=start, end=datetime.now(), interval=Interval.DAILY)
        return dfeed.query_bar_history(req)
    except Exception:
        return None


def _download_baostock(sym, ex):
    try:
        import baostock as bs
        from vnpy.trader.object import BarData
        bs.login()
        bs_code = f"{'sh' if ex.value == 'SSE' else 'sz'}.{sym}"
        rs = bs.query_history_k_data_plus(bs_code,
            "date,open,high,low,close,volume,amount",
            start_date="2018-01-01", end_date=datetime.now().strftime("%Y-%m-%d"),
            frequency="d", adjustflag="2")
        rows = []
        while rs.next(): rows.append(rs.get_row_data())
        bs.logout()
        if not rows: return None
        bars = []
        for row in rows:
            if row[0] == "" or row[1] == "0.000000": continue
            bars.append(BarData(gateway_name="BS", symbol=sym, exchange=ex,
                datetime=datetime.strptime(row[0], "%Y-%m-%d"), interval=Interval.DAILY,
                open_price=float(row[1]), high_price=float(row[2]),
                low_price=float(row[3]), close_price=float(row[4]),
                volume=float(row[5]), turnover=float(row[6])))
        return bars if bars else None
    except Exception:
        return None


def fetch_lhb(date_str):
    try:
        df = ak.stock_lhb_detail_em(start_date=date_str, end_date=date_str)
    except Exception as e:
        return None, f"下载失败: {e}"
    if len(df) == 0:
        return None, "无数据"

    df["换"] = pd.to_numeric(df["换手率"], errors="coerce")
    df["净"] = pd.to_numeric(df["龙虎榜净买额"], errors="coerce") / 10000
    df["市"] = pd.to_numeric(df["流通市值"], errors="coerce")
    df["因"] = df["上榜原因"].astype(str)
    df["日"] = pd.to_datetime(df["上榜日"])

    valid = df["代码"].astype(str).str.match(r"^(000|001|002|003|300|301|600|601|603|605)")
    base = df[~df["因"].str.contains("ST|连续|异常", na=False)
              & ~df["名称"].str.contains("ST", na=False)
              & valid]
    return base, f"{len(df)}条 → A股{len(base)}只"


def screen(base, params, db):
    mask = ((base["换"] >= params["hs_lo"]) & (base["换"] <= params["hs_hi"])
            & (base["市"] > params["mcap_lo"]) & (base["净"] > params["netbuy_lo"]))
    pool = base[mask].copy()
    if len(pool) == 0:
        return [], {"base": 0}

    results = []
    stats = {"base": len(pool), "nodb": 0}
    is_opt = "ma20_hi" in params

    for _, row in pool.iterrows():
        sym = str(row["代码"]).zfill(6)
        ex = Exchange.SSE if sym[0] == "6" else Exchange.SZSE
        d = row["日"]
        bars = db.load_bar_data(sym, ex, Interval.DAILY,
            start=(d - timedelta(days=150)).strftime("%Y-%m-%d"),
            end=(d + timedelta(days=1)).strftime("%Y-%m-%d"))
        if bars is None or len(bars) < 60:
            stats["nodb"] += 1; continue

        cl = np.array([b.close_price for b in bars])
        hi = np.array([b.high_price for b in bars])
        vo = np.array([b.volume for b in bars])
        idx = next((i for i, b in enumerate(bars) if b.datetime.date() == d.date()), None)
        if idx is None or idx < 60: continue

        c = cl[idx]; tb = bars[idx]; pc = cl[idx - 1]
        if tb.open_price >= pc * 1.098 or tb.low_price >= pc * 1.098: continue

        ma20_ratio = c / np.mean(cl[idx - 19:idx + 1])
        if ma20_ratio < params["ma20_lo"]: continue
        if is_opt and ma20_ratio > params["ma20_hi"]: continue

        g, l = [], []
        for i in range(idx - 13, idx + 1):
            diff = cl[i] - cl[i - 1]
            g.append(diff if diff > 0 else 0); l.append(-diff if diff < 0 else 0)
        rsi = 100 - 100 / (1 + np.mean(g) / np.mean(l)) if np.mean(l) > 0 else 100
        if rsi < params["rsi_lo"] or rsi > params["rsi_hi"]: continue

        if not is_opt:
            h60 = float(max(hi[idx - 59:idx + 1]))
            if (c - h60) / h60 * 100 < -15: continue

        ret20 = (c / cl[idx - 20] - 1) * 100
        if ret20 < params["ret20_lo"]: continue

        if not is_opt:
            vr = np.mean(vo[idx - 4:idx + 1]) / np.mean(vo[idx - 19:idx + 1])
            if vr < 1.2 or vr > 3.0: continue

        if idx >= 5:
            ret5 = (c / cl[idx - 5] - 1) * 100
            if ret5 >= params["ret5_hi"]: continue

        ud = 0
        for i in range(idx, 0, -1):
            if cl[i] > cl[i - 1] * 1.095: ud += 1
            else: break
        if ud > 1: continue

        results.append({
            "名称": row["名称"], "代码": sym,
            "涨幅": f'{row.get("涨跌幅", "?")}%', "换手": f'{row["换"]:.1f}%',
            "净买万": f'{row["净"]:.0f}', "20日涨": f'{ret20:.0f}%', "RSI": f'{rsi:.0f}',
        })
    return results, stats


def send_feishu(title, check_date, results, info):
    lines = [
        f"📅 {check_date.strftime('%Y-%m-%d')}",
        f"龙虎榜 {info} → {title} 命中 **{len(results)} 只**",
        "",
    ]
    for i, r in enumerate(results, 1):
        lines.append(
            f"**{i}. {r['名称']}**（{r['代码']}）\n"
            f"　涨幅{r['涨幅']}　换手{r['换手']}　净买{r['净买万']}万\n"
            f"　20日涨{r['20日涨']}　RSI{r['RSI']}\n"
            f"　→ 明日开盘买入，后日开盘卖出"
        )
    lines.append(""); lines.append("⚠ 以上为策略筛选结果，不构成投资建议")

    payload = {
        "msg_type": "interactive", "card": {
            "header": {"title": {"tag": "plain_text", "content": f"🐲 龙虎榜 · {title}"}, "template": "blue"},
            "elements": [{"tag": "markdown", "content": "\n".join(lines)}],
        },
    }
    try:
        r = requests.post(FEISHU_WEBHOOK, json=payload, timeout=10)
        return r.status_code == 200
    except Exception:
        return False


def main():
    check_date = get_date()
    date_str = check_date.strftime("%Y%m%d")
    print(f"日期: {check_date.strftime('%Y-%m-%d')}", flush=True)
    db = get_database()

    # 1. 下载龙虎榜
    base, info = fetch_lhb(date_str)
    if base is None:
        print(f"❌ {info}", flush=True); return
    print(f"[1] {info}", flush=True)

    # 2. 同步缺失数据
    ensure_data(base, db, check_date)

    # 3. 基础版筛选
    print("[2] 基础版...", flush=True)
    t0 = time.time()
    r1, s1 = screen(base, BASE_PARAMS, db)
    print(f"    基础{s1['base']}笔 → 命中{len(r1)}只 ({time.time()-t0:.0f}s)", flush=True)

    # 4. 优化版筛选
    print("[3] 优化版...", flush=True)
    t0 = time.time()
    r2, s2 = screen(base, OPT_PARAMS, db)
    print(f"    基础{s2['base']}笔 → 命中{len(r2)}只 ({time.time()-t0:.0f}s)", flush=True)

    # 5. 推送
    pushed = 0
    if r1:
        ok = send_feishu("基础版", check_date, r1, info)
        print(f"    基础版飞书: {'✅' if ok else '❌'}", flush=True)
        pushed += 1
    if r2:
        ok = send_feishu("2026优化版", check_date, r2, info)
        print(f"    优化版飞书: {'✅' if ok else '❌'}", flush=True)
        pushed += 1
    if pushed == 0:
        print("  无命中，不推送", flush=True)


if __name__ == "__main__":
    main()
