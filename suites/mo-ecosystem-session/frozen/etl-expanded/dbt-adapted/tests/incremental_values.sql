select 1 as mismatch where
  (select count(*) from {{ ref('incremental_rows') }}) <> 4
  or (select amount from {{ ref('incremental_rows') }} where id=2) <> -157.80
