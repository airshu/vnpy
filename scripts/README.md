# Scripts 目录说明

## 🎯 龙虎榜策略（核心）

| 脚本 | 作用 | 用法 |
|------|------|------|
| `lhb_2018_backtest.py` | v2 全量回测 (2018-2026)，169笔 +105%，胜率45% | `python scripts/lhb_2018_backtest.py` |
| `lhb_2026_optimized.py` | 2026 年最优版，11笔 +50%，胜率91%，月均2笔 | `python scripts/lhb_2026_optimized.py` |
| `lhb_2026_full_backtest.py` | 用 2026 最优参数跑全量历史，验证泛化能力 | `python scripts/lhb_2026_full_backtest.py` |
| `lhb_daily_screen.py` | 每日龙虎榜趋势股筛选，终端打印结果 | `python scripts/lhb_daily_screen.py` |
| `lhb_daily_alert.py` | 每日筛选 + 飞书 webhook 推送通知 | `python scripts/lhb_daily_alert.py` |
| `lhb_optimizer.py` | 参数网格搜索工具，用于寻找最优过滤条件 | `python scripts/lhb_optimizer.py` |

### 策略条件（lhb_2018_backtest v2 = lhb_daily_screen）

```
1.  非ST / 非异常波动
2.  换手率 3 ~ 10%
3.  流通市值 > 30亿
4.  净买额 > 3000万
5.  非一字板 / 非T字板
6.  MA20偏离 1.02 ~ 1.18
7.  RSI(14) 55 ~ 85
8.  距60日高 > -15%
9.  20日涨幅 > 15%
10. 量比 1.2 ~ 3.0
11. 5日涨幅 < 15%
```

### 2026 最优版条件（lhb_2026_optimized）

```
1.  非ST / 非异常波动
2.  非一字板 / 非T字板
3.  换手率 3 ~ 5%
4.  流通市值 > 20亿
5.  净买额 > 5000万
6.  MA20偏离 1.02 ~ 1.15
7.  RSI(14) 55 ~ 85
8.  20日涨幅 > 12%
9.  5日涨幅 < 25%
```

## 🔬 研究挖掘

| 脚本 | 作用 |
|------|------|
| `lhb_trend_strategy.py` | 龙虎榜 + K线趋势确认策略实验 |
| `lhb_kline_mining.py` | 龙虎榜上榜股的 K 线规律挖掘 |
| `lhb_pattern_mining.py` | 龙虎榜模式分析 |

## 💾 数据下载

| 脚本 | 作用 | 用法 |
|------|------|------|
| `backfill_baostock.py` | 用 baostock 补全 2018-2020 股票日线（推荐） | `python scripts/backfill_baostock.py` |
| `download_lhb_stocks.py` | 下载龙虎榜候选股票日线到本地数据库 | `python scripts/download_lhb_stocks.py` |
| `download_futures.py` | 下载期货品种日线（需 tushare fut_daily 权限） | `python scripts/download_futures.py` |
| `download_hourly_all.py` | 下载期货 1 小时 K 线 | `python scripts/download_hourly_all.py` |
| `download_rebar.py` | 下载螺纹钢期货数据 | `python scripts/download_rebar.py` |
| `sync_data.py` | 同步数据库已有品种到最新交易日 | `python scripts/sync_data.py` |

## 🐢 海龟交易策略

| 脚本 | 作用 |
|------|------|
| `run_backtest.py` | 海龟策略单品种回测 |
| `run_portfolio_backtest.py` | 海龟策略 20 品种组合回测 |
| `run_rebar_backtest.py` | 海龟策略螺纹钢回测 |

## 🔧 其他

| 脚本 | 作用 |
|------|------|
| `screen_dianjin.py` | 点金术基本面选股 |

## 📁 数据文件

| 文件 | 内容 |
|------|------|
| `lhb_2018_2026_trades.csv` | v2 全量回测 169 笔交易明细 |
| `lhb_2026_optimized_trades.csv` | 2026 最优版 11 笔交易明细 |
| `lhb_2026_full_trades.csv` | 2026 参数全量验证 79 笔 |
