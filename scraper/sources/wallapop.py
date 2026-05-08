"""
Wallapop scraper — uses the Wallapop web API.
Mallorca center coords: lat=39.6953, lon=3.0176
"""
import logging
import time
import requests
from typing import List
from ..models import CarListing

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-ES,es;q=0.9",
    "Referer": "https://es.wallapop.com/",
    "Origin": "https://es.wallapop.com",
}

FUEL_MAP = {
    "gasolina": "gasoline", "diesel": "diesel", "diésel": "diesel",
    "híbrido": "hybrid", "eléctrico": "electric", "gas": "gas",
}
GEARBOX_MAP = {"manual": "manual", "automático": "automatic"}


def fetch_page(start: int = 0, items: int = 40) -> dict:
    url = "https://api.wallapop.com/api/v3/cars/search"
    params = {
        "latitude": 39.6953, "longitude": 3.0176,
        "distance": 50000, "order_by": "newest",
        "start": start, "items": items,
    }
    r = requests.get(url, params=params, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.json()


def parse_item(item: dict) -> CarListing:
    # handle both wrapped and unwrapped formats
    content = item.get("content", item)
    specs = content.get("extra_info", content.get("car", {}))

    raw_fuel = (specs.get("engine", specs.get("fuel_type", "")) or "").lower()
    raw_gearbox = (specs.get("gearbox", specs.get("transmission", "")) or "").lower()

    price_data = content.get("sale_price", content.get("price", {}))
    if isinstance(price_data, dict):
        price = int(price_data.get("amount", 0)) or None
    elif isinstance(price_data, (int, float)):
        price = int(price_data) or None
    else:
        price = None

    slug = content.get("web_slug", content.get("slug", str(content.get("id", ""))))
    listing_url = f"https://es.wallapop.com/item/{slug}"

    images = content.get("images", [content.get("main_image", {})])
    image_url = None
    if images and isinstance(images[0], dict):
        image_url = images[0].get("medium", images[0].get("original"))

    location = content.get("location", {})
    city = location.get("city", location.get("postal_name", "Mallorca")) if isinstance(location, dict) else "Mallorca"

    return CarListing(
        source="wallapop",
        source_id=str(content["id"]),
        title=content.get("title", ""),
        listing_url=listing_url,
        price=price,
        year=specs.get("year", specs.get("registration_year")),
        mileage=specs.get("km", specs.get("kilometers")),
        fuel=FUEL_MAP.get(raw_fuel),
        gearbox=GEARBOX_MAP.get(raw_gearbox),
        make=specs.get("brand", specs.get("make")),
        model=specs.get("model"),
        location=city,
        image_url=image_url,
        description=str(content.get("description", ""))[:500],
    )


def scrape(max_pages: int = 10) -> List[CarListing]:
    listings: List[CarListing] = []
    page_size = 40

    for page in range(max_pages):
        start = page * page_size
        logger.info(f"Wallapop: fetching page {page + 1}/{max_pages} (start={start})")
        try:
            data = fetch_page(start=start, items=page_size)
            logger.info(f"Wallapop: response keys: {list(data.keys())}")
        except requests.HTTPError as e:
            logger.warning(f"Wallapop HTTP error on page {page}: {e}")
            break
        except Exception as e:
            logger.warning(f"Wallapop error: {e}")
            break

        # try multiple possible response keys
        items = (
            data.get("search_objects")
            or data.get("items")
            or data.get("data", {}).get("items", [])
            or data.get("data", {}).get("search_objects", [])
            or []
        )

        logger.info(f"Wallapop: found {len(items)} items on page {page + 1}")
        if not items:
            logger.info("Wallapop: no more results")
            break

        for item in items:
            try:
                listings.append(parse_item(item))
            except Exception as e:
                logger.debug(f"Wallapop: skipped item — {e}")

        time.sleep(1.5)

    logger.info(f"Wallapop: collected {len(listings)} listings")
    return listings
