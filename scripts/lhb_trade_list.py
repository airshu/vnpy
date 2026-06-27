"""列出所有交易明细"""
import akshare as ak; import pandas as pd; import numpy as np
from datetime import datetime, timedelta
from vnpy.trader.database import get_database
from vnpy.trader.constant import Exchange, Interval

end=datetime(2026,6,24);start=end-timedelta(days=365)
df=ak.stock_lhb_detail_em(start_date=start.strftime('%Y%m%d'),end_date=end.strftime('%Y%m%d'))
df['涨']=pd.to_numeric(df['涨跌幅'],errors='coerce');df['换']=pd.to_numeric(df['换手率'],errors='coerce')
df['净']=pd.to_numeric(df['龙虎榜净买额'],errors='coerce')/10000;df['市']=pd.to_numeric(df['流通市值'],errors='coerce')
df['因']=df['上榜原因'].astype(str);df['日']=pd.to_datetime(df['上榜日'])
m=(df['涨']>=9.8)&~df['因'].str.contains('ST|连续|异常',na=False)&(df['换']>=3)&(df['换']<=10)&(df['市']>30)&(df['净']>1000)
base=df[m].copy();db=get_database()
trades=[]

for _,row in base.iterrows():
    sym=str(row['代码']).zfill(6);ex=Exchange.SSE if sym[0]=='6' else Exchange.SZSE;d=row['日']
    bars=db.load_bar_data(sym,ex,Interval.DAILY,start=(d-timedelta(days=150)).strftime('%Y-%m-%d'),end=(d+timedelta(days=1)).strftime('%Y-%m-%d'))
    if bars is None or len(bars)<60: continue
    cl=np.array([b.close_price for b in bars]);hi=np.array([b.high_price for b in bars]);vo=np.array([b.volume for b in bars])
    idx=next((i for i,b in enumerate(bars) if b.datetime.date()==d.date()),None)
    if idx is None or idx<20: continue
    c=cl[idx];tb=bars[idx];pc=cl[idx-1]
    if tb.open_price>=pc*1.098 or tb.low_price>=pc*1.098: continue
    if c/np.mean(cl[idx-19:idx+1])<1.02: continue
    g,l2=[],[]
    for i in range(idx-13,idx+1): dd=cl[i]-cl[i-1];g.append(dd if dd>0 else 0);l2.append(-dd if dd<0 else 0)
    rsi=100-100/(1+np.mean(g)/np.mean(l2)) if np.mean(l2)>0 else 100
    if rsi<55 or rsi>85: continue
    if (c-float(max(hi[idx-59:idx+1])))/float(max(hi[idx-59:idx+1]))*100<-15: continue
    if (c/cl[idx-20]-1)*100<5: continue
    av5=np.mean(vo[idx-4:idx+1]);av20=np.mean(vo[idx-19:idx+1])
    if av5/av20<1.2 or av5/av20>3.0: continue
    if idx>=5 and (c/cl[idx-5]-1)*100>=15: continue
    ud=0
    for i in range(idx,0,-1):
        if cl[i]>cl[i-1]*1.095: ud+=1
        else: break
    if ud>1: continue

    b2=db.load_bar_data(sym,ex,Interval.DAILY,start=(d-timedelta(days=1)).strftime('%Y-%m-%d'),end=(d+timedelta(days=5)).strftime('%Y-%m-%d'))
    if b2 is None or len(b2)<3: continue
    lb=next((b for b in b2 if b.datetime.date()==d.date()),None)
    nb=next((b for b in b2 if b.datetime.date()>d.date()),None)
    sb=next((b for b in b2 if b.datetime.date()>(nb.datetime.date() if nb else d.date())),None)
    if not lb or not nb or not sb: continue
    bp=nb.open_price;sp=sb.open_price
    if bp>=lb.close_price*1.098: continue
    ret=(sp/bp-1)*100
    trades.append({'上榜日':d.strftime('%Y-%m-%d'),'股票':row['名称'],'代码':sym,
                   '买日':nb.datetime.strftime('%Y-%m-%d'),'买价':round(bp,2),
                   '卖日':sb.datetime.strftime('%Y-%m-%d'),'卖价':round(sp,2),
                   '盈亏%':round(ret,2),'盈':ret>0})

pd.DataFrame(trades).to_csv('scripts/lhb_trades_1y.csv', index=False)

print(f'共 {len(trades)} 笔\n')
hdr = "上榜日      股票        买日        买价    卖日        卖价    盈亏%"
print(f"共 {len(trades)} 笔\n")
print(hdr)
print("-" * 72)
print('-'*72)
for t in trades:
    c='✅' if t['盈'] else '❌'
    c_icon = "✅" if t["盈"] else "❌"
    print(f'{c_icon} {t["上榜日"]} {t["股票"]:<10} {t["买日"]} {t["买价"]:>8.2f} {t["卖日"]} {t["卖价"]:>8.2f} {t["盈亏%"]:>+6.1f}%')

rets=[t['盈亏%'] for t in trades];wins=sum(1 for t in trades if t['盈'])
print(f'\n均{np.mean(rets):+.2f}%  胜{wins}/{len(trades)}  累计{(np.cumprod([1+r/100 for r in rets])[-1]-1)*100:+.1f}%')
