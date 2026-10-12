{{ config(materialized='view') }}
select id,label,amount from {{ ref('transformed') }} where amount>0
