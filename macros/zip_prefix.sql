{#
  Brazilian CEP prefixes have five digits; the raw CSV stores them as integers, which
  drops the leading zero (01003 arrives as 1003). Restore it so they join as text.
#}
{% macro zip_prefix(column) -%}
    lpad(cast({{ column }} as string), 5, '0')
{%- endmacro %}
