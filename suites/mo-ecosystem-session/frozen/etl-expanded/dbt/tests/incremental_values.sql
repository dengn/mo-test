select 1 as mismatch where
  (select count(*) from {{ ref('incremental_rows') }}) <> 3
  or (select amount from {{ ref('incremental_rows') }} where id=2) <> -113.56
