"""80 complex SQL scenarios and 20 client numerical/ML pipelines."""
from data import BASE,params
import re

SQL=[]
def add(name,category,body): SQL.append((name,category,body))

# Commerce: preserve entity grain across one-to-many joins.
add('net_revenue_reconciliation','multi_table_commerce', ''', p AS (SELECT oid,SUM(CASE WHEN success=1 THEN paid ELSE 0 END) paid FROM payments GROUP BY oid),
r AS (SELECT oid,SUM(refunded) refunded FROM refunds GROUP BY oid),
b AS (SELECT o.cid,SUM(o.amount) gross,SUM(COALESCE(p.paid,0)-COALESCE(r.refunded,0)) net FROM oo o LEFT JOIN p ON o.oid=p.oid LEFT JOIN r ON o.oid=r.oid WHERE o.cancelled=0 GROUP BY o.cid)
SELECT COUNT(*),SUM(gross),SUM(net),AVG(net) FROM b''')
add('category_weighted_revenue','multi_table_commerce', ''', a AS (SELECT p.category,SUM(i.qty*i.price) revenue,SUM(i.qty) units FROM oo o JOIN items i ON o.oid=i.oid JOIN products p ON i.pid=p.pid WHERE o.cancelled=0 GROUP BY p.category)
SELECT COUNT(*),SUM(revenue),SUM(revenue)/NULLIF(SUM(units),0) FROM a''')
add('margin_segment_mix','multi_table_commerce', ''', a AS (SELECT c.tier,o.channel,SUM(o.amount-o.cost) margin,SUM(o.amount) rev FROM oo o JOIN scope c ON o.cid=c.cid GROUP BY c.tier,o.channel)
SELECT COUNT(*),SUM(margin),AVG(margin/NULLIF(rev,0)) FROM a''')
add('customer_lifetime_distribution','multi_table_commerce', ''', a AS (SELECT c.cid,c.tier,SUM(CASE WHEN o.cancelled=0 THEN o.amount ELSE 0 END) revenue,COUNT(o.oid) n FROM scope c LEFT JOIN oo o ON c.cid=o.cid GROUP BY c.cid,c.tier),
b AS (SELECT tier,AVG(revenue) rev,AVG(n) orders FROM a GROUP BY tier)
SELECT COUNT(*),SUM(rev),SUM(orders) FROM b''')
add('rfm_quantile_scoring','multi_table_commerce', ''', a AS (SELECT cid,{d1}-MAX(day) recency,COUNT(*) frequency,SUM(amount) monetary FROM oo WHERE cancelled=0 GROUP BY cid),
b AS (SELECT cid,NTILE(5) OVER(ORDER BY recency DESC,cid) r,NTILE(5) OVER(ORDER BY frequency,cid) f,NTILE(5) OVER(ORDER BY monetary,cid) m FROM a)
SELECT COUNT(*),SUM(r+f+m),SUM(CASE WHEN r+f+m>=11 THEN 1 ELSE 0 END) FROM b''')
add('basket_product_cooccurrence','multi_table_commerce', ''', a AS (SELECT i.pid p1,j.pid p2,COUNT(DISTINCT o.oid) n FROM oo o JOIN items i ON o.oid=i.oid JOIN items j ON i.oid=j.oid AND i.pid<j.pid GROUP BY i.pid,j.pid),
b AS (SELECT p1,p2,n,ROW_NUMBER() OVER(ORDER BY n DESC,p1,p2) rn FROM a)
SELECT COUNT(*),SUM(n) FROM b WHERE rn<={k}''')
add('repeat_purchase_intervals','multi_table_commerce', ''', a AS (SELECT cid,oid,day,LAG(day) OVER(PARTITION BY cid ORDER BY day,oid) prev FROM oo WHERE cancelled=0)
SELECT COUNT(prev),AVG(day-prev),VAR_POP(day-prev),MAX(day-prev) FROM a''')
add('refund_rate_by_category','multi_table_commerce', ''', r AS (SELECT DISTINCT oid FROM refunds),a AS (SELECT p.category,COUNT(DISTINCT o.oid) n,COUNT(DISTINCT r.oid) returned FROM oo o JOIN items i ON o.oid=i.oid JOIN products p ON i.pid=p.pid LEFT JOIN r ON o.oid=r.oid GROUP BY p.category)
SELECT COUNT(*),SUM(returned),AVG(returned*1.0/NULLIF(n,0)) FROM a''')
add('payment_coverage_anomaly','multi_table_commerce', ''', p AS (SELECT oid,SUM(CASE WHEN success=1 THEN paid ELSE 0 END) paid FROM payments GROUP BY oid),a AS (SELECT o.cid,o.amount,COALESCE(p.paid,0) paid FROM oo o LEFT JOIN p ON o.oid=p.oid)
SELECT COUNT(*),SUM(CASE WHEN paid<amount-0.000001 THEN 1 ELSE 0 END),SUM(amount-paid) FROM a''')
add('cancelled_customer_anti_join','multi_table_commerce', ''' SELECT COUNT(*),SUM(c.credit) FROM scope c WHERE EXISTS(SELECT 1 FROM oo o WHERE o.cid=c.cid AND o.cancelled=1) AND NOT EXISTS(SELECT 1 FROM oo o WHERE o.cid=c.cid AND o.cancelled=0)''')
add('purchase_without_payment','multi_table_commerce', ''' SELECT COUNT(*),SUM(o.amount) FROM oo o WHERE NOT EXISTS(SELECT 1 FROM payments p WHERE p.oid=o.oid AND p.success=1) AND o.cancelled=0''')
add('top_category_per_customer','multi_table_commerce', ''', a AS (SELECT o.cid,p.category,SUM(i.qty*i.price) rev FROM oo o JOIN items i ON o.oid=i.oid JOIN products p ON i.pid=p.pid GROUP BY o.cid,p.category),
b AS (SELECT cid,category,rev,ROW_NUMBER() OVER(PARTITION BY cid ORDER BY rev DESC,category) rn FROM a)
SELECT COUNT(*),SUM(category),SUM(rev) FROM b WHERE rn=1''')

# Windows and statistical distributions with explicit tie and frame semantics.
add('daily_rolling_sales','time_series', ''', a AS (SELECT day,SUM(amount) rev FROM oo WHERE cancelled=0 GROUP BY day),
b AS (SELECT d.day,COALESCE(a.rev,0) rev FROM calendar d LEFT JOIN a ON d.day=a.day WHERE d.day>={d0} AND d.day<{d1}),
c AS (SELECT day,AVG(rev) OVER(ORDER BY day ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) ma FROM b)
SELECT COUNT(*),SUM(ma),MAX(ma) FROM c''')
add('cumulative_revenue_share','time_series', ''', a AS (SELECT day,SUM(amount) rev FROM oo GROUP BY day),
b AS (SELECT day,rev,SUM(rev) OVER(ORDER BY day ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) cumulative,SUM(rev) OVER() total FROM a)
SELECT COUNT(*),SUM(cumulative/NULLIF(total,0)),MAX(cumulative) FROM b''')
add('week_over_week_growth','time_series', ''', a AS (SELECT d.week,SUM(o.amount) rev FROM oo o JOIN calendar d ON o.day=d.day GROUP BY d.week),
b AS (SELECT week,rev,LAG(rev) OVER(ORDER BY week) prev FROM a)
SELECT COUNT(prev),SUM((rev-prev)/NULLIF(ABS(prev),0)),SUM(rev-prev) FROM b''')
add('calendar_gap_detection','time_series', ''', a AS (SELECT DISTINCT day FROM oo),b AS (SELECT d.day,CASE WHEN a.day IS NULL THEN 1 ELSE 0 END missing FROM calendar d LEFT JOIN a ON d.day=a.day WHERE d.day>={d0} AND d.day<{d1}),
c AS (SELECT day,missing,SUM(missing) OVER(ORDER BY day ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) gaps FROM b)
SELECT SUM(missing),MAX(gaps),SUM(gaps) FROM c''')
add('daily_zscore_outliers','time_series', ''', a AS (SELECT day,SUM(amount) rev FROM oo GROUP BY day),b AS (SELECT day,rev,AVG(rev) OVER() mean,STDDEV_POP(rev) OVER() sd FROM a)
SELECT COUNT(*),SUM(CASE WHEN ABS(rev-mean)>2*sd THEN 1 ELSE 0 END),SUM((rev-mean)/NULLIF(sd,0)) FROM b''')
add('event_session_cumulative','window_analytics', ''', a AS (SELECT cid,session_id,eid,day,SUM(value) OVER(PARTITION BY cid,session_id ORDER BY day,eid ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) v FROM ee)
SELECT COUNT(*),SUM(v),MAX(v),MIN(v) FROM a''')
add('running_distinct_days','window_analytics', ''', a AS (SELECT cid,day FROM ee GROUP BY cid,day),b AS (SELECT cid,day,ROW_NUMBER() OVER(PARTITION BY cid ORDER BY day) n FROM a)
SELECT COUNT(*),SUM(n),MAX(n) FROM b''')
add('customer_dense_rank_ties','window_analytics', ''', a AS (SELECT cid,COUNT(*) n,SUM(amount) rev FROM oo GROUP BY cid),
b AS (SELECT cid,n,rev,RANK() OVER(ORDER BY n DESC) r,DENSE_RANK() OVER(ORDER BY n DESC) dr FROM a)
SELECT COUNT(*),SUM(r),SUM(dr),SUM(rev*dr) FROM b''')
add('percent_rank_distribution','window_analytics', ''', a AS (SELECT cid,SUM(amount) rev FROM oo GROUP BY cid),b AS (SELECT cid,rev,PERCENT_RANK() OVER(ORDER BY rev,cid) p FROM a)
SELECT COUNT(*),SUM(p),SUM(CASE WHEN p>=0.9 THEN rev ELSE 0 END) FROM b''')
add('cume_dist_threshold','window_analytics', ''', a AS (SELECT cid,SUM(amount) rev FROM oo GROUP BY cid),b AS (SELECT cid,rev,CUME_DIST() OVER(ORDER BY rev) p FROM a)
SELECT COUNT(*),SUM(p),SUM(CASE WHEN p<=0.5 THEN rev ELSE 0 END) FROM b''')
add('row_frame_vs_range_ties','window_analytics', ''', a AS (SELECT oid,day,amount,SUM(amount) OVER(ORDER BY day,oid ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) vr,SUM(amount) OVER(ORDER BY day RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) vg FROM oo)
SELECT COUNT(*),SUM(vr),SUM(vg),MAX(vg) FROM a''')
add('window_first_last_touch','window_analytics', ''', a AS (SELECT cid,eid,kind,FIRST_VALUE(kind) OVER(PARTITION BY cid ORDER BY day,eid ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) first_kind,LAST_VALUE(kind) OVER(PARTITION BY cid ORDER BY day,eid ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) last_kind FROM ee)
SELECT COUNT(*),SUM(first_kind),SUM(last_kind),SUM(CASE WHEN first_kind=last_kind THEN 1 ELSE 0 END) FROM a''')
add('second_purchase_nth_value','window_analytics', ''', a AS (SELECT cid,oid,amount,NTH_VALUE(amount,2) OVER(PARTITION BY cid ORDER BY day,oid ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) second_amount FROM oo)
SELECT COUNT(second_amount),SUM(second_amount),MAX(second_amount) FROM a''')
add('nested_window_rolling_rank','window_analytics', ''', a AS (SELECT cid,oid,amount,AVG(amount) OVER(PARTITION BY cid ORDER BY day,oid ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) ma FROM oo),
b AS (SELECT cid,oid,ma,ROW_NUMBER() OVER(PARTITION BY cid ORDER BY ma DESC,oid) rn FROM a)
SELECT COUNT(*),SUM(ma) FROM b WHERE rn<={k}''')
add('window_differencing_volatility','time_series', ''', a AS (SELECT day,SUM(amount) rev FROM oo GROUP BY day),b AS (SELECT day,rev-LAG(rev) OVER(ORDER BY day) delta FROM a),
c AS (SELECT day,delta,AVG(delta) OVER(ORDER BY day ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) trend FROM b)
SELECT COUNT(delta),SUM(delta),VAR_POP(delta),SUM(trend) FROM c''')
add('ntile_cross_segment','window_analytics', ''', a AS (SELECT c.tier,o.cid,SUM(o.amount) rev FROM oo o JOIN scope c ON o.cid=c.cid GROUP BY c.tier,o.cid),
b AS (SELECT tier,cid,rev,NTILE({k}) OVER(PARTITION BY tier ORDER BY rev,cid) bucket FROM a),
c AS (SELECT tier,bucket,COUNT(*) n,AVG(rev) rev FROM b GROUP BY tier,bucket)
SELECT COUNT(*),SUM(n),SUM(rev) FROM c''')

# Cohort, retention, funnels and attribution: test temporal eligibility explicitly.
add('cohort_age_retention','cohort_retention', ''', a AS (SELECT c.signup,e.day-c.signup age,COUNT(DISTINCT e.cid) active FROM ee e JOIN scope c ON e.cid=c.cid GROUP BY c.signup,e.day-c.signup),
b AS (SELECT signup,COUNT(*) n FROM scope GROUP BY signup)
SELECT COUNT(*),SUM(active),SUM(active*1.0/n) FROM a JOIN b ON a.signup=b.signup''')
add('rolling_retention_any_later','cohort_retention', ''', a AS (SELECT cid,MIN(day) first_day FROM ee GROUP BY cid)
SELECT COUNT(*),SUM(CASE WHEN EXISTS(SELECT 1 FROM ee e WHERE e.cid=a.cid AND e.day>=a.first_day+{k}) THEN 1 ELSE 0 END) FROM a''')
add('exact_day_retention','cohort_retention', ''', a AS (SELECT cid,MIN(day) first_day FROM ee GROUP BY cid),b AS (SELECT DISTINCT cid,day FROM ee)
SELECT COUNT(*),SUM(CASE WHEN b.cid IS NOT NULL THEN 1 ELSE 0 END) FROM a LEFT JOIN b ON a.cid=b.cid AND b.day=a.first_day+{k}''')
add('consecutive_activity_islands','cohort_retention', ''', a AS (SELECT DISTINCT cid,day FROM ee),b AS (SELECT cid,day,day-ROW_NUMBER() OVER(PARTITION BY cid ORDER BY day) island FROM a),
c AS (SELECT cid,island,COUNT(*) streak FROM b GROUP BY cid,island)
SELECT COUNT(*),MAX(streak),SUM(CASE WHEN streak>={k} THEN 1 ELSE 0 END) FROM c''')
add('churn_inactivity_threshold','cohort_retention', ''', a AS (SELECT cid,MAX(day) last_day FROM ee GROUP BY cid)
SELECT COUNT(*),SUM(CASE WHEN {d1}-COALESCE(a.last_day,{d0})>{k} THEN 1 ELSE 0 END),SUM({d1}-COALESCE(a.last_day,{d0})) FROM scope c LEFT JOIN a ON c.cid=a.cid''')
add('reactivation_after_gap','cohort_retention', ''', a AS (SELECT cid,eid,day,LAG(day) OVER(PARTITION BY cid ORDER BY day,eid) prev FROM ee),b AS (SELECT cid,COUNT(*) n FROM a WHERE day-prev>{k} GROUP BY cid)
SELECT COUNT(*),SUM(n),MAX(n) FROM b''')
add('retention_revenue_weighted','cohort_retention', ''', a AS (SELECT cid,SUM(amount) revenue FROM oo GROUP BY cid),b AS (SELECT cid,COUNT(DISTINCT day) active_days FROM ee GROUP BY cid)
SELECT COUNT(*),SUM(a.revenue*b.active_days)/NULLIF(SUM(a.revenue),0),SUM(CASE WHEN b.active_days>={k} THEN a.revenue ELSE 0 END) FROM a JOIN b ON a.cid=b.cid''')
add('cohort_survival_hazard','cohort_retention', ''', a AS (SELECT c.cid,c.signup,COALESCE(MAX(e.day),{d0}) last_day FROM scope c LEFT JOIN ee e ON c.cid=e.cid GROUP BY c.cid,c.signup),
b AS (SELECT signup,COUNT(*) n,SUM(CASE WHEN last_day<{d1}-{k} THEN 1 ELSE 0 END) churn FROM a GROUP BY signup)
SELECT COUNT(*),SUM(churn),SUM(churn*1.0/NULLIF(n,0)) FROM b''')
add('ordered_three_stage_funnel','funnel_attribution', ''', a AS (SELECT v.cid,MIN(v.day) start_day FROM ee v WHERE v.kind=0 GROUP BY v.cid),
b AS (SELECT a.cid,a.start_day,MIN(e.day) cart_day FROM a JOIN ee e ON a.cid=e.cid AND e.kind=1 AND e.day>=a.start_day GROUP BY a.cid,a.start_day),
c AS (SELECT b.cid,MIN(e.day) purchase_day FROM b JOIN ee e ON b.cid=e.cid AND e.kind=3 AND e.day>=b.cart_day AND e.day<=b.start_day+{k} GROUP BY b.cid)
SELECT (SELECT COUNT(*) FROM a),(SELECT COUNT(*) FROM b),(SELECT COUNT(*) FROM c)''')
add('same_session_conversion','funnel_attribution', ''', a AS (SELECT cid,session_id,MIN(CASE WHEN kind=0 THEN day END) viewed,MIN(CASE WHEN kind=1 THEN day END) carted,MAX(CASE WHEN kind=3 THEN day END) purchased FROM ee GROUP BY cid,session_id)
SELECT COUNT(*),SUM(CASE WHEN viewed IS NOT NULL AND purchased>=viewed THEN 1 ELSE 0 END),SUM(CASE WHEN carted IS NOT NULL AND purchased>=carted THEN 1 ELSE 0 END) FROM a''')
add('time_to_conversion_quantiles','funnel_attribution', ''', a AS (SELECT cid,MIN(CASE WHEN kind=0 THEN day END) viewed,MAX(CASE WHEN kind=3 THEN day END) purchased FROM ee GROUP BY cid),
b AS (SELECT cid,purchased-viewed delta FROM a WHERE purchased>=viewed),c AS (SELECT delta,ROW_NUMBER() OVER(ORDER BY delta,cid) rn,COUNT(*) OVER() n FROM b)
SELECT COUNT(*),AVG(delta),AVG(CASE WHEN rn IN(FLOOR((n+1)/2),FLOOR((n+2)/2)) THEN delta END) FROM c''')
add('last_touch_order_attribution','funnel_attribution', ''', a AS (SELECT o.oid,o.amount,e.kind,e.eid,ROW_NUMBER() OVER(PARTITION BY o.oid ORDER BY e.day DESC,e.eid DESC) rn FROM oo o JOIN ee e ON o.cid=e.cid AND e.day<=o.day AND e.day>=o.day-{k})
SELECT COUNT(*),SUM(kind),SUM(amount) FROM a WHERE rn=1''')
add('first_touch_order_attribution','funnel_attribution', ''', a AS (SELECT o.oid,o.amount,e.kind,e.eid,ROW_NUMBER() OVER(PARTITION BY o.oid ORDER BY e.day,e.eid) rn FROM oo o JOIN ee e ON o.cid=e.cid AND e.day<=o.day)
SELECT COUNT(*),SUM(kind),SUM(amount) FROM a WHERE rn=1''')
add('linear_multitouch_attribution','funnel_attribution', ''', a AS (SELECT o.oid,o.amount,e.kind,COUNT(*) OVER(PARTITION BY o.oid) touches FROM oo o JOIN ee e ON o.cid=e.cid AND e.day<=o.day AND e.day>=o.day-{k}),b AS (SELECT kind,SUM(amount/touches) revenue FROM a GROUP BY kind)
SELECT COUNT(*),SUM(revenue),MAX(revenue) FROM b''')
add('decay_multitouch_attribution','funnel_attribution', ''', a AS (SELECT o.oid,o.amount,e.kind,EXP(-{alpha}*(o.day-e.day)) w FROM oo o JOIN ee e ON o.cid=e.cid AND e.day<=o.day AND e.day>=o.day-{k}),
b AS (SELECT oid,amount,kind,w,SUM(w) OVER(PARTITION BY oid) total_w FROM a),c AS (SELECT kind,SUM(amount*w/total_w) revenue FROM b GROUP BY kind)
SELECT COUNT(*),SUM(revenue),MAX(revenue) FROM c''')
add('funnel_dropout_segments','funnel_attribution', ''', a AS (SELECT c.tier,e.cid,MAX(CASE WHEN e.kind=0 THEN 1 ELSE 0 END) viewed,MAX(CASE WHEN e.kind=3 THEN 1 ELSE 0 END) purchased FROM ee e JOIN scope c ON e.cid=c.cid GROUP BY c.tier,e.cid),
b AS (SELECT tier,SUM(viewed) visits,SUM(CASE WHEN viewed=1 AND purchased=0 THEN 1 ELSE 0 END) dropouts FROM a GROUP BY tier)
SELECT COUNT(*),SUM(dropouts),SUM(dropouts*1.0/NULLIF(visits,0)) FROM b''')

# Complex statistical calculations and feature engineering.
add('ols_regression_sufficient_stats','statistical_models', ''', a AS (SELECT cid,COUNT(*) x,SUM(amount) y FROM oo GROUP BY cid),b AS (SELECT COUNT(*) n,SUM(x) sx,SUM(y) sy,SUM(x*x) sxx,SUM(x*y) sxy FROM a)
SELECT n,(n*sxy-sx*sy)/NULLIF(n*sxx-sx*sx,0),(sy-((n*sxy-sx*sy)/NULLIF(n*sxx-sx*sx,0))*sx)/NULLIF(n,0) FROM b''')
add('regression_residual_distribution','statistical_models', ''', a AS (SELECT cid,COUNT(*) x,SUM(amount) y FROM oo GROUP BY cid),b AS (SELECT AVG(x) mx,AVG(y) my,AVG(x*y)-AVG(x)*AVG(y) cov,VAR_POP(x) vx FROM a),
c AS (SELECT a.cid,a.y-(b.my+(a.x-b.mx)*b.cov/NULLIF(b.vx,0)) residual FROM a CROSS JOIN b)
SELECT COUNT(*),SUM(residual),AVG(residual*residual),MAX(ABS(residual)) FROM c''')
add('pooled_vs_within_variance','statistical_models', ''', a AS (SELECT c.tier,o.amount x FROM oo o JOIN scope c ON o.cid=c.cid),b AS (SELECT tier,AVG(x) mean,VAR_POP(x) variance,COUNT(*) n FROM a GROUP BY tier)
SELECT (SELECT VAR_POP(x) FROM a),SUM(variance*n)/NULLIF(SUM(n),0),SUM(n*mean)/NULLIF(SUM(n),0) FROM b''')
add('welch_segment_t_statistic','statistical_models', ''', a AS (SELECT c.tier,AVG(o.amount) mean,VAR_SAMP(o.amount) variance,COUNT(*) n FROM oo o JOIN scope c ON o.cid=c.cid GROUP BY c.tier)
SELECT (a.mean-b.mean)/NULLIF(SQRT(a.variance/a.n+b.variance/b.n),0),a.n,b.n FROM a JOIN a b ON a.tier=0 AND b.tier=1''')
add('bernoulli_wilson_interval','statistical_models', ''', a AS (SELECT COUNT(*) n,SUM(CASE WHEN cancelled=0 THEN 1 ELSE 0 END) x FROM oo),b AS (SELECT n,x,x*1.0/NULLIF(n,0) p FROM a)
SELECT n,p,(p+1.9208/NULLIF(n,0)-1.96*SQRT(p*(1-p)/NULLIF(n,0)+0.9604/NULLIF(n*n,0)))/(1+3.8416/NULLIF(n,0)),(p+1.9208/NULLIF(n,0)+1.96*SQRT(p*(1-p)/NULLIF(n,0)+0.9604/NULLIF(n*n,0)))/(1+3.8416/NULLIF(n,0)) FROM b''')
add('empirical_entropy_of_channels','statistical_models', ''', a AS (SELECT channel,COUNT(*) n FROM oo GROUP BY channel),b AS (SELECT channel,n,n*1.0/SUM(n) OVER() p FROM a)
SELECT COUNT(*),-SUM(p*LN(p)),SUM(p*p) FROM b''')
add('mutual_information_tier_channel','statistical_models', ''', a AS (SELECT c.tier,o.channel,COUNT(*) n FROM oo o JOIN scope c ON o.cid=c.cid GROUP BY c.tier,o.channel),
b AS (SELECT tier,channel,n,SUM(n) OVER() total,SUM(n) OVER(PARTITION BY tier) nt,SUM(n) OVER(PARTITION BY channel) nc FROM a)
SELECT COUNT(*),SUM(n*1.0/total*LN(n*1.0*total/(nt*nc))) FROM b''')
add('observed_cell_chi_square_statistic','statistical_models', ''', a AS (SELECT c.tier,o.channel,COUNT(*) n FROM oo o JOIN scope c ON o.cid=c.cid GROUP BY c.tier,o.channel),
b AS (SELECT tier,channel,n,SUM(n) OVER() total,SUM(n) OVER(PARTITION BY tier) nt,SUM(n) OVER(PARTITION BY channel) nc FROM a),c AS (SELECT n,nt*1.0*nc/total expected FROM b)
SELECT COUNT(*),SUM((n-expected)*(n-expected)/NULLIF(expected,0)) FROM c''')
add('ordinal_rank_correlation','statistical_models', ''', a AS (SELECT cid,COUNT(*) frequency,SUM(amount) revenue FROM oo GROUP BY cid),b AS (SELECT cid,RANK() OVER(ORDER BY frequency,cid) x,RANK() OVER(ORDER BY revenue,cid) y FROM a)
SELECT COUNT(*),(AVG(x*y)-AVG(x)*AVG(y))/NULLIF(SQRT(VAR_POP(x)*VAR_POP(y)),0) FROM b''')
add('histogram_population_stability','statistical_models', ''', a AS (SELECT FLOOR(amount/100) bucket,SUM(CASE WHEN day<{d0}+{k} THEN 1 ELSE 0 END) early,SUM(CASE WHEN day>={d0}+{k} THEN 1 ELSE 0 END) late FROM oo GROUP BY FLOOR(amount/100)),
b AS (SELECT bucket,(early+1.0)/(SUM(early) OVER()+COUNT(*) OVER()) p,(late+1.0)/(SUM(late) OVER()+COUNT(*) OVER()) q FROM a)
SELECT COUNT(*),SUM((p-q)*LN(p/q)) FROM b''')
add('customer_winsorized_revenue','feature_engineering', ''', a AS (SELECT cid,SUM(amount) revenue FROM oo GROUP BY cid),b AS (SELECT cid,revenue,ROW_NUMBER() OVER(ORDER BY revenue,cid) rn,COUNT(*) OVER() n FROM a),
c AS (SELECT MIN(CASE WHEN rn>=CEIL(n*0.1) THEN revenue END) lo,MAX(CASE WHEN rn<=FLOOR(n*0.9) THEN revenue END) hi FROM b)
SELECT COUNT(*),AVG(CASE WHEN b.revenue<c.lo THEN c.lo WHEN b.revenue>c.hi THEN c.hi ELSE b.revenue END) FROM b CROSS JOIN c''')
add('customer_median_absolute_deviation','feature_engineering', ''', a AS (SELECT cid,SUM(amount) rev FROM oo GROUP BY cid),b AS (SELECT cid,rev,ROW_NUMBER() OVER(ORDER BY rev,cid) rn,COUNT(*) OVER() n FROM a),
c AS (SELECT AVG(rev) median FROM b WHERE rn IN(FLOOR((n+1)/2),FLOOR((n+2)/2))),d AS (SELECT cid,ABS(rev-median) dev FROM a CROSS JOIN c),
e AS (SELECT dev,ROW_NUMBER() OVER(ORDER BY dev,cid) rn,COUNT(*) OVER() n FROM d)
SELECT COUNT(*),AVG(CASE WHEN rn IN(FLOOR((n+1)/2),FLOOR((n+2)/2)) THEN dev END),SUM(dev) FROM e''')
add('cross_feature_normalization','feature_engineering', ''', a AS (SELECT cid,COUNT(*) frequency,SUM(amount) revenue FROM oo GROUP BY cid),b AS (SELECT cid,frequency,revenue,AVG(revenue) OVER() mean,STDDEV_POP(revenue) OVER() sd FROM a)
SELECT COUNT(*),SUM((revenue-mean)/NULLIF(sd,0)*LN(frequency+1)),AVG((revenue-mean)*(revenue-mean)/NULLIF(sd*sd,0)) FROM b''')
add('missing_credit_tier_imputation','feature_engineering', ''', a AS (SELECT tier,AVG(credit) mean FROM scope GROUP BY tier),b AS (SELECT c.cid,c.credit,COALESCE(c.credit,a.mean) imputed FROM scope c LEFT JOIN a ON c.tier=a.tier)
SELECT COUNT(*),COUNT(credit),SUM(imputed),VAR_POP(imputed) FROM b''')
add('bucketed_conditional_target_encoding','feature_engineering', ''', a AS (SELECT c.tier,o.channel,SUM(CASE WHEN o.cancelled=0 THEN 1 ELSE 0 END) successes,COUNT(*) n FROM oo o JOIN scope c ON o.cid=c.cid GROUP BY c.tier,o.channel),
b AS (SELECT tier,channel,(successes+{alpha})/(n+2*{alpha}) encoded,n FROM a)
SELECT COUNT(*),SUM(encoded*n),AVG(encoded) FROM b''')
add('leave_one_out_customer_encoding','feature_engineering', ''', a AS (SELECT c.tier,o.oid,o.cancelled,SUM(1-o.cancelled) OVER(PARTITION BY c.tier) s,COUNT(*) OVER(PARTITION BY c.tier) n FROM oo o JOIN scope c ON o.cid=c.cid)
SELECT COUNT(*),SUM((s-(1-cancelled)+{alpha})/(n-1+2*{alpha})),MIN(n) FROM a''')

# Graphs, complex subqueries, set operations and hierarchy traversal.
add('two_hop_neighbor_revenue','graph_analytics', ''', a AS (SELECT DISTINCT e2.dst cid FROM scope c JOIN edges e1 ON c.cid=e1.src JOIN edges e2 ON e1.dst=e2.src),b AS (SELECT o.cid,SUM(o.amount) rev FROM orders o JOIN a ON o.cid=a.cid WHERE o.day>={d0} AND o.day<{d1} GROUP BY o.cid)
SELECT COUNT(*),SUM(rev),MAX(rev) FROM b''')
add('triangle_motif_count','graph_analytics', ''' SELECT COUNT(*),SUM(e1.weight*e2.weight*e3.weight) FROM scope c JOIN edges e1 ON c.cid=e1.src JOIN edges e2 ON e1.dst=e2.src JOIN edges e3 ON e2.dst=e3.src AND e3.dst=c.cid WHERE e1.src<e1.dst AND e1.src<e2.dst''')
add('mutual_edges_weight','graph_analytics', ''' SELECT COUNT(*),SUM(a.weight*b.weight) FROM scope c JOIN edges a ON c.cid=a.src JOIN edges b ON a.dst=b.src AND b.dst=a.src WHERE a.src<a.dst''')
add('common_neighbor_similarity','graph_analytics', ''', a AS (SELECT e1.src s1,e2.src s2,COUNT(DISTINCT e1.dst) shared FROM edges e1 JOIN edges e2 ON e1.dst=e2.dst AND e1.src<e2.src JOIN scope c ON e1.src=c.cid GROUP BY e1.src,e2.src)
SELECT COUNT(*),SUM(shared),MAX(shared) FROM a''')
add('weighted_neighbor_credit','graph_analytics', ''', a AS (SELECT c.cid,SUM(n.credit*e.weight)/NULLIF(SUM(CASE WHEN n.credit IS NOT NULL THEN e.weight ELSE 0 END),0) weighted FROM scope c JOIN edges e ON c.cid=e.src JOIN customers n ON e.dst=n.cid GROUP BY c.cid)
SELECT COUNT(*),SUM(weighted),VAR_POP(weighted) FROM a''')
add('three_hop_path_weight','graph_analytics', ''' SELECT COUNT(*),SUM(e1.weight*e2.weight*e3.weight) FROM scope c JOIN edges e1 ON c.cid=e1.src JOIN edges e2 ON e1.dst=e2.src JOIN edges e3 ON e2.dst=e3.src WHERE e1.dst<>c.cid AND e2.dst<>c.cid AND e3.dst<>c.cid''')
add('in_out_degree_rank','graph_analytics', ''', a AS (SELECT src cid,COUNT(*) d FROM edges GROUP BY src),b AS (SELECT dst cid,COUNT(*) d FROM edges GROUP BY dst),
d AS (SELECT c.cid,COALESCE(a.d,0) outd,COALESCE(b.d,0) ind FROM scope c LEFT JOIN a ON c.cid=a.cid LEFT JOIN b ON c.cid=b.cid),
e AS (SELECT cid,ind,outd,DENSE_RANK() OVER(ORDER BY ind DESC) r FROM d)
SELECT COUNT(*),SUM(ind),SUM(outd),SUM(r) FROM e''')
add('recursive_bounded_reachability','graph_analytics', '''WITH RECURSIVE roots AS (SELECT cid FROM customers WHERE cid>={lo} AND cid<{hi} AND region<>{r}),
walk AS (SELECT cid root,cid node,0 depth FROM roots UNION ALL SELECT w.root,e.dst,w.depth+1 FROM walk w JOIN edges e ON w.node=e.src WHERE w.depth<3)
SELECT COUNT(*),COUNT(DISTINCT node),SUM(depth) FROM walk''')
add('correlated_topk_orders','subqueries_sets', ''' SELECT COUNT(*),SUM(o.amount) FROM oo o WHERE (SELECT COUNT(*) FROM oo x WHERE x.cid=o.cid AND (x.amount>o.amount OR (x.amount=o.amount AND x.oid<o.oid)))<{k}''')
add('correlated_above_peer_average','subqueries_sets', ''' SELECT COUNT(*),SUM(o.amount),AVG(o.amount) FROM oo o WHERE o.amount>(SELECT AVG(x.amount) FROM oo x WHERE x.channel=o.channel)''')
add('not_exists_double_negation','subqueries_sets', ''' SELECT COUNT(*),SUM(c.credit) FROM scope c WHERE NOT EXISTS(SELECT 1 FROM oo o WHERE o.cid=c.cid AND NOT EXISTS(SELECT 1 FROM payments p WHERE p.oid=o.oid AND p.success=1))''')
add('active_buyers_intersection','subqueries_sets', ''', a AS (SELECT cid FROM ee INTERSECT SELECT cid FROM oo)
SELECT COUNT(*),SUM(c.credit) FROM a JOIN scope c ON a.cid=c.cid''')
add('visitors_without_buyers_except','subqueries_sets', ''', a AS (SELECT cid FROM ee EXCEPT SELECT cid FROM oo)
SELECT COUNT(*),SUM(c.credit) FROM a JOIN scope c ON a.cid=c.cid''')
add('union_all_multisource_weight','subqueries_sets', ''', a AS (SELECT cid,amount v FROM oo UNION ALL SELECT cid,ABS(value) v FROM ee),b AS (SELECT cid,SUM(v) v,COUNT(*) n FROM a GROUP BY cid)
SELECT COUNT(*),SUM(v),SUM(v/NULLIF(n,0)) FROM b''')
add('full_outer_fact_reconciliation','subqueries_sets', ''', a AS (SELECT cid,COUNT(*) n FROM oo GROUP BY cid),b AS (SELECT cid,COUNT(*) n FROM ee GROUP BY cid)
SELECT COUNT(*),SUM(COALESCE(a.n,0)),SUM(COALESCE(b.n,0)),SUM(CASE WHEN a.cid IS NULL OR b.cid IS NULL THEN 1 ELSE 0 END) FROM a FULL OUTER JOIN b ON a.cid=b.cid''')
add('cte_self_join_aggregate','subqueries_sets', ''', a AS (SELECT cid,channel,SUM(amount) v FROM oo GROUP BY cid,channel)
SELECT COUNT(*),SUM(a.v*b.v),AVG(a.v-b.v) FROM a JOIN a b ON a.cid=b.cid AND a.channel<b.channel''')

# Further nontrivial combinations: percentile, robust loss, conditional time joins.
add('multi_dimensional_rollup','advanced_grouping', ''' SELECT tier,channel,COUNT(*) n,SUM(amount) v FROM oo o JOIN scope c ON o.cid=c.cid GROUP BY ROLLUP(tier,channel) ORDER BY COALESCE(tier,-1),COALESCE(channel,-1)''')
add('grouping_sets_sales_cube','advanced_grouping', ''' SELECT tier,channel,COUNT(*) n,SUM(amount) v FROM oo o JOIN scope c ON o.cid=c.cid GROUP BY GROUPING SETS((tier,channel),(tier),(channel),()) ORDER BY COALESCE(tier,-1),COALESCE(channel,-1)''')
add('ordered_percentile_cont','advanced_grouping', ''' SELECT channel,COUNT(*),PERCENTILE_CONT(0.9) WITHIN GROUP(ORDER BY amount),PERCENTILE_CONT(0.5) WITHIN GROUP(ORDER BY amount) FROM oo GROUP BY channel ORDER BY channel''')
add('median_by_manual_order_statistics','advanced_grouping', ''', a AS (SELECT channel,amount,ROW_NUMBER() OVER(PARTITION BY channel ORDER BY amount,oid) rn,COUNT(*) OVER(PARTITION BY channel) n FROM oo)
SELECT channel,AVG(amount) FROM a WHERE rn IN(FLOOR((n+1)/2),FLOOR((n+2)/2)) GROUP BY channel ORDER BY channel''')
add('payment_delay_asof_candidates','temporal_joins', ''', a AS (SELECT o.oid,o.amount,p.day-o.day delay,p.payid,ROW_NUMBER() OVER(PARTITION BY o.oid ORDER BY p.day,p.payid) rn FROM oo o JOIN payments p ON o.oid=p.oid AND p.success=1 AND p.day>=o.day)
SELECT COUNT(*),AVG(delay),SUM(amount*delay) FROM a WHERE rn=1''')
add('interval_event_purchase_join','temporal_joins', ''', a AS (SELECT e.cid,e.eid,COUNT(o.oid) purchases,SUM(o.amount) rev FROM ee e LEFT JOIN oo o ON e.cid=o.cid AND o.day BETWEEN e.day AND e.day+{k} GROUP BY e.cid,e.eid)
SELECT COUNT(*),SUM(purchases),SUM(rev),MAX(purchases) FROM a''')
add('logistic_probability_cross_features','statistical_models', ''', a AS (SELECT cid,COUNT(*) frequency,AVG(amount) avg_amount FROM oo GROUP BY cid),
b AS (SELECT c.cid,1.0/(1+EXP(-({alpha}*COALESCE(a.frequency,0)+COALESCE(a.avg_amount,0)/1000-c.tier))) p FROM scope c LEFT JOIN a ON c.cid=a.cid)
SELECT COUNT(*),SUM(p),SUM(p*(1-p)),SUM(CASE WHEN p>0.5 THEN 1 ELSE 0 END) FROM b''')
add('huber_loss_with_segment_baseline','statistical_models', ''', a AS (SELECT c.tier,AVG(o.amount) mean FROM oo o JOIN scope c ON o.cid=c.cid GROUP BY c.tier),b AS (SELECT o.oid,o.amount-a.mean residual FROM oo o JOIN scope c ON o.cid=c.cid JOIN a ON c.tier=a.tier)
SELECT COUNT(*),SUM(CASE WHEN ABS(residual)<={threshold} THEN residual*residual/2 ELSE {threshold}*(ABS(residual)-{threshold}/2) END),MAX(ABS(residual)) FROM b''')

SQL[:]=[x for x in SQL if x[0] not in {'customer_lifetime_distribution','running_distinct_days','first_touch_order_attribution','bucketed_conditional_target_encoding'}]
assert len(SQL)==80,len(SQL)

FEATURES=''', a AS (SELECT cid,COUNT(*) orders,SUM(amount) revenue,AVG(amount-cost) margin,STDDEV_POP(amount) volatility FROM oo WHERE cancelled=0 GROUP BY cid),
b AS (SELECT cid,COUNT(*) events,COUNT(DISTINCT day) active_days,AVG(value) activity FROM ee GROUP BY cid)
SELECT c.cid,c.tier,c.credit,COALESCE(a.orders,0),COALESCE(a.revenue,0),COALESCE(a.volatility,0),COALESCE(b.events,0),COALESCE(b.active_days,0),COALESCE(b.activity,0),COALESCE(a.margin,0)
FROM scope c LEFT JOIN a ON c.cid=a.cid LEFT JOIN b ON c.cid=b.cid ORDER BY c.cid'''

SCIENCE=[
 'covariance_eigenvalues','correlation_matrix','pca_explained_variance','svd_spectrum',
 'truncated_svd_error','qr_orthogonality','ols_coefficients','ridge_coefficients',
 'weighted_least_squares','huber_irls','logistic_irls','kmeans_centroids',
 'pairwise_cosine_distribution','mahalanobis_distance','fft_activity_power',
 'convolution_activity','bootstrap_mean_interval','quantile_scaling',
 'gaussian_kernel_mmd','feature_missingness_imputation',
]
assert len(SCIENCE)==20

def sql_for(family,i):
    if family<80:
        body=SQL[family][2]
        sql=(body if body.startswith('WITH RECURSIVE') else BASE+body).format(**params(i))
    else:
        sql=(BASE+FEATURES).format(**params(i))
    # MySQL decimal literals/AVG(integer) deliberately have fixed scales.
    # These scenarios ask for float64 scientific arithmetic explicitly, rather
    # than treating DuckDB's default double division as the MySQL type contract.
    sql=re.sub(r'(?<![\w.])\d+\.\d+(?![\w.])',lambda m:'CAST('+m[0]+' AS DOUBLE)',sql)
    positions=[m.end() for m in re.finditer(r'AVG\(',sql)]
    for start in reversed(positions):
        depth=1;end=start
        while depth:
            if sql[end]=='(':depth+=1
            elif sql[end]==')':depth-=1
            end+=1
        sql=sql[:start]+'CAST('+sql[start:end-1]+' AS DOUBLE)'+sql[end-1:]
    return sql

def label(family):
    return SQL[family][:2] if family<80 else (SCIENCE[family-80],'client_numerical_ml')
