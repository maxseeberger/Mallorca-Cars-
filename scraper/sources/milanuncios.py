"""
Milanuncios scraper — Playwright headless browser.
Increased timeouts and updated selectors for 2025 site version.
"""
import logging
import time
import re
from typing import List
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from ..models import CarListing

logger = logging.getLogger(__name__)

BASE_URL = "https://www.milanuncios.com/coches-de-segunda-mano-en-mallorca/"


def clean_price(text: str) -> int | None:
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


def scrape(max_pages: int = 8) -> List[CarListing]:
    listings: List[CarListing] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="es-ES",
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()

        for page_num in range(1, max_pages + 1):
            url = BASE_URL if page_num == 1 else f"{BASE_URL}?pagina={page_num}"
            logger.info(f"Milanuncios: page {page_num}/{max_pages} — {url}")

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)

                # Accept cookies
                if page_num == 1:
                    for selector in ["#didomi-notice-agree-button", "button[id*='accept']", "button[class*='accept']"]:
                        try:
                            page.click(selector, timeout=3000)
                            break
                        except PWTimeout:
                            continue

                # Try multiple card selectors
                card_selector = None
                for sel in ["article.ma-AdCard", "article[class*='AdCard']", "article[class*='ad-card']", ".ma-AdCard", "li[class*='aditem']"]:
                    try:
                        page.wait_for_selector(sel, timeout=15000)
                        card_selector = sel
                        break
                    except PWTimeout:
                        continue

                if not card_selector:
                    logger.warning(f"Milanuncios: no cards found on page {page_num}")
                    # Log page title to see what we got
                    logger.info(f"Milanuncios: page title = {page.title()}")
                    break

            except PWTimeout:
                logger.warning(f"Milanuncios: timeout on page {page_num}, stopping")
                break

            cards = page.query_selector_all(card_selector)
            logger.info(f"Milanuncios: found {len(cards)} cards on page {page_num}")

            for card in cards:
                try:
                    # Try multiple title selectors
                    title_el = (
                        card.query_selector(".ma-AdCard-titleContainer a")
                        or card.query_selector("a[class*='title']")
                        or card.query_selector("h2 a")
                        or card.query_selector("a[href*='/coches']")
                    )
                    if not title_el:
                        continue

                    title = title_el.inner_text().strip()
                    href = title_el.get_attribute("href") or ""
                    url_ = f"https://www.milanuncios.com{href}" if href.startswith("/") else href
                    id_match = re.search(r"/(\d+)\.htm", href)
                    source_id = id_match.group(1) if id_match else href

                    price_el = (
                        card.query_selector(".ma-AdPrice-value")
                        or card.query_selector("[class*='price']")
                    )

                    specs_els = card.query_selector_all(".ma-AdTagList-item, [class*='tag'], [class*='spec']")
                    year = mileage = fuel = None
                    for s in specs_els:
                        text = s.get_text(strip=True)
                        if re.match(r"^\d{4}$", text):
                            year = int(text)
                        elif "km" in text.lower():
                            raw = re.sub(r"[^\d]", "", text)
                            mileage = int(raw) if raw else None
                        elif text.lower() in ("diésel", "diesel"):
                            fuel = "diesel"
                        elif text.lower() == "gasolina":
                            fuel = "gasoline"
                        elif "híbrido" in text.lower():
                            fuel = "hybrid"
                        elif "eléctrico" in text.lower():
                            fuel = "electric"

                    img_el = card.query_selector("img")
                    loc_el = card.query_selector(".ma-AdLocation-text, [class*='location']")

                    listings.append(CarListing(
                        source="milanuncios",
                        source_id=source_id,
                        title=title,
                        listing_url=url_,
                        price=clean_price(price_el.inner_text()) if price_el else None,
                        year=year,
                        mileage=mileage,
                        fuel=fuel,
                        location=loc_el.inner_text().strip() if loc_el else "Mallorca",
                        image_url=img_el.get_attribute("src") if img_el else None,
                    ))
                except Exception as e:
                    logger.debug(f"Milanuncios: skipped card — {e}")

            time.sleep(2)

        browser.close()

    logger.info(f"Milanuncios: collected {len(listings)} listings")
    return listings
