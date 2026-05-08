"""
CochesMallorca.com scraper — the main Mallorca-specific used car aggregator.
938+ listings, clean server-rendered HTML, no JS rendering needed.
"""
import logging
import time
import re
import requests
from bs4 import BeautifulSoup
from typing import List
from ..models import CarListing

logger = logging.getLogger(__name__)

BASE_URL = "https://www.cochesmallorca.com/es/coches-segunda-mano/clasificacion/coches-segunda-mano/4/2"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-ES,es;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.cochesmallorca.com/",
}

FUEL_MAP = {
    "benzin": "gasoline", "gasolina": "gasoline", "petrol": "gasoline",
    "diesel": "diesel", "diésel": "diesel",
    "hybrid": "hybrid", "híbrido": "hybrid",
    "elektrisch": "electric", "eléctrico": "electric", "electric": "electric",
    "plug-in": "hybrid",
    "micro-hibrido diesel": "diesel", "micro-hibrido benzin": "gasoline",
}


def get_soup(url: str) -> BeautifulSoup:
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")


def parse_fuel(text: str) -> str | None:
    t = text.lower().strip()
    for key, val in FUEL_MAP.items():
        if key in t:
            return val
    return None


def parse_listing_page(soup: BeautifulSoup) -> List[CarListing]:
    listings = []

    # Each car is in a div/li that contains an image, price, title link, and specs
    # Pattern from the page: image → price → title link → year/fuel/km
    cards = soup.select("a[href*='/stock/']")

    seen_hrefs = set()
    for link in cards:
        href = link.get("href", "")
        if not href or href in seen_hrefs:
            continue
        seen_hrefs.add(href)

        # Extract ID from URL slug (last numeric part)
        id_match = re.search(r"-(\d{4,})$", href.rstrip("/"))
        if not id_match:
            # try alternate pattern like cl3259853
            id_match = re.search(r"-(cl\d+|ps\d+|\d{4,})$", href.rstrip("/"))
        source_id = id_match.group(1) if id_match else href

        title = link.get_text(strip=True)
        if not title or len(title) < 3:
            continue

        url_ = f"https://www.cochesmallorca.com{href}" if href.startswith("/") else href

        # Walk up to parent container to find price and specs
        container = link.parent
        for _ in range(5):  # walk up max 5 levels
            if container is None:
                break
            text_content = container.get_text(" ", strip=True)
            if "€" in text_content and ("km" in text_content.lower() or any(f in text_content.lower() for f in FUEL_MAP)):
                break
            container = container.parent

        price = year = mileage = fuel = image_url = None

        if container:
            full_text = container.get_text(" ", strip=True)

            # Price: number followed by €
            price_match = re.search(r"([\d\.]+)\s*€", full_text)
            if price_match:
                price_str = re.sub(r"\.", "", price_match.group(1))
                try:
                    price = int(price_str)
                    if price > 10_000_000:
                        price = None
                except ValueError:
                    price = None

            # Year: 4-digit number between 1990-2030
            year_match = re.search(r"\b(19[9]\d|20[0-3]\d)\b", full_text)
            if year_match:
                year = int(year_match.group(1))

            # Mileage: number followed by km
            km_match = re.search(r"([\d\.]+)\s*km", full_text, re.IGNORECASE)
            if km_match:
                km_str = re.sub(r"\.", "", km_match.group(1))
                try:
                    mileage = int(km_str)
                    if mileage > 2_000_000:
                        mileage = None
                except ValueError:
                    mileage = None

            # Fuel
            for key, val in FUEL_MAP.items():
                if key in full_text.lower():
                    fuel = val
                    break

            # Image
            img = container.find("img")
            if img:
                image_url = img.get("src") or img.get("data-src")

        # Extract make/model from title (first 1-2 words usually)
        title_parts = title.split()
        make = title_parts[0] if title_parts else None
        model = " ".join(title_parts[1:3]) if len(title_parts) > 1 else None

        listings.append(CarListing(
            source="cochesmallorca",
            source_id=str(source_id),
            title=title,
            listing_url=url_,
            price=price,
            year=year,
            mileage=mileage,
            fuel=fuel,
            make=make,
            model=model,
            location="Mallorca",
            image_url=image_url,
        ))

    return listings


def scrape(max_pages: int = 15) -> List[CarListing]:
    all_listings: List[CarListing] = []

    for page_num in range(1, max_pages + 1):
        url = f"{BASE_URL}?p={page_num}&ordre="
        logger.info(f"CochesMallorca: page {page_num}/{max_pages} — {url}")

        try:
            soup = get_soup(url)
        except requests.HTTPError as e:
            logger.warning(f"CochesMallorca: HTTP error on page {page_num} — {e}")
            break
        except Exception as e:
            logger.warning(f"CochesMallorca: error on page {page_num} — {e}")
            break

        listings = parse_listing_page(soup)
        logger.info(f"CochesMallorca: found {len(listings)} listings on page {page_num}")

        if not listings:
            logger.info("CochesMallorca: no more listings")
            break

        all_listings.extend(listings)
        time.sleep(1.5)

    logger.info(f"CochesMallorca: collected {len(all_listings)} total listings")
    return all_listings
