WITH selected_machines AS (SELECT * FROM machines WHERE plant<>7),
plant_energy AS (SELECT site,day,SUM(kwh*tariff) energy_cost,SUM(kwh) kwh,SUM(kwh*carbon) emissions FROM energy WHERE day BETWEEN 8 AND 83-1 GROUP BY site,day),
plant_capacity AS (SELECT plant,SUM(capacity) capacity FROM machines GROUP BY plant),
operation_facts AS (SELECT m.*,s.day,s.temperature,s.vibration,s.load_value,s.failure,s.downtime,p.output_units,p.defects,p.scrap_cost,e.energy_cost*m.capacity/c.capacity energy_cost,e.emissions*m.capacity/c.capacity emissions,
AVG(s.vibration) OVER(PARTITION BY m.machine ORDER BY s.day ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) rolling_vibration,
SUM(s.failure) OVER(PARTITION BY m.machine ORDER BY s.day ROWS BETWEEN 1 FOLLOWING AND 3 FOLLOWING) next_failures
FROM selected_machines m JOIN sensors s ON m.machine=s.machine JOIN production p ON m.machine=p.machine AND s.day=p.day JOIN plant_energy e ON m.plant=e.site AND s.day=e.day JOIN plant_capacity c ON m.plant=c.plant WHERE s.day BETWEEN 8 AND 83-1)
SELECT machine,plant,kind,day,age,capacity,temperature,vibration,load_value,failure,downtime,output_units,defects,scrap_cost,energy_cost,emissions,rolling_vibration,COALESCE(next_failures,0) next_failures FROM operation_facts ORDER BY machine,day;

WITH selected_machines AS (SELECT * FROM machines WHERE plant<>7),
plant_energy AS (SELECT site,day,SUM(kwh*tariff) energy_cost,SUM(kwh) kwh,SUM(kwh*carbon) emissions FROM energy WHERE day BETWEEN 8 AND 83-1 GROUP BY site,day),
plant_capacity AS (SELECT plant,SUM(capacity) capacity FROM machines GROUP BY plant),
operation_facts AS (SELECT m.*,s.day,s.temperature,s.vibration,s.load_value,s.failure,s.downtime,p.output_units,p.defects,p.scrap_cost,e.energy_cost*m.capacity/c.capacity energy_cost,e.emissions*m.capacity/c.capacity emissions,
AVG(s.vibration) OVER(PARTITION BY m.machine ORDER BY s.day ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) rolling_vibration,
SUM(s.failure) OVER(PARTITION BY m.machine ORDER BY s.day ROWS BETWEEN 1 FOLLOWING AND 3 FOLLOWING) next_failures
FROM selected_machines m JOIN sensors s ON m.machine=s.machine JOIN production p ON m.machine=p.machine AND s.day=p.day JOIN plant_energy e ON m.plant=e.site AND s.day=e.day JOIN plant_capacity c ON m.plant=c.plant WHERE s.day BETWEEN 8 AND 83-1)
SELECT machine,SUM(downtime) downtime,SUM(scrap_cost+energy_cost) operating_cost FROM operation_facts GROUP BY machine ORDER BY machine;