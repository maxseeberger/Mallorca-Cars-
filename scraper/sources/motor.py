"""
Motor.es scraper — requests + BeautifulSoup.
Filters to Baleares: https://www.motor.es/segunda-mano/baleares/?pg=N
~448 listings, 24 per page (~19 pages).

Each article element contains:
  - Title in the `title` attribute of a link
  - Listing URL base64-encoded in `data-goto`
  - Images as a JSON array in `data-miniaturas` (or within a hidden input)
  - Specs (year, fuel, km) in <li> elements
  - Price in text
"""
import logging
import time
import re
import json
import base64
import requests
from bs4 import BeautifulSoup
from typing import List
from ..models import CarListing

logger = logging.getLogger(__name__)

BASE_URL = "https://www.motor.es/segunda-mano/baleares/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-ES,es;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.motor.es/",
}

FUEL_MAP = {
    "gasolina": "gasoline", "diesel": "diesel", "diésel": "diesel",
    "híbrido": "hybrid", "eléctrico": "electric", "gas": "gas",
    "glp": "gas", "gnc": "gas",
}

# motor.es uses /image/s/235w157h/ thumbnails; upgrade to /image/s/800w535h/
IMG_THUMB_RE = re.compile(r"/image/s/\d+w\d+h/")


def _upgrade_img(url: str) -> str:
    return IMG_THUMB_RE.sub("/image/s/800w535h/", url)


def _parse_price(text: str) -> int | None:
    digits = re.sub(r"[^\d]", "", text)
    try:
        v = int(digits)
        return v if 500 < v < 5_000_000 else None
    except (ValueError, TypeError):
        return None


def _parse_article(article) -> CarListing | None:
    try:
        # Source ID from data-id attribute on the span
        data_id = article.select_one("[data-id]")
        source_id = data_id["data-id"] if data_id else None
        if not source_id:
            return None

        # Listing URL: base64-encoded in data-goto
        goto_el = article.select_one("[data-goto]")
        if goto_el:
            try:
                listing_url = base64.b64decode(goto_el["data-goto"]).decode("utf-8")
            except Exception:
                listing_url = f"https://www.motor.es/segunda-mano/anuncio/{source_id}/"
        else:
            listing_url = f"https://www.motor.es/segunda-mano/anuncio/{source_id}/"

        # Title
        title_el = article.select_one("[title]")
        title = title_el["title"].strip() if title_el else f"Car {source_id}"

        # Make/model from title (first two words)
        title_parts = title.split()
        make = title_parts[0] if title_parts else None
        model = title_parts[1] if len(title_parts) > 1 else None

        # Price
        price_el = article.select_one(".precio-anuncio, .precio, [class*='precio']")
        price = _parse_price(price_el.get_text()) if price_el else None
        if price is None:
            # Fallback: find first price-like text in article
            price_m = re.search(r"([\d\.]+)\s*€", article.get_text())
            if price_m:
                price = _parse_price(price_m.group(1))

        # Specs from <li> elements: year, fuel, km
        year = mileage = fuel = None
        for li in article.select("li"):
            text = li.get_text(strip=True)
            if re.match(r"^\d{4}$", text):
                year = int(text)
            elif re.search(r"km", text, re.IGNORECASE):
                km_digits = re.sub(r"[^\d]", "", text)
                try:
                    v = int(km_digits)
                    mileage = v if v < 2_000_000 else None
                except (ValueError, TypeError):
                    pass
            else:
                fl = text.lower()
                for key, val in FUEL_MAP.items():
                    if key in fl:
                        fuel = val
                        break

        # Images: JSON array in data-miniaturas or hidden input
        images: List[str] = []
        miniatures_input = article.select_one("input.miniaturas-data")
        if miniatures_input:
            try:
                raw = miniatures_input.get("value", "[]")
                # value may be HTML-escaped; BeautifulSoup handles that
                urls = json.loads(raw)
                images = [_upgrade_img(u) for u in urls if isinstance(u, str) and u.startswith("http")]
            except Exception:
                pass

        # Fallback: img tags
        if not images:
            for img in article.select("img[src]"):
                src = img.get("src", "")
                if src.startswith("http") and "cdn-images.motor.es" in src:
                    images.append(_upgrade_img(src))

        image_url = images[0] if images else None

        return CarListing(
            source="motor_es",
            source_id=str(source_id),
            title=title,
            listing_url=listing_url,
            price=price,
            year=year,
            mileage=mileage,
            fuel=fuel,
            make=make,
            model=model,
            location="Baleares",
            image_url=image_url,
            images=images,
        )
    except Exception as e:
        logger.debug(f"Motor.es: failed to parse article — {e}")
        return None


def scrape(max_pages: int = 22) -> List[CarListing]:
    """
    Scrape up to max_pages pages from motor.es Baleares search.
    ~22 listings per page × 21 pages = ~462 listings total.
    Pagination uses ?pagina=N (not ?pg=N).
    """
    listings: List[CarListing] = []
    seen_ids: set = set()

    for page_num in range(1, max_pages + 1):
        url = BASE_URL
        params = {"pagina": page_num} if page_num > 1 else {}
        logger.info(f"Motor.es: page {page_num}/{max_pages}")
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=20)
            r.raise_for_status()
        except requests.HTTPError as e:
            logger.warning(f"Motor.es: HTTP error on page {page_num} — {e}")
            break
        except Exception as e:
            logger.warning(f"Motor.es: request error on page {page_num} — {e}")
            break

        soup = BeautifulSoup(r.text, "html.parser")
        articles = soup.select("article")

        logger.info(f"Motor.es: {len(articles)} articles on page {page_num}")
        if not articles:
            logger.info("Motor.es: no articles, stopping")
            break

        new_on_page = 0
        for article in articles:
            listing = _parse_article(article)
            if listing and listing.source_id not in seen_ids:
                seen_ids.add(listing.source_id)
                listings.append(listing)
                new_on_page += 1

        if new_on_page == 0:
            logger.info("Motor.es: no new listings on page, stopping")
            break

        time.sleep(1.5)

    logger.info(f"Motor.es: done — {len(listings)} listings collected")
    return listings
