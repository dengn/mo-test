WITH selected_products AS (SELECT * FROM products WHERE category<>7),
price_facts AS (SELECT p.pid,p.category,r.day,r.list_price,r.sale_price,r.units,r.promo,r.stockout,s.lead_days,s.unit_cost,i.on_hand,
AVG(r.units) OVER(PARTITION BY p.pid ORDER BY r.day ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) rolling_demand
FROM selected_products p JOIN prices r ON p.pid=r.pid JOIN suppliers s ON p.pid=s.pid LEFT JOIN inventory i ON p.pid=i.pid AND r.day=i.day WHERE r.day BETWEEN 8 AND 83-1),
product_state AS (SELECT *,ROW_NUMBER() OVER(PARTITION BY pid ORDER BY day DESC) current_rank FROM price_facts),
supplier_facts AS (SELECT s.*,a.day,a.ordered,a.received,a.delay,a.received/a.ordered fill_rate FROM suppliers s JOIN selected_products p ON s.pid=p.pid JOIN supply a ON s.supplier=a.supplier WHERE a.day BETWEEN 8 AND 83-1)
SELECT supplier,pid,country,lead_days,unit_cost,COUNT(*) deliveries,AVG(delay) delay,VAR_POP(delay) delay_var,SUM(ordered) ordered,SUM(received) received,AVG(fill_rate) fill_rate FROM supplier_facts GROUP BY supplier,pid,country,lead_days,unit_cost ORDER BY supplier;

WITH selected_products AS (SELECT * FROM products WHERE category<>7),
price_facts AS (SELECT p.pid,p.category,r.day,r.list_price,r.sale_price,r.units,r.promo,r.stockout,s.lead_days,s.unit_cost,i.on_hand,
AVG(r.units) OVER(PARTITION BY p.pid ORDER BY r.day ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) rolling_demand
FROM selected_products p JOIN prices r ON p.pid=r.pid JOIN suppliers s ON p.pid=s.pid LEFT JOIN inventory i ON p.pid=i.pid AND r.day=i.day WHERE r.day BETWEEN 8 AND 83-1),
product_state AS (SELECT *,ROW_NUMBER() OVER(PARTITION BY pid ORDER BY day DESC) current_rank FROM price_facts),
supplier_facts AS (SELECT s.*,a.day,a.ordered,a.received,a.delay,a.received/a.ordered fill_rate FROM suppliers s JOIN selected_products p ON s.pid=p.pid JOIN supply a ON s.supplier=a.supplier WHERE a.day BETWEEN 8 AND 83-1)
SELECT pid,category,day,list_price,sale_price,units,promo,stockout,lead_days,unit_cost,on_hand FROM price_facts ORDER BY pid,day;