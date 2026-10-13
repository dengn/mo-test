"""Deterministic synthetic fixtures, imported from the validated source."""
import datetime as dt, decimal
from collections import defaultdict
D=decimal.Decimal
decimal.getcontext().prec=70
SCHEMA = {
 'customers': 'customer_id BIGINT PRIMARY KEY, region VARCHAR(40), segment VARCHAR(20), signup_date DATE, customer_name VARCHAR(100)',
 'products': 'product_id INT PRIMARY KEY, category VARCHAR(30), unit_cost DECIMAL(18,4)',
 'orders': 'order_id BIGINT PRIMARY KEY, customer_id BIGINT, product_id INT, order_date DATE, quantity INT, gross DECIMAL(18,4), discount DECIMAL(18,4), status VARCHAR(20), campaign VARCHAR(40)',
 'refunds': 'refund_id BIGINT PRIMARY KEY, order_id BIGINT, amount DECIMAL(18,4)',
 'events': 'event_id BIGINT PRIMARY KEY, customer_id BIGINT, event_time DATETIME, event_type VARCHAR(20), session_id BIGINT',
 'edge_values': 'id INT PRIMARY KEY, val DECIMAL(30,8), label VARCHAR(120), event_time DATETIME, json_text VARCHAR(1000)',
 'ledger': 'id BIGINT PRIMARY KEY, balance DECIMAL(18,4)',
}

def data(n=100000):
    D=decimal.Decimal
    customers=[(i,['华东','华南','华北','West','EU'][i%5],['SMB','Enterprise','Consumer'][i%3],dt.date(2024,1,1)+dt.timedelta(days=i%365),f'客户_{i}_Ω') for i in range(1,10001)]
    products=[(i,['Electronics','Home','Food','Fashion'][i%4],D(i%150+1)/10) for i in range(1,1001)]
    orders=[]; refunds=[]
    for i in range(1,n+1):
        gross=D(((i*37)%100000)+1)/100; discount=gross*D('0.05') if i%7==0 else D('0')
        orders.append((i,(i*17)%10000+1,(i*13)%1000+1,dt.date(2025,1,1)+dt.timedelta(days=i%365),i%5+1,gross,discount,'cancelled' if i%19==0 else 'paid',None if i%11==0 else ['organic','ads','邮件'][i%3]))
        if i%23==0 and i%19!=0:
            refunds.append((len(refunds)+1,i,gross*D('.10')))
            if i%46==0: refunds.append((len(refunds)+1,i,gross*D('.02')))
    events=[]
    for i in range(1,10001):
        base=dt.datetime(2025,1,1)+dt.timedelta(days=i%90,seconds=i%3600)
        events.append((len(events)+1,i,base,'view',i))
        if i%2==0: events.append((len(events)+1,i,base+dt.timedelta(minutes=1),'cart',i))
        if i%4==0: events.append((len(events)+1,i,base+dt.timedelta(minutes=3),'purchase',i))
        if i%10==0: events.append((len(events)+1,i,base+dt.timedelta(minutes=4),'view',i))
    edge=[(1,D('0.00000001'),'中文🙂',dt.datetime(2024,2,29,23,59,59),'{"k":1,"arr":[1,2]}'),
          (2,D('-0.00000001'),"quote'\\\n",dt.datetime(1970,1,1),'{}'),
          (3,D('99999999999999999999.12345678'),'',dt.datetime(2038,1,19,3,14,7),'{"k":null}'),
          (4,None,None,None,None),(5,D('-99999999999999999999.12345678'),'Ω',dt.datetime(2025,12,31),'{"k":2}')]
    return {'customers':customers,'products':products,'orders':orders,'refunds':refunds,'events':events,'edge_values':edge,'ledger':[(1,D('100')),(2,D('100'))]}
