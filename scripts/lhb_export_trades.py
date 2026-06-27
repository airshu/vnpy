"""导出3年所有交易明细到CSV"""
import akshare as ak; import pandas as pd; import numpy as np
from datetime import datetime, timedelta
from vnpy.trader.database import get_database
from vnpy.trader.constant import Exchange, Interval

df=ak.stock_lhb_detail_em(start_date='20230101',end_date='20251231')
df['涨']=pd.to_numeric(df['涨跌幅'],errors='coerce');df['换']=pd.to_numeric(df['换手率'],errors='coerce')
df['净']=pd.to_numeric(df['龙虎榜净买额'],errors='coerce')/10000;df['市']=pd.to_numeric(df['流通市值'],errors='coerce')
df['因']=df['上榜原因'].astype(str);df['日']=pd.to_datetime(df['上榜日'])
m=(df['涨']>=9.8)&~df['因'].str.contains('ST|连续|异常',na=False)&(df['换']>=3)&(df['换']<=10)&(df['市']>30)&(df['净']>3000)
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
    h60=float(max(hi[idx-59:idx+1]))
    if (c-h60)/h60*100<-15: continue
    if (c/cl[idx-20]-1)*100<5: continue
    av5=np.mean(vo[idx-4:idx+1]);av20=np.mean(vo[idx-19:idx+1])
    if av5/av20<1.2 or av5/av20>3.0: continue
    ret5=(c/cl[idx-5]-1)*100 if idx>=5 else 0
    if ret5>=15: continue
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
    if nb.open_price>=lb.close_price*1.098: continue
    buy=nb.open_price;sell=sb.open_price;ret=(sell-buy)/buy*100
    trades.append([d.strftime('%Y-%m-%d'),row['名称'],sym,
                   nb.datetime.strftime('%Y-%m-%d'),round(buy,2),
                   sb.datetime.strftime('%Y-%m-%d'),round(sell,2),
                   round(ret,2),round(row['净'],0),round(row['换'],1),
                   round((c/cl[idx-20]-1)*100),round(rsi),ud])

cols=['上榜日','股票','代码','买日','买价','卖日','卖价','盈亏%','净买万','换手%','20日涨','RSI','连板']
df_out=pd.DataFrame(trades,columns=cols)
df_out.to_csv('scripts/lhb_227trades.csv',index=False)
total=df_out['盈亏%'].sum();w=(df_out['盈亏%']>0).sum()
print(f'已保存 scripts/lhb_227trades.csv')
print(f'{len(df_out)}笔 总{total:+.1f}% 均{total/len(df_out):+.2f}% 胜{w}/{len(df_out)}({w/len(df_out)*100:.0f}%)')
