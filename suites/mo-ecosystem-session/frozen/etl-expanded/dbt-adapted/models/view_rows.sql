{{ config(materialized='mo_view') }}
select id,label,amount from {{ ref('transformed') }} where amount>0
