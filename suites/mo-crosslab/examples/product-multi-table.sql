WITH dense AS (SELECT p.pid,p.category,p.price,c.day,c.week,c.weekday FROM products p CROSS JOIN calendar c WHERE c.day BETWEEN 2 AND 75-1),
paid AS (SELECT oid,SUM(paid) cash FROM payments WHERE success=1 AND day<75 GROUP BY oid),
returned AS (SELECT oid,SUM(refunded) refunded FROM refunds WHERE day<75 GROUP BY oid),
item_sales AS (SELECT i.pid,o.day,SUM(i.qty) units,SUM((COALESCE(a.cash,0)-COALESCE(r.refunded,0))*i.qty*i.price/o.amount) revenue,
SUM((COALESCE(a.cash,0)-COALESCE(r.refunded,0)-o.cost-s.freight)*i.qty*i.price/o.amount) margin,
COUNT(DISTINCT o.cid) customers,AVG(CAST(CASE WHEN s.delivered_day<75 THEN GREATEST(0,s.delivered_day-s.promised_day) ELSE NULL END AS DOUBLE)) late
FROM items i JOIN orders o ON i.oid=o.oid JOIN customers cc ON o.cid=cc.cid LEFT JOIN paid a ON o.oid=a.oid
LEFT JOIN returned r ON o.oid=r.oid LEFT JOIN shipments s ON o.oid=s.oid WHERE o.cancelled=0 AND o.day BETWEEN 2 AND 75-1 GROUP BY i.pid,o.day),
stock AS (SELECT *,ROW_NUMBER() OVER(PARTITION BY pid ORDER BY day DESC) rn FROM inventory WHERE day<75),
price_path AS (SELECT *,LAG(units) OVER(PARTITION BY pid ORDER BY day) previous_units,
AVG(CAST(units AS DOUBLE)) OVER(PARTITION BY pid ORDER BY day ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) rolling_units FROM prices WHERE day<75),
received AS (SELECT supplier,pid,SUM(ordered) ordered,SUM(received) received,AVG(CAST(delay AS DOUBLE)) delay FROM supply WHERE day BETWEEN 2 AND 75-1 GROUP BY supplier,pid),
plant_daily AS (SELECT m.plant,s.day,SUM(p.output_units) output,SUM(p.defects) defects,SUM(p.scrap_cost) scrap,
AVG(CAST(s.vibration AS DOUBLE)) vibration,SUM(s.failure) failures,SUM(s.downtime) downtime,SUM(m.capacity) capacity
FROM machines m JOIN sensors s ON m.machine=s.machine JOIN production p ON m.machine=p.machine AND s.day=p.day
WHERE s.day BETWEEN 2 AND 75-1 GROUP BY m.plant,s.day),
energy_daily AS (SELECT site,day,SUM(kwh*tariff) energy_cost,SUM(kwh*carbon) carbon,SUM(kwh) kwh FROM energy WHERE day BETWEEN 2 AND 75-1 GROUP BY site,day),
market_lag AS (SELECT *,LAG(close_price) OVER(PARTITION BY asset ORDER BY day) previous_close FROM market WHERE day<75),
macro AS (SELECT asset,AVG(CAST(LN(close_price/previous_close) AS DOUBLE)) return_mean,AVG(CAST(volume AS DOUBLE)) volume FROM market_lag WHERE previous_close IS NOT NULL AND day>=2 GROUP BY asset),
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
(SELECT SUM(a2.received) FROM supply a2 WHERE a2.supplier=s.supplier AND a2.day=(SELECT MAX(a3.day) FROM supply a3 WHERE a3.supplier=a2.supplier AND a3.day<75)) latest_delivery,
CASE WHEN EXISTS(SELECT 1 FROM prices p2 WHERE p2.pid=d.pid AND p2.stockout=1 AND p2.day BETWEEN 2 AND 75-1
AND NOT EXISTS(SELECT 1 FROM supply a4 WHERE a4.pid=p2.pid AND a4.day=p2.day)) THEN 1 ELSE 0 END uncovered_stockout,
CASE WHEN d.pid IN(SELECT p3.pid FROM products p3 WHERE p3.price>(SELECT AVG(CAST(p4.price AS DOUBLE)) FROM products p4 WHERE p4.category=p3.category)) THEN 1 ELSE 0 END premium,
(SELECT AVG(CAST(ca.spend AS DOUBLE)) FROM campaigns ca WHERE ca.day BETWEEN 2 AND 75-1 AND ca.channel=d.category%4) marketing_spend
FROM summary d JOIN stock i ON d.pid=i.pid AND i.rn=1 JOIN suppliers s ON d.pid=s.pid
LEFT JOIN received r ON s.supplier=r.supplier AND d.pid=r.pid LEFT JOIN macro m ON d.category=m.asset)
SELECT * FROM wide ORDER BY pid