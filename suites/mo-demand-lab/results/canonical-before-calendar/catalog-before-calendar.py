"""Forty analysis requirements; each has inputs, a decision, and acceptance rules."""
from facts import *
MISSIONS=[]
def add(key,question,mart,select,context,acceptance):
 MISSIONS.append(dict(key=key,question=question,mart=mart,select=select,context=context,acceptance=acceptance))
CUSTOMER='SELECT cid,region,tier,orders,revenue,contribution,acquisition_cost,returned,outstanding,recency,COALESCE(credit,80) credit FROM customer_facts ORDER BY cid'
DAILY='SELECT day,SUM(net_revenue) revenue,SUM(contribution) margin,SUM(cost+freight+marketing_cost) expenses,SUM(outstanding) outstanding FROM order_facts GROUP BY day ORDER BY day'
PRODUCT='SELECT pid,category,SUM(qty) units,SUM(amount*item_share) gross,SUM(net_revenue*item_share) revenue,SUM(contribution*item_share) margin,SUM(returned*item_share) returned FROM product_facts GROUP BY pid,category ORDER BY pid'
PRICE='SELECT pid,category,day,list_price,sale_price,units,promo,stockout,lead_days,unit_cost,on_hand FROM price_facts ORDER BY pid,day'
OPS='SELECT machine,plant,kind,day,age,capacity,temperature,vibration,load_value,failure,downtime,output_units,defects,scrap_cost,energy_cost,emissions,rolling_vibration,COALESCE(next_failures,0) next_failures FROM operation_facts ORDER BY machine,day'
SUB='SELECT cid,region,tier,orders,revenue,contribution,acquisition_cost,returned,outstanding,recency,n_months,billed,paid,active_months,last_active,COALESCE(first_pause,n_months) first_pause,arrears,reactivations,COALESCE(credit,80) credit FROM subscription_customers ORDER BY cid'
EXP='SELECT cid,day,treatment,site,baseline,converted,revenue,latency,harm,past_margin FROM experiment_facts ORDER BY cid,day'
LOAN='SELECT loan_id,cid,region,tier,principal,apr,term_days,balance,dpd,defaulted,credit FROM credit_facts ORDER BY loan_id'
RET='SELECT asset,day,close_price,COALESCE(log_return,0) log_return,drawdown,volume FROM market_facts ORDER BY day,asset'
HEALTH='SELECT cid,region,tier,orders,revenue,contribution,acquisition_cost,returned,outstanding,recency,n_months,billed,paid,active_months,last_active,COALESCE(first_pause,n_months) first_pause,arrears,reactivations,tickets,handling,csat,reopens FROM health_facts ORDER BY cid'
add('profit_bridge','为什么本期利润变化？把销量、单位净收入、货品成本、运费、获客成本分开，并定位高贡献分组。',COMMERCE,'SELECT region,channel,CASE WHEN day<{split} THEN 0 ELSE 1 END period,COUNT(*) volume,SUM(net_revenue) revenue,SUM(cost) goods_cost,SUM(freight) freight,SUM(marketing_cost) marketing,SUM(contribution) margin FROM order_facts GROUP BY region,channel,CASE WHEN day<{split} THEN 0 ELSE 1 END ORDER BY region,channel,period',PRODUCT,'利润桥各因素之和等于总变化；商品分摊收入与订单收入一致。')
add('rfm','按最近购买、频次、毛利识别客户群，确定召回与高价值服务名单。',COMMERCE,CUSTOMER,DAILY,'聚类覆盖全部客户且唯一；空购买客户保留；召回投入不超过预算。')
add('cohort_retention','哪个获客群组在第几周流失？观察成熟度并估计复购收入。',JOURNEY,'SELECT s.cid,s.signup,s.tier,CAST(FLOOR((e.day-s.signup)/7) AS SIGNED) age_week,COUNT(DISTINCT e.day) active_days FROM selected s LEFT JOIN journey_events e ON s.cid=e.cid GROUP BY s.cid,s.signup,s.tier,CAST(FLOOR((e.day-s.signup)/7) AS SIGNED) ORDER BY s.cid,age_week',CUSTOMER,'分母按可观察周数调整；留存率在0到1；客户不重复计数。')
add('survival','订阅首次暂停的时间分布是什么？处理未暂停客户的右删失，估计限制平均存续期。',SUBS,SUB,'SELECT cid,month,active,billed,paid FROM subscription_history ORDER BY cid,month','生存曲线非增；风险集递减；删失样本不记为已暂停。')
add('ltv','结合贡献毛利、活跃存续和折现估计客户价值，限制可接受获客成本。',SUBS,SUB,DAILY,'折现价值不超过未折现正收益；获客后净价值核对；不同风险情景排序稳定。')
add('experiment','随机分配的新体验是否提高收入？按用户聚合、控制基线并核对样本平衡。',EXPERIMENT,EXP,CUSTOMER,'按用户而非事件计量；置信区间包含点估计；不混用训练与验证用户。')
add('attribution','转化前多触点如何分摊贡献？比较时间衰减渠道份额和获客成本。',JOURNEY,''' , touch_weights AS (SELECT o.oid,o.channel,o.net_revenue,e.kind,EXP(-{decay}*(o.day-e.day)) weight FROM order_facts o JOIN journey_events e ON o.cid=e.cid AND e.day BETWEEN o.day-{lookback} AND o.day),
 touch_normalized AS (SELECT *,SUM(weight) OVER(PARTITION BY oid) total_weight FROM touch_weights),
 eligible_orders AS (SELECT DISTINCT oid,net_revenue FROM touch_weights),
 eligible_total AS (SELECT SUM(net_revenue) eligible_revenue,COUNT(*) eligible_count FROM eligible_orders)
 SELECT kind,SUM(net_revenue*weight/total_weight) attributed,SUM(weight/total_weight) conversions,MAX(t.eligible_revenue) eligible_revenue,MAX(t.eligible_count) eligible_count FROM touch_normalized CROSS JOIN eligible_total t GROUP BY kind ORDER BY kind''','SELECT channel,SUM(marketing_cost) spend,SUM(net_revenue) revenue,COUNT(*) orders FROM order_facts GROUP BY channel ORDER BY channel','可归因订单的权重之和为1；归因总额等于对应净收入；不解释为因果增量。')
add('marketing_budget','在总预算和单渠道扩量上限下，如何分配投放使预计毛利最大？',COMMERCE,'SELECT channel,COUNT(*) orders,SUM(marketing_cost) spend,SUM(contribution) margin,SUM(returned) returned FROM order_facts GROUP BY channel ORDER BY channel',CUSTOMER,'非负投放、总预算和渠道上限成立；方案目标优于零投放；仅用观察收益率。')
add('forecast','用历史需求和星期效应预测SKU未来需求，滚动验证缺货校正后的误差。',PRICING,PRICE,'SELECT pid,MAX(lead_days) lead,AVG(fill_rate) fill_rate,AVG(delay) delay FROM supplier_facts GROUP BY pid ORDER BY pid','预测非负；验证期不参与拟合；报告实际留出误差和预测区间。')
add('replenishment','结合需求波动、交货期和现货量制定有限预算补货。',PRICING,PRICE,'SELECT pid,supplier,lead_days,unit_cost FROM suppliers WHERE MOD(pid,8)<>{plant} ORDER BY pid','补货非负整数；花费不超过预算；安全库存随服务水平提高而非减。')
add('assortment','有限SKU货架如何选品？考虑贡献毛利和同品类替代，保留品类覆盖。',COMMERCE,PRODUCT,'SELECT category,SUM(contribution*item_share) margin,SUM(qty) units FROM product_facts GROUP BY category ORDER BY category','选择不重复且不超过货架容量；选品目标包含同类拥挤惩罚；品类覆盖可核对。')
add('supplier_risk','哪个供应商同时存在交付波动、缺量和国家集中风险？确定备货优先级。',PRICING,'SELECT supplier,pid,country,lead_days,unit_cost,COUNT(*) deliveries,AVG(delay) delay,VAR_POP(delay) delay_var,SUM(ordered) ordered,SUM(received) received,AVG(fill_rate) fill_rate FROM supplier_facts GROUP BY supplier,pid,country,lead_days,unit_cost ORDER BY supplier',PRICE,'履约率在0到1；缺量守恒；国家集中度与供应商敞口相加一致。')
add('sla','各仓库和承运商的履约延迟如何？区分仍在运输与已交付，优先治理。',COMMERCE,'SELECT oid,cid,warehouse,carrier,promised_day,delivered_day,CASE WHEN delivered_day<{end} THEN 1 ELSE 0 END observed,COALESCE(late_days,0) late_days,net_revenue,freight,lost FROM order_facts ORDER BY oid',DAILY,'未交付单不当成零延迟样本；已观察SLA分母正确；整改优先级可追溯到订单。')
add('returns','退款损失集中在哪些商品和客户层？区分销量结构变化与退款率变化。',COMMERCE,PRODUCT,'SELECT tier,channel,COUNT(*) orders,SUM(net_revenue) revenue,SUM(returned) returned FROM order_facts GROUP BY tier,channel ORDER BY tier,channel','退款商品分摊额等于订单退款额；小样本率有平滑；不声称相关性即根因。')
add('cash_reconcile','支付成功流水、修订后的总账和账单是否一致？给出可追踪差异。',COMMERCE,'SELECT oid,cid,day,cash,ledger_amount,returned,invoice,collected,outstanding FROM order_facts ORDER BY oid',DAILY,'仅保留流水最高修订；总差异等于逐单差异之和；未来流水不提前确认。')
add('collections','按欠款、账龄、客户价值和触达成本选择催收名单。',COMMERCE,'SELECT cid,region,tier,SUM(outstanding) outstanding,MAX(days_overdue) days_overdue,SUM(contribution) margin,COALESCE(AVG(credit),80) credit FROM order_facts GROUP BY cid,region,tier ORDER BY cid',DAILY,'零欠款不触达；触达预算满足；预计净回收收益与逐客户合计一致。')
add('liquidity','未来收款延迟和经营支出变化下，现金余额何时跌破储备？',COMMERCE,DAILY,'SELECT days_overdue,SUM(outstanding) outstanding,COUNT(*) invoices FROM order_facts GROUP BY days_overdue ORDER BY days_overdue','逐期余额满足现金恒等式；概率在0到1；坏情景储备风险不低于好情景。')
add('credit','以当前可得资料估计违约概率和预期损失，检验校准和价值加权损失。',CREDIT,LOAN,'SELECT region,tier,SUM(balance) exposure,SUM(balance*defaulted) default_exposure FROM credit_facts GROUP BY region,tier ORDER BY region,tier','概率合法；损失不超过LGD敞口；验证样本不进入拟合；无未来贷后快照。')
add('concentration','地区、客户层和借款人集中度是多少？单群组受损对损失有多大影响？',CREDIT,LOAN,CUSTOMER,'HHI在0到1；各群敞口之和等于总敞口；压力损失守恒。')
add('portfolio_risk','组合的历史波动、回撤、VaR和尾部期望损失是什么？',MARKET,RET,'SELECT asset,AVG(log_return) mean_return,VAR_POP(log_return) variance,MIN(drawdown) drawdown FROM market_facts GROUP BY asset ORDER BY asset','协方差对称半正定；尾部损失不低于VaR；权重归一。')
add('portfolio_alloc','在长仓与单资产上限下，平衡预期收益、协方差风险和换手成本。',MARKET,RET,'SELECT asset,AVG(log_return) mean_return,VAR_POP(log_return) variance FROM market_facts GROUP BY asset ORDER BY asset','权重非负且和为1；单资产上限成立；求解目标不差于初始均配。')
add('pairs','寻找稳定价差资产对并在留出期核对均值回归交易成本后的收益。',MARKET,RET,'SELECT asset,MIN(close_price) low_price,MAX(close_price) high_price FROM market_facts GROUP BY asset ORDER BY asset','仅训练期选对和拟合；交易信号用上一时刻价格；收益扣除换手成本。')
add('elasticity','控制季节性与促销后，估计价格敏感性并模拟价格改变的销量和毛利。',PRICING,PRICE,'SELECT pid,unit_cost FROM suppliers ORDER BY pid','缺货日不当成完整需求；模拟销量非负；留出日期不参与回归。')
add('cannibalization','促销SKU上涨是否挤占同品类其他SKU？量化品类净变化。',PRICING,PRICE,'SELECT category,day,SUM(units) units,SUM(units*sale_price) revenue,SUM(promo) promo_skus FROM price_facts GROUP BY category,day ORDER BY category,day','SKU变化加总等于品类变化；报告相关性与混杂限制；对照组完整。')
add('fraud','共享设备、商户历史风险与交易金额能否优先发现拒付？验证检查预算和漏损。',FRAUD,'SELECT payment,cid,merchant,device,day,amount,chargeback,shared_users,prior_volume,prior_loss FROM fraud_features ORDER BY day,payment',CUSTOMER,'历史特征截止于训练分割；验证拒付标签不作为特征；检查额度满足。')
add('funnel','浏览、详情、加购、结账、购买哪一步流失？按客户层找最大收入机会。',JOURNEY,'SELECT cid,session_id,tier,region,day,view_day,detail_day,cart_day,checkout_day,purchase_day,events FROM session_facts ORDER BY session_id',CUSTOMER,'各阶段人数非增；购买发生在前序步骤之后；分母为会话而非事件数。')
add('journey','用户行为状态如何转移？估计到购买的吸收概率并识别瓶颈。',JOURNEY,'SELECT eid,cid,session_id,kind,day FROM journey_events ORDER BY session_id,kind,eid',CUSTOMER,'转移矩阵每行和为1；吸收概率在0到1；会话边界不跨连。')
add('capacity','预测订单与处理时长，制定仓库容量和超时缓冲。',COMMERCE,'SELECT warehouse,day,COUNT(*) orders,AVG(freight) handling_cost,SUM(CASE WHEN delivered_day>promised_day THEN 1 ELSE 0 END) late_orders FROM order_facts GROUP BY warehouse,day ORDER BY warehouse,day',DAILY,'需求预测非负；规划容量覆盖给定服务分位；成本与各仓合计一致。')
add('energy','在电价、充放电效率、功率和SOC约束下，安排电池削峰填谷。','WITH energy_facts AS (SELECT * FROM energy WHERE day BETWEEN {start} AND {end}-1 AND site={plant})','SELECT hour,AVG(kwh) demand,AVG(tariff) tariff,AVG(carbon) carbon,MAX(capacity) capacity FROM energy_facts GROUP BY hour ORDER BY hour','SELECT day,SUM(kwh*tariff) energy_cost,SUM(kwh) demand,MAX(kwh) peak FROM energy_facts GROUP BY day ORDER BY day','SOC和功率上下界成立；终端SOC等于初始；成本不超过不调度基线。')
add('maintenance','以历史振动、温度和负载预测近期故障，安排有限维护名额。',OPERATIONS,OPS,'SELECT machine,SUM(downtime) downtime,SUM(scrap_cost+energy_cost) operating_cost FROM operation_facts GROUP BY machine ORDER BY machine','验证未来故障只用于标签；时间分割正确；维护名额与预计避免损失可核对。')
add('quality','识别缺陷率的持续漂移，控制多重告警并估算废品损失。',OPERATIONS,OPS,'SELECT plant,day,SUM(defects) defects,SUM(output_units) output_units,SUM(scrap_cost) scrap_cost FROM operation_facts GROUP BY plant,day ORDER BY plant,day','缺陷率非负；训练基线与评估期分离；调整p值符合多重比较规则。')
add('reliability','机器首次故障与删失寿命分布如何？估计下一周期检修风险。',OPERATIONS,OPS,'SELECT machine,MAX(age) age,SUM(downtime) downtime FROM operation_facts GROUP BY machine ORDER BY machine','生存概率非增；无故障机器按右删失；风险不超过1。')
add('support_staff','客服到达率和处理时长需要多少坐席才能满足等候SLA？',SUPPORT,'SELECT kind,day,COUNT(*) arrivals,SUM(handle_minutes) handle_minutes,AVG(wait_minutes) wait_minutes,AVG(csat) csat FROM support_facts GROUP BY kind,day ORDER BY kind,day',HEALTH,'排队模型利用率小于1；人数为整数；达到指定服务水平；日成本加总一致。')
add('health','把活跃、欠款、服务体验与消费贡献结合，确定客户挽留优先级。',SUPPORT,HEALTH,'SELECT cid,month,active,billed,paid FROM subscription_history ORDER BY cid,month','无活动客户保留；触达预算成立；总可挽留价值与名单合计一致。')
add('recognition','预收合同的已赚收入、递延收入和未来服务成本如何滚动？',COMMERCE,'SELECT a.contract_id,a.cid,a.start_day,a.term_days,a.booked,a.cost_to_serve,c.tier,c.region,GREATEST(0,LEAST(a.term_days,{end}-a.start_day)) earned_days FROM contracts a JOIN selected c ON a.cid=c.cid WHERE a.start_day<{end} ORDER BY a.contract_id',DAILY,'已赚与递延之和等于签约额；已赚比例在0到1；预测收入不超过递延。')
add('expansion','根据持续付费、服务负担和贡献毛利选择升级或交叉销售客户。',SUPPORT,HEALTH,PRODUCT,'零净价值客户不被强推；销售预算满足；升级收入、服务成本和净收益守恒。')
add('guardrails','实验主指标提升时，延迟和损害护栏是否允许上线？分层核对异质效应。',EXPERIMENT,EXP,'SELECT site,treatment,COUNT(DISTINCT cid) users,AVG(latency) latency,AVG(CAST(harm AS DOUBLE)) harm FROM experiment_facts GROUP BY site,treatment ORDER BY site,treatment','按用户聚类；护栏越限禁止推荐全量；分层与总体权重一致。')
add('anomalies','识别收入时间序列异常，区分周期性、结构变化和单日异常。',COMMERCE,DAILY,'SELECT day,channel,SUM(net_revenue) revenue,SUM(returned) returned FROM order_facts GROUP BY day,channel ORDER BY day,channel','缺失日期补零；阈值仅从训练期估计；异常可下钻到渠道。')
add('stress','订单、收款延迟、价格和供应共同受冲击时，利润和资金缺口如何？',COMMERCE,DAILY,PRODUCT,'压力情景使用同一基础现金恒等式；贡献变化和资金变化分别核对；预算风险合法。')
PLANNING=COMMERCE+','+PRICING[5:]+','+OPERATIONS[5:]
add('planning','联动需求预测、采购预算、库存、产能、交付与现金储备制定下一周期经营计划。',PLANNING,''' , historical_product AS (SELECT pid,SUM(contribution*item_share) observed_margin,SUM(qty) sold_units FROM product_facts GROUP BY pid),
 product_forecast AS (SELECT pid,category,AVG(units) mean_demand,VAR_POP(units) demand_var,MAX(lead_days) lead,AVG(unit_cost) unit_cost FROM price_facts GROUP BY pid,category),
 plant_budget AS (SELECT plant,SUM(capacity*(1-downtime/24)) production_capacity,SUM(energy_cost+scrap_cost) plant_cost FROM operation_facts GROUP BY plant),
 integrated_plan AS (SELECT d.*,s.on_hand,COALESCE(h.observed_margin,0) observed_margin,COALESCE(h.sold_units,0) sold_units,COALESCE(p.production_capacity,0) production_capacity,COALESCE(p.plant_cost,0) plant_cost FROM product_forecast d JOIN product_state s ON d.pid=s.pid AND s.current_rank=1 LEFT JOIN historical_product h ON d.pid=h.pid LEFT JOIN plant_budget p ON d.category=p.plant)
 SELECT pid,category,mean_demand,demand_var,lead,unit_cost,on_hand,observed_margin,sold_units,production_capacity,plant_cost FROM integrated_plan ORDER BY pid''',DAILY,'采购预算、库存非负、映射品类产能和现金储备约束成立；预测与执行成本可追溯。')
assert len(MISSIONS)==40
MISSIONS[38]['extra']=(PRICING,'SELECT supplier,AVG(fill_rate) fill_rate,AVG(delay) delay,SUM(ordered*unit_cost) purchase_cost FROM supplier_facts GROUP BY supplier ORDER BY supplier')
def queries(f,i):
 m=MISSIONS[f]
 def query(select):
  # A requirement may extend its fact graph before emitting its dataset.
  return format_sql(m['mart']+(' ' if select.lstrip().startswith(',') else '\n')+select,i)
 out=[query(m['select']),query(m['context'])]
 if 'extra' in m:out.append(format_sql(m['extra'][0]+'\n'+m['extra'][1],i))
 return out
def catalog():return [{k:v for k,v in m.items() if k not in ['mart','select','context','extra']} for m in MISSIONS]
