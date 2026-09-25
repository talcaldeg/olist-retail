"""Download the Olist public dataset and load it into BigQuery `raw_olist`.

Idempotent: files already downloaded are skipped (unless --force-download) and every
table is dropped and reloaded, so re-running leaves the same nine tables with the same
contents and a fresh 59-day expiration (the project runs in the BigQuery sandbox). Row counts are asserted against the published dataset so a silently
truncated download fails loudly instead of poisoning the models downstream.

Source: https://huggingface.co/datasets/bulutttt/olist-raw-data (mirror of the Kaggle
dataset `olistbr/brazilian-ecommerce`, CC BY-NC-SA 4.0). The mirror is used so the repo
can be cloned and run without Kaggle credentials.
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.request
from pathlib import Path

from google.cloud import bigquery

PROJECT = os.environ.get("OLIST_GCP_PROJECT", "olist-retail-portfolio")
DATASET = "raw_olist"
LOCATION = "US"
EXPIRATION_MS = 59 * 24 * 60 * 60 * 1000  # sandbox limit is 60 days

BASE_URL = "https://huggingface.co/datasets/bulutttt/olist-raw-data/resolve/main"
RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

S = bigquery.enums.SqlTypeNames.STRING
I = bigquery.enums.SqlTypeNames.INTEGER
F = bigquery.enums.SqlTypeNames.FLOAT
T = bigquery.enums.SqlTypeNames.TIMESTAMP


def field(name: str, kind) -> bigquery.SchemaField:
    return bigquery.SchemaField(name, kind)


# table -> (csv file, expected rows, schema)
TABLES: dict[str, tuple[str, int, list[bigquery.SchemaField]]] = {
    "customers": (
        "olist_customers_dataset.csv",
        99_441,
        [
            field("customer_id", S),
            field("customer_unique_id", S),
            field("customer_zip_code_prefix", I),
            field("customer_city", S),
            field("customer_state", S),
        ],
    ),
    "geolocation": (
        "olist_geolocation_dataset.csv",
        1_000_163,
        [
            field("geolocation_zip_code_prefix", I),
            field("geolocation_lat", F),
            field("geolocation_lng", F),
            field("geolocation_city", S),
            field("geolocation_state", S),
        ],
    ),
    "order_items": (
        "olist_order_items_dataset.csv",
        112_650,
        [
            field("order_id", S),
            field("order_item_id", I),
            field("product_id", S),
            field("seller_id", S),
            field("shipping_limit_date", T),
            field("price", F),
            field("freight_value", F),
        ],
    ),
    "order_payments": (
        "olist_order_payments_dataset.csv",
        103_886,
        [
            field("order_id", S),
            field("payment_sequential", I),
            field("payment_type", S),
            field("payment_installments", I),
            field("payment_value", F),
        ],
    ),
    "order_reviews": (
        "olist_order_reviews_dataset.csv",
        99_224,
        [
            field("review_id", S),
            field("order_id", S),
            field("review_score", I),
            field("review_comment_title", S),
            field("review_comment_message", S),
            field("review_creation_date", T),
            field("review_answer_timestamp", T),
        ],
    ),
    "orders": (
        "olist_orders_dataset.csv",
        99_441,
        [
            field("order_id", S),
            field("customer_id", S),
            field("order_status", S),
            field("order_purchase_timestamp", T),
            field("order_approved_at", T),
            field("order_delivered_carrier_date", T),
            field("order_delivered_customer_date", T),
            field("order_estimated_delivery_date", T),
        ],
    ),
    "products": (
        "olist_products_dataset.csv",
        32_951,
        [
            field("product_id", S),
            field("product_category_name", S),
            field("product_name_lenght", I),
            field("product_description_lenght", I),
            field("product_photos_qty", I),
            field("product_weight_g", I),
            field("product_length_cm", I),
            field("product_height_cm", I),
            field("product_width_cm", I),
        ],
    ),
    "sellers": (
        "olist_sellers_dataset.csv",
        3_095,
        [
            field("seller_id", S),
            field("seller_zip_code_prefix", I),
            field("seller_city", S),
            field("seller_state", S),
        ],
    ),
    "product_category_name_translation": (
        "product_category_name_translation.csv",
        71,
        [
            field("product_category_name", S),
            field("product_category_name_english", S),
        ],
    ),
}


def download(force: bool) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for csv_name, _, _ in TABLES.values():
        target = RAW_DIR / csv_name
        if target.exists() and not force:
            print(f"  ya estaba: {csv_name}")
            continue
        print(f"  bajando:   {csv_name}")
        urllib.request.urlretrieve(f"{BASE_URL}/{csv_name}", target)


def ensure_dataset(client: bigquery.Client) -> None:
    """Create the dataset so it is valid in the BigQuery sandbox.

    The project has no billing account linked, so it can never be charged; the price
    is that the sandbox rejects datasets without a default expiration under 60 days.
    """
    dataset = bigquery.Dataset(f"{PROJECT}.{DATASET}")
    dataset.location = LOCATION
    dataset.default_table_expiration_ms = EXPIRATION_MS
    dataset.default_partition_expiration_ms = EXPIRATION_MS
    dataset = client.create_dataset(dataset, exists_ok=True)
    if dataset.default_table_expiration_ms != EXPIRATION_MS:
        dataset.default_table_expiration_ms = EXPIRATION_MS
        dataset.default_partition_expiration_ms = EXPIRATION_MS
        client.update_dataset(
            dataset, ["default_table_expiration_ms", "default_partition_expiration_ms"]
        )


def load(client: bigquery.Client) -> list[str]:
    ensure_dataset(client)
    problems: list[str] = []
    for table, (csv_name, expected_rows, schema) in TABLES.items():
        table_id = f"{PROJECT}.{DATASET}.{table}"
        # The sandbox caps expiration at 60 days from the table's *creation*, and
        # WRITE_TRUNCATE keeps the original creation time. Dropping first makes every
        # reload start a fresh 59-day window.
        client.delete_table(table_id, not_found_ok=True)
        job_config = bigquery.LoadJobConfig(
            schema=schema,
            source_format=bigquery.SourceFormat.CSV,
            skip_leading_rows=1,
            allow_quoted_newlines=True,  # review comments contain line breaks
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        )
        with open(RAW_DIR / csv_name, "rb") as fh:
            client.load_table_from_file(fh, table_id, job_config=job_config).result()
        got = client.get_table(table_id).num_rows
        flag = "ok" if got == expected_rows else f"ESPERADAS {expected_rows:,}"
        print(f"  {table:<34} {got:>9,} filas   {flag}")
        if got != expected_rows:
            problems.append(f"{table}: {got} filas, se esperaban {expected_rows}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force-download",
        action="store_true",
        help="volver a bajar los CSV aunque ya estén en data/raw",
    )
    args = parser.parse_args()

    print(f"1. CSV en {RAW_DIR}")
    download(args.force_download)
    print(f"2. Carga a {PROJECT}.{DATASET}")
    problems = load(bigquery.Client(project=PROJECT, location=LOCATION))
    if problems:
        print("\nLa carga no cuadra con el dataset publicado:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("\nListo: nueve tablas cargadas y cuadradas contra el conteo publicado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
