{#
  Olist is thin at both ends: three sparse months in 2016 (none in November) and a single
  sale in September 2018. Marts keep every month so totals reconcile with the raw data,
  and flag the months that are complete enough to compare. The window lives in
  dbt_project.yml.
#}
{% macro in_reporting_window(month_column) -%}
    {{ month_column }} between date '{{ var("reporting_start") }}'
        and date '{{ var("reporting_end") }}'
{%- endmacro %}
