"""Business marts with one row per entity, as-of joins and nested predicates."""
import re

def params(i):
    start=i%19; end=57+i%33
    return dict(lo=1+(i*31)%730,hi=min(1201,1+(i*31)%730+300+i%6*35),start=start,end=end,
                month=21+(end-1)//30,budget=8000+(i%47)*375,risk=.03+(i%11)*.01,
                ridge=.03+(i%17)*.04,seed=2026101200+i,service=.85+(i%9)*.015,
                holdout=i%5,discount=.008+(i%13)*.002,capacity=25+i%20)

CUSTOMER='''WITH chosen AS (SELECT * FROM customers WHERE cid>={lo} AND cid<{hi}),
cash AS (SELECT oid,SUM(paid) cash FROM payments WHERE success=1 AND day<{end} GROUP BY oid),
returns AS (SELECT oid,SUM(refunded) returned FROM refunds WHERE day<{end} GROUP BY oid),
revision AS (SELECT *,ROW_NUMBER() OVER(PARTITION BY event_id ORDER BY revision_no DESC,entry_id DESC) rn FROM ledger WHERE day<{end}),
book AS (SELECT oid,SUM(amount) booked FROM revision WHERE rn=1 GROUP BY oid),
mix AS (SELECT i.oid,SUM(i.qty) units,COUNT(DISTINCT p.category) categories,SUM(i.qty*p.price) list_value FROM items i JOIN products p ON i.pid=p.pid GROUP BY i.oid),
channel AS (SELECT channel,day,COUNT(*) buyers FROM orders WHERE cancelled=0 GROUP BY channel,day),
order_detail AS (SELECT o.*,COALESCE(p.cash,0) cash,COALESCE(r.returned,0) returned,COALESCE(b.booked,0) booked,
COALESCE(x.units,0) units,COALESCE(x.categories,0) categories,COALESCE(x.list_value,0) list_value,
s.freight,s.warehouse,s.carrier,CASE WHEN s.delivered_day<{end} THEN GREATEST(0,s.delivered_day-s.promised_day) ELSE NULL END late,
CASE WHEN s.delivered_day>={end} THEN 1 ELSE 0 END pending,
COALESCE(m.spend/v.buyers,0) acquisition,GREATEST(0,a.invoice-COALESCE(p.cash,0)) outstanding,
CASE WHEN a.due_day<{end} THEN GREATEST(0,a.invoice-COALESCE(p.cash,0)) ELSE 0 END overdue
FROM orders o JOIN chosen c ON o.cid=c.cid LEFT JOIN cash p ON o.oid=p.oid LEFT JOIN returns r ON o.oid=r.oid
LEFT JOIN book b ON o.oid=b.oid LEFT JOIN mix x ON o.oid=x.oid LEFT JOIN shipments s ON o.oid=s.oid
LEFT JOIN receivables a ON o.oid=a.oid LEFT JOIN channel v ON o.channel=v.channel AND o.day=v.day
LEFT JOIN campaigns m ON o.channel=m.channel AND o.day=m.day
WHERE o.cancelled=0 AND o.day BETWEEN {start} AND {end}-1),
sales AS (SELECT cid,COUNT(*) n_orders,SUM(cash-returned) revenue,SUM(cash-returned-cost-freight-acquisition) margin,
SUM(cost) AS cost,SUM(acquisition) acquisition,SUM(outstanding) outstanding,SUM(overdue) overdue,SUM(units) units,
AVG(late) late,SUM(pending) pending,SUM(booked-cash) ledger_gap,AVG(categories) variety,
AVG(CASE WHEN day<({start}+{end})/2 THEN cash-returned ELSE NULL END) early,
AVG(CASE WHEN day>=({start}+{end})/2 THEN cash-returned ELSE NULL END) recent FROM order_detail GROUP BY cid),
support AS (SELECT cid,COUNT(*) tickets,SUM(handle_minutes) handling,AVG(csat) csat,SUM(reopened) reopened FROM tickets WHERE day BETWEEN {start} AND {end}-1 GROUP BY cid),
sessions AS (SELECT cid,session_id,MAX(kind) depth,COUNT(*) n FROM events WHERE day BETWEEN {start} AND {end}-1 GROUP BY cid,session_id),
journey AS (SELECT cid,COUNT(*) sessions,SUM(CASE WHEN depth=4 THEN 1 ELSE 0 END) converted,AVG(depth) depth FROM sessions GROUP BY cid),
subs_rank AS (SELECT *,ROW_NUMBER() OVER(PARTITION BY cid ORDER BY month DESC) rn FROM subscriptions WHERE month<={month}),
subs AS (SELECT cid,SUM(billed-paid) arrears,SUM(active) active_months,MAX(CASE WHEN rn=1 THEN active ELSE NULL END) active FROM subs_rank GROUP BY cid),
contracts_now AS (SELECT cid,SUM(booked*LEAST(1.0,GREATEST(0.0,CAST({end}-start_day AS DOUBLE)/term_days))) earned,
SUM(booked*(1-LEAST(1.0,GREATEST(0.0,CAST({end}-start_day AS DOUBLE)/term_days)))) deferred_revenue
FROM contracts WHERE start_day<{end} GROUP BY cid),
loan_rank AS (SELECT *,ROW_NUMBER() OVER(PARTITION BY loan_id ORDER BY day DESC) rn FROM loan_performance WHERE day<{end}),
credit_now AS (SELECT l.cid,SUM(COALESCE(p.balance,l.principal)) balance,MAX(COALESCE(p.dpd,0)) dpd,
MAX(COALESCE(p.defaulted,0)) defaulted FROM loans l LEFT JOIN loan_rank p ON l.loan_id=p.loan_id AND p.rn=1 WHERE l.opened<{end} GROUP BY l.cid),
fraud AS (SELECT cid,COUNT(*) fraud_payments,SUM(amount*chargeback) chargeback,SUM(amount) payment_volume FROM fraud_payments WHERE day<{end} GROUP BY cid),
exp AS (SELECT cid,AVG(baseline) baseline,AVG(revenue) exp_revenue,AVG(latency) latency FROM experiment WHERE day<{end} GROUP BY cid),
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
{end}-COALESCE((SELECT MAX(o2.day) FROM orders o2 WHERE o2.cid=c.cid AND o2.cancelled=0 AND o2.day<{end}),c.signup) recency,
CASE WHEN EXISTS(SELECT 1 FROM receivables ar JOIN orders oo ON ar.oid=oo.oid WHERE oo.cid=c.cid AND oo.day<{end} AND ar.due_day<{end}
AND NOT EXISTS(SELECT 1 FROM payments pp WHERE pp.oid=oo.oid AND pp.success=1 AND pp.day<{end})) THEN 1 ELSE 0 END unpaid_order,
CASE WHEN NOT EXISTS(SELECT 1 FROM fraud_payments ff WHERE ff.cid=c.cid AND ff.chargeback=1 AND ff.day<{end}) THEN 1 ELSE 0 END clean_history,
CASE WHEN c.cid IN(SELECT ev.cid FROM events ev WHERE ev.kind=4 AND ev.day BETWEEN {start} AND {end}-1
AND EXISTS(SELECT 1 FROM orders eo WHERE eo.cid=ev.cid AND eo.day<=ev.day AND eo.cancelled=0)) THEN 1 ELSE 0 END confirmed_journey,
COALESCE((SELECT AVG(pc.credit) FROM edges ee JOIN customers pc ON ee.dst=pc.cid WHERE ee.src=c.cid AND pc.credit IS NOT NULL),80) peer_credit
FROM chosen c LEFT JOIN sales s ON c.cid=s.cid LEFT JOIN support t ON c.cid=t.cid LEFT JOIN journey j ON c.cid=j.cid
LEFT JOIN subs u ON c.cid=u.cid LEFT JOIN contracts_now k ON c.cid=k.cid LEFT JOIN credit_now l ON c.cid=l.cid
LEFT JOIN fraud f ON c.cid=f.cid LEFT JOIN exp x ON c.cid=x.cid LEFT JOIN peer e ON c.cid=e.src)
SELECT * FROM wide ORDER BY cid'''

PRODUCT='''WITH dense AS (SELECT p.pid,p.category,p.price,c.day,c.week,c.weekday FROM products p CROSS JOIN calendar c WHERE c.day BETWEEN {start} AND {end}-1),
paid AS (SELECT oid,SUM(paid) cash FROM payments WHERE success=1 AND day<{end} GROUP BY oid),
returned AS (SELECT oid,SUM(refunded) refunded FROM refunds WHERE day<{end} GROUP BY oid),
item_sales AS (SELECT i.pid,o.day,SUM(i.qty) units,SUM((COALESCE(a.cash,0)-COALESCE(r.refunded,0))*i.qty*i.price/o.amount) revenue,
SUM((COALESCE(a.cash,0)-COALESCE(r.refunded,0)-o.cost-s.freight)*i.qty*i.price/o.amount) margin,
COUNT(DISTINCT o.cid) customers,AVG(CASE WHEN s.delivered_day<{end} THEN GREATEST(0,s.delivered_day-s.promised_day) ELSE NULL END) late
FROM items i JOIN orders o ON i.oid=o.oid JOIN customers cc ON o.cid=cc.cid LEFT JOIN paid a ON o.oid=a.oid
LEFT JOIN returned r ON o.oid=r.oid LEFT JOIN shipments s ON o.oid=s.oid WHERE o.cancelled=0 AND o.day BETWEEN {start} AND {end}-1 GROUP BY i.pid,o.day),
stock AS (SELECT *,ROW_NUMBER() OVER(PARTITION BY pid ORDER BY day DESC) rn FROM inventory WHERE day<{end}),
price_path AS (SELECT *,LAG(units) OVER(PARTITION BY pid ORDER BY day) previous_units,
AVG(units) OVER(PARTITION BY pid ORDER BY day ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) rolling_units FROM prices WHERE day<{end}),
received AS (SELECT supplier,pid,SUM(ordered) ordered,SUM(received) received,AVG(delay) delay FROM supply WHERE day BETWEEN {start} AND {end}-1 GROUP BY supplier,pid),
plant_daily AS (SELECT m.plant,s.day,SUM(p.output_units) output,SUM(p.defects) defects,SUM(p.scrap_cost) scrap,
AVG(s.vibration) vibration,SUM(s.failure) failures,SUM(s.downtime) downtime,SUM(m.capacity) capacity
FROM machines m JOIN sensors s ON m.machine=s.machine JOIN production p ON m.machine=p.machine AND s.day=p.day
WHERE s.day BETWEEN {start} AND {end}-1 GROUP BY m.plant,s.day),
energy_daily AS (SELECT site,day,SUM(kwh*tariff) energy_cost,SUM(kwh*carbon) carbon,SUM(kwh) kwh FROM energy WHERE day BETWEEN {start} AND {end}-1 GROUP BY site,day),
market_lag AS (SELECT *,LAG(close_price) OVER(PARTITION BY asset ORDER BY day) previous_close FROM market WHERE day<{end}),
macro AS (SELECT asset,AVG(LN(close_price/previous_close)) return_mean,AVG(volume) volume FROM market_lag WHERE previous_close IS NOT NULL AND day>={start} GROUP BY asset),
daily AS (SELECT d.*,COALESCE(x.units,0) sold,COALESCE(x.revenue,0) revenue,COALESCE(x.margin,0) margin,
COALESCE(x.customers,0) buyers,COALESCE(x.late,0) late,pr.units observed_demand,pr.sale_price,pr.promo,pr.stockout,pr.rolling_units,
pl.output,pl.defects,pl.vibration,pl.failures,pl.downtime,pl.capacity,en.energy_cost,en.carbon,en.kwh,
t.revenue_target,t.risk_budget FROM dense d LEFT JOIN item_sales x ON d.pid=x.pid AND d.day=x.day
JOIN price_path pr ON d.pid=pr.pid AND d.day=pr.day JOIN plant_daily pl ON d.category=pl.plant AND d.day=pl.day
JOIN energy_daily en ON pl.plant=en.site AND pl.day=en.day LEFT JOIN targets t ON t.tier=d.category%3 AND t.week=d.week),
summary AS (SELECT pid,category,MAX(price) price,COUNT(*) calendar_days,SUM(sold) sold,SUM(revenue) revenue,SUM(margin) margin,
AVG(observed_demand) demand,AVG(observed_demand*observed_demand)-AVG(observed_demand)*AVG(observed_demand) demand_variance,
AVG(sale_price) sale_price,AVG(CAST(promo AS DOUBLE)) promo_rate,AVG(CAST(stockout AS DOUBLE)) stockout_rate,
AVG(rolling_units) rolling_units,AVG(buyers) buyers,AVG(late) late,AVG(output) output,AVG(defects) defects,
AVG(vibration) vibration,SUM(failures) failures,SUM(downtime) downtime,AVG(capacity) capacity,
AVG(energy_cost) energy_cost,AVG(carbon) carbon,AVG(kwh) kwh,AVG(revenue_target) revenue_target,AVG(risk_budget) risk_budget FROM daily GROUP BY pid,category),
wide AS (SELECT d.*,i.on_hand,i.lead_days,s.supplier,s.country,s.unit_cost,
COALESCE(r.received/NULLIF(r.ordered,0),1) fill_rate,COALESCE(r.delay,0) delay,
COALESCE(m.return_mean,0) macro_return,COALESCE(m.volume,0) macro_volume,
(SELECT AVG(s2.unit_cost) FROM suppliers s2 WHERE s2.country=s.country) country_cost,
(SELECT SUM(a2.received) FROM supply a2 WHERE a2.supplier=s.supplier AND a2.day=(SELECT MAX(a3.day) FROM supply a3 WHERE a3.supplier=a2.supplier AND a3.day<{end})) latest_delivery,
CASE WHEN EXISTS(SELECT 1 FROM prices p2 WHERE p2.pid=d.pid AND p2.stockout=1 AND p2.day BETWEEN {start} AND {end}-1
AND NOT EXISTS(SELECT 1 FROM supply a4 WHERE a4.pid=p2.pid AND a4.day=p2.day)) THEN 1 ELSE 0 END uncovered_stockout,
CASE WHEN d.pid IN(SELECT p3.pid FROM products p3 WHERE p3.price>(SELECT AVG(p4.price) FROM products p4 WHERE p4.category=p3.category)) THEN 1 ELSE 0 END premium,
(SELECT AVG(ca.spend) FROM campaigns ca WHERE ca.day BETWEEN {start} AND {end}-1 AND ca.channel=d.category%4) marketing_spend
FROM summary d JOIN stock i ON d.pid=i.pid AND i.rn=1 JOIN suppliers s ON d.pid=s.pid
LEFT JOIN received r ON s.supplier=r.supplier AND d.pid=r.pid LEFT JOIN macro m ON d.category=m.asset)
SELECT * FROM wide ORDER BY pid'''

def query(domain,i):
    sql=(CUSTOMER if domain=='customer' else PRODUCT).format(**params(i))
    # MySQL decimal literals and Spark/DuckDB floating arithmetic share a type contract.
    return re.sub(r'(?<![\w.])\d+\.\d+(?![\w.])',lambda m:'CAST('+m[0]+' AS DOUBLE)',sql)

QUESTIONS=[
('customer','margin_drivers','多渠道、多账本、多履约成本下，客户利润由哪些因素驱动？'),
('customer','lifetime_tail','订阅、合同和订单联动后，客户终身价值下行风险有多大？'),
('customer','credit_calibration','客户服务、交易和信贷快照合并后，信用风险如何校准并检查分组偏差？'),
('customer','peer_contagion','客户相似图上的信用与逾期风险如何传播？'),
('customer','customer_segments','复杂客户行为经降维和聚类后，哪些客群有利润或服务风险？'),
('customer','retention_budget','在预算及区域覆盖约束下，如何分配客户挽留资源？'),
('customer','credit_cvar','相关客户的贷款损失在压力情境下如何控制尾部风险？'),
('customer','support_assignment','按服务负担与收益，如何在容量约束下分配客户服务资源？'),
('customer','behavior_regimes','客户交易、支持、订阅与旅程行为是否形成混合分布？'),
('customer','customer_allocation','收益与风险共同约束下，应如何配置客户经营资源？'),
('product','demand_drivers','价格、推广、物流、库存与工厂状况如何共同解释商品需求？'),
('product','inventory_tail','需求不确定性和供给不足同时发生时，怎样安排整数补货？'),
('product','sourcing_transport','跨国家供应与工厂资源约束下，如何优化采购运输？'),
('product','supply_contagion','共享国家及品类的供应网络如何传播断供风险？'),
('product','energy_frontier','商品价值、产能、能耗与碳排联动后的经营前沿在哪里？'),
('product','quality_regimes','需求、质量、机器故障和履约风险如何形成异常生产群？'),
('product','factory_stress','供给延迟与机器停机叠加时，产销利润尾部损失有多大？'),
('product','assortment_coverage','预算和品类覆盖约束下，如何配置商品组合？'),
('product','pricing_surface','多因素非线性模型下，各品类的价格与需求关联是否稳定？'),
('product','integrated_planning','怎样联合安排采购、库存、产能、现金与碳排预算？')]
