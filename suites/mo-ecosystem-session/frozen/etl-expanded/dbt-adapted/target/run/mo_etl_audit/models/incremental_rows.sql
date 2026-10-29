
      insert into `etl_dbt_adapted`.`incremental_rows` (`id`, `label`, `amount`)
    (
       select `id`, `label`, `amount`
       from `etl_dbt_adapted`.`incremental_rows__dbt_tmp`
    )
  