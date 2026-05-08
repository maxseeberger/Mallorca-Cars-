# cochesmallorca.com — scraper

Pulls used car listings from Wallapop, Milanuncios, and Coches.net,
stores them in Supabase. Runs daily via GitHub Actions at 09:00 Mallorca time.

---

## First-time setup (15 min)

### 1. Supabase
1. Create a free project at https://supabase.com
2. Go to **SQL Editor** and paste + run the contents of `schema.sql`
3. Copy your **Project URL** and **service_role key** (Settings → API)

### 2. GitHub repo
1. Push this folder to a new GitHub repo (can be private)
2. Go to **Settings → Secrets and variables → Actions** and add:
   - `SUPABASE_URL`  → your Supabase project URL
   - `SUPABASE_SERVICE_KEY` → your service_role key (not the anon key)

### 3. Test it locally first
```bash
python -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium

export SUPABASE_URL="https://xxxx.supabase.co"
export SUPABASE_SERVICE_KEY="eyJ..."

# Dry run — no DB writes, just check it scrapes
python -m scraper.main --dry-run

# Full run
python -m scraper.main
```

### 4. Trigger first run in GitHub
Go to **Actions → Daily car scraper → Run workflow**

After that it runs automatically every morning.

---

## File structure

```
scraper/
  main.py              # orchestrator — runs all sources
  models.py            # CarListing dataclass
  db.py                # Supabase upsert logic
  sources/
    wallapop.py        # Wallapop API (cleanest, no browser needed)
    milanuncios.py     # Playwright-based (JS-rendered site)
    coches_net.py      # requests + BeautifulSoup
.github/
  workflows/
    scraper.yml        # GitHub Actions cron job
schema.sql             # Run once in Supabase SQL editor
requirements.txt
```

---

## Tuning

| What | Where | Default |
|------|-------|---------|
| Pages per source | `main.py` SOURCES list | 8–10 |
| Scrape schedule | `scraper.yml` cron | `0 7 * * *` |
| Stale threshold | `schema.sql` function | 3 days |
| Mallorca radius | `wallapop.py` distance | 50 km |

---

## Monitoring

GitHub Actions logs show per-source counts after each run.
If a source consistently returns 0, the site likely changed its HTML structure —
check the selectors in `sources/milanuncios.py` or `sources/coches_net.py`.

Wallapop uses a JSON API and is the most stable.

---

## Next step: the Next.js frontend

See the `/frontend` folder (coming next) for the website that reads from Supabase
and displays listings with filters, bilingual routing, and dealer featured slots.
