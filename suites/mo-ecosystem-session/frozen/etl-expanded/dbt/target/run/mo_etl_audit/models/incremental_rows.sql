
      insert into `etl_dbt`.`incremental_rows` (`id`, `label`, `amount`)
    (
       select `id`, `label`, `amount`
       from `etl_dbt`.`incremental_rows__dbt_tmp`
    )
  