"""Reusable business facts, not lists of database operators to exercise."""
import re
def params(i):
 start=i%23;end=52+i%38
 return dict(lo=1+(i*29)%850,hi=min(1201,1+(i*29)%850+180+(i%7)*25),start=start,end=end,split=(start+end)//2,horizon=5+i%10,lookback=7+i%14,decay=.02+(i%11)*.015,budget=1500+(i%31)*125,service=.85+(i%10)*.014,discount=.004+(i%11)*.002,month=21+(end-1)//30,m0=i%31,m1=160+i%150,risk=.05+(i%7)*.01,plant=i%8)

COMMERCE='''WITH selected AS (SELECT * FROM customers WHERE cid>={lo} AND cid<{hi}),
successful_cash AS (SELECT oid,SUM(paid) cash FROM payments WHERE success=1 AND day<{end} GROUP BY oid),
returned_cash AS (SELECT oid,SUM(refunded) returned FROM refunds WHERE day<{end} GROUP BY oid),
ledger_versions AS (SELECT l.*,ROW_NUMBER() OVER(PARTITION BY event_id ORDER BY revision_no DESC,entry_id DESC) version_rank FROM ledger l WHERE day<{end}),
ledger_cash AS (SELECT oid,SUM(amount) ledger_amount FROM ledger_versions WHERE version_rank=1 GROUP BY oid),
channel_volume AS (SELECT channel,day,COUNT(*) buyers FROM orders WHERE cancelled=0 GROUP BY channel,day),
order_costs AS (SELECT o.*,c.region,c.tier,c.signup,c.credit,COALESCE(p.cash,0) cash,COALESCE(r.returned,0) returned,COALESCE(l.ledger_amount,0) ledger_amount,
COALESCE(s.freight,0) freight,COALESCE(m.spend/v.buyers,0) marketing_cost,s.warehouse,s.carrier,s.promised_day,s.delivered_day,s.lost,
GREATEST(0,{end}-a.due_day) days_overdue,a.invoice,COALESCE(p.cash,0) collected
FROM orders o JOIN selected c ON o.cid=c.cid LEFT JOIN successful_cash p ON o.oid=p.oid LEFT JOIN returned_cash r ON o.oid=r.oid LEFT JOIN ledger_cash l ON o.oid=l.oid LEFT JOIN shipments s ON o.oid=s.oid LEFT JOIN channel_volume v ON o.channel=v.channel AND o.day=v.day LEFT JOIN campaigns m ON o.channel=m.channel AND o.day=m.day LEFT JOIN receivables a ON o.oid=a.oid WHERE o.cancelled=0 AND o.day BETWEEN {start} AND {end}-1),
order_facts AS (SELECT *,cash-returned net_revenue,cash-returned-cost-freight-marketing_cost contribution,CASE WHEN delivered_day<{end} THEN GREATEST(0,delivered_day-promised_day) ELSE NULL END late_days,GREATEST(0,invoice-collected) outstanding FROM order_costs),
customer_facts AS (SELECT c.cid,c.region,c.tier,c.credit,c.signup,COUNT(o.oid) orders,COALESCE(SUM(o.net_revenue),0) revenue,COALESCE(SUM(o.contribution),0) contribution,COALESCE(SUM(o.marketing_cost),0) acquisition_cost,COALESCE(SUM(o.returned),0) returned,COALESCE(SUM(o.outstanding),0) outstanding,{end}-COALESCE(MAX(o.day),c.signup) recency FROM selected c LEFT JOIN order_facts o ON c.cid=o.cid GROUP BY c.cid,c.region,c.tier,c.credit,c.signup),
product_facts AS (SELECT o.*,p.pid,p.category,i.qty,i.price,CAST(i.qty*i.price AS DOUBLE)/o.amount item_share FROM order_facts o JOIN items i ON o.oid=i.oid JOIN products p ON i.pid=p.pid)'''

SUBS=COMMERCE+''',
subscription_history AS (SELECT s.*,LAG(active) OVER(PARTITION BY s.cid ORDER BY month) prior_active,SUM(billed-paid) OVER(PARTITION BY s.cid ORDER BY month) arrears FROM subscriptions s JOIN selected c ON s.cid=c.cid WHERE month<={month}),
subscription_summary AS (SELECT cid,COUNT(*) n_months,SUM(billed) billed,SUM(paid) paid,SUM(active) active_months,MAX(CASE WHEN active=1 THEN month END) last_active,MIN(CASE WHEN active=0 THEN month END) first_pause,MAX(arrears) arrears,SUM(CASE WHEN prior_active=0 AND active=1 THEN 1 ELSE 0 END) reactivations FROM subscription_history GROUP BY cid),
subscription_customers AS (SELECT c.*,s.n_months,s.billed,s.paid,s.active_months,s.last_active,s.first_pause,s.arrears,s.reactivations FROM customer_facts c LEFT JOIN subscription_summary s ON c.cid=s.cid)'''

PRICING='''WITH selected_products AS (SELECT * FROM products WHERE category<>{plant}),
price_facts AS (SELECT p.pid,p.category,r.day,r.list_price,r.sale_price,r.units,r.promo,r.stockout,s.lead_days,s.unit_cost,i.on_hand,
AVG(r.units) OVER(PARTITION BY p.pid ORDER BY r.day ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) rolling_demand
FROM selected_products p JOIN prices r ON p.pid=r.pid JOIN suppliers s ON p.pid=s.pid LEFT JOIN inventory i ON p.pid=i.pid AND r.day=i.day WHERE r.day BETWEEN {start} AND {end}-1),
product_state AS (SELECT *,ROW_NUMBER() OVER(PARTITION BY pid ORDER BY day DESC) current_rank FROM price_facts),
supplier_facts AS (SELECT s.*,a.day,a.ordered,a.received,a.delay,a.received/a.ordered fill_rate FROM suppliers s JOIN selected_products p ON s.pid=p.pid JOIN supply a ON s.supplier=a.supplier WHERE a.day BETWEEN {start} AND {end}-1)'''

EXPERIMENT=COMMERCE+''',
experiment_facts AS (SELECT e.*,c.tier,c.region,COALESCE(c.contribution,0) past_margin FROM experiment e JOIN customer_facts c ON e.cid=c.cid WHERE e.day BETWEEN {start} AND {end}-1)'''

CREDIT=COMMERCE+''',
loan_asof AS (SELECT p.*,ROW_NUMBER() OVER(PARTITION BY loan_id ORDER BY day DESC) current_rank FROM loan_performance p WHERE day<{end}),
credit_facts AS (SELECT l.*,c.region,c.tier,COALESCE(c.credit,80) credit,p.day observed_day,COALESCE(p.balance,l.principal) balance,COALESCE(p.dpd,0) dpd,COALESCE(p.defaulted,0) defaulted FROM loans l JOIN selected c ON l.cid=c.cid LEFT JOIN loan_asof p ON l.loan_id=p.loan_id AND p.current_rank=1 WHERE l.opened<{end})'''

MARKET='''WITH prices_lag AS (SELECT *,LAG(close_price) OVER(PARTITION BY asset ORDER BY day) prior_close FROM market),
market_returns AS (SELECT *,LN(close_price/prior_close) log_return FROM prices_lag WHERE day BETWEEN {m0} AND {m1}),
market_facts AS (SELECT *,close_price/MAX(close_price) OVER(PARTITION BY asset ORDER BY day ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)-1 drawdown FROM market_returns)'''

OPERATIONS='''WITH selected_machines AS (SELECT * FROM machines WHERE plant<>{plant}),
plant_energy AS (SELECT site,day,SUM(kwh*tariff) energy_cost,SUM(kwh) kwh,SUM(kwh*carbon) emissions FROM energy WHERE day BETWEEN {start} AND {end}-1 GROUP BY site,day),
plant_capacity AS (SELECT plant,SUM(capacity) capacity FROM machines GROUP BY plant),
operation_facts AS (SELECT m.*,s.day,s.temperature,s.vibration,s.load_value,s.failure,s.downtime,p.output_units,p.defects,p.scrap_cost,e.energy_cost*m.capacity/c.capacity energy_cost,e.emissions*m.capacity/c.capacity emissions,
AVG(s.vibration) OVER(PARTITION BY m.machine ORDER BY s.day ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) rolling_vibration,
SUM(s.failure) OVER(PARTITION BY m.machine ORDER BY s.day ROWS BETWEEN 1 FOLLOWING AND 3 FOLLOWING) next_failures
FROM selected_machines m JOIN sensors s ON m.machine=s.machine JOIN production p ON m.machine=p.machine AND s.day=p.day JOIN plant_energy e ON m.plant=e.site AND s.day=e.day JOIN plant_capacity c ON m.plant=c.plant WHERE s.day BETWEEN {start} AND {end}-1)'''

SUPPORT=SUBS+''',
support_facts AS (SELECT t.*,c.tier,c.region,c.revenue,c.arrears FROM tickets t JOIN subscription_customers c ON t.cid=c.cid WHERE t.day BETWEEN {start} AND {end}-1),
support_customer AS (SELECT cid,COUNT(*) tickets,SUM(handle_minutes) handling,AVG(csat) csat,SUM(reopened) reopens FROM support_facts GROUP BY cid),
health_facts AS (SELECT s.*,COALESCE(t.tickets,0) tickets,COALESCE(t.handling,0) handling,COALESCE(t.csat,4) csat,COALESCE(t.reopens,0) reopens FROM subscription_customers s LEFT JOIN support_customer t ON s.cid=t.cid)'''

JOURNEY=COMMERCE+''',
journey_events AS (SELECT e.*,c.tier,c.region FROM events e JOIN selected c ON e.cid=c.cid WHERE day BETWEEN {start} AND {end}-1),
session_facts AS (SELECT cid,session_id,tier,region,MIN(day) AS day,MIN(CASE WHEN kind=0 THEN day END) view_day,MIN(CASE WHEN kind=1 THEN day END) detail_day,MIN(CASE WHEN kind=2 THEN day END) cart_day,MIN(CASE WHEN kind=3 THEN day END) checkout_day,MIN(CASE WHEN kind=4 THEN day END) purchase_day,COUNT(*) events FROM journey_events GROUP BY cid,session_id,tier,region)'''

FRAUD=COMMERCE+''',
payment_facts AS (SELECT f.*,c.region,c.tier FROM fraud_payments f JOIN selected c ON f.cid=c.cid WHERE day BETWEEN {start} AND {end}-1),
device_history AS (SELECT device,COUNT(DISTINCT cid) users,COUNT(*) payments,SUM(amount) volume FROM fraud_payments WHERE day<{start} GROUP BY device),
merchant_history AS (SELECT merchant,AVG(CAST(chargeback AS DOUBLE)) prior_loss FROM fraud_payments WHERE day<{start} GROUP BY merchant),
fraud_features AS (SELECT f.*,COALESCE(d.users,1) shared_users,COALESCE(d.volume,0) prior_volume,COALESCE(m.prior_loss,0) prior_loss FROM payment_facts f LEFT JOIN device_history d ON f.device=d.device LEFT JOIN merchant_history m ON f.merchant=m.merchant)'''

def format_sql(sql,i):
 sql=sql.format(**params(i))
 return re.sub(r'(?<![\w.])\d+\.\d+(?![\w.])',lambda m:'CAST('+m[0]+' AS DOUBLE)',sql)
