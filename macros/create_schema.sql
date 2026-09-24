{#
  The GCP project runs in the BigQuery sandbox (no billing account linked), so it can
  never be charged. The sandbox rejects datasets without a default expiration under 60
  days, so every dataset dbt creates declares one. Rebuilding refreshes the objects.
#}
{% macro bigquery__create_schema(relation) -%}
    {% call statement('create_schema') %}
        create schema if not exists `{{ relation.database }}`.`{{ relation.schema }}`
        options(
            location = '{{ target.location or "US" }}',
            default_table_expiration_days = 59,
            default_partition_expiration_days = 59
        )
    {% endcall %}
{%- endmacro %}
