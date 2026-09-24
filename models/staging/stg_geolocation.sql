-- One row per raw point: a zip prefix appears many times with slightly different
-- coordinates. Collapsing to one point per prefix is a modelling decision, not cleanup,
-- so it is left to the layer that needs it.
select
    {{ zip_prefix('geolocation_zip_code_prefix') }} as zip_code_prefix,
    geolocation_lat as latitude,
    geolocation_lng as longitude,
    geolocation_city as city,
    upper(geolocation_state) as state
from {{ source('olist', 'geolocation') }}
