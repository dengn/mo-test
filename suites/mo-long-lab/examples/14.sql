-- chain_14_commerce_market_marketing_subscription
WITH selected_customers AS (SELECT * FROM customers WHERE cid>=1 AND cid<91),
oo AS (SELECT o.* FROM orders o JOIN selected_customers c ON o.cid=c.cid WHERE o.day BETWEEN 0 AND 55-1),
ee AS (SELECT e.* FROM events e JOIN selected_customers c ON e.cid=c.cid WHERE e.day BETWEEN 0 AND 55-1),

pay_ok AS (SELECT oid,SUM(CASE WHEN success=1 THEN paid ELSE 0 END) paid FROM payments GROUP BY oid),
refund_ok AS (SELECT oid,SUM(refunded) refund FROM refunds GROUP BY oid),
commerce_order AS (SELECT o.*,COALESCE(p.paid,0)-COALESCE(r.refund,0) net FROM oo o LEFT JOIN pay_ok p ON o.oid=p.oid LEFT JOIN refund_ok r ON o.oid=r.oid),
commerce_customer AS (SELECT cid,SUM(net) x,AVG(amount-cost) y,SUM(amount-net)/NULLIF(SUM(amount),0) z FROM commerce_order WHERE cancelled=0 GROUP BY cid),

market_lag AS (SELECT asset,day,close_price,LAG(close_price) OVER(PARTITION BY asset ORDER BY day) prev FROM market),
market_returns AS (SELECT asset,day,close_price,LN(close_price/prev) ret FROM market_lag WHERE day BETWEEN 0 AND 180),
market_rolling AS (SELECT asset,day,close_price,ret,AVG(ret) OVER(PARTITION BY asset ORDER BY day ROWS BETWEEN 20 PRECEDING AND CURRENT ROW) ma,VAR_POP(ret) OVER(PARTITION BY asset ORDER BY day ROWS BETWEEN 20 PRECEDING AND CURRENT ROW) rv FROM market_returns),
market_peak AS (SELECT asset,day,ret,ma,rv,close_price/MAX(close_price) OVER(PARTITION BY asset ORDER BY day ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)-1 drawdown FROM market_rolling),
market_asset AS (SELECT asset,SUM(ret) growth,AVG(rv) volatility,MIN(drawdown) drawdown FROM market_peak GROUP BY asset),
market_customer AS (SELECT c.cid,a.growth*COALESCE(c.credit,0) x,a.volatility y,a.drawdown z FROM selected_customers c JOIN market_asset a ON MOD(c.cid,8)=a.asset),

marketing_counts AS (SELECT MOD(kind,4) channel,day,COUNT(*) n FROM ee GROUP BY MOD(kind,4),day),
marketing_alloc AS (SELECT e.cid,e.day,e.kind,c.spend/CAST(a.n AS DOUBLE) allocated FROM ee e JOIN marketing_counts a ON MOD(e.kind,4)=a.channel AND e.day=a.day JOIN campaigns c ON a.channel=c.channel AND a.day=c.day),
marketing_customer_cost AS (SELECT cid,SUM(allocated) allocated_cost,SUM(CASE WHEN kind=3 THEN allocated ELSE 0 END) conv_rates FROM marketing_alloc GROUP BY cid),
marketing_customer_rev AS (SELECT cid,SUM(amount-cost) margin FROM oo WHERE cancelled=0 GROUP BY cid),
marketing_customer AS (SELECT c.cid,COALESCE(r.margin,0)/NULLIF(c.allocated_cost,0) x,c.allocated_cost y,c.conv_rates/NULLIF(c.allocated_cost,0) z FROM marketing_customer_cost c LEFT JOIN marketing_customer_rev r ON c.cid=r.cid),

subscription_rows AS (SELECT s.*,s.billed-s.paid arrears FROM subscriptions s JOIN selected_customers c ON s.cid=c.cid WHERE month BETWEEN 0 AND 15),
subscription_running AS (SELECT cid,month,active,arrears,SUM(arrears) OVER(PARTITION BY cid ORDER BY month ROWS BETWEEN 5 PRECEDING AND CURRENT ROW) backlog,LAG(active) OVER(PARTITION BY cid ORDER BY month) prev_active FROM subscription_rows),
subscription_lifecycle AS (SELECT cid,SUM(arrears) arrears,MAX(backlog) backlog,SUM(CASE WHEN active=1 AND prev_active=0 THEN 1 ELSE 0 END) reactivated,AVG(CAST(active AS DOUBLE)) active_retention FROM subscription_running GROUP BY cid),
subscription_credit AS (SELECT tier,AVG(credit) credit FROM selected_customers GROUP BY tier),
subscription_customer AS (SELECT c.cid,l.arrears/NULLIF(COALESCE(c.credit,t.credit),0) x,l.backlog y,l.active_retention+CAST(l.reactivated AS DOUBLE)/10 z FROM selected_customers c JOIN subscription_lifecycle l ON c.cid=l.cid LEFT JOIN subscription_credit t ON c.tier=t.tier),
feature_raw AS (SELECT c.cid,c.tier,c.region,COALESCE(b0.x,0) f1,COALESCE(b0.y,0) f2,COALESCE(b0.z,0) f3,COALESCE(b1.x,0) f4,COALESCE(b1.y,0) f5,COALESCE(b1.z,0) f6,COALESCE(b2.x,0) f7,COALESCE(b2.y,0) f8,COALESCE(b2.z,0) f9,COALESCE(b3.x,0) f10,COALESCE(b3.y,0) f11,COALESCE(b3.z,0) f12 FROM selected_customers c LEFT JOIN commerce_customer b0 ON c.cid=b0.cid LEFT JOIN market_customer b1 ON c.cid=b1.cid LEFT JOIN marketing_customer b2 ON c.cid=b2.cid LEFT JOIN subscription_customer b3 ON c.cid=b3.cid),
feature_normalized AS (SELECT cid,tier,region,f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,(f1-AVG(f1) OVER())/COALESCE(NULLIF(STDDEV_POP(f1) OVER(),0),1)+(f2-AVG(f2) OVER())/COALESCE(NULLIF(STDDEV_POP(f2) OVER(),0),1)+(f3-AVG(f3) OVER())/COALESCE(NULLIF(STDDEV_POP(f3) OVER(),0),1)+(f4-AVG(f4) OVER())/COALESCE(NULLIF(STDDEV_POP(f4) OVER(),0),1)+(f5-AVG(f5) OVER())/COALESCE(NULLIF(STDDEV_POP(f5) OVER(),0),1)+(f6-AVG(f6) OVER())/COALESCE(NULLIF(STDDEV_POP(f6) OVER(),0),1)+(f7-AVG(f7) OVER())/COALESCE(NULLIF(STDDEV_POP(f7) OVER(),0),1)+(f8-AVG(f8) OVER())/COALESCE(NULLIF(STDDEV_POP(f8) OVER(),0),1)+(f9-AVG(f9) OVER())/COALESCE(NULLIF(STDDEV_POP(f9) OVER(),0),1)+(f10-AVG(f10) OVER())/COALESCE(NULLIF(STDDEV_POP(f10) OVER(),0),1)+(f11-AVG(f11) OVER())/COALESCE(NULLIF(STDDEV_POP(f11) OVER(),0),1)+(f12-AVG(f12) OVER())/COALESCE(NULLIF(STDDEV_POP(f12) OVER(),0),1) normalized_score FROM feature_raw),
feedback_0 AS (SELECT cid,tier,region,f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,1/(1+EXP(-LEAST(30,GREATEST(-30,normalized_score/12)))) score FROM feature_normalized),
feedback_1 AS (SELECT cid,tier,region,f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,(score+1/(1+EXP(-LEAST(30,GREATEST(-30,CAST(0.1300 AS DOUBLE)*score+CAST(0.0040 AS DOUBLE)*LN(1+ABS(f2)))))))/2 score FROM feedback_0),
feedback_2 AS (SELECT cid,tier,region,f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,(score+1/(1+EXP(-LEAST(30,GREATEST(-30,CAST(0.1400 AS DOUBLE)*score+CAST(0.0050 AS DOUBLE)*LN(1+ABS(f3)))))))/2 score FROM feedback_1),
feedback_3 AS (SELECT cid,tier,region,f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,(score+1/(1+EXP(-LEAST(30,GREATEST(-30,CAST(0.1500 AS DOUBLE)*score+CAST(0.0060 AS DOUBLE)*LN(1+ABS(f4)))))))/2 score FROM feedback_2),
feedback_4 AS (SELECT cid,tier,region,f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,(score+1/(1+EXP(-LEAST(30,GREATEST(-30,CAST(0.1600 AS DOUBLE)*score+CAST(0.0070 AS DOUBLE)*LN(1+ABS(f5)))))))/2 score FROM feedback_3),
feedback_5 AS (SELECT cid,tier,region,f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,(score+1/(1+EXP(-LEAST(30,GREATEST(-30,CAST(0.1700 AS DOUBLE)*score+CAST(0.0030 AS DOUBLE)*LN(1+ABS(f6)))))))/2 score FROM feedback_4),
customer_rank AS (SELECT cid,tier,region,f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,score,ROW_NUMBER() OVER(PARTITION BY tier ORDER BY ROUND(score,9) DESC,cid) rn,NTILE(3) OVER(PARTITION BY tier ORDER BY ROUND(score,9),cid) bucket FROM feedback_5),
budget_join AS (SELECT r.*,t.revenue_target,t.risk_budget FROM customer_rank r JOIN targets t ON r.tier=t.tier AND t.week=FLOOR((55-1)/7))
SELECT tier,bucket,COUNT(*),SUM(score),SUM(f1),SUM(score*risk_budget) FROM budget_join GROUP BY GROUPING SETS((tier,bucket),(tier),()) ORDER BY COALESCE(tier,-1),COALESCE(bucket,-1);
