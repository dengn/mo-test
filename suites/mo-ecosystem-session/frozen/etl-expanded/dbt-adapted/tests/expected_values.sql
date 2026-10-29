select 1 as mismatch where
  (select count(*) from {{ ref('transformed') }}) <> 4
  or (select amount from {{ ref('transformed') }} where id=1) <> 24.68
  or (select amount from {{ ref('transformed') }} where id=2) <> -157.80
  or (select label from {{ ref('transformed') }} where id=1) <> '中文'
