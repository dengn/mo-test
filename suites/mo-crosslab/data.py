"""Business-oriented synthetic facts with physical/accounting units and edge cases."""
import os
from pathlib import Path
import numpy as np,pandas as pd
import base_data as base
ROOT=Path(__file__).resolve().parent
DB=os.getenv('MO_CROSS_DATABASE','ds_cross_20261011')
SEED=2026101105;base.DB=DB;base.SEED=SEED
SCHEMAS=base.SCHEMAS.copy()
SCHEMAS.update({
 'shipments':'oid INT,warehouse INT,carrier INT,promised_day INT,delivered_day INT,freight DOUBLE,lost INT',
 'receivables':'oid INT,due_day INT,invoice DOUBLE,collected DOUBLE',
 'ledger':'entry_id INT,event_id INT,oid INT,day INT,amount DOUBLE,revision_no INT',
 'experiment':'cid INT,day INT,treatment INT,site INT,baseline DOUBLE,converted INT,revenue DOUBLE,latency DOUBLE,harm INT',
 'prices':'pid INT,day INT,list_price DOUBLE,sale_price DOUBLE,units DOUBLE,promo INT,stockout INT',
 'suppliers':'supplier INT,pid INT,country INT,lead_days INT,unit_cost DOUBLE',
 'supply':'supplier INT,pid INT,day INT,ordered DOUBLE,received DOUBLE,delay DOUBLE',
 'loans':'loan_id INT,cid INT,opened INT,principal DOUBLE,apr DOUBLE,term_days INT',
 'loan_performance':'loan_id INT,day INT,balance DOUBLE,dpd INT,defaulted INT',
 'machines':'machine INT,plant INT,kind INT,age DOUBLE,capacity DOUBLE',
 'sensors':'machine INT,day INT,temperature DOUBLE,vibration DOUBLE,load_value DOUBLE,failure INT,downtime DOUBLE',
 'production':'machine INT,day INT,output_units DOUBLE,defects DOUBLE,scrap_cost DOUBLE',
 'energy':'site INT,day INT,hour INT,kwh DOUBLE,tariff DOUBLE,carbon DOUBLE,capacity DOUBLE',
 'tickets':'ticket INT,cid INT,agent INT,kind INT,day INT,handle_minutes DOUBLE,wait_minutes DOUBLE,reopened INT,csat DOUBLE',
 'contracts':'contract_id INT,cid INT,start_day INT,term_days INT,booked DOUBLE,cost_to_serve DOUBLE',
 'fraud_payments':'payment INT,cid INT,merchant INT,device INT,day INT,amount DOUBLE,chargeback INT'
})
base.SCHEMAS=SCHEMAS
def connect(database=DB):return base.connect(database)
engine=base.engine
local_oracle=base.local_oracle
setup=base.setup

def tables():
 d=base.tables();rng=np.random.default_rng(SEED+20);o=d['orders'];n=len(o)
 # Include both right-censored subscriptions and customers paused immediately.
 d['subscriptions'].loc[d['subscriptions'].cid%5==0,'active']=1
 d['subscriptions'].loc[(d['subscriptions'].cid%29==0)&(d['subscriptions'].cid%5!=0),'active']=0
 journeys=[]
 for customer in range(1,1177):
  for session in range(12):
   day=int(rng.integers(customer%10,89));steps=1+int(rng.choice([0,1,2,3,4],p=[.15,.15,.20,.20,.30]))
   for step in range(steps):
    minute=step*7+int(rng.integers(0,4));journeys.append((len(journeys)+1,customer,day,customer*100+session,step,float(rng.uniform(0,3)),pd.Timestamp('2024-01-01')+pd.Timedelta(days=day,minutes=minute)))
 d['events']=pd.DataFrame(journeys,columns=['eid','cid','day','session_id','kind','value','ts'])
 promised=o.day.to_numpy()+2+o.oid.to_numpy()%5;delivered=promised+rng.integers(-2,7,n)
 d['shipments']=pd.DataFrame(dict(oid=o.oid,warehouse=o.oid%6,carrier=o.oid%4,promised_day=promised,delivered_day=delivered,freight=3+o.amount*.025,lost=(o.oid%97==0).astype(int)))
 paid=d['payments'].assign(v=lambda x:x.paid*x.success).groupby('oid').v.sum().reindex(o.oid).to_numpy()
 d['receivables']=pd.DataFrame(dict(oid=o.oid,due_day=o.day+14,invoice=o.amount,collected=paid))
 event=np.arange(1,n+1);extra=np.flatnonzero(event%17==0)
 ledger=pd.DataFrame(dict(entry_id=event,event_id=event,oid=o.oid,day=o.day+2,amount=paid,revision_no=np.zeros(n,dtype=int)))
 correction=ledger.iloc[extra].copy();correction.entry_id=np.arange(n+1,n+1+len(extra));correction.revision_no=1;correction.amount=correction.amount+np.where(correction.oid%3==0,.01,-.01)
 d['ledger']=pd.concat([ledger,correction],ignore_index=True)
 cid=np.repeat(np.arange(1,1201),6);day=np.tile(np.arange(6)*14+3,1200);treat=rng.integers(0,2,1200)[cid-1];site=cid%8
 baseline=np.nan_to_num(d['customers'].credit.to_numpy(),nan=80)[cid-1];p=np.clip(.16+baseline*.001+treat*(.015+.006*(site%3)),.02,.8);converted=(rng.random(len(cid))<p).astype(int)
 d['experiment']=pd.DataFrame(dict(cid=cid,day=day,treatment=treat,site=site,baseline=baseline,converted=converted,revenue=converted*rng.gamma(3,30,len(cid)),latency=100+site*5+treat*7+rng.normal(0,12,len(cid)),harm=(rng.random(len(cid))<(.025+treat*.01)).astype(int)))
 pid=np.repeat(np.arange(1,81),96);day=np.tile(np.arange(96),80);price=d['products'].price.to_numpy()[pid-1];promo=((pid+day)%13<3).astype(int);sale=price*(1-.12*promo+.015*np.sin(day/6))
 demand=(25+pid%17)*(sale/price)**(-1.3-(pid%4)*.25)*(1+.22*np.sin(day/7)+.08*(day%7==5));stockout=((pid*7+day)%31==0).astype(int)
 d['prices']=pd.DataFrame(dict(pid=pid,day=day,list_price=price,sale_price=sale,units=np.maximum(0,demand+rng.normal(0,2,len(pid)))*(1-.8*stockout),promo=promo,stockout=stockout))
 suppliers=np.arange(1,81);d['suppliers']=pd.DataFrame(dict(supplier=suppliers,pid=suppliers,country=suppliers%7,lead_days=2+suppliers%14,unit_cost=d['products'].price.to_numpy()*.45))
 sp=np.repeat(suppliers,14);day=np.tile(np.arange(14)*7,80);ordered=100+sp%30;received=ordered*np.clip(1-rng.exponential(.04,len(sp))-.08*(sp%9==0),.4,1)
 d['supply']=pd.DataFrame(dict(supplier=sp,pid=sp,day=day,ordered=ordered.astype(float),received=received,delay=np.maximum(-2,rng.normal(sp%5-1,1.5,len(sp)))))
 lc=np.repeat(np.arange(1,1201),3);lid=np.arange(1,len(lc)+1);opened=np.tile([0,15,30],1200);principal=500+lc%100*20;term=45+lid%45
 d['loans']=pd.DataFrame(dict(loan_id=lid,cid=lc,opened=opened,principal=principal.astype(float),apr=.04+lc%5*.012,term_days=term))
 plid=np.repeat(lid,3);pd_day=np.repeat(opened,3)+np.tile([20,40,60],len(lid));default=((plid*11)%53==0).astype(int)
 d['loan_performance']=pd.DataFrame(dict(loan_id=plid,day=pd_day,balance=np.repeat(principal,3)*(1-np.tile([.2,.4,.6],len(lid)))*(1-.3*default),dpd=np.where(default,30+plid%40,plid%11),defaulted=default))
 machine=np.arange(1,65);capacity=80+machine%8*10
 d['machines']=pd.DataFrame(dict(machine=machine,plant=machine%8,kind=machine%4,age=1+machine*.08,capacity=capacity.astype(float)))
 mm=np.repeat(machine,96);day=np.tile(np.arange(96),64);load=.45+.25*np.sin(day/8+mm/10)+rng.uniform(0,.2,len(mm));temp=55+load*25+mm%5+rng.normal(0,2,len(mm));vib=.3+mm*.012+load*.25+rng.normal(0,.08,len(mm));failure=((rng.random(len(mm))<(.007+.025*(vib>1)))).astype(int);downtime=failure*rng.uniform(1,8,len(mm))
 d['sensors']=pd.DataFrame(dict(machine=mm,day=day,temperature=temp,vibration=vib,load_value=load,failure=failure,downtime=downtime))
 output=capacity[mm-1]*load*(1-downtime/24);defects=output*np.clip(.015+.003*(temp-70)+rng.normal(0,.01,len(mm)),0,.2)
 d['production']=pd.DataFrame(dict(machine=mm,day=day,output_units=output,defects=defects,scrap_cost=defects*(4+mm%4)))
 site=np.repeat(np.arange(8),96*24);day=np.tile(np.repeat(np.arange(96),24),8);hour=np.tile(np.arange(24),8*96);kwh=50+site*8+20*np.sin((hour-6)*np.pi/12)+10*np.sin(day/7)+rng.normal(0,3,len(site));tariff=.08+.16*((hour>=17)&(hour<=21))+.04*((hour>=8)&(hour<=16))
 d['energy']=pd.DataFrame(dict(site=site,day=day,hour=hour,kwh=kwh,tariff=tariff,carbon=.35+.1*np.sin(hour/5),capacity=(110+site*7).astype(float)))
 tid=np.arange(1,12001);tc=tid%1200+1;kind=tid%5
 d['tickets']=pd.DataFrame(dict(ticket=tid,cid=tc,agent=tid%32,kind=kind,day=tid*19%96,handle_minutes=rng.gamma(2,6,len(tid))*(1+kind*.2),wait_minutes=rng.gamma(2,8,len(tid)),reopened=(tid%17==0).astype(int),csat=np.clip(rng.normal(4.1, .6,len(tid))-.2*(kind==3),1,5)))
 cc=np.repeat(np.arange(1,1201),2);contract_id=np.arange(1,len(cc)+1);start=np.tile([0,30],1200)+cc%11;terms=90+cc%4*30;booked=(30+cc%21)*terms/30
 d['contracts']=pd.DataFrame(dict(contract_id=contract_id,cid=cc,start_day=start,term_days=terms,booked=booked,cost_to_serve=booked*.25))
 pay=np.arange(1,6001);fc=pay*31%1200+1;device=(fc*17)%500;device=np.where(fc%23==0,fc%7,device)
 d['fraud_payments']=pd.DataFrame(dict(payment=pay,cid=fc,merchant=pay%80,device=device,day=pay*11%96,amount=rng.lognormal(4, .7,len(pay)),chargeback=((fc%23==0)&(pay%3==0)).astype(int)))
 return d
