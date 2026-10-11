WITH energy_facts AS (SELECT * FROM energy WHERE day BETWEEN 8 AND 83-1 AND site=7)
SELECT hour,AVG(kwh) demand,AVG(tariff) tariff,AVG(carbon) carbon,MAX(capacity) capacity FROM energy_facts GROUP BY hour ORDER BY hour;

WITH energy_facts AS (SELECT * FROM energy WHERE day BETWEEN 8 AND 83-1 AND site=7)
SELECT day,SUM(kwh*tariff) energy_cost,SUM(kwh) demand,MAX(kwh) peak FROM energy_facts GROUP BY day ORDER BY day;