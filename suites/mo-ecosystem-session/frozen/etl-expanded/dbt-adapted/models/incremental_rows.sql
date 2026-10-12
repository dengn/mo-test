{{ config(materialized='incremental',unique_key='id') }}
select id,label,amount from {{ ref('transformed') }}
