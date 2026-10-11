WITH customer_snapshot AS (WITH chosen AS (SELECT * FROM customers WHERE cid>=1 AND cid<301),
cash AS (SELECT oid,SUM(paid) cash FROM payments WHERE success=1 AND day<57 GROUP BY oid),
returns AS (SELECT oid,SUM(refunded) returned FROM refunds WHERE day<57 GROUP BY oid),
revision AS (SELECT *,ROW_NUMBER() OVER(PARTITION BY event_id ORDER BY revision_no DESC,entry_id DESC) rn FROM ledger WHERE day<57),
book AS (SELECT oid,SUM(amount) booked FROM revision WHERE rn=1 GROUP BY oid),
mix AS (SELECT i.oid,SUM(i.qty) units,COUNT(DISTINCT p.category) categories,SUM(i.qty*p.price) list_value FROM items i JOIN products p ON i.pid=p.pid GROUP BY i.oid),
channel AS (SELECT channel,day,COUNT(*) buyers FROM orders WHERE cancelled=0 GROUP BY channel,day),
order_detail AS (SELECT o.*,COALESCE(p.cash,0) cash,COALESCE(r.returned,0) returned,COALESCE(b.booked,0) booked,
COALESCE(x.units,0) units,COALESCE(x.categories,0) categories,COALESCE(x.list_value,0) list_value,
s.freight,s.warehouse,s.carrier,CASE WHEN s.delivered_day<57 THEN GREATEST(0,s.delivered_day-s.promised_day) ELSE NULL END late,
CASE WHEN s.delivered_day>=57 THEN 1 ELSE 0 END pending,
COALESCE(m.spend/v.buyers,0) acquisition,GREATEST(0,a.invoice-COALESCE(p.cash,0)) outstanding,
CASE WHEN a.due_day<57 THEN GREATEST(0,a.invoice-COALESCE(p.cash,0)) ELSE 0 END overdue
FROM orders o JOIN chosen c ON o.cid=c.cid LEFT JOIN cash p ON o.oid=p.oid LEFT JOIN returns r ON o.oid=r.oid
LEFT JOIN book b ON o.oid=b.oid LEFT JOIN mix x ON o.oid=x.oid LEFT JOIN shipments s ON o.oid=s.oid
LEFT JOIN receivables a ON o.oid=a.oid LEFT JOIN channel v ON o.channel=v.channel AND o.day=v.day
LEFT JOIN campaigns m ON o.channel=m.channel AND o.day=m.day
WHERE o.cancelled=0 AND o.day BETWEEN 0 AND 57-1),
sales AS (SELECT cid,COUNT(*) n_orders,SUM(cash-returned) revenue,SUM(cash-returned-cost-freight-acquisition) margin,
SUM(cost) AS cost,SUM(acquisition) acquisition,SUM(outstanding) outstanding,SUM(overdue) overdue,SUM(units) units,
AVG(CAST(late AS DOUBLE)) late,SUM(pending) pending,SUM(booked-cash) ledger_gap,AVG(CAST(categories AS DOUBLE)) variety,
AVG(CAST(CASE WHEN day<(0+57)/2 THEN cash-returned ELSE NULL END AS DOUBLE)) early,
AVG(CAST(CASE WHEN day>=(0+57)/2 THEN cash-returned ELSE NULL END AS DOUBLE)) recent FROM order_detail GROUP BY cid),
support AS (SELECT cid,COUNT(*) tickets,SUM(handle_minutes) handling,AVG(CAST(csat AS DOUBLE)) csat,SUM(reopened) reopened FROM tickets WHERE day BETWEEN 0 AND 57-1 GROUP BY cid),
sessions AS (SELECT cid,session_id,MAX(kind) depth,COUNT(*) n FROM events WHERE day BETWEEN 0 AND 57-1 GROUP BY cid,session_id),
journey AS (SELECT cid,COUNT(*) sessions,SUM(CASE WHEN depth=4 THEN 1 ELSE 0 END) converted,AVG(CAST(depth AS DOUBLE)) depth FROM sessions GROUP BY cid),
subs_rank AS (SELECT *,ROW_NUMBER() OVER(PARTITION BY cid ORDER BY month DESC) rn FROM subscriptions WHERE month<=22),
subs AS (SELECT cid,SUM(billed-paid) arrears,SUM(active) active_months,MAX(CASE WHEN rn=1 THEN active ELSE NULL END) active FROM subs_rank GROUP BY cid),
contracts_now AS (SELECT cid,SUM(booked*LEAST(CAST(1.0 AS DOUBLE),GREATEST(CAST(0.0 AS DOUBLE),CAST(57-start_day AS DOUBLE)/term_days))) earned,
SUM(booked*(1-LEAST(CAST(1.0 AS DOUBLE),GREATEST(CAST(0.0 AS DOUBLE),CAST(57-start_day AS DOUBLE)/term_days)))) deferred_revenue
FROM contracts WHERE start_day<57 GROUP BY cid),
loan_rank AS (SELECT *,ROW_NUMBER() OVER(PARTITION BY loan_id ORDER BY day DESC) rn FROM loan_performance WHERE day<57),
credit_now AS (SELECT l.cid,SUM(COALESCE(p.balance,l.principal)) balance,MAX(COALESCE(p.dpd,0)) dpd,
MAX(COALESCE(p.defaulted,0)) defaulted FROM loans l LEFT JOIN loan_rank p ON l.loan_id=p.loan_id AND p.rn=1 WHERE l.opened<57 GROUP BY l.cid),
fraud AS (SELECT cid,COUNT(*) fraud_payments,SUM(amount*chargeback) chargeback,SUM(amount) payment_volume FROM fraud_payments WHERE day<57 GROUP BY cid),
exp AS (SELECT cid,AVG(CAST(baseline AS DOUBLE)) baseline,AVG(CAST(revenue AS DOUBLE)) exp_revenue,AVG(CAST(latency AS DOUBLE)) latency FROM experiment WHERE day<57 GROUP BY cid),
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
57-COALESCE((SELECT MAX(o2.day) FROM orders o2 WHERE o2.cid=c.cid AND o2.cancelled=0 AND o2.day<57),c.signup) recency,
CASE WHEN EXISTS(SELECT 1 FROM receivables ar JOIN orders oo ON ar.oid=oo.oid WHERE oo.cid=c.cid AND oo.day<57 AND ar.due_day<57
AND NOT EXISTS(SELECT 1 FROM payments pp WHERE pp.oid=oo.oid AND pp.success=1 AND pp.day<57)) THEN 1 ELSE 0 END unpaid_order,
CASE WHEN NOT EXISTS(SELECT 1 FROM fraud_payments ff WHERE ff.cid=c.cid AND ff.chargeback=1 AND ff.day<57) THEN 1 ELSE 0 END clean_history,
CASE WHEN c.cid IN(SELECT ev.cid FROM events ev WHERE ev.kind=4 AND ev.day BETWEEN 0 AND 57-1
AND EXISTS(SELECT 1 FROM orders eo WHERE eo.cid=ev.cid AND eo.day<=ev.day AND eo.cancelled=0)) THEN 1 ELSE 0 END confirmed_journey,
COALESCE((SELECT AVG(CAST(pc.credit AS DOUBLE)) FROM edges ee JOIN customers pc ON ee.dst=pc.cid WHERE ee.src=c.cid AND pc.credit IS NOT NULL),80) peer_credit
FROM chosen c LEFT JOIN sales s ON c.cid=s.cid LEFT JOIN support t ON c.cid=t.cid LEFT JOIN journey j ON c.cid=j.cid
LEFT JOIN subs u ON c.cid=u.cid LEFT JOIN contracts_now k ON c.cid=k.cid LEFT JOIN credit_now l ON c.cid=l.cid
LEFT JOIN fraud f ON c.cid=f.cid LEFT JOIN exp x ON c.cid=x.cid LEFT JOIN peer e ON c.cid=e.src)
SELECT * FROM wide),
product_snapshot AS (WITH dense AS (SELECT p.pid,p.category,p.price,c.day,c.week,c.weekday FROM products p CROSS JOIN calendar c WHERE c.day BETWEEN 0 AND 57-1),
paid AS (SELECT oid,SUM(paid) cash FROM payments WHERE success=1 AND day<57 GROUP BY oid),
returned AS (SELECT oid,SUM(refunded) refunded FROM refunds WHERE day<57 GROUP BY oid),
item_sales AS (SELECT i.pid,o.day,SUM(i.qty) units,SUM((COALESCE(a.cash,0)-COALESCE(r.refunded,0))*i.qty*i.price/o.amount) revenue,
SUM((COALESCE(a.cash,0)-COALESCE(r.refunded,0)-o.cost-s.freight)*i.qty*i.price/o.amount) margin,
COUNT(DISTINCT o.cid) customers,AVG(CAST(CASE WHEN s.delivered_day<57 THEN GREATEST(0,s.delivered_day-s.promised_day) ELSE NULL END AS DOUBLE)) late
FROM items i JOIN orders o ON i.oid=o.oid JOIN customers cc ON o.cid=cc.cid LEFT JOIN paid a ON o.oid=a.oid
LEFT JOIN returned r ON o.oid=r.oid LEFT JOIN shipments s ON o.oid=s.oid WHERE o.cancelled=0 AND o.day BETWEEN 0 AND 57-1 GROUP BY i.pid,o.day),
stock AS (SELECT *,ROW_NUMBER() OVER(PARTITION BY pid ORDER BY day DESC) rn FROM inventory WHERE day<57),
price_path AS (SELECT *,LAG(units) OVER(PARTITION BY pid ORDER BY day) previous_units,
AVG(CAST(units AS DOUBLE)) OVER(PARTITION BY pid ORDER BY day ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) rolling_units FROM prices WHERE day<57),
received AS (SELECT supplier,pid,SUM(ordered) ordered,SUM(received) received,AVG(CAST(delay AS DOUBLE)) delay FROM supply WHERE day BETWEEN 0 AND 57-1 GROUP BY supplier,pid),
plant_daily AS (SELECT m.plant,s.day,SUM(p.output_units) output,SUM(p.defects) defects,SUM(p.scrap_cost) scrap,
AVG(CAST(s.vibration AS DOUBLE)) vibration,SUM(s.failure) failures,SUM(s.downtime) downtime,SUM(m.capacity) capacity
FROM machines m JOIN sensors s ON m.machine=s.machine JOIN production p ON m.machine=p.machine AND s.day=p.day
WHERE s.day BETWEEN 0 AND 57-1 GROUP BY m.plant,s.day),
energy_daily AS (SELECT site,day,SUM(kwh*tariff) energy_cost,SUM(kwh*carbon) carbon,SUM(kwh) kwh FROM energy WHERE day BETWEEN 0 AND 57-1 GROUP BY site,day),
market_lag AS (SELECT *,LAG(close_price) OVER(PARTITION BY asset ORDER BY day) previous_close FROM market WHERE day<57),
macro AS (SELECT asset,AVG(CAST(LN(close_price/previous_close) AS DOUBLE)) return_mean,AVG(CAST(volume AS DOUBLE)) volume FROM market_lag WHERE previous_close IS NOT NULL AND day>=0 GROUP BY asset),
daily AS (SELECT d.*,COALESCE(x.units,0) sold,COALESCE(x.revenue,0) revenue,COALESCE(x.margin,0) margin,
COALESCE(x.customers,0) buyers,COALESCE(x.late,0) late,pr.units observed_demand,pr.sale_price,pr.promo,pr.stockout,pr.rolling_units,
pl.output,pl.defects,pl.vibration,pl.failures,pl.downtime,pl.capacity,en.energy_cost,en.carbon,en.kwh,
t.revenue_target,t.risk_budget FROM dense d LEFT JOIN item_sales x ON d.pid=x.pid AND d.day=x.day
JOIN price_path pr ON d.pid=pr.pid AND d.day=pr.day JOIN plant_daily pl ON d.category=pl.plant AND d.day=pl.day
JOIN energy_daily en ON pl.plant=en.site AND pl.day=en.day LEFT JOIN targets t ON t.tier=d.category%3 AND t.week=d.week),
summary AS (SELECT pid,category,MAX(price) price,COUNT(*) calendar_days,SUM(sold) sold,SUM(revenue) revenue,SUM(margin) margin,
AVG(CAST(observed_demand AS DOUBLE)) demand,AVG(CAST(observed_demand*observed_demand AS DOUBLE))-AVG(CAST(observed_demand AS DOUBLE))*AVG(CAST(observed_demand AS DOUBLE)) demand_variance,
AVG(CAST(sale_price AS DOUBLE)) sale_price,AVG(CAST(CAST(promo AS DOUBLE) AS DOUBLE)) promo_rate,AVG(CAST(CAST(stockout AS DOUBLE) AS DOUBLE)) stockout_rate,
AVG(CAST(rolling_units AS DOUBLE)) rolling_units,AVG(CAST(buyers AS DOUBLE)) buyers,AVG(CAST(late AS DOUBLE)) late,AVG(CAST(output AS DOUBLE)) output,AVG(CAST(defects AS DOUBLE)) defects,
AVG(CAST(vibration AS DOUBLE)) vibration,SUM(failures) failures,SUM(downtime) downtime,AVG(CAST(capacity AS DOUBLE)) capacity,
AVG(CAST(energy_cost AS DOUBLE)) energy_cost,AVG(CAST(carbon AS DOUBLE)) carbon,AVG(CAST(kwh AS DOUBLE)) kwh,AVG(CAST(revenue_target AS DOUBLE)) revenue_target,AVG(CAST(risk_budget AS DOUBLE)) risk_budget FROM daily GROUP BY pid,category),
wide AS (SELECT d.*,i.on_hand,i.lead_days,s.supplier,s.country,s.unit_cost,
COALESCE(r.received/NULLIF(r.ordered,0),1) fill_rate,COALESCE(r.delay,0) delay,
COALESCE(m.return_mean,0) macro_return,COALESCE(m.volume,0) macro_volume,
(SELECT AVG(CAST(s2.unit_cost AS DOUBLE)) FROM suppliers s2 WHERE s2.country=s.country) country_cost,
(SELECT SUM(a2.received) FROM supply a2 WHERE a2.supplier=s.supplier AND a2.day=(SELECT MAX(a3.day) FROM supply a3 WHERE a3.supplier=a2.supplier AND a3.day<57)) latest_delivery,
CASE WHEN EXISTS(SELECT 1 FROM prices p2 WHERE p2.pid=d.pid AND p2.stockout=1 AND p2.day BETWEEN 0 AND 57-1
AND NOT EXISTS(SELECT 1 FROM supply a4 WHERE a4.pid=p2.pid AND a4.day=p2.day)) THEN 1 ELSE 0 END uncovered_stockout,
CASE WHEN d.pid IN(SELECT p3.pid FROM products p3 WHERE p3.price>(SELECT AVG(CAST(p4.price AS DOUBLE)) FROM products p4 WHERE p4.category=p3.category)) THEN 1 ELSE 0 END premium,
(SELECT AVG(CAST(ca.spend AS DOUBLE)) FROM campaigns ca WHERE ca.day BETWEEN 0 AND 57-1 AND ca.channel=d.category%4) marketing_spend
FROM summary d JOIN stock i ON d.pid=i.pid AND i.rn=1 JOIN suppliers s ON d.pid=s.pid
LEFT JOIN received r ON s.supplier=r.supplier AND d.pid=r.pid LEFT JOIN macro m ON d.category=m.asset)
SELECT * FROM wide),
purchases AS (WITH cash AS (SELECT oid,SUM(paid) cash FROM payments WHERE success=1 AND day<57 GROUP BY oid),
    returned AS (SELECT oid,SUM(refunded) refund FROM refunds WHERE day<57 GROUP BY oid),
    linked AS (SELECT o.cid,i.pid,i.qty,(COALESCE(c.cash,0)-COALESCE(r.refund,0))*i.qty*i.price/o.amount net_value
    FROM orders o JOIN items i ON o.oid=i.oid JOIN products pr ON i.pid=pr.pid JOIN customers cu ON o.cid=cu.cid
    LEFT JOIN cash c ON o.oid=c.oid LEFT JOIN returned r ON o.oid=r.oid
    WHERE o.cancelled=0 AND o.day BETWEEN 0 AND 57-1 AND cu.cid>=1 AND cu.cid<301)
    SELECT cid,pid,SUM(qty) units,SUM(net_value) net_value FROM linked GROUP BY cid,pid)
SELECT b.cid AS cid,b.pid AS pid,b.units AS bridge_units,b.net_value AS bridge_value,c.region AS c_region,c.tier AS c_tier,c.credit AS c_credit,c.n_orders AS c_n_orders,c.revenue AS c_revenue,c.margin AS c_margin,c.cost AS c_cost,c.acquisition AS c_acquisition,c.outstanding AS c_outstanding,c.overdue AS c_overdue,c.units AS c_units,c.late AS c_late,c.pending AS c_pending,c.ledger_gap AS c_ledger_gap,c.variety AS c_variety,c.momentum AS c_momentum,c.tickets AS c_tickets,c.handling AS c_handling,c.csat AS c_csat,c.reopened AS c_reopened,c.sessions AS c_sessions,c.converted AS c_converted,c.depth AS c_depth,c.arrears AS c_arrears,c.active_months AS c_active_months,c.active AS c_active,c.earned AS c_earned,c.deferred_revenue AS c_deferred_revenue,c.balance AS c_balance,c.dpd AS c_dpd,c.defaulted AS c_defaulted,c.chargeback AS c_chargeback,c.payment_volume AS c_payment_volume,c.baseline AS c_baseline,c.exp_revenue AS c_exp_revenue,c.latency AS c_latency,c.peer_margin AS c_peer_margin,c.recency AS c_recency,c.unpaid_order AS c_unpaid_order,c.clean_history AS c_clean_history,c.confirmed_journey AS c_confirmed_journey,c.peer_credit AS c_peer_credit,p.category AS p_category,p.price AS p_price,p.calendar_days AS p_calendar_days,p.sold AS p_sold,p.revenue AS p_revenue,p.margin AS p_margin,p.demand AS p_demand,p.demand_variance AS p_demand_variance,p.sale_price AS p_sale_price,p.promo_rate AS p_promo_rate,p.stockout_rate AS p_stockout_rate,p.rolling_units AS p_rolling_units,p.buyers AS p_buyers,p.late AS p_late,p.output AS p_output,p.defects AS p_defects,p.vibration AS p_vibration,p.failures AS p_failures,p.downtime AS p_downtime,p.capacity AS p_capacity,p.energy_cost AS p_energy_cost,p.carbon AS p_carbon,p.kwh AS p_kwh,p.revenue_target AS p_revenue_target,p.risk_budget AS p_risk_budget,p.on_hand AS p_on_hand,p.lead_days AS p_lead_days,p.supplier AS p_supplier,p.country AS p_country,p.unit_cost AS p_unit_cost,p.fill_rate AS p_fill_rate,p.delay AS p_delay,p.macro_return AS p_macro_return,p.macro_volume AS p_macro_volume,p.country_cost AS p_country_cost,p.latest_delivery AS p_latest_delivery,p.uncovered_stockout AS p_uncovered_stockout,p.premium AS p_premium,p.marketing_spend AS p_marketing_spend FROM purchases b JOIN customer_snapshot c ON b.cid=c.cid JOIN product_snapshot p ON b.pid=p.pid ORDER BY b.cid,b.pid;
