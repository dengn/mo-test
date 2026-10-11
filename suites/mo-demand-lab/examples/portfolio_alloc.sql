WITH prices_lag AS (SELECT *,LAG(close_price) OVER(PARTITION BY asset ORDER BY day) prior_close FROM market),
market_returns AS (SELECT *,LN(close_price/prior_close) log_return FROM prices_lag WHERE day BETWEEN 0 AND 191),
market_facts AS (SELECT *,close_price/MAX(close_price) OVER(PARTITION BY asset ORDER BY day ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)-1 drawdown FROM market_returns)
SELECT asset,day,close_price,COALESCE(log_return,0) log_return,drawdown,volume FROM market_facts ORDER BY day,asset;

WITH prices_lag AS (SELECT *,LAG(close_price) OVER(PARTITION BY asset ORDER BY day) prior_close FROM market),
market_returns AS (SELECT *,LN(close_price/prior_close) log_return FROM prices_lag WHERE day BETWEEN 0 AND 191),
market_facts AS (SELECT *,close_price/MAX(close_price) OVER(PARTITION BY asset ORDER BY day ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)-1 drawdown FROM market_returns)
SELECT asset,AVG(log_return) mean_return,VAR_POP(log_return) variance FROM market_facts GROUP BY asset ORDER BY asset;