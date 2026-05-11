"""
Main scraper entry point.
"""
import argparse
import logging
import sys
from .sources import cochesmallorca, coches_net, wallapop, autoscout24, motor
from . import db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("main")

SOURCES = [
    ("CochesMallorca", cochesmallorca.scrape, {"max_pages": 15}),
    ("Coches.net",     coches_net.scrape,     {"max_pages": 8}),
    ("AutoScout24",    autoscout24.scrape,    {"max_pages": 40}),
    ("Motor.es",       motor.scrape,          {"max_pages": 20}),
    ("Wallapop",       wallapop.scrape,       {"max_pages": 10}),
]


def run(dry_run: bool = False):
    all_listings = []

    for name, scrape_fn, kwargs in SOURCES:
        logger.info(f"--- Starting {name} ---")
        try:
            results = scrape_fn(**kwargs)
            all_listings.extend(results)
            logger.info(f"{name}: {len(results)} listings scraped")
        except Exception as e:
            logger.error(f"{name}: FAILED — {e}", exc_info=True)

    logger.info(f"Total listings collected: {len(all_listings)}")

    if dry_run:
        logger.info("Dry run — skipping database write")
        for l in all_listings[:5]:
            logger.info(f"  Sample: {l.title} | {l.price}€ | {l.source}")
        return

    saved = db.upsert_listings(all_listings)
    logger.info(f"Saved/updated {saved} rows in Supabase")
    db.deactivate_stale()
    logger.info("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
