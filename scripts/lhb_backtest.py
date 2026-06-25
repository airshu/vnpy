"""
龙虎榜策略 · 回测脚本

核心逻辑：
1. 每日筛选龙虎榜中「净买入 > 0 + 非一字板」的股票
2. 次日开盘买入，持有N日卖出
3. 计算组合收益

数据来源：akshare stock_lhb_detail_em（自带上榜后1/2/5/10日涨跌幅）
"""
import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime, timedelta


def fetch_lhb_range(start: str, end: str) -> pd.DataFrame:
    """下载指定日期范围的龙虎榜数据"""
    df = ak.stock_lhb_detail_em(start_date=start, end_date=end)
    df["净买额"] = pd.to_numeric(df["龙虎榜净买额"], errors="coerce")
    df["涨跌幅"] = pd.to_numeric(df["涨跌幅"], errors="coerce")
    df["上榜原因"] = df["上榜原因"].astype(str)
    for col in ["上榜后1日", "上榜后2日", "上榜后5日", "上榜后10日"]:
        df[col] = pd.to_numeric(df[f"{col}"], errors="coerce")
    return df


def filter_candidates(df: pd.DataFrame, min_net_buy: float = 0,
                      max_gain: float = 9.5, min_gain: float = 2.0,
                      min_turnover: float = 3.0) -> pd.DataFrame:
    """筛选候选股票
    - 净买入 > 0
    - 涨幅 2%~9.5%（排除一字板和微涨股）
    - 换手率 > 3%
    """
    mask = (
        (df["净买额"] > min_net_buy * 10000) &
        (df["涨跌幅"] >= min_gain) &
        (df["涨跌幅"] <= max_gain) &
        (pd.to_numeric(df["换手率"], errors="coerce") >= min_turnover)
    )
    # 排除ST、连续一字板
    mask &= ~df["上榜原因"].str.contains("ST|连续三个交易日|异常波动", na=False)
    return df[mask]


def run_backtest(start: str = "20240101", end: str = "20260623",
                 hold_days: int = 5):
    """回测龙虎榜策略"""
    print(f"\n龙虎榜策略回测 ({start} ~ {end}, 持有{hold_days}日)")
    print("=" * 55)

    # 下载数据
    df = fetch_lhb_range(start, end)
    print(f"原始龙虎榜数据: {len(df)} 条记录")

    # 筛选
    candidates = filter_candidates(df)
    print(f"筛选后候选: {len(candidates)} 条")
    print(f"涉及 {candidates['代码'].nunique()} 只股票\n")

    # 分析上榜后收益
    col = f"上榜后{hold_days}日"
    if col not in candidates.columns:
        print(f"⚠ {col}列不存在")
        return

    valid = candidates[col].dropna()
    if len(valid) == 0:
        print("无有效数据")
        return

    # 统计
    avg_ret = valid.mean()
    median_ret = valid.median()
    win_rate = (valid > 0).sum() / len(valid) * 100
    max_gain = valid.max()
    max_loss = valid.min()

    print(f"持有{hold_days}日统计 ({len(valid)}笔交易):")
    print(f"  平均收益:   {avg_ret:+.2f}%")
    print(f"  中位数收益: {median_ret:+.2f}%")
    print(f"  胜率:       {win_rate:.1f}%")
    print(f"  最大盈利:   {max_gain:+.2f}%")
    print(f"  最大亏损:   {max_loss:+.2f}%")

    # 按月份统计
    candidates["月份"] = pd.to_datetime(candidates["上榜日"]).dt.strftime("%Y-%m")
    monthly = candidates.groupby("月份")[col].agg(["mean", "count"])
    print(f"\n月度表现 (最近6个月):")
    for idx, row in monthly.tail(6).iterrows():
        bar = "█" * int(abs(row["mean"]) * 2) if row["mean"] > 0 else "░" * int(abs(row["mean"]) * 2)
        print(f"  {idx}: {row['mean']:>+6.2f}% ({int(row['count'])}笔) {bar}")

    # 累计收益
    valid_sorted = valid.sort_index()
    cumulative = (1 + valid_sorted / 100).cumprod()
    print(f"\n累计净值: {cumulative.iloc[-1]:.3f} ({'盈利' if cumulative.iloc[-1] > 1 else '亏损'})")

    return valid


if __name__ == "__main__":
    # 测试不同持有期
    for days in [1, 2, 5, 10]:
        run_backtest(hold_days=days)
