"""Real dependency chains: analytical blocks combined into long scoring queries."""
import itertools,re
import numpy as np
BLOCKS={}
def block(name,sql):BLOCKS[name]=sql
block('commerce','''
pay_ok AS (SELECT oid,SUM(CASE WHEN success=1 THEN paid ELSE 0 END) paid FROM payments GROUP BY oid),
refund_ok AS (SELECT oid,SUM(refunded) refund FROM refunds GROUP BY oid),
commerce_order AS (SELECT o.*,COALESCE(p.paid,0)-COALESCE(r.refund,0) net FROM oo o LEFT JOIN pay_ok p ON o.oid=p.oid LEFT JOIN refund_ok r ON o.oid=r.oid),
commerce_customer AS (SELECT cid,SUM(net) x,AVG(amount-cost) y,SUM(amount-net)/NULLIF(SUM(amount),0) z FROM commerce_order WHERE cancelled=0 GROUP BY cid)''')
block('cohort','''
cohort_days AS (SELECT DISTINCT cid,day FROM ee),
cohort_seq AS (SELECT cid,day,day-CAST(ROW_NUMBER() OVER(PARTITION BY cid ORDER BY day) AS BIGINT) island FROM cohort_days),
cohort_streak AS (SELECT cid,island,COUNT(*) n FROM cohort_seq GROUP BY cid,island),
cohort_longest AS (SELECT cid,MAX(n) streak FROM cohort_streak GROUP BY cid),
cohort_session AS (SELECT cid,session_id,MIN(CASE WHEN kind=0 THEN day END) viewed,MAX(CASE WHEN kind=3 THEN day END) purchased FROM ee GROUP BY cid,session_id),
cohort_conv_rate AS (SELECT cid,AVG(CAST(CASE WHEN purchased>=viewed THEN 1 ELSE 0 END AS DOUBLE)) conv_rate FROM cohort_session GROUP BY cid),
cohort_customer AS (SELECT a.cid,CAST(a.streak AS DOUBLE) x,COALESCE(b.conv_rate,0) y,CAST({d1}-MAX(e.day) AS DOUBLE) z FROM cohort_longest a LEFT JOIN cohort_conv_rate b ON a.cid=b.cid JOIN ee e ON a.cid=e.cid GROUP BY a.cid,a.streak,b.conv_rate)''')
block('attribution','''
attribution_touch AS (SELECT o.cid,o.oid,o.amount,e.kind,EXP(-CAST({alpha} AS DOUBLE)*(o.day-e.day)) w FROM oo o JOIN ee e ON o.cid=e.cid AND e.day BETWEEN o.day-{k} AND o.day),
attribution_weight AS (SELECT cid,oid,amount,kind,w,SUM(w) OVER(PARTITION BY oid) total FROM attribution_touch),
attribution_channel AS (SELECT cid,kind,SUM(amount*w/total) rev FROM attribution_weight GROUP BY cid,kind),
attribution_probability AS (SELECT cid,kind,rev,rev/NULLIF(SUM(rev) OVER(PARTITION BY cid),0) p FROM attribution_channel),
attribution_customer AS (SELECT cid,SUM(rev) x,SUM(rev*kind)/NULLIF(SUM(rev),0) y,-SUM(p*LN(NULLIF(p,0))) z FROM attribution_probability GROUP BY cid)''')
block('time_series','''
time_daily AS (SELECT cid,day,SUM(amount) revenue FROM oo WHERE cancelled=0 GROUP BY cid,day),
time_grid AS (SELECT c.cid,d.day,COALESCE(a.revenue,0) revenue FROM selected_customers c CROSS JOIN calendar d LEFT JOIN time_daily a ON c.cid=a.cid AND d.day=a.day WHERE d.day BETWEEN {d0} AND {d1}-1),
time_rolling AS (SELECT cid,day,revenue,AVG(revenue) OVER(PARTITION BY cid ORDER BY day ROWS BETWEEN {window} PRECEDING AND CURRENT ROW) ma FROM time_grid),
time_delta AS (SELECT cid,day,revenue,ma,ma-LAG(ma) OVER(PARTITION BY cid ORDER BY day) delta FROM time_rolling),
time_regime AS (SELECT cid,day,revenue,ma,delta,AVG(delta) OVER(PARTITION BY cid ORDER BY day ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) trend FROM time_delta),
time_series_customer AS (SELECT cid,AVG(ma) x,STDDEV_POP(delta) y,SUM(COALESCE(trend,0)) z FROM time_regime GROUP BY cid)''')
block('statistics','''
statistics_order AS (SELECT cid,oid,day,amount,ROW_NUMBER() OVER(PARTITION BY cid ORDER BY amount,oid) rn,COUNT(*) OVER(PARTITION BY cid) n FROM oo),
statistics_median AS (SELECT cid,AVG(CASE WHEN rn IN(FLOOR((n+1)/2),FLOOR((n+2)/2)) THEN amount END) median FROM statistics_order GROUP BY cid),
statistics_fit AS (SELECT cid,AVG(CAST(day AS DOUBLE)) mx,AVG(amount) my,AVG(day*amount)-AVG(CAST(day AS DOUBLE))*AVG(amount) cov,VAR_POP(day) vx FROM statistics_order GROUP BY cid),
statistics_residual AS (SELECT o.cid,o.amount,m.median,o.amount-(f.my+(o.day-f.mx)*COALESCE(f.cov/NULLIF(f.vx,0),0)) residual FROM statistics_order o JOIN statistics_median m ON o.cid=m.cid JOIN statistics_fit f ON o.cid=f.cid),
statistics_customer AS (SELECT cid,AVG(ABS(amount-median)) x,AVG(residual*residual) y,SUM(CASE WHEN ABS(residual)<={threshold} THEN residual*residual/2 ELSE {threshold}*(ABS(residual)-{threshold}/2) END) z FROM statistics_residual GROUP BY cid)''')
block('graph','''
graph_first AS (SELECT c.cid,e.dst,e.weight FROM selected_customers c JOIN edges e ON c.cid=e.src WHERE e.dst<>c.cid),
graph_second AS (SELECT a.cid,e.dst,a.weight*e.weight weight FROM graph_first a JOIN edges e ON a.dst=e.src WHERE e.dst<>a.cid),
graph_paths AS (SELECT a.cid,e.dst,a.weight*e.weight weight FROM graph_second a JOIN edges e ON a.dst=e.src WHERE e.dst<>a.cid),
graph_neighbor AS (SELECT a.cid,a.dst,a.weight,c.credit,c.tier FROM graph_paths a JOIN customers c ON a.dst=c.cid),
graph_customer AS (SELECT cid,SUM(weight*credit)/NULLIF(SUM(CASE WHEN credit IS NOT NULL THEN weight ELSE 0 END),0) x,VAR_POP(credit) y,SUM(weight*tier)/NULLIF(SUM(weight),0) z FROM graph_neighbor GROUP BY cid)''')
block('market','''
market_lag AS (SELECT asset,day,close_price,LAG(close_price) OVER(PARTITION BY asset ORDER BY day) prev FROM market),
market_returns AS (SELECT asset,day,close_price,LN(close_price/prev) ret FROM market_lag WHERE day BETWEEN {m0} AND {m1}),
market_rolling AS (SELECT asset,day,close_price,ret,AVG(ret) OVER(PARTITION BY asset ORDER BY day ROWS BETWEEN 20 PRECEDING AND CURRENT ROW) ma,VAR_POP(ret) OVER(PARTITION BY asset ORDER BY day ROWS BETWEEN 20 PRECEDING AND CURRENT ROW) rv FROM market_returns),
market_peak AS (SELECT asset,day,ret,ma,rv,close_price/MAX(close_price) OVER(PARTITION BY asset ORDER BY day ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)-1 drawdown FROM market_rolling),
market_asset AS (SELECT asset,SUM(ret) growth,AVG(rv) volatility,MIN(drawdown) drawdown FROM market_peak GROUP BY asset),
market_customer AS (SELECT c.cid,a.growth*COALESCE(c.credit,0) x,a.volatility y,a.drawdown z FROM selected_customers c JOIN market_asset a ON MOD(c.cid,8)=a.asset)''')
block('inventory','''
inventory_period AS (SELECT i.pid,AVG(CAST(on_hand AS DOUBLE)) stock,AVG(CAST(CASE WHEN on_hand<lead_days THEN 1 ELSE 0 END AS DOUBLE)) shortage,MAX(lead_days) lead FROM inventory i WHERE day BETWEEN {d0} AND {d1}-1 GROUP BY i.pid),
inventory_category AS (SELECT p.category,AVG(i.shortage) shortage,AVG(i.stock) stock,AVG(CAST(i.lead AS DOUBLE)) lead FROM inventory_period i JOIN products p ON i.pid=p.pid GROUP BY p.category),
inventory_basket AS (SELECT o.cid,p.category,SUM(i.qty*i.price) spend FROM oo o JOIN items i ON o.oid=i.oid JOIN products p ON i.pid=p.pid GROUP BY o.cid,p.category),
inventory_exposure AS (SELECT a.cid,a.spend,b.shortage,b.stock,b.lead FROM inventory_basket a JOIN inventory_category b ON a.category=b.category),
inventory_customer AS (SELECT cid,SUM(spend*shortage)/NULLIF(SUM(spend),0) x,SUM(spend*stock)/NULLIF(SUM(spend),0) y,SUM(spend*lead)/NULLIF(SUM(spend),0) z FROM inventory_exposure GROUP BY cid)''')
block('marketing','''
marketing_counts AS (SELECT MOD(kind,4) channel,day,COUNT(*) n FROM ee GROUP BY MOD(kind,4),day),
marketing_alloc AS (SELECT e.cid,e.day,e.kind,c.spend/CAST(a.n AS DOUBLE) allocated FROM ee e JOIN marketing_counts a ON MOD(e.kind,4)=a.channel AND e.day=a.day JOIN campaigns c ON a.channel=c.channel AND a.day=c.day),
marketing_customer_cost AS (SELECT cid,SUM(allocated) allocated_cost,SUM(CASE WHEN kind=3 THEN allocated ELSE 0 END) conv_rates FROM marketing_alloc GROUP BY cid),
marketing_customer_rev AS (SELECT cid,SUM(amount-cost) margin FROM oo WHERE cancelled=0 GROUP BY cid),
marketing_customer AS (SELECT c.cid,COALESCE(r.margin,0)/NULLIF(c.allocated_cost,0) x,c.allocated_cost y,c.conv_rates/NULLIF(c.allocated_cost,0) z FROM marketing_customer_cost c LEFT JOIN marketing_customer_rev r ON c.cid=r.cid)''')
block('subscription','''
subscription_rows AS (SELECT s.*,s.billed-s.paid arrears FROM subscriptions s JOIN selected_customers c ON s.cid=c.cid WHERE month BETWEEN {s0} AND {s1}),
subscription_running AS (SELECT cid,month,active,arrears,SUM(arrears) OVER(PARTITION BY cid ORDER BY month ROWS BETWEEN 5 PRECEDING AND CURRENT ROW) backlog,LAG(active) OVER(PARTITION BY cid ORDER BY month) prev_active FROM subscription_rows),
subscription_lifecycle AS (SELECT cid,SUM(arrears) arrears,MAX(backlog) backlog,SUM(CASE WHEN active=1 AND prev_active=0 THEN 1 ELSE 0 END) reactivated,AVG(CAST(active AS DOUBLE)) active_retention FROM subscription_running GROUP BY cid),
subscription_credit AS (SELECT tier,AVG(credit) credit FROM selected_customers GROUP BY tier),
subscription_customer AS (SELECT c.cid,l.arrears/NULLIF(COALESCE(c.credit,t.credit),0) x,l.backlog y,l.active_retention+CAST(l.reactivated AS DOUBLE)/10 z FROM selected_customers c JOIN subscription_lifecycle l ON c.cid=l.cid LEFT JOIN subscription_credit t ON c.tier=t.tier)''')
OUTPUT={'commerce':'commerce_customer','cohort':'cohort_customer','attribution':'attribution_customer','time_series':'time_series_customer','statistics':'statistics_customer','graph':'graph_customer','market':'market_customer','inventory':'inventory_customer','marketing':'marketing_customer','subscription':'subscription_customer'}
NAMES=list(BLOCKS)
combos=list(itertools.combinations(NAMES,4));rng=np.random.default_rng(2026101103);rng.shuffle(combos)
COMBOS=combos[:30]+[tuple(NAMES[j] for j in sorted(rng.choice(10,6+(i%3),replace=False))) for i in range(10)]
assert len(COMBOS)==40

def parameters(i):
 lo=1+(i*23)%1050;return dict(lo=lo,hi=min(1201,lo+90+(i%9)*25),d0=i%19,d1=55+i%36,k=7+i%15,alpha=.01+(i%9)*.0125,threshold=150+(i%11)*31,window=6+i%15,m0=i%90,m1=180+i%150,s0=i%8,s1=15+i%9)

def profile(f):
 base=f if f<40 else (f-40)*4+3
 selected=COMBOS[base];depth=3+base%6 if base<30 else 12+(base-30)
 return selected,depth

def sql_for(f,i,rows=False,materialized=False):
 p=parameters(i);selected,depth=profile(f)
 ctes=['selected_customers AS (SELECT * FROM customers WHERE cid>={lo} AND cid<{hi})','oo AS (SELECT o.* FROM orders o JOIN selected_customers c ON o.cid=c.cid WHERE o.day BETWEEN {d0} AND {d1}-1)','ee AS (SELECT e.* FROM events e JOIN selected_customers c ON e.cid=c.cid WHERE e.day BETWEEN {d0} AND {d1}-1)']
 ctes.extend((OUTPUT[b]+' AS (SELECT cid,x,y,z FROM staged_'+b+')') if materialized else BLOCKS[b] for b in selected)
 feats=[];joins=[]
 for j,b in enumerate(selected):
  joins.append(f'LEFT JOIN {OUTPUT[b]} b{j} ON c.cid=b{j}.cid')
  for axis in ['x','y','z']:feats.append(f'COALESCE(b{j}.{axis},0) f{len(feats)+1}')
 n=len(feats);cols=['cid','tier','region']+[f'f{j+1}' for j in range(n)];colstr=','.join(cols)
 ctes.append('feature_raw AS (SELECT c.cid,c.tier,c.region,'+','.join(feats)+' FROM selected_customers c '+' '.join(joins)+')')
 # Each selected block affects the combined score through standardization.
 zs=[f'(f{j}-AVG(f{j}) OVER())/COALESCE(NULLIF(STDDEV_POP(f{j}) OVER(),0),1)' for j in range(1,n+1)]
 ctes.append('feature_normalized AS (SELECT '+colstr+','+'+'.join(zs)+f' normalized_score FROM feature_raw)')
 ctes.append('feedback_0 AS (SELECT '+colstr+',1/(1+EXP(-LEAST(30,GREATEST(-30,normalized_score/'+str(n)+')))) score FROM feature_normalized)')
 for j in range(1,depth+1):
  # Dependent risk updates; no padding CTEs. All original features contribute.
  mix=f'CAST({.12+.01*(j%7):.4f} AS DOUBLE)*score+CAST({.003+.001*(j%5):.4f} AS DOUBLE)*LN(1+ABS(f{1+(j% n)}))'
  ctes.append(f'feedback_{j} AS (SELECT {colstr},(score+1/(1+EXP(-LEAST(30,GREATEST(-30,{mix})))))/2 score FROM feedback_{j-1})')
 ctes.append(f'customer_rank AS (SELECT {colstr},score,ROW_NUMBER() OVER(PARTITION BY tier ORDER BY ROUND(score,9) DESC,cid) rn,NTILE({3+i%5}) OVER(PARTITION BY tier ORDER BY ROUND(score,9),cid) bucket FROM feedback_{depth})')
 # Every final query also joins KPI target budgets at the relevant cohort week.
 ctes.append('budget_join AS (SELECT r.*,t.revenue_target,t.risk_budget FROM customer_rank r JOIN targets t ON r.tier=t.tier AND t.week={d1}//7)'.replace('{d1}//7','FLOOR(({d1}-1)/7)'))
 feature_sum='+'.join(f'f{j}' for j in range(1,n+1))
 mode=f%5
 if rows:final=f'SELECT cid,tier,region,score,{feature_sum} feature_sum,score*({feature_sum}) weighted FROM budget_join ORDER BY cid'
 elif mode==0:final='SELECT tier,bucket,COUNT(*),AVG(score),SUM(score*risk_budget),SUM(f1),SUM(f2),SUM(f3) FROM budget_join GROUP BY tier,bucket ORDER BY tier,bucket'
 elif mode==1:final=f'SELECT cid,tier,rn,score,f1,f2,f3,{feature_sum} feature_sum FROM budget_join WHERE rn<={2+i%7} ORDER BY tier,rn'
 elif mode==2:final='SELECT tier,region,COUNT(*),AVG(score),VAR_POP(score),AVG(f1),AVG(f2),AVG(f3) FROM budget_join GROUP BY tier,region ORDER BY tier,region'
 elif mode==3:final=f'SELECT COUNT(*),SUM(score),VAR_POP(score),SUM(f1*f2),SUM({feature_sum}),SUM(score*({feature_sum})),SUM(CASE WHEN score>risk_budget THEN 1 ELSE 0 END) FROM budget_join'
 else:final='SELECT tier,bucket,COUNT(*),SUM(score),SUM(f1),SUM(score*risk_budget) FROM budget_join GROUP BY GROUPING SETS((tier,bucket),(tier),()) ORDER BY COALESCE(tier,-1),COALESCE(bucket,-1)'
 sql=('WITH '+',\n'.join(ctes)+'\n'+final).format(**p)
 # Scientific division literals must be DOUBLE on MySQL-compatible engines.
 sql=re.sub(r'(?<![\w.])\d+\.\d+(?![\w.])',lambda m:'CAST('+m[0]+' AS DOUBLE)',sql)
 # Avoid nested CAST generated for explicitly typed feedback constants.
 sql=re.sub(r'CAST\(CAST\(([^()]+) AS DOUBLE\) AS DOUBLE\)',r'CAST(\1 AS DOUBLE)',sql)
 return sql

def label(f):
 blocks,depth=profile(f)
 return ('chain_'+str(f)+'_'+'_'.join(blocks), 'long_sql' if f<40 else 'multi_stage_commit_rollback')

def complexity(f,i):
 s=sql_for(f,i,rows=f>=40)
 return {'sql_bytes':len(s.encode()),'sql_lines':len(s.splitlines()),'cte_count':s.count(' AS (SELECT'),'feedback_depth':profile(f)[1],'analytical_blocks':list(profile(f)[0]),'window_expressions':s.count(' OVER('),'join_count':len(re.findall(r'\bJOIN\b',s))}
