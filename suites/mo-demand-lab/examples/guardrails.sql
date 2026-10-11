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
experiment_facts AS (SELECT e.*,c.tier,c.region,COALESCE(c.contribution,0) past_margin FROM experiment e JOIN customer_facts c ON e.cid=c.cid WHERE e.day BETWEEN 8 AND 83-1)
SELECT cid,day,treatment,site,baseline,converted,revenue,latency,harm,past_margin FROM experiment_facts ORDER BY cid,day;

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
experiment_facts AS (SELECT e.*,c.tier,c.region,COALESCE(c.contribution,0) past_margin FROM experiment e JOIN customer_facts c ON e.cid=c.cid WHERE e.day BETWEEN 8 AND 83-1)
SELECT site,treatment,COUNT(DISTINCT cid) users,AVG(latency) latency,AVG(CAST(harm AS DOUBLE)) harm FROM experiment_facts GROUP BY site,treatment ORDER BY site,treatment;