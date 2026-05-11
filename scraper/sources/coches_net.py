"""
Coches.net scraper — requests + BeautifulSoup.
Filters to Baleares (covers Mallorca, Ibiza, Menorca).

Two-pass approach:
  1. Scrape list pages for basic fields + thumbnail.
  2. Fetch each detail page to extract the full photo gallery.
"""
import logging
import time
import re
import requests
from bs4 import BeautifulSoup
from typing import List
from ..models import CarListing

logger = logging.getLogger(__name__)

BASE_URL = "https://www.coches.net/segunda-mano/"
PARAMS_BASE = {"Provincia": "Baleares", "Orden": "fecha-desc"}
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-ES,es;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.coches.net/",
}

FUEL_MAP = {
    "diésel": "diesel", "diesel": "diesel", "gasolina": "gasoline",
    "híbrido": "hybrid", "eléctrico": "electric", "gas": "gas",
}


def get_soup(url: str, params: dict = None) -> BeautifulSoup:
    r = requests.get(url, params=params, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")


def fetch_gallery_images(url: str) -> List[str]:
    """Fetch all gallery images from a coches.net listing detail page."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        images: List[str] = []

        for selector in [
            "[class*='gallery'] img", "[class*='Gallery'] img",
            "[class*='slider'] img", "[class*='carousel'] img",
            "[class*='photos'] img", "[class*='photo'] img",
            "[class*='swiper'] img", "[class*='mt-Gallery'] img",
            "[class*='c-gallery'] img", "[class*='DetailGallery'] img",
        ]:
            imgs = soup.select(selector)
            if imgs:
                for img in imgs:
                    src = img.get("data-src") or img.get("src") or img.get("data-original")
                    if src and src.startswith("http") and "placeholder" not in src.lower():
                        images.append(src)
                if images:
                    break

        if not images:
            for img in soup.find_all("img"):
                src = img.get("data-src") or img.get("src")
                if not src or not src.startswith("http"):
                    continue
                if any(x in src.lower() for x in ["logo", "icon", "placeholder", "sprite", "blank", "avatar"]):
                    continue
                w, h = img.get("width"), img.get("height")
                if w and h:
                    try:
                        if int(w) < 150 or int(h) < 100:
                            continue
                    except (ValueError, TypeError):
                        pass
                images.append(src)

        seen: set = set()
        unique: List[str] = []
        for img in images:
            if img not in seen:
                seen.add(img)
                unique.append(img)
        return unique[:20]

    except Exception as e:
        logger.debug(f"Coches.net: could not fetch gallery from {url} — {e}")
        return []


def parse_card(card) -> CarListing | None:
    try:
        title_el = (
            card.select_one("a.mt-CardBasic-title")
            or card.select_one("a.c-title")
            or card.select_one("h2 a")
            or card.select_one("a[class*='title']")
            or card.select_one("a[class*='Title']")
        )
        if not title_el:
            return None

        title = title_el.get_text(strip=True)
        href = title_el.get("href", "")
        url_ = f"https://www.coches.net{href}" if href.startswith("/") else href
        id_match = re.search(r"-(\d+)/?$", href)
        source_id = id_match.group(1) if id_match else href

        price_el = (
            card.select_one(".mt-CardBasic-price")
            or card.select_one(".c-price__value")
            or card.select_one("[class*='price']")
            or card.select_one("[class*='Price']")
        )
        price_text = price_el.get_text(strip=True) if price_el else ""
        price = int(re.sub(r"[^\d]", "", price_text)) if price_text else None

        specs = card.select(".mt-CardBasicInfo-feature, .c-tags__item, [class*='feature'], [class*='tag']")
        year = mileage = fuel = None
        for s in specs:
            text = s.get_text(strip=True)
            if re.match(r"^\d{4}$", text):
                year = int(text)
            elif "km" in text.lower():
                raw = re.sub(r"[^\d]", "", text)
                mileage = int(raw) if raw else None
            else:
                fl = text.lower()
                for key, val in FUEL_MAP.items():
                    if key in fl:
                        fuel = val
                        break

        img_el = card.select_one("img")
        img_url = (img_el.get("data-src") or img_el.get("src")) if img_el else None

        loc_el = (
            card.select_one(".mt-CardBasic-location")
            or card.select_one(".c-location")
            or card.select_one("[class*='location']")
        )
        location = loc_el.get_text(strip=True) if loc_el else "Baleares"

        return CarListing(
            source="coches_net", source_id=source_id, title=title,
            listing_url=url_, price=price, year=year, mileage=mileage,
            fuel=fuel, location=location, image_url=img_url,
        )
    except Exception as e:
        logger.debug(f"Coches.net: failed to parse card — {e}")
        return None


def scrape(max_pages: int = 8, fetch_images: bool = True) -> List[CarListing]:
    listings: List[CarListing] = []

    # Pass 1 — collect listings from list pages
    for page_num in range(1, max_pages + 1):
        params = {**PARAMS_BASE, "pg": page_num}
        logger.info(f"Coches.net: page {page_num}/{max_pages}")
        try:
            soup = get_soup(BASE_URL, params=params)
        except requests.HTTPError as e:
            logger.warning(f"Coches.net: HTTP error page {page_num} — {e}")
            break

        cards = (
            soup.select("article.mt-CardBasic")
            or soup.select("article.c-card")
            or soup.select("article[class*='Card']")
            or soup.select("li[class*='card']")
            or soup.select("[class*='CardBasic']")
        )

        logger.info(f"Coches.net: found {len(cards)} cards on page {page_num}")
        if not cards:
            logger.info("Coches.net: no more cards")
            break

        for card in cards:
            result = parse_card(card)
            if result:
                listings.append(result)

        time.sleep(1.5)

    logger.info(f"Coches.net: collected {len(listings)} listings from list pages")

    # Pass 2 — enrich with full gallery images
    if fetch_images and listings:
        logger.info(f"Coches.net: fetching gallery images for {len(listings)} listings…")
        for i, listing in enumerate(listings):
            gallery = fetch_gallery_images(listing.listing_url)
            if gallery:
                listing.images = gallery
                listing.image_url = gallery[0]
            if (i + 1) % 20 == 0:
                logger.info(f"Coches.net: enriched {i + 1}/{len(listings)}")
            time.sleep(0.5)
        logger.info("Coches.net: gallery enrichment complete")

    logger.info(f"Coches.net: done — {len(listings)} total listings")
    return listings
