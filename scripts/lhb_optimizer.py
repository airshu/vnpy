"""
龙虎榜策略 · 参数优化器
从全量基线数据中测试不同条件组合，寻找最优策略
"""
import akshare as ak, pandas as pd, numpy as np
from datetime import datetime, timedelta
from vnpy.trader.database import get_database
from vnpy.trader.constant import Exchange, Interval

db = get_database()

# ===== Step 1: 加载2026基线和K线特征 =====
print("[1/3] 加载基线数据...")
baseline = pd.read_csv('scripts/lhb_2026_all_baseline.csv')

# 补充龙虎榜原始字段
print("[2/3] 补充龙虎榜字段...")
df_lhb = ak.stock_lhb_detail_em(start_date='20260101', end_date='20260625')
df_lhb['上榜日'] = pd.to_datetime(df_lhb['上榜日'])
df_lhb['涨跌幅'] = pd.to_numeric(df_lhb['涨跌幅'], errors='coerce')
df_lhb['换手率'] = pd.to_numeric(df_lhb['换手率'], errors='coerce')
df_lhb['净买额'] = pd.to_numeric(df_lhb['龙虎榜净买额'], errors='coerce') / 10000
df_lhb['流通市值'] = pd.to_numeric(df_lhb['流通市值'], errors='coerce')
df_lhb['原因'] = df_lhb['上榜原因'].astype(str)
df_lhb['代码'] = df_lhb['代码'].astype(str)

baseline['上榜日'] = pd.to_datetime(baseline['上榜日'])
baseline['代码'] = baseline['代码'].astype(str)
df_lhb['代码'] = df_lhb['代码'].astype(str)

# Merge
merged = baseline.merge(
    df_lhb[['代码','上榜日','涨跌幅','换手率','净买额','流通市值','原因']],
    on=['代码','上榜日'], how='left'
)

# 计算K线特征
print("[3/3] 计算K线特征...")
features = []
for i, row in merged.iterrows():
    if i % 500 == 0:
        print(f"  {i}/{len(merged)}...")
    
    sym = row['代码'].zfill(6)
    ex = Exchange.SSE if sym.startswith('6') else Exchange.SZSE
    d = row['上榜日']
    
    bars = db.load_bar_data(sym, ex, Interval.DAILY,
        start=(d-timedelta(days=150)).strftime('%Y-%m-%d'),
        end=(d+timedelta(days=1)).strftime('%Y-%m-%d'))
    
    if bars is None or len(bars) < 60:
        features.append(None)
        continue
    
    closes = np.array([b.close_price for b in bars])
    highs = np.array([b.high_price for b in bars])
    vols = np.array([b.volume for b in bars])
    
    idx = next((j for j,b in enumerate(bars) if b.datetime.date()==d.date()), None)
    if idx is None or idx < 60:
        features.append(None)
        continue
    
    c = closes[idx]; tb = bars[idx]; pc = closes[idx-1]
    
    # MA20
    ma20 = np.mean(closes[idx-19:idx+1])
    ma20_r = c / ma20
    
    # RSI
    g,l2 = [],[]
    for k in range(idx-13, idx+1):
        dd = closes[k]-closes[k-1]
        g.append(dd if dd>0 else 0)
        l2.append(-dd if dd<0 else 0)
    rsi = 100-100/(1+np.mean(g)/np.mean(l2)) if np.mean(l2)>0 else 100
    
    # 20日涨幅
    ret20 = (c/closes[idx-20]-1)*100 if idx>=20 else 0
    
    # 5日涨幅
    ret5 = (c/closes[idx-5]-1)*100 if idx>=5 else 0
    
    # 量比
    vr = np.mean(vols[idx-4:idx+1])/np.mean(vols[idx-19:idx+1]) if idx>=20 else 0
    
    # 距60日高
    h60 = float(max(highs[idx-59:idx+1]))
    dist60 = (c-h60)/h60*100
    
    # 一字/T字板
    is_oneside = (tb.open_price >= pc*1.098 or tb.low_price >= pc*1.098)
    
    # ST
    is_st = 'ST' in str(row.get('原因','')) or 'ST' in str(row.get('名称',''))
    
    features.append({
        'ma20_r': round(ma20_r, 3),
        'rsi': round(rsi, 1),
        'ret20': round(ret20, 1),
        'ret5': round(ret20, 1),  # actually ret20
        'vr': round(vr, 2),
        'dist60': round(dist60, 1),
        'is_oneside': is_oneside,
        'is_st': is_st,
    })

# Attach features
merged['ma20_r'] = [f['ma20_r'] if f else None for f in features]
merged['rsi'] = [f['rsi'] if f else None for f in features]
merged['ret20'] = [f['ret20'] if f else None for f in features]
merged['ret5'] = merged['ret20']  # use ret20 for ret5
merged['vr'] = [f['vr'] if f else None for f in features]
merged['dist60'] = [f['dist60'] if f else None for f in features]
merged['is_oneside'] = [f['is_oneside'] if f else True for f in features]
merged['is_st'] = [f['is_st'] if f else False for f in features]

# Actual ret5 calculation
print("  计算5日涨幅...")
ret5_list = []
for i, row in merged.iterrows():
    if i % 500 == 0: print(f"  {i}/{len(merged)}...")
    sym = row['代码'].zfill(6)
    ex = Exchange.SSE if sym.startswith('6') else Exchange.SZSE
    bars = db.load_bar_data(sym, ex, Interval.DAILY,
        start=(row['上榜日']-timedelta(days=10)).strftime('%Y-%m-%d'),
        end=(row['上榜日']+timedelta(days=1)).strftime('%Y-%m-%d'))
    if bars and len(bars)>=6:
        cl = np.array([b.close_price for b in bars])
        idx = next((j for j,b in enumerate(bars) if b.datetime.date()==row['上榜日'].date()), None)
        if idx and idx>=5:
            ret5_list.append(round((cl[idx]/cl[idx-5]-1)*100, 1))
        else:
            ret5_list.append(None)
    else:
        ret5_list.append(None)
merged['ret5'] = ret5_list

# Save with features
merged.to_csv('scripts/lhb_2026_features.csv', index=False)
print(f"\n特征保存: scripts/lhb_2026_features.csv ({len(merged)} 条)")

# ===== Step 2: 参数优化 =====
print("\n" + "="*60)
print("  参数优化")
print("="*60)

# Define test ranges
param_grid = {
    'ma20_lo': [1.02, 1.03, 1.05],
    'ma20_hi': [1.15, 1.18, 1.20, 1.25],
    'rsi_lo': [55, 50],
    'rsi_hi': [85, 80],
    'ret20_lo': [15, 10, 5],
    'ret5_hi': [15, 20, 25],
    'vr_lo': [1.2, 1.0],
    'vr_hi': [3.0, 3.5],
    'dist60_lo': [-15, -20, -25],
    'no_st': [True],
    'no_oneside': [True],
    'hs_lo': [3, 2, 1],
    'hs_hi': [10, 15],
    'mcap_lo': [30, 20],
    'netbuy_lo': [3000, 2000, 1000],
}

data = merged.dropna(subset=['盈亏%','ma20_r','rsi','ret20','vr','dist60'])

def evaluate(params):
    """评估一组参数"""
    mask = pd.Series(True, index=data.index)
    
    if params.get('no_st', False):
        mask &= ~data['is_st']
    if params.get('no_oneside', False):
        mask &= ~data['is_oneside']
    if 'hs_lo' in params:
        mask &= data['换手率'] >= params['hs_lo']
    if 'hs_hi' in params:
        mask &= data['换手率'] <= params['hs_hi']
    if 'mcap_lo' in params:
        mask &= data['流通市值'] > params['mcap_lo']
    if 'netbuy_lo' in params:
        mask &= data['净买额'] > params['netbuy_lo']
    if 'ma20_lo' in params:
        mask &= data['ma20_r'] >= params['ma20_lo']
    if 'ma20_hi' in params:
        mask &= data['ma20_r'] <= params['ma20_hi']
    if 'rsi_lo' in params:
        mask &= data['rsi'] >= params['rsi_lo']
    if 'rsi_hi' in params:
        mask &= data['rsi'] <= params['rsi_hi']
    if 'ret20_lo' in params:
        mask &= data['ret20'] >= params['ret20_lo']
    if 'ret5_hi' in params:
        mask &= data['ret5'] <= params['ret5_hi']
    if 'vr_lo' in params:
        mask &= data['vr'] >= params['vr_lo']
    if 'vr_hi' in params:
        mask &= data['vr'] <= params['vr_hi']
    if 'dist60_lo' in params:
        mask &= data['dist60'] >= params['dist60_lo']
    
    filtered = data[mask]
    if len(filtered) < 5:
        return None
    
    total = filtered['盈亏%'].sum()
    avg = filtered['盈亏%'].mean()
    win = (filtered['盈亏%']>0).sum()
    wr = win/len(filtered)*100
    
    # 综合评分: 总收益 + 胜率 + 笔数
    score = total * 0.6 + wr * 0.2 + min(len(filtered)/30, 1) * 100 * 0.2
    
    return {
        'trades': len(filtered),
        'total': round(total, 1),
        'avg': round(avg, 2),
        'win_rate': round(wr, 1),
        'score': round(score, 1),
        'params': params,
    }

# 当前策略基准
current = evaluate({
    'no_st': True, 'no_oneside': True,
    'hs_lo': 3, 'hs_hi': 10, 'mcap_lo': 30, 'netbuy_lo': 3000,
    'ma20_lo': 1.02, 'ma20_hi': 1.18,
    'rsi_lo': 55, 'rsi_hi': 85,
    'ret20_lo': 15, 'ret5_hi': 15,
    'vr_lo': 1.2, 'vr_hi': 3.0,
    'dist60_lo': -15,
})
print(f"\n  当前策略: {current['trades']}笔 总{current['total']:+.1f}%  胜率{current['win_rate']}%  评分{current['score']}")

# Test: relax one condition at a time
tests = [
    ("放宽MA20上限", {'ma20_hi': [1.22, 1.25, 1.28, 1.30]}),
    ("放宽换手率", {'hs_lo': [1, 2], 'hs_hi': [15, 20]}),
    ("放宽净买额", {'netbuy_lo': [500, 1000, 2000]}),
    ("放宽流通市值", {'mcap_lo': [10, 20]}),
    ("放宽RSI", {'rsi_lo': [45, 50], 'rsi_hi': [80, 90]}),
    ("放宽20日涨幅", {'ret20_lo': [5, 10, 12]}),
]

best = current
print("\n  单项优化:")
print(f"  {'条件':<16} {'参数':>18} {'笔数':>5} {'总盈亏':>8} {'均':>7} {'胜率':>6}")
print(f"  {'-'*65}")

for label, test_params in tests:
    for key, vals in test_params.items():
        for v in vals:
            p = current['params'].copy()
            p[key] = v
            # 更新相关参数名
            if key.startswith('ma20'):
                if 'hi' in key: p['ma20_hi'] = v
                else: p['ma20_lo'] = v
            elif key.startswith('rsi'):
                if 'hi' in key: p['rsi_hi'] = v
                else: p['rsi_lo'] = v
            elif key.startswith('hs'):
                if 'hi' in key: p['hs_hi'] = v
                else: p['hs_lo'] = v
            elif key == 'netbuy_lo': p['netbuy_lo'] = v
            elif key == 'mcap_lo': p['mcap_lo'] = v
            elif key == 'ret20_lo': p['ret20_lo'] = v
            
            # 运行评估时用真实的key值
            e = evaluate(p)
            if e:
                star = '⭐' if e['score'] > best['score'] else '  '
                mark = f'{label[:14]:<14} {key}={v:<10}' 
                print(f"  {star} {mark:<30} {e['trades']:>4}  {e['total']:>+7.1f}% {e['avg']:>+6.2f}% {e['win_rate']:>5.1f}%")
                if e['score'] > best['score']:
                    best = e

print(f"\n  最优: {best['trades']}笔 总{best['total']:+.1f}%  胜率{best['win_rate']}%")
print(f"  参数: {best['params']}")

# ===== Step 3: 组合测试 =====
print(f"\n{'='*60}")
print(f"  组合优化")
print(f"{'='*60}")

combos = [
    ("放宽ret20+netbuy", {'ret20_lo': 10, 'netbuy_lo': 500}),
    ("放宽ret20+hs_hi", {'ret20_lo': 10, 'hs_hi': 15}),
    ("放宽netbuy+hs_hi", {'netbuy_lo': 500, 'hs_hi': 15}),
    ("放宽ret20+netbuy+hs_hi", {'ret20_lo': 10, 'netbuy_lo': 500, 'hs_hi': 15}),
    ("放宽三件+ma20", {'ret20_lo': 10, 'netbuy_lo': 500, 'hs_hi': 15, 'ma20_hi': 1.22}),
    ("只留核心条件", {'no_st': True, 'no_oneside': True, 'ma20_lo': 1.02, 'ma20_hi': 1.18, 'rsi_lo': 55, 'rsi_hi': 85}),
    ("只留ma20+rsi+ret20", {'no_st': True, 'no_oneside': True, 'ma20_lo': 1.02, 'ma20_hi': 1.18, 'rsi_lo': 55, 'rsi_hi': 85, 'ret20_lo': 10}),
]

print(f"  {'方案':<25} {'笔数':>5} {'总盈亏':>8} {'均':>7} {'胜率':>6}")
print(f"  {'-'*55}")

combo_best = best
for name, extras in combos:
    p = current['params'].copy()
    for k, v in extras.items():
        p[k] = v
    e = evaluate(p)
    if e:
        star = '⭐' if e['score'] > combo_best['score'] else '  '
        print(f"  {star} {name:<23} {e['trades']:>4}  {e['total']:>+7.1f}% {e['avg']:>+6.2f}% {e['win_rate']:>5.1f}%")
        if e['score'] > combo_best['score']:
            combo_best = e

print(f"\n  组合最优: {combo_best['trades']}笔 总{combo_best['total']:+.1f}%  胜率{combo_best['win_rate']}%")
print(f"  参数: {combo_best['params']}")