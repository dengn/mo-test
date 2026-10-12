WITH scope AS (SELECT * FROM entities WHERE eid>=49 AND eid<61),
events_visible AS (SELECT e.*,s.region,s.sector,c.weekday,c.offset_min,minute+c.offset_min civil_min FROM events e JOIN scope s ON s.eid=e.eid JOIN calendar c ON c.day=e.day WHERE e.day>=10 AND e.day<78 AND received_min<=28517760),
ev AS (SELECT *,CAST(magnitude AS DOUBLE) x,ROW_NUMBER() OVER(PARTITION BY eid ORDER BY minute,event_id) rn,LAG(minute) OVER(PARTITION BY eid ORDER BY minute,event_id) prev_min,LAG(kind) OVER(PARTITION BY eid ORDER BY minute,event_id) prev_kind FROM events_visible),
decay AS (SELECT a.eid,a.event_id,SUM(b.x*EXP(-CAST(a.minute-b.minute AS DOUBLE)/5760))/NULLIF(SUM(EXP(-CAST(a.minute-b.minute AS DOUBLE)/5760)),0) decayed FROM ev a JOIN ev b ON a.eid=b.eid AND b.minute<=a.minute AND b.minute>=a.minute-5760 GROUP BY a.eid,a.event_id),
a AS (SELECT e.*,d.decayed FROM ev e JOIN decay d ON e.eid=d.eid AND e.event_id=d.event_id),
b AS (SELECT *,AVG(decayed) OVER(PARTITION BY eid ORDER BY minute,event_id ROWS BETWEEN 4 PRECEDING AND CURRENT ROW) decayed_mean,LAG(decayed,5) OVER(PARTITION BY eid ORDER BY minute,event_id) prior_decay FROM a)
SELECT eid,minute,event_id,x,rn,decayed,decayed_mean,prior_decay FROM b WHERE day>=30 ORDER BY eid,minute,event_id;
