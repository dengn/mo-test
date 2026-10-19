"""100 demand-driven workflows: ten templates per domain, 1000 configurations each."""
import json,re,hashlib
from data import ROOT,EPOCH
DOMAINS=['point_in_time','incremental','streaming','causal','attribution','hierarchical_forecast','temporal_graph','risk_simulation','spatial','model_monitoring']
TITLES=['严格时点特征','增量修正','流式事件','实验与因果','归因与旅程','层级预测回测','时序图与反欺诈','风险与模拟','空间轨迹','模型监控漂移']
TEMPLATES=[
 ['已知数据滚动特征','缺失与观测覆盖','双时态属性特征','历史趋势与跨度','已知修订敏感性','未来信息可见性断言','严格时点训练标签','截面标准化特征','多版本连接基数','历史训练到当前预测'],
 ['增量日总额','更正后的滚动均值','删除后的累计指标','更正窗口差分','历史峰谷重算','受影响期间分组','零观测与完整日历','异常基线修正','区间预算与累计','最新状态及更正敏感性'],
 ['事件时间桶','乱序后的滚动汇总','迟到策略及接纳密度','去重事件指标','会话切分与合并','已关闭窗口状态','条件事件指标','事件类型转移','状态及观测缺失','恢复与幂等状态'],
 ['随机实验Welch差异','CUPED调整','双重差分','Hajek逆倾向加权','基线最近邻匹配','聚类稳健标准误','分层Bootstrap区间','Beta-Binomial转化后验','分群异质性','多重比较BH校正'],
 ['最后触点','首次触点','线性归因','时间衰减归因','位置归因','精确Shapley归因','Markov移除效应','转化时长及漏斗','渠道去重信用','预算约束收益分配'],
 ['季节朴素预测','趋势季节Ridge','自回归Ridge','多项式趋势预测','滚动原点回测','层级协调','残差分位区间','已知日历协变量','冷启动回退','近期加权漂移适应'],
 ['时序可达路径','循环资金路径','扇入扇出团伙','样本路径中心性','动态加权PageRank','原生递归时序路径','最短风险路径','动态连通分量','资金集中度','时点图差异'],
 ['Gaussian VaR-CVaR','多资产Monte Carlo','情景压力损失','相关冲击','重要性及暴露集中度','CVaR约束分配','Delta-Gamma模拟','方差降低与反向样本','分群资本分配','模拟尾部置信区间'],
 ['围栏严格包含','围栏边界覆盖','轨迹相交','区域停留','速度异常','时空邻近','道路路径','网格热力','日界线最短距离','DST重复民用时间'],
 ['AUC含并列','校准及ECE','Brier与LogLoss','分群TPR-FPR','PSI分布漂移','KS分布漂移','特征相关漂移','迟到标签回填','阈值敏感性','分群显著性BH'],
]

def params(domain,j,i):
 lo=1+i%24;width=3+(i//24)%4;cut=24+((i//96)*5+i%5)%56;lb=8+(i*7+j*3)%16
 p=dict(domain=domain,template=j,parameter=i,lo=lo,hi=min(32,lo+width-1),cut=cut,lb=lb,h=1+(i+j)%5,k=2+(i+j)%5,alpha=.9+((i+j)%9)*.01,seed=SEED_LOCAL+domain*100000+j*1000+i,checkpoint=i%10,policy=(i//10)%5,threshold=.2+((i+j)%7)*.1)
 if domain==3:p['cut']=38+((i//96)*3+i%5)%16
 if domain==8 and j==8:p.update(lo=31,hi=32)
 if domain==8 and j==9:p.update(lo=2,hi=3,cut=22+i%5,lb=10+(i//5)%8)
 return p
SEED_LOCAL=202610120900

def point_sql(p):
 lo,hi,cut,lb,h,j=[p[k] for k in ['lo','hi','cut','lb','h','template']]
 anchor=f'c.day BETWEEN {cut-4} AND {cut}' if j in [6,9] else f'c.day={cut}'
 return f'''WITH anchors AS (SELECT u.uid,u.region,c.day FROM units u JOIN calendar c ON {anchor} WHERE u.uid BETWEEN {lo} AND {hi}),
visible AS (SELECT a.uid,a.day anchor_day,m.rid,m.event_id,m.day,m.received_day,m.revision,m.valid,m.v,ROW_NUMBER() OVER(PARTITION BY a.uid,a.day,m.event_id ORDER BY m.revision DESC,m.rid DESC) choice FROM anchors a JOIN observations m ON m.uid=a.uid AND m.day BETWEEN a.day-{lb} AND a.day-1 AND m.received_day<=a.day),
picked AS (SELECT * FROM visible WHERE choice=1 AND valid=1),
attr_versions AS (SELECT a.uid,a.day,b.aid,b.recorded_day,b.scale,ROW_NUMBER() OVER(PARTITION BY a.uid,a.day ORDER BY b.recorded_day DESC,b.revision DESC,b.aid DESC) choice FROM anchors a LEFT JOIN attrs b ON b.uid=a.uid AND b.valid_from<=a.day AND b.valid_to>a.day AND b.recorded_day<=a.day),
features AS (SELECT a.uid,a.day,a.region,COUNT(x.v) n,COUNT(x.event_id) n_rows,SUM(x.v) val_sum,AVG(x.v) mean_val,VAR_POP(x.v) var_val,MIN(x.v) min_val,MAX(x.v) max_val,MAX(x.received_day) max_received,MAX(x.revision) max_revision FROM anchors a LEFT JOIN picked x ON x.uid=a.uid AND x.anchor_day=a.day GROUP BY a.uid,a.day,a.region)
SELECT f.*,b.aid,b.recorded_day,COALESCE(b.scale,CAST(1 AS DOUBLE)) attr_scale,l.y label_y,l.ready_day FROM features f LEFT JOIN attr_versions b ON f.uid=b.uid AND f.day=b.day AND b.choice=1 LEFT JOIN labels l ON l.uid=f.uid AND l.day=f.day+{h} AND l.ready_day<={cut} ORDER BY f.uid,f.day'''

def sql_for(domain,j,i):
 p=params(domain,j,i);lo,hi,cut,lb,h=[p[k] for k in ['lo','hi','cut','lb','h']]
 if domain==0:return point_sql(p)
 if domain==1:
  return f'''WITH amounts AS (SELECT uid,day,SUM(v) raw_total,COUNT(v) raw_n FROM inc_state GROUP BY uid,day)
SELECT u.uid,c.day,COALESCE(a.total,CAST(0 AS DOUBLE)) v,COALESCE(a.n,0) n,COALESCE(b.raw_total,CAST(0 AS DOUBLE)) raw_total,COALESCE(b.raw_n,0) raw_n,c.weekday FROM units u JOIN calendar c ON c.day BETWEEN {cut-lb} AND {cut} LEFT JOIN inc_daily a ON a.uid=u.uid AND a.day=c.day LEFT JOIN amounts b ON b.uid=u.uid AND b.day=c.day WHERE u.uid BETWEEN {lo} AND {hi} ORDER BY u.uid,c.day'''
 if domain==2:
  end=p['checkpoint']*10+6
  return f'''WITH a AS (SELECT event_id,uid,event_min,batch,v,kind,LAG(event_min) OVER(PARTITION BY uid ORDER BY event_min,event_id) prev_min FROM stream_accepted WHERE policy={p['policy']} AND uid BETWEEN {lo} AND {hi} AND event_min BETWEEN {end-lb*2} AND {end}),
flags AS (SELECT *,CASE WHEN prev_min IS NULL OR event_min-prev_min>{p['k']} THEN 1 ELSE 0 END boundary FROM a)
SELECT event_id,uid,event_min,batch,v,kind,prev_min,SUM(boundary) OVER(PARTITION BY uid ORDER BY event_min,event_id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) session_id FROM flags ORDER BY uid,event_min,event_id'''
 if domain==3:
  sid='s.sid>384' if j in [3,4] else 's.sid<=384'
  return f'''SELECT s.sid,s.uid,s.segment,s.arm,s.propensity,s.age,s.pre,
AVG(CASE WHEN o.day<32 THEN o.y ELSE NULL END) pre_mean,AVG(CASE WHEN o.day>=32 THEN o.y ELSE NULL END) post_mean,
COUNT(CASE WHEN o.day<32 THEN 1 ELSE NULL END) n_pre,COUNT(CASE WHEN o.day>=32 THEN 1 ELSE NULL END) n_post,
SUM(CASE WHEN o.day>=32 THEN o.converted ELSE 0 END) successes
FROM subjects s JOIN outcomes o ON o.sid=s.sid AND o.ready_day<={cut} AND o.day BETWEEN 8 AND {cut} WHERE s.uid BETWEEN {lo} AND {hi} AND {sid} GROUP BY s.sid,s.uid,s.segment,s.arm,s.propensity,s.age,s.pre ORDER BY s.sid'''
 if domain==4:
  return f'''WITH eligible_touches AS (SELECT t.* FROM touches t JOIN identities z ON z.device=t.device AND z.person=t.person AND z.recorded_day<={cut} WHERE t.received_day<={cut}),
eligible AS (SELECT c.cid,c.person,c.day,c.minute conversion_min,c.revenue,c.converted,t.tid,t.channel,t.minute touch_min,t.score
FROM conversions c LEFT JOIN eligible_touches t ON t.person=c.person AND t.minute BETWEEN c.minute-{lb*1440} AND c.minute AND t.received_day<={cut}
WHERE c.person BETWEEN {lo} AND {hi} AND c.day BETWEEN {cut-lb} AND {cut})
SELECT e.*,k.spend,k.quality FROM eligible e LEFT JOIN campaigns k ON k.channel=e.channel ORDER BY cid,touch_min,tid'''
 if domain==5:
  return f'''SELECT d.uid,d.day,u.region,c.weekday,c.holiday,d.signal,d.demand,d.price,d.weather,CASE WHEN d.day<={cut} THEN 1 ELSE 0 END train_flag
FROM daily d JOIN units u ON u.uid=d.uid JOIN calendar c ON c.day=d.day WHERE d.uid BETWEEN {lo} AND {hi} AND d.day BETWEEN {cut-lb} AND {cut+h} ORDER BY d.uid,d.day'''
 if domain==6:
  end=EPOCH+cut*1440+600;start=EPOCH+(cut-lb)*1440
  if j==5:
   depth=2+(i%2);gap=240+p['k']*20
   return f'''WITH RECURSIVE edges AS (SELECT * FROM flows WHERE day BETWEEN {cut-lb} AND {cut} AND received_day<={cut}),
paths AS (SELECT src uid,dst node,minute last_min,CAST(amount AS DOUBLE) amount,CAST(1 AS BIGINT) hops,CAST(src*33+dst AS BIGINT) code FROM edges WHERE src={lo}
UNION ALL SELECT p.uid,e.dst,e.minute,p.amount+e.amount,p.hops+1,p.code*33+e.dst FROM paths p JOIN edges e ON e.src=p.node AND e.minute>p.last_min AND e.minute-p.last_min<={gap} WHERE p.hops<{depth})
SELECT uid,node,last_min,amount,hops,code FROM paths ORDER BY last_min,code,hops,amount'''
  return f'''SELECT f.fid,f.src,f.dst,f.day,f.minute,f.amount,u.region,u.sector FROM flows f JOIN units u ON f.src=u.uid WHERE f.day BETWEEN {cut-lb} AND {cut} AND f.received_day<={cut} AND (f.src BETWEEN {lo} AND {hi} OR f.dst BETWEEN {lo} AND {hi}) ORDER BY f.minute,f.fid'''
 if domain==7:
  return f'''WITH a AS (SELECT d.uid,d.day,d.price,d.signal,d.weather,u.region,LAG(d.price) OVER(PARTITION BY d.uid ORDER BY d.day) prev_price FROM daily d JOIN units u ON d.uid=u.uid WHERE d.uid BETWEEN {lo} AND {min(32,lo+3)} AND d.day BETWEEN {cut-lb} AND {cut})
SELECT uid,day,price,signal,weather,region,CASE WHEN prev_price IS NULL THEN NULL ELSE LN(price/prev_price) END x_return FROM a ORDER BY uid,day'''
 if domain==8:
  return f'''WITH a AS (SELECT g.*,u.region,LAG(g.lat) OVER(PARTITION BY g.uid ORDER BY g.minute,g.pid) prev_lat,LAG(g.lon) OVER(PARTITION BY g.uid ORDER BY g.minute,g.pid) prev_lon,LAG(g.minute) OVER(PARTITION BY g.uid ORDER BY g.minute,g.pid) prev_min FROM gps g JOIN units u ON g.uid=u.uid WHERE g.uid BETWEEN {lo} AND {hi} AND g.day BETWEEN {cut-lb} AND {cut} AND g.received_day<={cut} AND g.valid=1)
SELECT pid,uid,day,minute,lat,lon,offset_min,local_min,fold,region,prev_lat,prev_lon,prev_min FROM a ORDER BY uid,minute,pid'''
 if domain==9:
  return f'''SELECT pid,uid,day,model,segment,prob,CASE WHEN ready_day<={cut} THEN label ELSE NULL END AS label,ready_day,feature,
CASE WHEN ready_day<={cut+3} THEN label ELSE NULL END backfill_label FROM predictions WHERE uid BETWEEN {lo} AND {hi} AND day BETWEEN {cut-lb} AND {cut} AND model={j%2} ORDER BY day,pid'''
 raise ValueError(domain)

def complexity(sql):
 return dict(bytes=len(sql.encode()),ctes=len(re.findall(r'\bAS\s*\(',sql,re.I)),joins=len(re.findall(r'\bJOIN\b',sql,re.I)),windows=len(re.findall(r'\bOVER\s*\(',sql,re.I)),sha256=hashlib.sha256(sql.encode()).hexdigest())
if __name__=='__main__':
 catalog=[]
 for d in range(10):
  for j in range(10):catalog.append(dict(domain=d,name=DOMAINS[d],title=TITLES[d],template=j,question=TEMPLATES[d][j],cases=1000,example_sql=sql_for(d,j,0)))
 (ROOT/'scenario-catalog.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2));print('100 workflows, target 100000 cases')
