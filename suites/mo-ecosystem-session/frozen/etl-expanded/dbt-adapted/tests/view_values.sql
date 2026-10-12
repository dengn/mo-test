select 1 as mismatch where
  (select count(*) from {{ ref('view_rows') }}) <> 3
  or (select amount from {{ ref('view_rows') }} where id=1) <> 24.68
