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
product_facts AS (SELECT o.*,p.pid,p.category,i.qty,i.price,CAST(i.qty*i.price AS DOUBLE)/o.amount item_share FROM order_facts o JOIN items i ON o.oid=i.oid JOIN products p ON i.pid=p.pid),selected_products AS (SELECT * FROM products WHERE category<>7),
price_facts AS (SELECT p.pid,p.category,r.day,r.list_price,r.sale_price,r.units,r.promo,r.stockout,s.lead_days,s.unit_cost,i.on_hand,
AVG(r.units) OVER(PARTITION BY p.pid ORDER BY r.day ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) rolling_demand
FROM selected_products p JOIN prices r ON p.pid=r.pid JOIN suppliers s ON p.pid=s.pid LEFT JOIN inventory i ON p.pid=i.pid AND r.day=i.day WHERE r.day BETWEEN 8 AND 83-1),
product_state AS (SELECT *,ROW_NUMBER() OVER(PARTITION BY pid ORDER BY day DESC) current_rank FROM price_facts),
supplier_facts AS (SELECT s.*,a.day,a.ordered,a.received,a.delay,a.received/a.ordered fill_rate FROM suppliers s JOIN selected_products p ON s.pid=p.pid JOIN supply a ON s.supplier=a.supplier WHERE a.day BETWEEN 8 AND 83-1),selected_machines AS (SELECT * FROM machines WHERE plant<>7),
plant_energy AS (SELECT site,day,SUM(kwh*tariff) energy_cost,SUM(kwh) kwh,SUM(kwh*carbon) emissions FROM energy WHERE day BETWEEN 8 AND 83-1 GROUP BY site,day),
plant_capacity AS (SELECT plant,SUM(capacity) capacity FROM machines GROUP BY plant),
operation_facts AS (SELECT m.*,s.day,s.temperature,s.vibration,s.load_value,s.failure,s.downtime,p.output_units,p.defects,p.scrap_cost,e.energy_cost*m.capacity/c.capacity energy_cost,e.emissions*m.capacity/c.capacity emissions,
AVG(s.vibration) OVER(PARTITION BY m.machine ORDER BY s.day ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) rolling_vibration,
SUM(s.failure) OVER(PARTITION BY m.machine ORDER BY s.day ROWS BETWEEN 1 FOLLOWING AND 3 FOLLOWING) next_failures
FROM selected_machines m JOIN sensors s ON m.machine=s.machine JOIN production p ON m.machine=p.machine AND s.day=p.day JOIN plant_energy e ON m.plant=e.site AND s.day=e.day JOIN plant_capacity c ON m.plant=c.plant WHERE s.day BETWEEN 8 AND 83-1)  , historical_product AS (SELECT pid,SUM(contribution*item_share) observed_margin,SUM(qty) sold_units FROM product_facts GROUP BY pid),
 product_forecast AS (SELECT pid,category,AVG(units) mean_demand,VAR_POP(units) demand_var,MAX(lead_days) lead,AVG(unit_cost) unit_cost FROM price_facts GROUP BY pid,category),
 plant_budget AS (SELECT plant,SUM(capacity*(1-downtime/24)) production_capacity,SUM(energy_cost+scrap_cost) plant_cost FROM operation_facts GROUP BY plant),
 integrated_plan AS (SELECT d.*,s.on_hand,COALESCE(h.observed_margin,0) observed_margin,COALESCE(h.sold_units,0) sold_units,COALESCE(p.production_capacity,0) production_capacity,COALESCE(p.plant_cost,0) plant_cost FROM product_forecast d JOIN product_state s ON d.pid=s.pid AND s.current_rank=1 LEFT JOIN historical_product h ON d.pid=h.pid LEFT JOIN plant_budget p ON d.category=p.plant)
 SELECT pid,category,mean_demand,demand_var,lead,unit_cost,on_hand,observed_margin,sold_units,production_capacity,plant_cost FROM integrated_plan ORDER BY pid;

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
product_facts AS (SELECT o.*,p.pid,p.category,i.qty,i.price,CAST(i.qty*i.price AS DOUBLE)/o.amount item_share FROM order_facts o JOIN items i ON o.oid=i.oid JOIN products p ON i.pid=p.pid),selected_products AS (SELECT * FROM products WHERE category<>7),
price_facts AS (SELECT p.pid,p.category,r.day,r.list_price,r.sale_price,r.units,r.promo,r.stockout,s.lead_days,s.unit_cost,i.on_hand,
AVG(r.units) OVER(PARTITION BY p.pid ORDER BY r.day ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) rolling_demand
FROM selected_products p JOIN prices r ON p.pid=r.pid JOIN suppliers s ON p.pid=s.pid LEFT JOIN inventory i ON p.pid=i.pid AND r.day=i.day WHERE r.day BETWEEN 8 AND 83-1),
product_state AS (SELECT *,ROW_NUMBER() OVER(PARTITION BY pid ORDER BY day DESC) current_rank FROM price_facts),
supplier_facts AS (SELECT s.*,a.day,a.ordered,a.received,a.delay,a.received/a.ordered fill_rate FROM suppliers s JOIN selected_products p ON s.pid=p.pid JOIN supply a ON s.supplier=a.supplier WHERE a.day BETWEEN 8 AND 83-1),selected_machines AS (SELECT * FROM machines WHERE plant<>7),
plant_energy AS (SELECT site,day,SUM(kwh*tariff) energy_cost,SUM(kwh) kwh,SUM(kwh*carbon) emissions FROM energy WHERE day BETWEEN 8 AND 83-1 GROUP BY site,day),
plant_capacity AS (SELECT plant,SUM(capacity) capacity FROM machines GROUP BY plant),
operation_facts AS (SELECT m.*,s.day,s.temperature,s.vibration,s.load_value,s.failure,s.downtime,p.output_units,p.defects,p.scrap_cost,e.energy_cost*m.capacity/c.capacity energy_cost,e.emissions*m.capacity/c.capacity emissions,
AVG(s.vibration) OVER(PARTITION BY m.machine ORDER BY s.day ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) rolling_vibration,
SUM(s.failure) OVER(PARTITION BY m.machine ORDER BY s.day ROWS BETWEEN 1 FOLLOWING AND 3 FOLLOWING) next_failures
FROM selected_machines m JOIN sensors s ON m.machine=s.machine JOIN production p ON m.machine=p.machine AND s.day=p.day JOIN plant_energy e ON m.plant=e.site AND s.day=e.day JOIN plant_capacity c ON m.plant=c.plant WHERE s.day BETWEEN 8 AND 83-1)
SELECT c.day,COALESCE(SUM(o.net_revenue),0) revenue,COALESCE(SUM(o.contribution),0) margin,COALESCE(SUM(o.cost+o.freight+o.marketing_cost),0) expenses,COALESCE(SUM(o.outstanding),0) outstanding FROM calendar c LEFT JOIN order_facts o ON c.day=o.day WHERE c.day BETWEEN 8 AND 83-1 GROUP BY c.day ORDER BY c.day;