import os
import logging
from typing import List
from supabase import create_client, Client
from .models import CarListing

logger = logging.getLogger(__name__)

MAX_MILEAGE = 2_000_000
MAX_PRICE   = 10_000_000

def get_client() -> Client:
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_KEY"]
    return create_client(url, key)

def sanitize(listing: CarListing) -> dict:
    row = listing.to_dict()
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

    # Deduplicate by (source, source_id) — keep last occurrence
    seen = {}
    for l in listings:
        key = (l.source, l.source_id)
        seen[key] = l
    unique = list(seen.values())
    logger.info(f"Deduped {len(listings)} → {len(unique)} unique listings")

    client = get_client()
    # Upload in batches of 100 to avoid request size limits
    total = 0
    for i in range(0, len(unique), 100):
        batch = [sanitize(l) for l in unique[i:i+100]]
        result = (
            client.table("listings")
            .upsert(batch, on_conflict="source,source_id")
            .execute()
        )
        total += len(result.data) if result.data else 0

    logger.info(f"Upserted {total} listings")
    return total

def deactivate_stale() -> None:
    client = get_client()
    client.rpc("deactivate_stale_listings").execute()
    logger.info("Deactivated stale listings")
