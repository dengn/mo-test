WITH scope AS (
 SELECT e.*,CASE WHEN e.eid<118 THEN 0 WHEN e.eid<130 THEN 1 ELSE 2 END AS split_id,
 CASE WHEN e.eid<118 THEN 27 WHEN e.eid<130 THEN 32 ELSE 37 END AS anchor FROM entities e WHERE e.eid>=78 AND e.eid<142),
 ts AS (SELECT t.eid,t.day,SUM(t.amount) AS amt FROM trades t JOIN scope s ON s.eid=t.eid WHERE t.valid=1 AND t.day<=s.anchor GROUP BY t.eid,t.day),
 es AS (SELECT v.eid,v.day,SUM(v.value) AS ev FROM events v JOIN scope s ON s.eid=v.eid WHERE v.day<=s.anchor AND NOT EXISTS(SELECT 1 FROM interventions z WHERE z.eid=v.eid AND z.day=v.day AND z.active=1) GROUP BY v.eid,v.day),
 ms AS (SELECT s.eid,MAX(m.day) AS md FROM scope s LEFT JOIN maintenance m ON m.eid=s.eid AND m.day<=s.anchor GROUP BY s.eid),
 ex AS (SELECT x.eid,SUM(x.weight*g.multiplier) AS exposure FROM exposures x JOIN segments g ON g.sector=x.sector GROUP BY x.eid),
 gr AS (SELECT a.src,SUM(a.weight) AS degree FROM edges a JOIN scope s ON s.eid=a.src JOIN scope d ON d.eid=a.dst AND d.split_id=s.split_id GROUP BY a.src),
 hist AS (SELECT s.eid,s.split_id,s.anchor,r.day,r.x0,r.x1,r.x2,r.x3,COALESCE(LAG(r.x0) OVER(PARTITION BY s.eid ORDER BY r.day),r.x0) AS lag0
 FROM scope s JOIN readings r ON r.eid=s.eid AND r.day>s.anchor-12 AND r.day<=s.anchor)
 SELECT a.eid,a.split_id,a.anchor,a.day,a.x0,a.x1,a.x2,a.x3,a.lag0,
 COALESCE(t.amt,0) AS amt,COALESCE(v.ev,0) AS ev,COALESCE(m.score,0) AS maintenance,
 COALESCE(o.minutes,0) AS outage,w.temp,c.weekday,p.price,x.exposure,z.cap,COALESCE(g.degree,0) AS degree,
 e.bias,e.sector,e.region,lb.response,lb.risk,lbc.anomaly,cl.c0,cl.c1,cl.c2,cl.c3
 FROM hist a JOIN scope e ON e.eid=a.eid LEFT JOIN ts t ON t.eid=a.eid AND t.day=a.day
 LEFT JOIN es v ON v.eid=a.eid AND v.day=a.day LEFT JOIN ms ON ms.eid=a.eid LEFT JOIN maintenance m ON m.eid=ms.eid AND m.day=ms.md
 LEFT JOIN outages o ON o.eid=a.eid AND o.day=a.day JOIN weather w ON w.region=e.region AND w.day=a.day
 JOIN calendar c ON c.day=a.day JOIN prices p ON p.sector=e.sector AND p.day=a.day JOIN ex x ON x.eid=a.eid
 JOIN policies z ON z.region=e.region LEFT JOIN gr g ON g.src=a.eid
 JOIN labels lb ON lb.eid=a.eid AND lb.day=a.anchor+4 JOIN labels lbc ON lbc.eid=a.eid AND lbc.day=a.anchor JOIN targets cl ON cl.eid=a.eid AND cl.day=a.anchor
 ORDER BY a.eid,a.day