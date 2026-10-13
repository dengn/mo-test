"""Deterministic synthetic fixtures, imported from the validated source."""
import datetime as dt, decimal
from collections import defaultdict
from templates import DOMAIN_SPECS
D=decimal.Decimal
decimal.getcontext().prec=70
PROFILES=[('empty',0),('singleton',1),('pair',2),('sparse',8),('balanced',32),
 ('skewed',64),('null_heavy',96),('duplicate_events',96),('missing_dimensions',96),
 ('decimal_micro',64),('decimal_large',64),('cancelling_pairs',96),('unicode',64),
 ('leap_day',64),('year_boundary',64),('future_2038',64),('ties',96),
 ('high_cardinality',256),('out_of_order',128),('dense',1024)]

FACT_COLS='scenario_id INT, fact_id BIGINT, entity_id INT, category VARCHAR(32), event_time DATETIME, amount DECIMAL(24,6), quantity INT, state VARCHAR(24), channel VARCHAR(32), duration_ms BIGINT, note VARCHAR(200), code VARCHAR(64)'

SCHEMA={spec[0]:FACT_COLS for spec in DOMAIN_SPECS.values()}

SCHEMA.update({
 'entities':'scenario_id INT, entity_id INT, region VARCHAR(32), segment VARCHAR(32), joined_at DATE, display_name VARCHAR(100)',
 'entity_history':'scenario_id INT, entity_id INT, segment VARCHAR(32), valid_from DATETIME, valid_to DATETIME',
 'adjustments':'domain VARCHAR(32), scenario_id INT, adjustment_id BIGINT, fact_id BIGINT, amount DECIMAL(24,6)',
 'fx_rates':'scenario_id INT, currency VARCHAR(8), year INT, month INT, rate DECIMAL(12,6)',
})

COLNAMES={t:[c.strip().split()[0] for c in s.split(', ') if c.strip()] for t,s in SCHEMA.items()}

def scenarios():
    for p,(name,n) in enumerate(PROFILES):
        for seed in range(1,11):
            yield {'scenario_id':p*10+seed,'profile':name,'seed':seed,'rows_per_domain':n,
                   'entities':64 if name=='high_cardinality' else 16}

def fixtures():
    data={t:[] for t in SCHEMA}
    audit=[]
    for sc in scenarios():
        sid,seed,n,prof,ne=sc['scenario_id'],sc['seed'],sc['rows_per_domain'],sc['profile'],sc['entities']
        for e in range(1,ne+1):
            joined=dt.date(2023+(e+seed)%2,1+(e%12),1+(e%20))
            region=['华东','华南','EU','West'][((e*3)+seed)%4]
            segment=['SMB','enterprise','consumer'][(e+seed)%3]
            data['entities'].append((sid,e,region,segment,joined,f'客户_{sid}_{e}_Ω🙂'))
            data['entity_history'] += [(sid,e,'original',dt.datetime(1970,1,1),dt.datetime(2025,7,1)),
                                      (sid,e,'upgraded',dt.datetime(2025,7,1),dt.datetime(2040,1,1))]
        for y in (2024,2025,2026,2038):
            for m in range(1,13):
                for c,k in [('USD',1),('EUR',2),('CNY',3),('GBP',4)]:
                    data['fx_rates'].append((sid,c,y,m,D(k)/D(3)+D(seed)/D(1000)))
        for domidx,(domain,spec) in enumerate(DOMAIN_SPECS.items()):
            table,states,categories,_=spec
            amounts=[]
            for i in range(1,n+1):
                eid=(i*7+seed)%ne+1
                if prof=='skewed' and i%10!=0:eid=1
                if prof=='missing_dimensions' and i%4==0:eid=ne+99
                cyc=i-1
                if prof=='duplicate_events':cyc=(i-1)//2
                base=dt.datetime(2025,1,1)
                when=base+dt.timedelta(days=(cyc*17+seed*11)%365,seconds=(cyc*173+seed*31)%86400)
                if prof=='leap_day':when=dt.datetime(2024,2,28,23,59,59)+dt.timedelta(seconds=cyc*3600+seed)
                if prof=='year_boundary':when=dt.datetime(2025,12,31,23,59,59)+dt.timedelta(seconds=cyc*3600+seed-5)
                if prof=='future_2038':when=dt.datetime(2038,1,19,3,14,0)+dt.timedelta(seconds=cyc*173+seed)
                if prof=='out_of_order':when=base+dt.timedelta(days=(n-i)*2+seed)
                if prof=='dense':when=base+dt.timedelta(seconds=cyc*11+seed)
                if prof=='ties':when=base+dt.timedelta(days=cyc//8)
                amount=(D((i*3703+seed*109+domidx*47)%1000000)-D(1000))/D(1000)
                if prof=='decimal_micro':amount=D((i%7)-3)/D(1000000)
                if prof=='decimal_large':amount=D('9000000000000.123456')+D(i)/D(1000000)
                if prof=='cancelling_pairs':amount=D((i+1)//2)*D('17.123456')*(1 if i%2 else -1);eid=((i+1)//2)%ne+1
                if prof=='ties':amount=D((i%4)*100)
                if domain=='finance' and prof!='cancelling_pairs':amount*=1 if i%2 else -1
                if domain=='telemetry' and prof not in ('decimal_large','decimal_micro','cancelling_pairs'):amount=D((i*31+seed)%2000-1000)/D(10)
                quantity=(i*3+seed)%17
                if domain=='inventory' and i%3==0:quantity=-quantity
                state=states[cyc%3]
                category=categories[(cyc+seed)%4]
                channel=['organic','ads','邮件','direct'][(cyc+seed)%4]
                if i%11==0 or (prof=='null_heavy' and i%2==0):channel=None
                elif i%13==0:channel=''
                duration=(i*1000003+seed*997)%200000000
                if i%19==0:duration=0
                if i%17==0 or (prof=='null_heavy' and i%3==0):duration=None
                note='普通'
                if prof=='unicode':note=["中文🙂Ω", "quote'\\line\nnext", '', 'NULL'][i%4]
                if prof=='null_heavy' and i%2:note=None
                # Duplicate fingerprints intentionally preserve same entity and
                # event state/time/category, while physical fact IDs differ.
                if prof=='duplicate_events':eid=(cyc*7+seed)%ne+1
                code=None if i%9==0 else f'K{(cyc+seed)%23}'
                row=(sid,i,eid,category,when,amount.quantize(D('.000001')),quantity,state,channel,duration,note,code)
                data[table].append(row);amounts.append(row[5])
                if i%5==0:
                    for split,rate in enumerate([D('.10'),D('.02')] if i%10==0 else [D('.10')]):
                        data['adjustments'].append((domain,sid,i*10+split,i,(row[5]*rate).quantize(D('.000001'))))
            audit.append({'domain':domain,'scenario_id':sid,'row_count':n,'python_decimal_sum':str(sum(amounts,D(0)))})
    return data,audit
