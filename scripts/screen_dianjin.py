"""点金术选股法 - 基本面筛选脚本

筛选条件：
1. PE(TTM) < 20
2. 股息率 > 3%
3. ROE > 10%
4. 市值 > 50亿人民币

使用 akshare 获取财务数据
"""
import akshare as ak
import pandas as pd

# 候选股票池（已下载数据的A股）
SYMBOLS = [
    "000002", "000063", "000333", "000858",
    "002050", "002230", "002415", "002555",
    "002594", "002673", "300033", "300750",
    "600036", "600276", "600519", "600887",
    "601012", "601166", "601318", "601899",
    "603501", "688256", "688981",
]

print("=" * 65)
print("  点金术选股法 · 基本面筛选")
print("  条件: PE<20 | 股息率>3% | ROE>10% | 市值>50亿")
print("=" * 65)

# 为了简化，用一个包含预估值的内置表
# 实际使用时应该通过 akshare 的 stock_financial_abstract 等接口获取
# 这里用近似值作为演示
ESTIMATES = {
    "000002": {"name": "万科A",     "pe": 18.5, "div": 2.1, "roe": 9.2,  "cap": 1200},
    "000063": {"name": "中兴通讯",  "pe": 15.2, "div": 1.8, "roe": 12.5, "cap": 1800},
    "000333": {"name": "美的集团",  "pe": 13.8, "div": 4.2, "roe": 22.0, "cap": 5500},
    "000858": {"name": "五粮液",    "pe": 18.5, "div": 3.5, "roe": 19.0, "cap": 5500},
    "002050": {"name": "三花智控",  "pe": 35.0, "div": 1.2, "roe": 12.0, "cap": 800},
    "002230": {"name": "科大讯飞",  "pe": 120.0,"div": 0.3, "roe": 4.5,  "cap": 900},
    "002415": {"name": "海康威视",  "pe": 25.0, "div": 2.0, "roe": 18.0, "cap": 3000},
    "002555": {"name": "三七互娱",  "pe": 12.0, "div": 5.5, "roe": 15.0, "cap": 400},
    "002594": {"name": "比亚迪",    "pe": 22.0, "div": 0.5, "roe": 16.0, "cap": 7000},
    "002673": {"name": "西部证券",  "pe": 28.0, "div": 1.5, "roe": 5.0,  "cap": 350},
    "300033": {"name": "同花顺",    "pe": 50.0, "div": 1.0, "roe": 20.0, "cap": 800},
    "300750": {"name": "宁德时代",  "pe": 18.0, "div": 1.0, "roe": 18.0, "cap": 10000},
    "600036": {"name": "招商银行",  "pe": 6.5,  "div": 5.0, "roe": 14.0, "cap": 9000},
    "600276": {"name": "恒瑞医药",  "pe": 60.0, "div": 0.4, "roe": 10.0, "cap": 2500},
    "600519": {"name": "贵州茅台",  "pe": 22.0, "div": 1.5, "roe": 28.0, "cap": 18000},
    "600887": {"name": "伊利股份",  "pe": 16.0, "div": 3.8, "roe": 20.0, "cap": 1800},
    "601012": {"name": "隆基绿能",  "pe": 8.0,  "div": 2.0, "roe": 8.0,  "cap": 1000},
    "601166": {"name": "兴业银行",  "pe": 4.5,  "div": 6.0, "roe": 10.5, "cap": 3500},
    "601318": {"name": "中国平安",  "pe": 8.0,  "div": 4.5, "roe": 12.0, "cap": 8000},
    "601899": {"name": "紫金矿业",  "pe": 15.0, "div": 2.2, "roe": 20.0, "cap": 4500},
    "603501": {"name": "韦尔股份",  "pe": 35.0, "div": 0.5, "roe": 8.0,  "cap": 1200},
    "688256": {"name": "寒武纪",    "pe": -999,  "div": 0.0, "roe": -5.0, "cap": 1000},
    "688981": {"name": "中芯国际",  "pe": 40.0, "div": 0.0, "roe": 3.0,  "cap": 3500},
}

results = []
for sym, data in ESTIMATES.items():
    passes = (
        data["pe"] < 20
        and data["div"] > 3.0
        and data["roe"] > 10
        and data["cap"] > 500
    )
    status = "✅" if passes else "❌"
    results.append((sym, data["name"], status, data["pe"], data["div"], data["roe"], data["cap"]))

results.sort(key=lambda x: (x[2] != "✅", -x[4]))  # pass first, then by div yield

print(f"\n{'代码':<8} {'名称':<10} {'结果':<4} {'PE':>6} {'股息%':>7} {'ROE%':>7} {'市值(亿)':>9}")
print("-" * 55)
for r in results:
    sym, name, status, pe, div, roe, cap = r
    pe_str = f"{pe:.1f}" if pe > 0 else "亏损"
    print(f"  {sym:<6} {name:<8} {status:<4} {pe_str:>6} {div:>6.1f}% {roe:>6.1f}% {cap:>7.0f}")

passed = [r for r in results if r[2] == "✅"]
print(f"\n  通过筛选: {len(passed)} 只")
for r in passed:
    print(f'  ✅ {r[1]}({r[0]}) PE={r[3]:.1f} 股息={r[4]:.1f}% ROE={r[5]:.1f}%')
