-- chain_44_attribution_time_series_graph_inventory
WITH selected_customers AS (SELECT * FROM customers WHERE cid>=1 AND cid<91),
oo AS (SELECT o.* FROM orders o JOIN selected_customers c ON o.cid=c.cid WHERE o.day BETWEEN 0 AND 55-1),
ee AS (SELECT e.* FROM events e JOIN selected_customers c ON e.cid=c.cid WHERE e.day BETWEEN 0 AND 55-1),

attribution_touch AS (SELECT o.cid,o.oid,o.amount,e.kind,EXP(-CAST(0.01 AS DOUBLE)*(o.day-e.day)) w FROM oo o JOIN ee e ON o.cid=e.cid AND e.day BETWEEN o.day-7 AND o.day),
attribution_weight AS (SELECT cid,oid,amount,kind,w,SUM(w) OVER(PARTITION BY oid) total FROM attribution_touch),
attribution_channel AS (SELECT cid,kind,SUM(amount*w/total) rev FROM attribution_weight GROUP BY cid,kind),
attribution_probability AS (SELECT cid,kind,rev,rev/NULLIF(SUM(rev) OVER(PARTITION BY cid),0) p FROM attribution_channel),
attribution_customer AS (SELECT cid,SUM(rev) x,SUM(rev*kind)/NULLIF(SUM(rev),0) y,-SUM(p*LN(NULLIF(p,0))) z FROM attribution_probability GROUP BY cid),

time_daily AS (SELECT cid,day,SUM(amount) revenue FROM oo WHERE cancelled=0 GROUP BY cid,day),
time_grid AS (SELECT c.cid,d.day,COALESCE(a.revenue,0) revenue FROM selected_customers c CROSS JOIN calendar d LEFT JOIN time_daily a ON c.cid=a.cid AND d.day=a.day WHERE d.day BETWEEN 0 AND 55-1),
time_rolling AS (SELECT cid,day,revenue,AVG(revenue) OVER(PARTITION BY cid ORDER BY day ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) ma FROM time_grid),
time_delta AS (SELECT cid,day,revenue,ma,ma-LAG(ma) OVER(PARTITION BY cid ORDER BY day) delta FROM time_rolling),
time_regime AS (SELECT cid,day,revenue,ma,delta,AVG(delta) OVER(PARTITION BY cid ORDER BY day ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) trend FROM time_delta),
time_series_customer AS (SELECT cid,AVG(ma) x,STDDEV_POP(delta) y,SUM(COALESCE(trend,0)) z FROM time_regime GROUP BY cid),

graph_first AS (SELECT c.cid,e.dst,e.weight FROM selected_customers c JOIN edges e ON c.cid=e.src WHERE e.dst<>c.cid),
graph_second AS (SELECT a.cid,e.dst,a.weight*e.weight weight FROM graph_first a JOIN edges e ON a.dst=e.src WHERE e.dst<>a.cid),
graph_paths AS (SELECT a.cid,e.dst,a.weight*e.weight weight FROM graph_second a JOIN edges e ON a.dst=e.src WHERE e.dst<>a.cid),
graph_neighbor AS (SELECT a.cid,a.dst,a.weight,c.credit,c.tier FROM graph_paths a JOIN customers c ON a.dst=c.cid),
graph_customer AS (SELECT cid,SUM(weight*credit)/NULLIF(SUM(CASE WHEN credit IS NOT NULL THEN weight ELSE 0 END),0) x,VAR_POP(credit) y,SUM(weight*tier)/NULLIF(SUM(weight),0) z FROM graph_neighbor GROUP BY cid),

inventory_period AS (SELECT i.pid,AVG(CAST(on_hand AS DOUBLE)) stock,AVG(CAST(CASE WHEN on_hand<lead_days THEN 1 ELSE 0 END AS DOUBLE)) shortage,MAX(lead_days) lead FROM inventory i WHERE day BETWEEN 0 AND 55-1 GROUP BY i.pid),
inventory_category AS (SELECT p.category,AVG(i.shortage) shortage,AVG(i.stock) stock,AVG(CAST(i.lead AS DOUBLE)) lead FROM inventory_period i JOIN products p ON i.pid=p.pid GROUP BY p.category),
inventory_basket AS (SELECT o.cid,p.category,SUM(i.qty*i.price) spend FROM oo o JOIN items i ON o.oid=i.oid JOIN products p ON i.pid=p.pid GROUP BY o.cid,p.category),
inventory_exposure AS (SELECT a.cid,a.spend,b.shortage,b.stock,b.lead FROM inventory_basket a JOIN inventory_category b ON a.category=b.category),
inventory_customer AS (SELECT cid,SUM(spend*shortage)/NULLIF(SUM(spend),0) x,SUM(spend*stock)/NULLIF(SUM(spend),0) y,SUM(spend*lead)/NULLIF(SUM(spend),0) z FROM inventory_exposure GROUP BY cid),
feature_raw AS (SELECT c.cid,c.tier,c.region,COALESCE(b0.x,0) f1,COALESCE(b0.y,0) f2,COALESCE(b0.z,0) f3,COALESCE(b1.x,0) f4,COALESCE(b1.y,0) f5,COALESCE(b1.z,0) f6,COALESCE(b2.x,0) f7,COALESCE(b2.y,0) f8,COALESCE(b2.z,0) f9,COALESCE(b3.x,0) f10,COALESCE(b3.y,0) f11,COALESCE(b3.z,0) f12 FROM selected_customers c LEFT JOIN attribution_customer b0 ON c.cid=b0.cid LEFT JOIN time_series_customer b1 ON c.cid=b1.cid LEFT JOIN graph_customer b2 ON c.cid=b2.cid LEFT JOIN inventory_customer b3 ON c.cid=b3.cid),
feature_normalized AS (SELECT cid,tier,region,f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,(f1-AVG(f1) OVER())/COALESCE(NULLIF(STDDEV_POP(f1) OVER(),0),1)+(f2-AVG(f2) OVER())/COALESCE(NULLIF(STDDEV_POP(f2) OVER(),0),1)+(f3-AVG(f3) OVER())/COALESCE(NULLIF(STDDEV_POP(f3) OVER(),0),1)+(f4-AVG(f4) OVER())/COALESCE(NULLIF(STDDEV_POP(f4) OVER(),0),1)+(f5-AVG(f5) OVER())/COALESCE(NULLIF(STDDEV_POP(f5) OVER(),0),1)+(f6-AVG(f6) OVER())/COALESCE(NULLIF(STDDEV_POP(f6) OVER(),0),1)+(f7-AVG(f7) OVER())/COALESCE(NULLIF(STDDEV_POP(f7) OVER(),0),1)+(f8-AVG(f8) OVER())/COALESCE(NULLIF(STDDEV_POP(f8) OVER(),0),1)+(f9-AVG(f9) OVER())/COALESCE(NULLIF(STDDEV_POP(f9) OVER(),0),1)+(f10-AVG(f10) OVER())/COALESCE(NULLIF(STDDEV_POP(f10) OVER(),0),1)+(f11-AVG(f11) OVER())/COALESCE(NULLIF(STDDEV_POP(f11) OVER(),0),1)+(f12-AVG(f12) OVER())/COALESCE(NULLIF(STDDEV_POP(f12) OVER(),0),1) normalized_score FROM feature_raw),
feedback_0 AS (SELECT cid,tier,region,f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,1/(1+EXP(-LEAST(30,GREATEST(-30,normalized_score/12)))) score FROM feature_normalized),
feedback_1 AS (SELECT cid,tier,region,f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,(score+1/(1+EXP(-LEAST(30,GREATEST(-30,CAST(0.1300 AS DOUBLE)*score+CAST(0.0040 AS DOUBLE)*LN(1+ABS(f2)))))))/2 score FROM feedback_0),
feedback_2 AS (SELECT cid,tier,region,f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,(score+1/(1+EXP(-LEAST(30,GREATEST(-30,CAST(0.1400 AS DOUBLE)*score+CAST(0.0050 AS DOUBLE)*LN(1+ABS(f3)))))))/2 score FROM feedback_1),
feedback_3 AS (SELECT cid,tier,region,f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,(score+1/(1+EXP(-LEAST(30,GREATEST(-30,CAST(0.1500 AS DOUBLE)*score+CAST(0.0060 AS DOUBLE)*LN(1+ABS(f4)))))))/2 score FROM feedback_2),
feedback_4 AS (SELECT cid,tier,region,f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,(score+1/(1+EXP(-LEAST(30,GREATEST(-30,CAST(0.1600 AS DOUBLE)*score+CAST(0.0070 AS DOUBLE)*LN(1+ABS(f5)))))))/2 score FROM feedback_3),
customer_rank AS (SELECT cid,tier,region,f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,score,ROW_NUMBER() OVER(PARTITION BY tier ORDER BY ROUND(score,9) DESC,cid) rn,NTILE(3) OVER(PARTITION BY tier ORDER BY ROUND(score,9),cid) bucket FROM feedback_4),
budget_join AS (SELECT r.*,t.revenue_target,t.risk_budget FROM customer_rank r JOIN targets t ON r.tier=t.tier AND t.week=FLOOR((55-1)/7))
SELECT cid,tier,region,score,f1+f2+f3+f4+f5+f6+f7+f8+f9+f10+f11+f12 feature_sum,score*(f1+f2+f3+f4+f5+f6+f7+f8+f9+f10+f11+f12) weighted FROM budget_join ORDER BY cid;
