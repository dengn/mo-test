select id, upper(label) as label, cast(amount * 2 as decimal(18,2)) as amount from {{ ref('source_rows') }}
