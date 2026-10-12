WITH scope AS (SELECT * FROM entities WHERE eid>=49 AND eid<61),
mr AS (SELECT m.*,ROW_NUMBER() OVER(PARTITION BY event_id ORDER BY revision DESC,rid DESC) revision_rank FROM measurements m JOIN scope s ON m.eid=s.eid WHERE m.day>=10 AND m.day<78 AND received_day<=81),
mq AS (SELECT * FROM mr WHERE revision_rank=1 AND valid=1),
md AS (SELECT eid,day,AVG(CAST(value AS DOUBLE)) sensor,COUNT(value) observations,COUNT(*) raw_count,SUM(CAST(value AS DOUBLE)*CAST(value AS DOUBLE)) sensor_sq FROM mq GROUP BY eid,day),
original_md AS (SELECT eid,day,AVG(CAST(value AS DOUBLE)) original_sensor FROM measurements WHERE revision=0 AND day>=10 AND day<78 GROUP BY eid,day),
reversal_sum AS (SELECT tid,SUM(amount) reversed FROM reversals WHERE day<=81 GROUP BY tid),
td AS (SELECT t.eid,t.day,SUM(CASE WHEN settled=1 THEN amount-COALESCE(r.reversed,0) ELSE 0 END) net FROM trades t JOIN scope s ON t.eid=s.eid LEFT JOIN reversal_sum r ON t.tid=r.tid WHERE t.day>=10 AND t.day<78 GROUP BY t.eid,t.day),
shipment_sum AS (SELECT sh0.oid,SUM(sh0.qty) shipped,SUM(CASE WHEN sh0.day-o.day>3 THEN sh0.qty ELSE 0 END) late_qty FROM (SELECT sh.oid,sh.day,sh.qty FROM shipments sh WHERE sh.day<=81) sh0 JOIN orders o ON sh0.oid=o.oid GROUP BY sh0.oid),
od AS (SELECT o.eid,o.day,SUM(o.qty) demand,SUM(COALESCE(ss.shipped,0)) shipped,SUM(COALESCE(ss.late_qty,0)) late_qty FROM orders o JOIN scope s ON o.eid=s.eid LEFT JOIN shipment_sum ss ON o.oid=ss.oid WHERE o.day>=10 AND o.day<78 GROUP BY o.eid,o.day),
ed AS (SELECT e.eid,e.day,COUNT(*) event_count,SUM(CASE WHEN received_min-minute>1440 THEN 1 ELSE 0 END) late_count,SUM(CASE WHEN kind=0 THEN 1 ELSE 0 END) phase0,SUM(CASE WHEN kind=1 THEN 1 ELSE 0 END) phase1 FROM events e JOIN scope s ON e.eid=s.eid WHERE e.day>=10 AND e.day<78 AND received_min<=28517760 GROUP BY e.eid,e.day),
grid AS (SELECT s.eid,s.region,s.sector,s.scale,c.* FROM scope s CROSS JOIN calendar c WHERE c.day>=10 AND c.day<78),
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
daily AS (SELECT j.*,COALESCE(sensor,0)/scale+demand/CAST(target AS DOUBLE)+temp/50+y/scale/20+severity-stock/100.0-capacity/200+effect+neighbor/scale/20+price/100+rate/10-budget/10000+late_qty/20.0+late_count/100.0 x FROM joined j),
a AS (SELECT *,MAX(CASE WHEN sensor IS NOT NULL THEN day ELSE NULL END) OVER(PARTITION BY eid ORDER BY day ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) observed_day FROM daily),
b AS (SELECT *,MAX(sensor) OVER(PARTITION BY eid,observed_day) carried FROM a),
c AS (SELECT *,AVG(carried) OVER(PARTITION BY eid ORDER BY day ROWS BETWEEN 4 PRECEDING AND CURRENT ROW) carried_mean FROM b)
SELECT eid,day,x,sensor,observed_day,carried,day-observed_day age,carried_mean FROM c WHERE day>=30 ORDER BY eid,day;
