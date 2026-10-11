WITH chosen AS (SELECT * FROM customers WHERE cid>=420 AND cid<825),
cash AS (SELECT oid,SUM(paid) cash FROM payments WHERE success=1 AND day<75 GROUP BY oid),
returns AS (SELECT oid,SUM(refunded) returned FROM refunds WHERE day<75 GROUP BY oid),
revision AS (SELECT *,ROW_NUMBER() OVER(PARTITION BY event_id ORDER BY revision_no DESC,entry_id DESC) rn FROM ledger WHERE day<75),
book AS (SELECT oid,SUM(amount) booked FROM revision WHERE rn=1 GROUP BY oid),
mix AS (SELECT i.oid,SUM(i.qty) units,COUNT(DISTINCT p.category) categories,SUM(i.qty*p.price) list_value FROM items i JOIN products p ON i.pid=p.pid GROUP BY i.oid),
channel AS (SELECT channel,day,COUNT(*) buyers FROM orders WHERE cancelled=0 GROUP BY channel,day),
order_detail AS (SELECT o.*,COALESCE(p.cash,0) cash,COALESCE(r.returned,0) returned,COALESCE(b.booked,0) booked,
COALESCE(x.units,0) units,COALESCE(x.categories,0) categories,COALESCE(x.list_value,0) list_value,
s.freight,s.warehouse,s.carrier,CASE WHEN s.delivered_day<75 THEN GREATEST(0,s.delivered_day-s.promised_day) ELSE NULL END late,
CASE WHEN s.delivered_day>=75 THEN 1 ELSE 0 END pending,
COALESCE(m.spend/v.buyers,0) acquisition,GREATEST(0,a.invoice-COALESCE(p.cash,0)) outstanding,
CASE WHEN a.due_day<75 THEN GREATEST(0,a.invoice-COALESCE(p.cash,0)) ELSE 0 END overdue
FROM orders o JOIN chosen c ON o.cid=c.cid LEFT JOIN cash p ON o.oid=p.oid LEFT JOIN returns r ON o.oid=r.oid
LEFT JOIN book b ON o.oid=b.oid LEFT JOIN mix x ON o.oid=x.oid LEFT JOIN shipments s ON o.oid=s.oid
LEFT JOIN receivables a ON o.oid=a.oid LEFT JOIN channel v ON o.channel=v.channel AND o.day=v.day
LEFT JOIN campaigns m ON o.channel=m.channel AND o.day=m.day
WHERE o.cancelled=0 AND o.day BETWEEN 2 AND 75-1),
sales AS (SELECT cid,COUNT(*) n_orders,SUM(cash-returned) revenue,SUM(cash-returned-cost-freight-acquisition) margin,
SUM(cost) AS cost,SUM(acquisition) acquisition,SUM(outstanding) outstanding,SUM(overdue) overdue,SUM(units) units,
AVG(CAST(late AS DOUBLE)) late,SUM(pending) pending,SUM(booked-cash) ledger_gap,AVG(CAST(categories AS DOUBLE)) variety,
AVG(CAST(CASE WHEN day<(2+75)/2 THEN cash-returned ELSE NULL END AS DOUBLE)) early,
AVG(CAST(CASE WHEN day>=(2+75)/2 THEN cash-returned ELSE NULL END AS DOUBLE)) recent FROM order_detail GROUP BY cid),
support AS (SELECT cid,COUNT(*) tickets,SUM(handle_minutes) handling,AVG(CAST(csat AS DOUBLE)) csat,SUM(reopened) reopened FROM tickets WHERE day BETWEEN 2 AND 75-1 GROUP BY cid),
sessions AS (SELECT cid,session_id,MAX(kind) depth,COUNT(*) n FROM events WHERE day BETWEEN 2 AND 75-1 GROUP BY cid,session_id),
journey AS (SELECT cid,COUNT(*) sessions,SUM(CASE WHEN depth=4 THEN 1 ELSE 0 END) converted,AVG(CAST(depth AS DOUBLE)) depth FROM sessions GROUP BY cid),
subs_rank AS (SELECT *,ROW_NUMBER() OVER(PARTITION BY cid ORDER BY month DESC) rn FROM subscriptions WHERE month<=23),
subs AS (SELECT cid,SUM(billed-paid) arrears,SUM(active) active_months,MAX(CASE WHEN rn=1 THEN active ELSE NULL END) active FROM subs_rank GROUP BY cid),
contracts_now AS (SELECT cid,SUM(booked*LEAST(CAST(1.0 AS DOUBLE),GREATEST(CAST(0.0 AS DOUBLE),CAST(75-start_day AS DOUBLE)/term_days))) earned,
SUM(booked*(1-LEAST(CAST(1.0 AS DOUBLE),GREATEST(CAST(0.0 AS DOUBLE),CAST(75-start_day AS DOUBLE)/term_days)))) deferred_revenue
FROM contracts WHERE start_day<75 GROUP BY cid),
loan_rank AS (SELECT *,ROW_NUMBER() OVER(PARTITION BY loan_id ORDER BY day DESC) rn FROM loan_performance WHERE day<75),
credit_now AS (SELECT l.cid,SUM(COALESCE(p.balance,l.principal)) balance,MAX(COALESCE(p.dpd,0)) dpd,
MAX(COALESCE(p.defaulted,0)) defaulted FROM loans l LEFT JOIN loan_rank p ON l.loan_id=p.loan_id AND p.rn=1 WHERE l.opened<75 GROUP BY l.cid),
fraud AS (SELECT cid,COUNT(*) fraud_payments,SUM(amount*chargeback) chargeback,SUM(amount) payment_volume FROM fraud_payments WHERE day<75 GROUP BY cid),
exp AS (SELECT cid,AVG(CAST(baseline AS DOUBLE)) baseline,AVG(CAST(revenue AS DOUBLE)) exp_revenue,AVG(CAST(latency AS DOUBLE)) latency FROM experiment WHERE day<75 GROUP BY cid),
peer AS (SELECT e.src,COUNT(*) peers,SUM(e.weight*COALESCE(s.margin,0))/SUM(e.weight) peer_margin FROM edges e LEFT JOIN sales s ON e.dst=s.cid GROUP BY e.src),
wide AS (SELECT c.cid,c.region,c.tier,COALESCE(c.credit,80) credit,
COALESCE(s.n_orders,0) n_orders,COALESCE(s.revenue,0) revenue,COALESCE(s.margin,0) margin,COALESCE(s.cost,0) AS cost,
COALESCE(s.acquisition,0) acquisition,COALESCE(s.outstanding,0) outstanding,COALESCE(s.overdue,0) overdue,
COALESCE(s.units,0) units,COALESCE(s.late,0) late,COALESCE(s.pending,0) pending,COALESCE(s.ledger_gap,0) ledger_gap,
COALESCE(s.variety,0) variety,COALESCE(s.recent,0)-COALESCE(s.early,0) momentum,
COALESCE(t.tickets,0) tickets,COALESCE(t.handling,0) handling,COALESCE(t.csat,4) csat,COALESCE(t.reopened,0) reopened,
COALESCE(j.sessions,0) sessions,COALESCE(j.converted,0) converted,COALESCE(j.depth,0) depth,
COALESCE(u.arrears,0) arrears,COALESCE(u.active_months,0) active_months,COALESCE(u.active,0) active,
COALESCE(k.earned,0) earned,COALESCE(k.deferred_revenue,0) deferred_revenue,COALESCE(l.balance,0) balance,COALESCE(l.dpd,0) dpd,COALESCE(l.defaulted,0) defaulted,
COALESCE(f.chargeback,0) chargeback,COALESCE(f.payment_volume,0) payment_volume,COALESCE(x.baseline,80) baseline,
COALESCE(x.exp_revenue,0) exp_revenue,COALESCE(x.latency,0) latency,COALESCE(e.peer_margin,0) peer_margin,
75-COALESCE((SELECT MAX(o2.day) FROM orders o2 WHERE o2.cid=c.cid AND o2.cancelled=0 AND o2.day<75),c.signup) recency,
CASE WHEN EXISTS(SELECT 1 FROM receivables ar JOIN orders oo ON ar.oid=oo.oid WHERE oo.cid=c.cid AND oo.day<75 AND ar.due_day<75
AND NOT EXISTS(SELECT 1 FROM payments pp WHERE pp.oid=oo.oid AND pp.success=1 AND pp.day<75)) THEN 1 ELSE 0 END unpaid_order,
CASE WHEN NOT EXISTS(SELECT 1 FROM fraud_payments ff WHERE ff.cid=c.cid AND ff.chargeback=1 AND ff.day<75) THEN 1 ELSE 0 END clean_history,
CASE WHEN c.cid IN(SELECT ev.cid FROM events ev WHERE ev.kind=4 AND ev.day BETWEEN 2 AND 75-1
AND EXISTS(SELECT 1 FROM orders eo WHERE eo.cid=ev.cid AND eo.day<=ev.day AND eo.cancelled=0)) THEN 1 ELSE 0 END confirmed_journey,
COALESCE((SELECT AVG(CAST(pc.credit AS DOUBLE)) FROM edges ee JOIN customers pc ON ee.dst=pc.cid WHERE ee.src=c.cid AND pc.credit IS NOT NULL),80) peer_credit
FROM chosen c LEFT JOIN sales s ON c.cid=s.cid LEFT JOIN support t ON c.cid=t.cid LEFT JOIN journey j ON c.cid=j.cid
LEFT JOIN subs u ON c.cid=u.cid LEFT JOIN contracts_now k ON c.cid=k.cid LEFT JOIN credit_now l ON c.cid=l.cid
LEFT JOIN fraud f ON c.cid=f.cid LEFT JOIN exp x ON c.cid=x.cid LEFT JOIN peer e ON c.cid=e.src)
SELECT * FROM wide ORDER BY cid