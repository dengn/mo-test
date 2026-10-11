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
loan_asof AS (SELECT p.*,ROW_NUMBER() OVER(PARTITION BY loan_id ORDER BY day DESC) current_rank FROM loan_performance p WHERE day<83),
credit_facts AS (SELECT l.*,c.region,c.tier,COALESCE(c.credit,80) credit,p.day observed_day,COALESCE(p.balance,l.principal) balance,COALESCE(p.dpd,0) dpd,COALESCE(p.defaulted,0) defaulted FROM loans l JOIN selected c ON l.cid=c.cid LEFT JOIN loan_asof p ON l.loan_id=p.loan_id AND p.current_rank=1 WHERE l.opened<83)
SELECT loan_id,cid,region,tier,principal,apr,term_days,balance,dpd,defaulted,credit FROM credit_facts ORDER BY loan_id;

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
loan_asof AS (SELECT p.*,ROW_NUMBER() OVER(PARTITION BY loan_id ORDER BY day DESC) current_rank FROM loan_performance p WHERE day<83),
credit_facts AS (SELECT l.*,c.region,c.tier,COALESCE(c.credit,80) credit,p.day observed_day,COALESCE(p.balance,l.principal) balance,COALESCE(p.dpd,0) dpd,COALESCE(p.defaulted,0) defaulted FROM loans l JOIN selected c ON l.cid=c.cid LEFT JOIN loan_asof p ON l.loan_id=p.loan_id AND p.current_rank=1 WHERE l.opened<83)
SELECT region,tier,SUM(balance) exposure,SUM(balance*defaulted) default_exposure FROM credit_facts GROUP BY region,tier ORDER BY region,tier;