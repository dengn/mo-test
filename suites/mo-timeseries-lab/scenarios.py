"""Fifty time-series questions; 200 real configurations each, not function smoke tests."""
import hashlib,json,re
from data import ROOT,SCHEMAS

QUESTIONS=[
('revenue_roll','收入滚动核对','多币种收入、撤销与业务压力在短长窗口中的变化'),
('weighted_service','加权服务率','订单量加权履约率与实体间排名，避免平均比率偏差'),
('causal_alarm','历史基线告警','基线排除当前行，历史均值与二阶矩形成异常分数'),
('rolling_volatility','滚动波动','滚动方差、标准差与业务压力的联动'),
('local_trend','局部趋势回归','滚动 OLS 的时间、响应、乘积与平方矩同时计算'),
('lag_forecast','多尺度动量','多个滞后项、历史均值和预测 horizon 组成可审计历史特征'),
('weekday_seasonality','周内季节性','同星期几窗口去季节化，再计算连续时间残差窗口'),
('drawdown','回撤与水下区间','累计现金、历史高点、回撤岛与区间长度'),
('change_regime','变化段识别','历史差分阈值确定状态段，再计算段内统计'),
('outage_islands','故障连续区间','故障边界、岛编号、连续时长及累计压力'),
('recovery_censoring','恢复与删失','连续故障区间的结束时间、未结束标记和区间内排名'),
('revision_impact','迟到修订影响','按固定可见快照去重，比较原始观测与修订后的滚动影响'),
('watermark_monitor','事件水位监控','已到达事件的迟到率、事件量与多尺度压力窗口'),
('dense_demand','补齐日历的需求','无事件日保留在分母，区分活动日均值与日历日均值'),
('temporal_ranking','历史分位与排名','实体历史排名、百分秩与累计分布后再取滚动分数'),
('cross_section','同日行业截面','行业排名、相同分数同秩、同业均值及随后时间窗口'),
('concentration','集中度时间变化','同日收入份额、份额平方、行业集中度与时间趋势'),
('top_bucket','分桶与头部压力','日截面 NTILE、行业排名及持续头部天数'),
('multiscale','多尺度记忆','多个 ROWS/RANGE 滚动尺度、前后文和累积窗口联动'),
('shipping_delay','履约延误','快照内发运延迟占比、累计差额和前后期服务变化'),
('stockout','缺货与需求删失','连续缺货岛、历史需求均值和补货压力'),
('future_inventory','描述性未来需求','显式未来窗口累计需求与当前库存覆盖；不作为因果训练特征'),
('price_response','价格需求关联','滚动价格需求协方差、变化滞后及响应强度'),
('resource_balance','资源累计余额','预算约束下的累计压力、峰值与未来容量需求'),
('capacity_gaps','容量余量区间','容量不足岛、连续缺口与短长窗口平滑'),
('cash_deficit','现金缺口年龄','累计净收入、负余额区间起点、区间累计缺口'),
('inactivity','无事件活跃段','无观测连续段、当前段起点及窗口内活跃密度'),
('event_funnel_days','日级漏斗状态','事件类型时点、前后阶段与日历连续窗口组合'),
('paired_signal','配对信号关联','实体与图邻居的滚动协方差、残差和价差动量'),
('network_pressure','网络时序压力','边权聚合、邻居冲击、时间滞后与同业压力排名'),
('joint_alarm','多信号联合告警','多个独立窗口条件交叉，滚动告警密度与告警段'),
('hierarchical_reconcile','实体行业层级核对','实体累计、行业每日总额、行业滚动及分摊对账'),
('budget_consumption','时点预算消耗','有效期预算切换、段内累计使用和预算首末值'),
('frame_endpoints','窗口边界值','FIRST/LAST/NTH 的显式框架与多阶 LEAD/LAG 组合'),
('tail_bucket','尾部压力排序','同业分桶、历史极值和尾部持续时长'),
('irregular_frames','不规则采样框架','同一事件序列的 ROWS 与真实时间 RANGE 计算差异'),
('carry_missing','缺失值前向携带','最后有效观测组、携带值、观测年龄与后续滚动'),
('offset_transition','时间偏移切换','UTC 排序与合成民用时间偏移，跨切换点间隔和窗口'),
('event_sessions','事件会话切分','不规则事件间隙、会话边界、编号、首末事件及会话内累积'),
('session_funnel','会话内阶段漏斗','会话内第一阶段/第二阶段时点、累计阶段与后续响应'),
('transition_entropy','事件转移多样性','类型变化和条件计数形成窗口概率与熵'),
('peer_exclusion','同时间戳同伴框架','RANGE 同伴与 GROUPS/EXCLUDE 同伴排除的业务差异'),
('finite_decay','有限衰减记忆','真实时间距离的指数加权聚合与后续时序窗口'),
('quality_age','采样质量与年龄','NULL、有效值、原生 LAST_VALUE 与历史缺失密度'),
('consecutive_trigger','连续触发边界','布尔状态岛、区间排名、区间累计和未来触发时点'),
('adaptive_memory','自适应记忆','依据前序波动选择短长窗口，避免同层窗口嵌套'),
('deep_rolling_filter','深层滚动滤波','20–32 层非线性窗口反馈，每层使用前层的平滑/滞后/跨度'),
('deep_peer_filter','深层同业反馈','24–36 层时间与行业截面窗口交替更新压力'),
('deep_regime_filter','深层状态反馈','18–30 层差分、移动中心和边界激励反馈'),
('materialized_risk','物化风险窗口事务','20–32 层分析后绑定写回，服务端再窗口化并验证提交/回滚'),
]

def params(i):
 # The (lo,d0,...) tuple is distinct for every i. Some selections include empty entities.
 lo=1+(i*17)%115;d0=28+(i*13)%55;d1=min(146,d0+36+i%17)
 return dict(lo=lo,hi=min(129,lo+8+i%5),d0=d0,d1=d1,start=d0-20,k=3+i%9,long=13+i%11,h=1+i%5,snapshot=d1+i%7,gap=1600+(i%7)*200,range_min=1440*(3+i%6),threshold=round(.13+(i%13)*.017,6),nth=1+i%3,depth=20+i%13)

def daily_ctes(i):
 p=params(i);lo,hi,start,end,snapshot=[p[k] for k in ['lo','hi','start','d1','snapshot']]
 return f'''scope AS (SELECT * FROM entities WHERE eid>={lo} AND eid<{hi}),
mr AS (SELECT m.*,ROW_NUMBER() OVER(PARTITION BY event_id ORDER BY revision DESC,rid DESC) revision_rank FROM measurements m JOIN scope s ON m.eid=s.eid WHERE m.day>={start} AND m.day<{end} AND received_day<={snapshot}),
mq AS (SELECT * FROM mr WHERE revision_rank=1 AND valid=1),
md AS (SELECT eid,day,AVG(CAST(value AS DOUBLE)) sensor,COUNT(value) observations,COUNT(*) raw_count,SUM(CAST(value AS DOUBLE)*CAST(value AS DOUBLE)) sensor_sq FROM mq GROUP BY eid,day),
original_md AS (SELECT eid,day,AVG(CAST(value AS DOUBLE)) original_sensor FROM measurements WHERE revision=0 AND day>={start} AND day<{end} GROUP BY eid,day),
reversal_sum AS (SELECT tid,SUM(amount) reversed FROM reversals WHERE day<={snapshot} GROUP BY tid),
td AS (SELECT t.eid,t.day,SUM(CASE WHEN settled=1 THEN amount-COALESCE(r.reversed,0) ELSE 0 END) net FROM trades t JOIN scope s ON t.eid=s.eid LEFT JOIN reversal_sum r ON t.tid=r.tid WHERE t.day>={start} AND t.day<{end} GROUP BY t.eid,t.day),
shipment_sum AS (SELECT sh0.oid,SUM(sh0.qty) shipped,SUM(CASE WHEN sh0.day-o.day>3 THEN sh0.qty ELSE 0 END) late_qty FROM (SELECT sh.oid,sh.day,sh.qty FROM shipments sh WHERE sh.day<={snapshot}) sh0 JOIN orders o ON sh0.oid=o.oid GROUP BY sh0.oid),
od AS (SELECT o.eid,o.day,SUM(o.qty) demand,SUM(COALESCE(ss.shipped,0)) shipped,SUM(COALESCE(ss.late_qty,0)) late_qty FROM orders o JOIN scope s ON o.eid=s.eid LEFT JOIN shipment_sum ss ON o.oid=ss.oid WHERE o.day>={start} AND o.day<{end} GROUP BY o.eid,o.day),
ed AS (SELECT e.eid,e.day,COUNT(*) event_count,SUM(CASE WHEN received_min-minute>1440 THEN 1 ELSE 0 END) late_count,SUM(CASE WHEN kind=0 THEN 1 ELSE 0 END) phase0,SUM(CASE WHEN kind=1 THEN 1 ELSE 0 END) phase1 FROM events e JOIN scope s ON e.eid=s.eid WHERE e.day>={start} AND e.day<{end} AND received_min<={28401120+snapshot*1440} GROUP BY e.eid,e.day),
grid AS (SELECT s.eid,s.region,s.sector,s.scale,c.* FROM scope s CROSS JOIN calendar c WHERE c.day>={start} AND c.day<{end}),
qd AS (SELECT g.eid,g.day,SUM(q.severity) severity FROM grid g LEFT JOIN outages q ON q.eid=g.eid AND q.start_day<=g.day AND q.end_day>g.day GROUP BY g.eid,g.day),
peer AS (SELECT e.src eid,m.day,SUM(e.weight*m.sensor)/NULLIF(SUM(CASE WHEN m.sensor IS NOT NULL THEN e.weight ELSE 0 END),0) neighbor FROM edges e JOIN md m ON e.dst=m.eid GROUP BY e.src,m.day),
joined AS (SELECT g.*,m.sensor,COALESCE(m.observations,0) observations,COALESCE(m.raw_count,0) raw_count,COALESCE(om.original_sensor,0) original_sensor,
COALESCE(t.net,0)*fx.rate y,COALESCE(o.demand,0) demand,COALESCE(o.shipped,0) shipped,COALESCE(o.late_qty,0) late_qty,
iv.on_hand stock,cap.available capacity,w.temp,pr.price,fx.rate,tg.target,COALESCE(q.severity,0) severity,pol.budget,COALESCE(it.effect,0) effect,
COALESCE(ev.event_count,0) event_count,COALESCE(ev.late_count,0) late_count,COALESCE(ev.phase0,0) phase0,COALESCE(ev.phase1,0) phase1,COALESCE(pe.neighbor,0) neighbor
FROM grid g LEFT JOIN md m ON g.eid=m.eid AND g.day=m.day LEFT JOIN original_md om ON g.eid=om.eid AND g.day=om.day
LEFT JOIN td t ON g.eid=t.eid AND g.day=t.day LEFT JOIN od o ON g.eid=o.eid AND g.day=o.day
JOIN inventory iv ON g.eid=iv.eid AND g.day=iv.day JOIN capacity cap ON g.region=cap.region AND g.day=cap.day
JOIN weather w ON g.region=w.region AND g.day=w.day JOIN prices pr ON g.sector=pr.sector AND g.day=pr.day
JOIN fx ON g.region=fx.region AND g.day=fx.day JOIN targets tg ON g.sector=tg.sector AND g.weekday=tg.weekday
LEFT JOIN qd q ON g.eid=q.eid AND g.day=q.day JOIN policies pol ON g.eid=pol.eid AND g.day>=pol.valid_from AND g.day<pol.valid_to
LEFT JOIN interventions it ON g.eid=it.eid AND g.day=it.day LEFT JOIN ed ev ON g.eid=ev.eid AND g.day=ev.day
LEFT JOIN peer pe ON g.eid=pe.eid AND g.day=pe.day),
daily AS (SELECT j.*,COALESCE(sensor,0)/scale+demand/CAST(target AS DOUBLE)+temp/50+y/scale/20+severity-stock/100.0-capacity/200+effect+neighbor/scale/20+price/100+rate/10-budget/10000+late_qty/20.0+late_count/100.0 x FROM joined j)'''

def events_ctes(i):
 p=params(i)
 return f'''scope AS (SELECT * FROM entities WHERE eid>={p['lo']} AND eid<{p['hi']}),
events_visible AS (SELECT e.*,s.region,s.sector,c.weekday,c.offset_min,minute+c.offset_min civil_min FROM events e JOIN scope s ON s.eid=e.eid JOIN calendar c ON c.day=e.day WHERE e.day>={p['start']} AND e.day<{p['d1']} AND received_min<={28401120+p['snapshot']*1440}),
ev AS (SELECT *,CAST(magnitude AS DOUBLE) x,ROW_NUMBER() OVER(PARTITION BY eid ORDER BY minute,event_id) rn,LAG(minute) OVER(PARTITION BY eid ORDER BY minute,event_id) prev_min,LAG(kind) OVER(PARTITION BY eid ORDER BY minute,event_id) prev_kind FROM events_visible)'''

def sql_for(f,i):
 p=params(i);k=p['k'];long=p['long'];h=p['h'];d0=p['d0'];extra=[]
 def add(name,body):extra.append(name+' AS ('+body+')');return name
 w=f'PARTITION BY eid ORDER BY day ROWS BETWEEN {k} PRECEDING AND CURRENT ROW'
 wl=f'PARTITION BY eid ORDER BY day ROWS BETWEEN {long} PRECEDING AND CURRENT ROW'
 past=f'PARTITION BY eid ORDER BY day ROWS BETWEEN {k} PRECEDING AND 1 PRECEDING'
 run='PARTITION BY eid ORDER BY day ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW'
 base=daily_ctes(i);source='daily';key='eid,day';tail=f'day>={d0}'
 # Every daily output retains the original composite x, consuming the complete joined context.
 if f==0:
  add('a',f'SELECT *,SUM(y) OVER({w}) revenue,AVG(x) OVER({wl}) pressure,LAG(y,{h}) OVER(PARTITION BY eid ORDER BY day) lag_revenue FROM daily');cols='revenue,pressure,lag_revenue'
 elif f==1:
  add('a',f'SELECT *,SUM(shipped) OVER({w}) shipped_sum,SUM(demand) OVER({w}) demand_sum,SUM(CAST(shipped AS DOUBLE)) OVER({wl})/NULLIF(SUM(demand) OVER({wl}),0) long_service FROM daily');add('b','SELECT *,shipped_sum/NULLIF(CAST(demand_sum AS DOUBLE),0) service,RANK() OVER(PARTITION BY day ORDER BY ROUND(long_service,8) DESC,eid) service_rank FROM a');cols='shipped_sum,demand_sum,long_service,service,service_rank'
 elif f==2:
  add('a',f'SELECT *,AVG(x) OVER({past}) baseline,AVG(x*x) OVER({past}) second_moment,COUNT(*) OVER({past}) n FROM daily');add('b','SELECT *,CASE WHEN second_moment-baseline*baseline>1e-12 THEN (x-baseline)/SQRT(second_moment-baseline*baseline) ELSE 0 END anomaly FROM a');cols='baseline,second_moment,n,anomaly'
 elif f==3:
  add('a',f'SELECT *,VAR_POP(x) OVER({w}) variance,STDDEV_POP(x) OVER({wl}) volatility,AVG(y) OVER({w}) net_mean FROM daily');cols='variance,volatility,net_mean'
 elif f==4:
  add('a',f'SELECT *,AVG(CAST(day AS DOUBLE)) OVER({w}) mt,AVG(x) OVER({w}) mx,AVG(day*x) OVER({w}) mtx,AVG(CAST(day AS DOUBLE)*day) OVER({w}) mt2 FROM daily');add('b','SELECT *,CASE WHEN mt2-mt*mt>1e-12 THEN (mtx-mt*mx)/(mt2-mt*mt) ELSE 0 END slope FROM a');cols=f'mt,mx,mtx,mt2,slope,mx+slope*(day-mt+{h}) prediction'
 elif f==5:
  add('a',f'SELECT *,LAG(x,{h}) OVER(PARTITION BY eid ORDER BY day) lag1,LAG(x,{h+2}) OVER(PARTITION BY eid ORDER BY day) lag2,AVG(x) OVER({past}) history,SUM(y) OVER({past}) past_revenue FROM daily');cols='lag1,lag2,history,past_revenue,x-lag1 momentum'
 elif f==6:
  add('a',f'SELECT *,AVG(x) OVER(PARTITION BY eid,weekday ORDER BY day ROWS BETWEEN {k} PRECEDING AND 1 PRECEDING) seasonal FROM daily');add('b',f'SELECT *,x-COALESCE(seasonal,0) residual FROM a');add('c',f'SELECT *,AVG(residual) OVER({w}) residual_mean,SUM(residual*residual) OVER({wl}) residual_energy FROM b');cols='seasonal,residual,residual_mean,residual_energy'
 elif f in [7,25]:
  add('a',f'SELECT *,SUM(y-budget/160) OVER({run}) balance FROM daily');add('b',f'SELECT *,MAX(balance) OVER({run}) peak FROM a');flag='balance<0' if f==25 else 'balance<peak-1e-7';add('c',f'SELECT *,CASE WHEN {flag} THEN 1 ELSE 0 END flag FROM b');add('d','SELECT *,LAG(flag,1,0) OVER(PARTITION BY eid ORDER BY day) previous_flag FROM c');add('e',f'SELECT *,SUM(CASE WHEN flag<>previous_flag THEN 1 ELSE 0 END) OVER({run}) island_id FROM d');add('g','SELECT *,ROW_NUMBER() OVER(PARTITION BY eid,island_id ORDER BY day) island_age,SUM(peak-balance) OVER(PARTITION BY eid,island_id ORDER BY day ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) deficit FROM e');cols='balance,peak,flag,island_id,island_age,deficit'
 elif f in [8,9,10,20,24,26,30,44]:
  add('a',f'SELECT *,LAG(x,1,x) OVER(PARTITION BY eid ORDER BY day) previous_x,AVG(x) OVER({past}) previous_mean,AVG(CAST(demand AS DOUBLE)) OVER({past}) expected_demand FROM daily')
  condition={8:f'ABS(x-previous_x)>{p["threshold"]}',9:'severity>0',10:'severity>0',20:'stock=0',24:'demand*8>capacity',26:'observations=0',30:f'x>previous_mean+{p["threshold"]} AND late_count>0',44:f'x>previous_mean+{p["threshold"]}'}[f]
  add('b',f'SELECT *,CASE WHEN {condition} THEN 1 ELSE 0 END flag FROM a');add('c','SELECT *,LAG(flag,1,0) OVER(PARTITION BY eid ORDER BY day) previous_flag FROM b');add('d',f'SELECT *,SUM(CASE WHEN flag<>previous_flag THEN 1 ELSE 0 END) OVER({run}) island_id FROM c');add('e',f'SELECT *,ROW_NUMBER() OVER(PARTITION BY eid,island_id ORDER BY day) island_age,MIN(day) OVER(PARTITION BY eid,island_id) first_day,MAX(day) OVER(PARTITION BY eid,island_id) last_day,SUM(x) OVER(PARTITION BY eid,island_id ORDER BY day ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) accumulated,SUM(flag) OVER({w}) recent_trigger_count FROM d');cols=f'flag,island_id,island_age,first_day,last_day,accumulated,recent_trigger_count,expected_demand,CASE WHEN last_day={p["d1"]-1} THEN 1 ELSE 0 END right_censored'
  if f==10:
   add('recovery',f'SELECT *,MIN(CASE WHEN flag=0 THEN day ELSE NULL END) OVER(PARTITION BY eid ORDER BY day ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING) recovery_day FROM e');cols+=',recovery_day,recovery_day-day recovery_wait'
 elif f==11:
  add('a',f'SELECT *,COALESCE(sensor,0)-original_sensor correction,SUM(COALESCE(sensor,0)-original_sensor) OVER({w}) rolling_correction,LAST_VALUE(sensor) OVER({w}) current_last FROM daily');cols='sensor,original_sensor,correction,rolling_correction,current_last,observations,raw_count'
 elif f==12:
  add('a',f'SELECT *,SUM(event_count) OVER({w}) n,SUM(late_count) OVER({w}) late,SUM(x) OVER(PARTITION BY eid ORDER BY utc_min RANGE BETWEEN {p["range_min"]} PRECEDING AND CURRENT ROW) range_pressure FROM daily');cols='n,late,late/NULLIF(CAST(n AS DOUBLE),0) late_rate,range_pressure'
 elif f==13:
  add('a',f'SELECT *,AVG(CAST(demand AS DOUBLE)) OVER({w}) calendar_mean,SUM(CAST(demand AS DOUBLE)) OVER({w})/NULLIF(SUM(CASE WHEN demand>0 THEN 1 ELSE 0 END) OVER({w}),0) active_mean,COUNT(*) OVER({w}) calendar_days FROM daily');cols='calendar_mean,active_mean,calendar_days,demand,event_count'
 elif f in [14,15,17,34]:
  partition='eid' if f==14 else 'sector,day';add('a',f'SELECT *,RANK() OVER(PARTITION BY {partition} ORDER BY ROUND(x,8)) signal_rank,DENSE_RANK() OVER(PARTITION BY {partition} ORDER BY ROUND(x,8)) dense_order,PERCENT_RANK() OVER(PARTITION BY {partition} ORDER BY ROUND(x,8)) percentile,CUME_DIST() OVER(PARTITION BY {partition} ORDER BY ROUND(x,8)) distribution,NTILE({2+i%5}) OVER(PARTITION BY {partition} ORDER BY ROUND(x,8),eid,day) bucket FROM daily');add('b',f'SELECT *,AVG(percentile) OVER({w}) rank_memory,SUM(CASE WHEN bucket=1 THEN 1 ELSE 0 END) OVER({wl}) low_bucket_days FROM a');cols='signal_rank,dense_order,percentile,distribution,bucket,rank_memory,low_bucket_days'
  if f==17:
   add('head',f'SELECT *,SUM(CASE WHEN bucket=1 THEN x ELSE 0 END) OVER({w}) head_pressure FROM b');cols+=',head_pressure'
  if f==34:
   add('tail',f'SELECT *,SUM(CASE WHEN bucket={2+i%5} THEN x ELSE 0 END) OVER({w}) tail_pressure,MAX(x) OVER({past}) historical_peak FROM b');cols+=',tail_pressure,historical_peak'
 elif f==16:
  add('a','SELECT *,y/NULLIF(SUM(y) OVER(PARTITION BY sector,day),0) revenue_share FROM daily');add('b','SELECT *,SUM(revenue_share*revenue_share) OVER(PARTITION BY sector,day) concentration FROM a');add('c',f'SELECT *,AVG(concentration) OVER({w}) concentration_mean,LAG(concentration,{h}) OVER(PARTITION BY eid ORDER BY day) earlier FROM b');cols='revenue_share,concentration,concentration_mean,earlier'
 elif f==18:
  add('a',f'SELECT *,AVG(x) OVER({w}) short_mean,AVG(x) OVER({wl}) long_mean,SUM(x) OVER({run}) cumulative,SUM(x) OVER(PARTITION BY eid ORDER BY day RANGE BETWEEN {k} PRECEDING AND {h} FOLLOWING) two_sided FROM daily');cols='short_mean,long_mean,cumulative,two_sided,short_mean-long_mean momentum'
 elif f==19:
  add('a',f'SELECT *,SUM(late_qty) OVER({w}) late_sum,SUM(demand) OVER({w}) demand_sum,SUM(demand-shipped) OVER({run}) backlog,LEAD(shipped,{h}) OVER(PARTITION BY eid ORDER BY day) later_shipped FROM daily');cols='late_sum,demand_sum,late_sum/NULLIF(CAST(demand_sum AS DOUBLE),0) delay_rate,backlog,later_shipped'
 elif f==21:
  add('a',f'SELECT *,SUM(demand) OVER(PARTITION BY eid ORDER BY day ROWS BETWEEN 1 FOLLOWING AND {long} FOLLOWING) future_demand,AVG(x) OVER({past}) causal_pressure FROM daily');cols='future_demand,stock-future_demand inventory_gap,causal_pressure'
 elif f==22:
  add('a',f'SELECT *,AVG(price) OVER({w}) mp,AVG(CAST(demand AS DOUBLE)) OVER({w}) mq,AVG(price*demand) OVER({w}) mpq,AVG(price*price) OVER({w}) mp2,LAG(price,{h}) OVER(PARTITION BY eid ORDER BY day) prior_price FROM daily');cols='mp,mq,mpq,mp2,prior_price,CASE WHEN mp2-mp*mp>1e-12 THEN (mpq-mp*mq)/(mp2-mp*mp) ELSE 0 END response'
 elif f==23:
  add('a',f'SELECT *,SUM(capacity-demand*8-severity*10) OVER({run}) resource_balance,AVG(x) OVER({wl}) pressure_mean FROM daily');add('b',f'SELECT *,MIN(resource_balance) OVER({w}) floor_balance,MAX(resource_balance) OVER({w}) peak_balance FROM a');cols='resource_balance,pressure_mean,floor_balance,peak_balance'
 elif f==27:
  add('a',f'SELECT *,MAX(CASE WHEN phase0>0 THEN day ELSE NULL END) OVER({run}) phase0_day,MAX(CASE WHEN phase1>0 THEN day ELSE NULL END) OVER({run}) phase1_day,SUM(phase0) OVER({w}) phase0_count,SUM(phase1) OVER({w}) phase1_count FROM daily');cols='phase0_day,phase1_day,phase0_count,phase1_count,phase1_count/NULLIF(CAST(phase0_count AS DOUBLE),0) stage_conversion'
 elif f in [28,29]:
  add('a',f'SELECT *,AVG(COALESCE(sensor,0)) OVER({w}) ms,AVG(neighbor) OVER({w}) mn,AVG(COALESCE(sensor,0)*neighbor) OVER({w}) msn,LAG(neighbor,{h}) OVER(PARTITION BY eid ORDER BY day) neighbor_lag,AVG(x) OVER(PARTITION BY region,day) regional FROM daily');add('b',f'SELECT *,msn-ms*mn covariance,COALESCE(sensor,0)-neighbor spread FROM a');add('c',f'SELECT *,AVG(spread) OVER({wl}) spread_mean FROM b');cols='ms,mn,msn,covariance,neighbor_lag,regional,spread,spread_mean'
  if f==29:
   add('network',f'SELECT *,neighbor-neighbor_lag peer_shock,RANK() OVER(PARTITION BY region,day ORDER BY ROUND(x-regional,8),eid) regional_rank FROM c');cols+=',peer_shock,regional_rank'
 elif f==31:
  add('a',f'SELECT *,SUM(y) OVER(PARTITION BY sector,day) sector_total,SUM(y) OVER({run}) entity_total,ROW_NUMBER() OVER(PARTITION BY sector,day ORDER BY eid) representative FROM daily');add('b',f'SELECT *,SUM(CASE WHEN representative=1 THEN sector_total ELSE 0 END) OVER(PARTITION BY sector ORDER BY day,eid ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) hierarchy_total FROM a');cols='sector_total,entity_total,representative,hierarchy_total'
 elif f==32:
  add('a','SELECT *,LAG(budget,1,budget) OVER(PARTITION BY eid ORDER BY day) previous_budget FROM daily');add('b',f'SELECT *,SUM(CASE WHEN budget<>previous_budget THEN 1 ELSE 0 END) OVER({run}) island_id FROM a');add('c','SELECT *,SUM(y) OVER(PARTITION BY eid,island_id ORDER BY day ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) spent,FIRST_VALUE(budget) OVER(PARTITION BY eid,island_id ORDER BY day ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) opening_budget,LAST_VALUE(budget) OVER(PARTITION BY eid,island_id ORDER BY day ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) closing_budget FROM b');cols='budget,island_id,spent,opening_budget,closing_budget,budget-spent remaining_budget'
 elif f==33:
  add('a',f'SELECT *,FIRST_VALUE(sensor) OVER({w}) first_observed,LAST_VALUE(sensor) OVER({w}) last_observed,NTH_VALUE(sensor,{p["nth"]}) OVER({w}) nth_observed,LAG(x,{h},0) OVER(PARTITION BY eid ORDER BY day) earlier,LEAD(x,{h},0) OVER(PARTITION BY eid ORDER BY day) later FROM daily');cols='first_observed,last_observed,nth_observed,earlier,later'
 elif f==36:
  add('a',f'SELECT *,MAX(CASE WHEN sensor IS NOT NULL THEN day ELSE NULL END) OVER({run}) observed_day FROM daily');add('b','SELECT *,MAX(sensor) OVER(PARTITION BY eid,observed_day) carried FROM a');add('c',f'SELECT *,AVG(carried) OVER({w}) carried_mean FROM b');cols='sensor,observed_day,carried,day-observed_day age,carried_mean'
 elif f==45:
  add('a',f'SELECT *,AVG(x) OVER({past}) center,AVG(x*x) OVER({past}) second_moment,AVG(x) OVER({w}) short_mean,AVG(x) OVER({wl}) long_mean FROM daily');add('b',f'SELECT *,CASE WHEN second_moment-center*center>{p["threshold"]**2:.12f} THEN short_mean ELSE long_mean END adaptive FROM a');add('c',f'SELECT *,LAG(adaptive,{h}) OVER(PARTITION BY eid ORDER BY day) prior_adaptive,AVG(adaptive) OVER({w}) stabilized FROM b');cols='center,second_moment,short_mean,long_mean,adaptive,prior_adaptive,stabilized'
 elif f>=46:
  depth=p['depth']+(4 if f==47 else -2 if f==48 else 0);last='daily';score='x'
  for layer in range(depth):
   a=f'layer{layer}_windows';b=f'layer{layer}_score';kw=2+(layer+i)%9
   smooth=f'AVG({score}) OVER(PARTITION BY eid ORDER BY day ROWS BETWEEN {kw} PRECEDING AND CURRENT ROW)'
   cross=f'AVG({score}) OVER(PARTITION BY sector,day)' if f==47 else f'LAG({score},1,{score}) OVER(PARTITION BY eid ORDER BY day)'
   add(a,f'SELECT eid,day,x,sector,region,y,budget,observations,{score} input_score,{smooth} smooth_{layer},{cross} peer_{layer},MAX({score}) OVER(PARTITION BY eid ORDER BY day ROWS BETWEEN {kw} PRECEDING AND CURRENT ROW)-MIN({score}) OVER(PARTITION BY eid ORDER BY day ROWS BETWEEN {kw} PRECEDING AND CURRENT ROW) span_{layer} FROM {last}')
   expr=f'CAST(0.53 AS DOUBLE)*input_score+CAST(0.29 AS DOUBLE)*smooth_{layer}+CAST(0.18 AS DOUBLE)*peer_{layer}+CAST(0.013 AS DOUBLE)*span_{layer}/(1+ABS(span_{layer}))'
   if f==48:expr+=f'+CAST(0.017 AS DOUBLE)*(input_score-peer_{layer})/(1+ABS(input_score-peer_{layer}))'
   if f==49:expr+='+CAST(0.009 AS DOUBLE)*(y/budget)/(1+ABS(y/budget))'
   add(b,f'SELECT eid,day,x,sector,region,y,budget,observations,{expr} score_{layer} FROM {a}');last=b;score=f'score_{layer}'
  add('deep_result',f'SELECT *,AVG({score}) OVER({wl}) final_mean,RANK() OVER(PARTITION BY sector,day ORDER BY ROUND({score},8),eid) final_rank FROM {last}');cols=f'{score} score,final_mean,final_rank,budget,y,observations'
 else:
  base=events_ctes(i);source='ev';key='eid,minute,event_id';tail=f'day>={d0}'
  ew=f'PARTITION BY eid ORDER BY minute,event_id ROWS BETWEEN {k} PRECEDING AND CURRENT ROW';er=f'PARTITION BY eid ORDER BY minute RANGE BETWEEN {p["range_min"]} PRECEDING AND CURRENT ROW';eu='PARTITION BY eid ORDER BY minute,event_id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW'
  if f==35:
   add('a',f'SELECT *,SUM(x) OVER({ew}) rows_sum,SUM(x) OVER({er}) range_sum,COUNT(*) OVER({ew}) rows_count,COUNT(*) OVER({er}) range_count,AVG(x) OVER({er}) time_mean FROM ev');cols='rn,rows_sum,range_sum,rows_count,range_count,time_mean'
  elif f==37:
   add('a',f'SELECT *,LAG(civil_min) OVER(PARTITION BY eid ORDER BY minute,event_id) previous_civil,SUM(x) OVER({er}) utc_window,SUM(x) OVER(PARTITION BY eid ORDER BY civil_min RANGE BETWEEN {p["range_min"]} PRECEDING AND CURRENT ROW) civil_window FROM ev');cols='civil_min,previous_civil,minute-prev_min utc_gap,civil_min-previous_civil civil_gap,utc_window,civil_window'
  elif f in [38,39]:
   add('a',f'SELECT *,CASE WHEN prev_min IS NULL OR minute-prev_min>{p["gap"]} THEN 1 ELSE 0 END boundary FROM ev');add('b',f'SELECT *,SUM(boundary) OVER({eu}) session_id FROM a');sw='PARTITION BY eid,session_id ORDER BY minute,event_id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW';add('c',f'SELECT *,FIRST_VALUE(minute) OVER({sw}) first_min,LAST_VALUE(minute) OVER(PARTITION BY eid,session_id ORDER BY minute,event_id ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) last_min,SUM(x) OVER({sw}) cumulative,MIN(CASE WHEN kind=0 THEN minute ELSE NULL END) OVER({sw}) first_phase0,MIN(CASE WHEN kind=1 THEN minute ELSE NULL END) OVER({sw}) first_phase1,ROW_NUMBER() OVER(PARTITION BY eid,session_id ORDER BY minute,event_id) session_rank FROM b');cols='rn,session_id,first_min,last_min,cumulative,first_phase0,first_phase1,session_rank'
   if f==39:
    add('funnel','SELECT *,MIN(CASE WHEN kind=2 THEN minute ELSE NULL END) OVER(PARTITION BY eid,session_id ORDER BY minute,event_id ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING) next_phase2 FROM c');cols+=',next_phase2,next_phase2-first_phase0 response_gap'
  elif f==40:
   add('a',f'SELECT *,SUM(CASE WHEN kind<>prev_kind THEN 1 ELSE 0 END) OVER({ew}) changes,SUM(CASE WHEN kind=0 THEN 1 ELSE 0 END) OVER({ew}) zeros,COUNT(*) OVER({ew}) n FROM ev');add('b','SELECT *,zeros/CAST(n AS DOUBLE) probability FROM a');cols='rn,changes,zeros,n,probability,CASE WHEN probability>0 AND probability<1 THEN -probability*LN(probability)-(1-probability)*LN(1-probability) ELSE 0 END entropy'
  elif f==41:
   # Required peer-exclusion semantics are deliberately tested, even on unsupported engines.
   frame=f'PARTITION BY eid ORDER BY minute GROUPS BETWEEN {k} PRECEDING AND CURRENT ROW EXCLUDE TIES'
   add('a',f'SELECT *,SUM(x) OVER({er}) peer_inclusive,SUM(x) OVER({frame}) peer_excluded,SUM(x) OVER(PARTITION BY eid ORDER BY minute RANGE BETWEEN {p["range_min"]} PRECEDING AND CURRENT ROW EXCLUDE CURRENT ROW) excluding_self FROM ev');cols='rn,peer_inclusive,peer_excluded,excluding_self'
  elif f==42:
   add('decay',f'SELECT a.eid,a.event_id,SUM(b.x*EXP(-CAST(a.minute-b.minute AS DOUBLE)/{p["range_min"]}))/NULLIF(SUM(EXP(-CAST(a.minute-b.minute AS DOUBLE)/{p["range_min"]})),0) decayed FROM ev a JOIN ev b ON a.eid=b.eid AND b.minute<=a.minute AND b.minute>=a.minute-{p["range_min"]} GROUP BY a.eid,a.event_id');add('a','SELECT e.*,d.decayed FROM ev e JOIN decay d ON e.eid=d.eid AND e.event_id=d.event_id');add('b',f'SELECT *,AVG(decayed) OVER({ew}) decayed_mean,LAG(decayed,{h}) OVER(PARTITION BY eid ORDER BY minute,event_id) prior_decay FROM a');cols='rn,decayed,decayed_mean,prior_decay'
  elif f==43:
   base=daily_ctes(i);source='daily';key='eid,day';add('a',f'SELECT *,COUNT(sensor) OVER({w}) window_observations,SUM(CASE WHEN sensor IS NULL THEN 1 ELSE 0 END) OVER({w}) null_count,LAST_VALUE(sensor) OVER({w}) observed_last,MAX(CASE WHEN sensor IS NOT NULL THEN day ELSE NULL END) OVER({run}) last_day FROM daily');cols='window_observations observations,null_count,observed_last,last_day,day-last_day staleness'
  else:raise ValueError(f)
 final=extra[-1].split(' AS (',1)[0] if extra else source
 # No implicit numeric order for floating ties: ranks explicitly use round(...,8) and deterministic entity keys.
 return 'WITH '+base+(',\n'+',\n'.join(extra) if extra else '')+f'\nSELECT {key},x,{cols} FROM {final} WHERE {tail} ORDER BY {key}'

def complexity(sql):
 return dict(bytes=len(sql.encode()),ctes=len(re.findall(r'\bAS\s*\(',sql,re.I)),windows=len(re.findall(r'\bOVER\s*\(',sql,re.I)),joins=len(re.findall(r'\bJOIN\b',sql,re.I)),source_tables=[n for n in SCHEMAS if re.search(r'\b'+n+r'\b',sql)],sha256=hashlib.sha256(sql.encode()).hexdigest())

if __name__=='__main__':
 rows=[]
 for f,(name,title,question) in enumerate(QUESTIONS):
  sql=sql_for(f,199);rows.append(dict(family=f,name=name,title=title,question=question,parameters=200,complexity=complexity(sql)))
  (ROOT/'examples'/f'{f:02d}-{name}.sql').write_text(sql+';\n')
 (ROOT/'scenario-catalog.json').write_text(json.dumps(rows,indent=2,ensure_ascii=False))
 hashes={complexity(sql_for(f,i))['sha256'] for f in range(50) for i in range(200)};assert len(hashes)==10000,len(hashes)
 print('Distinct complete SQL:',len(hashes),'max windows',max(r['complexity']['windows'] for r in rows))
