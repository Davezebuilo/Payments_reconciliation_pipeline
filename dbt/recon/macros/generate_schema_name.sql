{#
  By default dbt names custom schemas "<target schema>_<custom>", e.g. analytics_staging.
  This uses the custom name as-is, so models land in "staging", "intermediate" and "marts".
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}{{ target.schema }}{%- else -%}{{ custom_schema_name | trim }}{%- endif -%}
{%- endmacro %}