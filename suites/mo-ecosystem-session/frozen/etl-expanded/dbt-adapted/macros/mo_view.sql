{# Isolated compatibility probe: direct replacement avoids unsupported view rename. #}
{% materialization mo_view, adapter='mysql' %}
  {% call statement('main') %}
    create or replace view {{ this }} as {{ sql }}
  {% endcall %}
  {{ adapter.commit() }}
  {{ return({'relations': [this]}) }}
{% endmaterialization %}
