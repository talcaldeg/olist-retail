{#
  Whether an order takes units out of the seller's stock. Canceled and unavailable
  orders never shipped; every other status (delivered, shipped, invoiced, processing,
  created, approved) has the goods committed. Defined once so sales and stock agree.
#}
{% macro consumes_stock(order_status) -%}
    {{ order_status }} not in ('canceled', 'unavailable')
{%- endmacro %}
