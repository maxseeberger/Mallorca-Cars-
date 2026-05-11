"""
CochesMallorca.com scraper — the main Mallorca-specific used car aggregator.

Two-pass approach:
  1. Scrape list pages to collect all listing URLs + basic fields.
  2. Fetch each detail page to extract the full photo gallery.

Set fetch_images=False for fast/dry runs where image freshness isn't needed.
"""
import logging
import time
import re
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin
from typing import List, Tuple
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


SKIP_PATTERNS = ["logo", "icon", "placeholder", "sprite", "blank", "whatsapp", "nodisponible", ".gif", "50x50"]


def fetch_gallery_images(url: str) -> List[str]:
    """Fetch all gallery images from a listing detail page."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        images: List[str] = []

        # Try gallery/slider containers first
        for selector in [
            "[class*='gallery'] img", "[class*='slider'] img",
            "[class*='carousel'] img", "[class*='photos'] img",
            "[class*='photo'] img", "[class*='swiper'] img",
            "[class*='galeria'] img", "[class*='fotos'] img",
            "[id*='gallery'] img", "[id*='slider'] img",
        ]:
            imgs = soup.select(selector)
            if imgs:
                for img in imgs:
                    src = img.get("src") or img.get("data-src") or img.get("data-original")
                    if not src:
                        continue
                    src = urljoin(url, src)  # resolve relative → absolute
                    if not any(p in src.lower() for p in SKIP_PATTERNS):
                        images.append(src)
                if images:
                    break

        # Fallback: all reasonably sized images on the page
        if not images:
            for img in soup.find_all("img"):
                src = img.get("src") or img.get("data-src") or img.get("data-original")
                if not src:
                    continue
                src = urljoin(url, src)  # resolve relative → absolute
                if not src.startswith("http"):
                    continue
                if any(p in src.lower() for p in SKIP_PATTERNS):
                    continue
                w, h = img.get("width"), img.get("height")
                if w and h:
                    try:
                        if int(w) < 150 or int(h) < 100:
                            continue
                    except (ValueError, TypeError):
                        pass
                images.append(src)

        # Deduplicate, preserve order, cap at 20
        seen: set = set()
        unique: List[str] = []
        for img in images:
            if img not in seen:
                seen.add(img)
                unique.append(img)
        return unique[:20]

    except Exception as e:
        logger.debug(f"CochesMallorca: could not fetch gallery from {url} — {e}")
        return []


def parse_listing_page(soup: BeautifulSoup) -> List[CarListing]:
    listings = []
    cards = soup.select("a[href*='/stock/']")
    seen_hrefs = set()

    for link in cards:
        href = link.get("href", "")
        if not href or href in seen_hrefs:
            continue
        seen_hrefs.add(href)

        id_match = re.search(r"-(\d{4,})$", href.rstrip("/"))
        if not id_match:
            id_match = re.search(r"-(cl\d+|ps\d+|\d{4,})$", href.rstrip("/"))
        source_id = id_match.group(1) if id_match else href

        title = link.get_text(strip=True)
        if not title or len(title) < 3:
            continue

        url_ = f"https://www.cochesmallorca.com{href}" if href.startswith("/") else href

        container = link.parent
        for _ in range(5):
            if container is None:
                break
            text_content = container.get_text(" ", strip=True)
            if "€" in text_content and ("km" in text_content.lower() or any(f in text_content.lower() for f in FUEL_MAP)):
                break
            container = container.parent

        price = year = mileage = fuel = image_url = None

        if container:
            full_text = container.get_text(" ", strip=True)

            price_match = re.search(r"([\d\.]+)\s*€", full_text)
            if price_match:
                price_str = re.sub(r"\.", "", price_match.group(1))
                try:
                    price = int(price_str)
                    if price > 10_000_000:
                        price = None
                except ValueError:
                    price = None

            year_match = re.search(r"\b(19[9]\d|20[0-3]\d)\b", full_text)
            if year_match:
                year = int(year_match.group(1))

            km_match = re.search(r"([\d\.]+)\s*km", full_text, re.IGNORECASE)
            if km_match:
                km_str = re.sub(r"\.", "", km_match.group(1))
                try:
                    mileage = int(km_str)
                    if mileage > 2_000_000:
                        mileage = None
                except ValueError:
                    mileage = None

            for key, val in FUEL_MAP.items():
                if key in full_text.lower():
                    fuel = val
                    break

            img = container.find("img")
            if img:
                image_url = img.get("src") or img.get("data-src")

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


def scrape(max_pages: int = 15, fetch_images: bool = True) -> List[CarListing]:
    all_listings: List[CarListing] = []

    # Pass 1 — collect listings from all list pages
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

    logger.info(f"CochesMallorca: collected {len(all_listings)} listings from list pages")

    # Pass 2 — enrich each listing with full gallery from detail page (parallel)
    if fetch_images and all_listings:
        logger.info(f"CochesMallorca: fetching gallery images for {len(all_listings)} listings (parallel)…")
        total = len(all_listings)
        completed = 0

        def _fetch(args: Tuple[int, "CarListing"]):
            idx, listing = args
            return idx, fetch_gallery_images(listing.listing_url)

        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {executor.submit(_fetch, (i, l)): i for i, l in enumerate(all_listings)}
            for future in as_completed(futures):
                try:
                    idx, gallery = future.result()
                    if gallery:
                        all_listings[idx].images = gallery
                        all_listings[idx].image_url = gallery[0]
                except Exception as e:
                    logger.debug(f"CochesMallorca: enrichment error — {e}")
                completed += 1
                if completed % 50 == 0:
                    logger.info(f"CochesMallorca: enriched {completed}/{total}")

        logger.info("CochesMallorca: gallery enrichment complete")

    logger.info(f"CochesMallorca: done — {len(all_listings)} total listings")
    return all_listings
