WITH selected AS (SELECT * FROM customers WHERE cid>=50 AND cid<305),
successful_cash AS (SELECT oid,SUM(paid) cash FROM payments WHERE success=1 AND day<83 GROUP BY oid),
returned_cash AS (SELECT oid,SUM(refunded) returned FROM refunds WHERE day<83 GROUP BY oid),
ledger_versions AS (SELECT l.*,ROW_NUMBER() OVER(PARTITION BY event_id ORDER BY revision_no DESC,entry_id DESC) version_rank FROM ledger l WHERE day<83),
ledger_cash AS (SELECT oid,SUM(amount) ledger_amount FROM ledger_versions WHERE version_rank=1 GROUP BY oid),
channel_volume AS (SELECT channel,day,COUNT(*) buyers FROM orders WHERE cancelled=0 GROUP BY channel,day),
order_costs AS (SELECT o.*,c.region,c.tier,c.signup,c.credit,COALESCE(p.cash,0) cash,COALESCE(r.returned,0) returned,COALESCE(l.ledger_amount,0) ledger_amount,
COALESCE(s.freight,0) freight,COALESCE(m.spend/v.buyers,0) marketing_cost,s.warehouse,s.carrier,s.promised_day,s.delivered_day,s.lost,
GREATEST(0,83-a.due_day) days_overdue,a.invoice,COALESCE(p.cash,0) collected
FROM orders o JOIN selected c ON o.cid=c.cid LEFT JOIN successful_cash p ON o.oid=p.oid LEFT JOIN returned_cash r ON o.oid=r.oid LEFT JOIN ledger_cash l ON o.oid=l.oid LEFT JOIN shipments s ON o.oid=s.oid LEFT JOIN channel_volume v ON o.channel=v.channel AND o.day=v.day LEFT JOIN campaigns m ON o.channel=m.channel AND o.day=m.day LEFT JOIN receivables a ON o.oid=a.oid WHERE o.cancelled=0 AND o.day BETWEEN 8 AND 83-1),
order_facts AS (SELECT *,cash-returned net_revenue,cash-returned-cost-freight-marketing_cost contribution,CASE WHEN delivered_day<83 THEN GREATEST(0,delivered_day-promised_day) ELSE NULL END late_days,GREATEST(0,invoice-collected) outstanding FROM order_costs),
customer_facts AS (SELECT c.cid,c.region,c.tier,c.credit,c.signup,COUNT(o.oid) orders,COALESCE(SUM(o.net_revenue),0) revenue,COALESCE(SUM(o.contribution),0) contribution,COALESCE(SUM(o.marketing_cost),0) acquisition_cost,COALESCE(SUM(o.returned),0) returned,COALESCE(SUM(o.outstanding),0) outstanding,83-COALESCE(MAX(o.day),c.signup) recency FROM selected c LEFT JOIN order_facts o ON c.cid=o.cid GROUP BY c.cid,c.region,c.tier,c.credit,c.signup),
product_facts AS (SELECT o.*,p.pid,p.category,i.qty,i.price,CAST(i.qty*i.price AS DOUBLE)/o.amount item_share FROM order_facts o JOIN items i ON o.oid=i.oid JOIN products p ON i.pid=p.pid),
subscription_history AS (SELECT s.*,LAG(active) OVER(PARTITION BY s.cid ORDER BY month) prior_active,SUM(billed-paid) OVER(PARTITION BY s.cid ORDER BY month) arrears FROM subscriptions s JOIN selected c ON s.cid=c.cid WHERE month<=23),
subscription_summary AS (SELECT cid,COUNT(*) n_months,SUM(billed) billed,SUM(paid) paid,SUM(active) active_months,MAX(CASE WHEN active=1 THEN month END) last_active,MIN(CASE WHEN active=0 THEN month END) first_pause,MAX(arrears) arrears,SUM(CASE WHEN prior_active=0 AND active=1 THEN 1 ELSE 0 END) reactivations FROM subscription_history GROUP BY cid),
subscription_customers AS (SELECT c.*,s.n_months,s.billed,s.paid,s.active_months,s.last_active,s.first_pause,s.arrears,s.reactivations FROM customer_facts c LEFT JOIN subscription_summary s ON c.cid=s.cid)
SELECT cid,region,tier,orders,revenue,contribution,acquisition_cost,returned,outstanding,recency,n_months,billed,paid,active_months,last_active,COALESCE(first_pause,n_months) first_pause,arrears,reactivations,COALESCE(credit,80) credit FROM subscription_customers ORDER BY cid;

WITH selected AS (SELECT * FROM customers WHERE cid>=50 AND cid<305),
successful_cash AS (SELECT oid,SUM(paid) cash FROM payments WHERE success=1 AND day<83 GROUP BY oid),
returned_cash AS (SELECT oid,SUM(refunded) returned FROM refunds WHERE day<83 GROUP BY oid),
ledger_versions AS (SELECT l.*,ROW_NUMBER() OVER(PARTITION BY event_id ORDER BY revision_no DESC,entry_id DESC) version_rank FROM ledger l WHERE day<83),
ledger_cash AS (SELECT oid,SUM(amount) ledger_amount FROM ledger_versions WHERE version_rank=1 GROUP BY oid),
channel_volume AS (SELECT channel,day,COUNT(*) buyers FROM orders WHERE cancelled=0 GROUP BY channel,day),
order_costs AS (SELECT o.*,c.region,c.tier,c.signup,c.credit,COALESCE(p.cash,0) cash,COALESCE(r.returned,0) returned,COALESCE(l.ledger_amount,0) ledger_amount,
COALESCE(s.freight,0) freight,COALESCE(m.spend/v.buyers,0) marketing_cost,s.warehouse,s.carrier,s.promised_day,s.delivered_day,s.lost,
GREATEST(0,83-a.due_day) days_overdue,a.invoice,COALESCE(p.cash,0) collected
FROM orders o JOIN selected c ON o.cid=c.cid LEFT JOIN successful_cash p ON o.oid=p.oid LEFT JOIN returned_cash r ON o.oid=r.oid LEFT JOIN ledger_cash l ON o.oid=l.oid LEFT JOIN shipments s ON o.oid=s.oid LEFT JOIN channel_volume v ON o.channel=v.channel AND o.day=v.day LEFT JOIN campaigns m ON o.channel=m.channel AND o.day=m.day LEFT JOIN receivables a ON o.oid=a.oid WHERE o.cancelled=0 AND o.day BETWEEN 8 AND 83-1),
order_facts AS (SELECT *,cash-returned net_revenue,cash-returned-cost-freight-marketing_cost contribution,CASE WHEN delivered_day<83 THEN GREATEST(0,delivered_day-promised_day) ELSE NULL END late_days,GREATEST(0,invoice-collected) outstanding FROM order_costs),
customer_facts AS (SELECT c.cid,c.region,c.tier,c.credit,c.signup,COUNT(o.oid) orders,COALESCE(SUM(o.net_revenue),0) revenue,COALESCE(SUM(o.contribution),0) contribution,COALESCE(SUM(o.marketing_cost),0) acquisition_cost,COALESCE(SUM(o.returned),0) returned,COALESCE(SUM(o.outstanding),0) outstanding,83-COALESCE(MAX(o.day),c.signup) recency FROM selected c LEFT JOIN order_facts o ON c.cid=o.cid GROUP BY c.cid,c.region,c.tier,c.credit,c.signup),
product_facts AS (SELECT o.*,p.pid,p.category,i.qty,i.price,CAST(i.qty*i.price AS DOUBLE)/o.amount item_share FROM order_facts o JOIN items i ON o.oid=i.oid JOIN products p ON i.pid=p.pid),
subscription_history AS (SELECT s.*,LAG(active) OVER(PARTITION BY s.cid ORDER BY month) prior_active,SUM(billed-paid) OVER(PARTITION BY s.cid ORDER BY month) arrears FROM subscriptions s JOIN selected c ON s.cid=c.cid WHERE month<=23),
subscription_summary AS (SELECT cid,COUNT(*) n_months,SUM(billed) billed,SUM(paid) paid,SUM(active) active_months,MAX(CASE WHEN active=1 THEN month END) last_active,MIN(CASE WHEN active=0 THEN month END) first_pause,MAX(arrears) arrears,SUM(CASE WHEN prior_active=0 AND active=1 THEN 1 ELSE 0 END) reactivations FROM subscription_history GROUP BY cid),
subscription_customers AS (SELECT c.*,s.n_months,s.billed,s.paid,s.active_months,s.last_active,s.first_pause,s.arrears,s.reactivations FROM customer_facts c LEFT JOIN subscription_summary s ON c.cid=s.cid)
SELECT cid,month,active,billed,paid FROM subscription_history ORDER BY cid,month;