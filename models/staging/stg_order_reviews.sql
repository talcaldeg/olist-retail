-- review_id alone is not unique in the source (the same review can be attached to
-- several orders); the grain is (review_id, order_id).
select
    review_id,
    order_id,
    review_score,
    nullif(trim(review_comment_title), '') as review_comment_title,
    nullif(trim(review_comment_message), '') as review_comment_message,
    datetime(review_creation_date) as review_created_at,
    datetime(review_answer_timestamp) as review_answered_at
from {{ source('olist', 'order_reviews') }}
