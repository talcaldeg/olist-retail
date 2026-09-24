select
    order_id,
    customer_id,
    order_status,
    datetime(order_purchase_timestamp) as purchased_at,
    datetime(order_approved_at) as approved_at,
    datetime(order_delivered_carrier_date) as delivered_to_carrier_at,
    datetime(order_delivered_customer_date) as delivered_to_customer_at,
    datetime(order_estimated_delivery_date) as estimated_delivery_at
from {{ source('olist', 'orders') }}
