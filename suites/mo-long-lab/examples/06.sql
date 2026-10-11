-- chain_6_cohort_graph_inventory_marketing
WITH selected_customers AS (SELECT * FROM customers WHERE cid>=1 AND cid<91),
oo AS (SELECT o.* FROM orders o JOIN selected_customers c ON o.cid=c.cid WHERE o.day BETWEEN 0 AND 55-1),
ee AS (SELECT e.* FROM events e JOIN selected_customers c ON e.cid=c.cid WHERE e.day BETWEEN 0 AND 55-1),

cohort_days AS (SELECT DISTINCT cid,day FROM ee),
cohort_seq AS (SELECT cid,day,day-CAST(ROW_NUMBER() OVER(PARTITION BY cid ORDER BY day) AS BIGINT) island FROM cohort_days),
cohort_streak AS (SELECT cid,island,COUNT(*) n FROM cohort_seq GROUP BY cid,island),
cohort_longest AS (SELECT cid,MAX(n) streak FROM cohort_streak GROUP BY cid),
cohort_session AS (SELECT cid,session_id,MIN(CASE WHEN kind=0 THEN day END) viewed,MAX(CASE WHEN kind=3 THEN day END) purchased FROM ee GROUP BY cid,session_id),
cohort_conv_rate AS (SELECT cid,AVG(CAST(CASE WHEN purchased>=viewed THEN 1 ELSE 0 END AS DOUBLE)) conv_rate FROM cohort_session GROUP BY cid),
cohort_customer AS (SELECT a.cid,CAST(a.streak AS DOUBLE) x,COALESCE(b.conv_rate,0) y,CAST(55-MAX(e.day) AS DOUBLE) z FROM cohort_longest a LEFT JOIN cohort_conv_rate b ON a.cid=b.cid JOIN ee e ON a.cid=e.cid GROUP BY a.cid,a.streak,b.conv_rate),

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

marketing_counts AS (SELECT MOD(kind,4) channel,day,COUNT(*) n FROM ee GROUP BY MOD(kind,4),day),
marketing_alloc AS (SELECT e.cid,e.day,e.kind,c.spend/CAST(a.n AS DOUBLE) allocated FROM ee e JOIN marketing_counts a ON MOD(e.kind,4)=a.channel AND e.day=a.day JOIN campaigns c ON a.channel=c.channel AND a.day=c.day),
marketing_customer_cost AS (SELECT cid,SUM(allocated) allocated_cost,SUM(CASE WHEN kind=3 THEN allocated ELSE 0 END) conv_rates FROM marketing_alloc GROUP BY cid),
marketing_customer_rev AS (SELECT cid,SUM(amount-cost) margin FROM oo WHERE cancelled=0 GROUP BY cid),
marketing_customer AS (SELECT c.cid,COALESCE(r.margin,0)/NULLIF(c.allocated_cost,0) x,c.allocated_cost y,c.conv_rates/NULLIF(c.allocated_cost,0) z FROM marketing_customer_cost c LEFT JOIN marketing_customer_rev r ON c.cid=r.cid),
feature_raw AS (SELECT c.cid,c.tier,c.region,COALESCE(b0.x,0) f1,COALESCE(b0.y,0) f2,COALESCE(b0.z,0) f3,COALESCE(b1.x,0) f4,COALESCE(b1.y,0) f5,COALESCE(b1.z,0) f6,COALESCE(b2.x,0) f7,COALESCE(b2.y,0) f8,COALESCE(b2.z,0) f9,COALESCE(b3.x,0) f10,COALESCE(b3.y,0) f11,COALESCE(b3.z,0) f12 FROM selected_customers c LEFT JOIN cohort_customer b0 ON c.cid=b0.cid LEFT JOIN graph_customer b1 ON c.cid=b1.cid LEFT JOIN inventory_customer b2 ON c.cid=b2.cid LEFT JOIN marketing_customer b3 ON c.cid=b3.cid),
feature_normalized AS (SELECT cid,tier,region,f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,(f1-AVG(f1) OVER())/COALESCE(NULLIF(STDDEV_POP(f1) OVER(),0),1)+(f2-AVG(f2) OVER())/COALESCE(NULLIF(STDDEV_POP(f2) OVER(),0),1)+(f3-AVG(f3) OVER())/COALESCE(NULLIF(STDDEV_POP(f3) OVER(),0),1)+(f4-AVG(f4) OVER())/COALESCE(NULLIF(STDDEV_POP(f4) OVER(),0),1)+(f5-AVG(f5) OVER())/COALESCE(NULLIF(STDDEV_POP(f5) OVER(),0),1)+(f6-AVG(f6) OVER())/COALESCE(NULLIF(STDDEV_POP(f6) OVER(),0),1)+(f7-AVG(f7) OVER())/COALESCE(NULLIF(STDDEV_POP(f7) OVER(),0),1)+(f8-AVG(f8) OVER())/COALESCE(NULLIF(STDDEV_POP(f8) OVER(),0),1)+(f9-AVG(f9) OVER())/COALESCE(NULLIF(STDDEV_POP(f9) OVER(),0),1)+(f10-AVG(f10) OVER())/COALESCE(NULLIF(STDDEV_POP(f10) OVER(),0),1)+(f11-AVG(f11) OVER())/COALESCE(NULLIF(STDDEV_POP(f11) OVER(),0),1)+(f12-AVG(f12) OVER())/COALESCE(NULLIF(STDDEV_POP(f12) OVER(),0),1) normalized_score FROM feature_raw),
feedback_0 AS (SELECT cid,tier,region,f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,1/(1+EXP(-LEAST(30,GREATEST(-30,normalized_score/12)))) score FROM feature_normalized),
feedback_1 AS (SELECT cid,tier,region,f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,(score+1/(1+EXP(-LEAST(30,GREATEST(-30,CAST(0.1300 AS DOUBLE)*score+CAST(0.0040 AS DOUBLE)*LN(1+ABS(f2)))))))/2 score FROM feedback_0),
feedback_2 AS (SELECT cid,tier,region,f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,(score+1/(1+EXP(-LEAST(30,GREATEST(-30,CAST(0.1400 AS DOUBLE)*score+CAST(0.0050 AS DOUBLE)*LN(1+ABS(f3)))))))/2 score FROM feedback_1),
feedback_3 AS (SELECT cid,tier,region,f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,(score+1/(1+EXP(-LEAST(30,GREATEST(-30,CAST(0.1500 AS DOUBLE)*score+CAST(0.0060 AS DOUBLE)*LN(1+ABS(f4)))))))/2 score FROM feedback_2),
customer_rank AS (SELECT cid,tier,region,f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,score,ROW_NUMBER() OVER(PARTITION BY tier ORDER BY ROUND(score,9) DESC,cid) rn,NTILE(3) OVER(PARTITION BY tier ORDER BY ROUND(score,9),cid) bucket FROM feedback_3),
budget_join AS (SELECT r.*,t.revenue_target,t.risk_budget FROM customer_rank r JOIN targets t ON r.tier=t.tier AND t.week=FLOOR((55-1)/7))
SELECT cid,tier,rn,score,f1,f2,f3,f1+f2+f3+f4+f5+f6+f7+f8+f9+f10+f11+f12 feature_sum FROM budget_join WHERE rn<=2 ORDER BY tier,rn;
