import os
import logging
from typing import List
from supabase import create_client, Client
from .models import CarListing

logger = logging.getLogger(__name__)

MAX_MILEAGE = 2_000_000   # sanity cap — no car has more than 2M km
MAX_PRICE   = 10_000_000  # sanity cap


def get_client() -> Client:
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_KEY"]
    return create_client(url, key)


def sanitize(listing: CarListing) -> dict:
    row = listing.to_dict()
    # clamp numeric fields to safe ranges
    if row.get("mileage") and row["mileage"] > MAX_MILEAGE:
        row["mileage"] = None
    if row.get("price") and row["price"] > MAX_PRICE:
        row["price"] = None
    if row.get("year") and (row["year"] < 1900 or row["year"] > 2030):
        row["year"] = None
    row["last_seen"] = "now()"
    return row


def upsert_listings(listings: List[CarListing]) -> int:
    if not listings:
        return 0

    client = get_client()
    rows = [sanitize(l) for l in listings]

    result = (
        client.table("listings")
        .upsert(rows, on_conflict="source,source_id")
        .execute()
    )
    count = len(result.data) if result.data else 0
    logger.info(f"Upserted {count} listings")
    return count


def deactivate_stale() -> None:
    client = get_client()
    client.rpc("deactivate_stale_listings").execute()
    logger.info("Deactivated stale listings")
