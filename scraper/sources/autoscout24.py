"""
AutoScout24.es scraper — parses __NEXT_DATA__ JSON embedded in search pages.
Searches by postal code 07001 (Palma de Mallorca) with a 100km radius,
which covers all of Mallorca and most of the Balearic Islands.

No detail-page enrichment needed: the listing API already returns full image
galleries (up to 11 images per car) in the search results JSON.
"""
import logging
import time
import re
import requests
from typing import List
from ..models import CarListing

try:
    import json
except ImportError:
    import simplejson as json

logger = logging.getLogger(__name__)

BASE_URL = "https://www.autoscout24.es/lst"
PARAMS_BASE = {
    "atype": "C",
    "cy": "E",
    "zip": "07001",
    "zipr": "100",
    "sort": "age",
    "desc": "0",
    "offer": "J,U",
    "ustate": "N,U",
    "climit": "20",
}
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.autoscout24.es/",
}

FUEL_MAP = {
    "diésel": "diesel", "diesel": "diesel",
    "gasolina": "gasoline", "benzina": "gasoline",
    "híbrido": "hybrid", "hybrid": "hybrid",
    "electro/gasolina": "hybrid", "eléctrico/gasolina": "hybrid",
    "eléctrico": "electric", "electric": "electric",
    "gas": "gas", "glp": "gas", "gnc": "gas",
}
GEARBOX_MAP = {
    "manual": "manual",
    "automático": "automatic", "automatico": "automatic",
    "semiautomático": "automatic",
}


def _upgrade_image_url(url: str) -> str:
    """Replace AutoScout24 thumbnail size suffix with a larger one."""
    # e.g. .../image.jpg/250x188.webp  →  .../image.jpg/800x600.webp
    return re.sub(r"/\d+x\d+\.webp$", "/800x600.webp", url)


def _parse_price(formatted: str) -> int | None:
    """'€ 12.500' → 12500"""
    digits = re.sub(r"[^\d]", "", formatted)
    try:
        v = int(digits)
        return v if 500 < v < 5_000_000 else None
    except (ValueError, TypeError):
        return None


def _parse_km(km_str: str) -> int | None:
    """'105.000 km' → 105000"""
    digits = re.sub(r"[^\d]", "", km_str)
    try:
        v = int(digits)
        return v if v < 2_000_000 else None
    except (ValueError, TypeError):
        return None


def _parse_listing(item: dict) -> CarListing | None:
    try:
        source_id = item.get("id", "")
        url_path = item.get("url", "")
        listing_url = f"https://www.autoscout24.es{url_path}" if url_path.startswith("/") else url_path

        price_data = item.get("price", {})
        price = _parse_price(price_data.get("priceFormatted", ""))

        vehicle = item.get("vehicle", {})
        make = vehicle.get("make")
        model = vehicle.get("model")
        raw_fuel = (vehicle.get("fuel") or "").lower()
        raw_gear = (vehicle.get("transmission") or "").lower()
        fuel = FUEL_MAP.get(raw_fuel)
        gearbox = GEARBOX_MAP.get(raw_gear)
        mileage = _parse_km(vehicle.get("mileageInKm") or "")

        title_parts = [p for p in [make, model, vehicle.get("modelVersionInput")] if p]
        title = " ".join(title_parts[:2]) or vehicle.get("variant") or source_id

        loc = item.get("location", {})
        city = loc.get("city", "")
        location = city.title() if city else "Mallorca"

        raw_images = item.get("images") or []
        images = [_upgrade_image_url(u) for u in raw_images if u]
        image_url = images[0] if images else None

        if not title or not source_id:
            return None

        return CarListing(
            source="autoscout24",
            source_id=source_id,
            title=title,
            listing_url=listing_url,
            price=price,
            mileage=mileage,
            fuel=fuel,
            gearbox=gearbox,
            make=make,
            model=model,
            location=location,
            image_url=image_url,
            images=images,
        )
    except Exception as e:
        logger.debug(f"AutoScout24: failed to parse listing — {e}")
        return None


def scrape(max_pages: int = 40) -> List[CarListing]:
    """
    Scrape up to max_pages pages from AutoScout24.es Mallorca/Baleares search.
    20 listings per page × 40 pages = up to 800 listings per run.
    The search returns ~1,500 total; capping at 40 pages keeps runtime reasonable.
    """
    listings: List[CarListing] = []
    seen_ids: set = set()

    for page_num in range(1, max_pages + 1):
        params = {**PARAMS_BASE, "page": page_num}
        logger.info(f"AutoScout24: page {page_num}/{max_pages}")
        try:
            r = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=20)
            r.raise_for_status()
        except requests.HTTPError as e:
            logger.warning(f"AutoScout24: HTTP error on page {page_num} — {e}")
            break
        except Exception as e:
            logger.warning(f"AutoScout24: request error on page {page_num} — {e}")
            break

        # Extract __NEXT_DATA__ JSON
        import re as _re
        m = _re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            r.text, _re.DOTALL,
        )
        if not m:
            logger.warning(f"AutoScout24: no __NEXT_DATA__ on page {page_num}")
            break

        try:
            data = json.loads(m.group(1))
            page_props = data["props"]["pageProps"]
            items = page_props.get("listings", [])
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"AutoScout24: JSON parse error on page {page_num} — {e}")
            break

        if not items:
            logger.info(f"AutoScout24: no items on page {page_num}, stopping")
            break

        logger.info(
            f"AutoScout24: {len(items)} listings on page {page_num} "
            f"(total available: {page_props.get('numberOfResults', '?')})"
        )

        new_on_page = 0
        for item in items:
            listing = _parse_listing(item)
            if listing and listing.source_id not in seen_ids:
                seen_ids.add(listing.source_id)
                listings.append(listing)
                new_on_page += 1

        if new_on_page == 0:
            logger.info("AutoScout24: no new listings on page, stopping")
            break

        time.sleep(1.5)

    logger.info(f"AutoScout24: done — {len(listings)} listings collected")
    return listings
