# remates-cr-scraper

Python scraper that ingests property listings into the Remates.cr public catalog.

## What it does

Daily cron (via GitHub Actions, 02:00 Costa Rica time):

1. **Spiders** (parallel): `bcr` (Playwright) and `judicial` (PDF download).
2. **Promote**: validates `raw_listings` with pydantic, upserts to `listings`/`auctions`/`listing_images`.
3. **Enrich**: geocodes new listings, downloads images to R2.
4. **Reconcile**: marks expired listings.

## Local development

```bash
uv sync
uv run playwright install chromium

# Spin up local Postgres + apply migrations
./tests/init_test_db.sh
export DATABASE_URL=postgresql://postgres:test@localhost:5499/remates_test

# Run a spider
uv run python -m remates_scraper.jobs.run_spider bcr

# Run a job
uv run python -m remates_scraper.jobs.run_job promote
```

## Tests

```bash
uv run pytest -v
uv run mypy src/
uv run ruff check src/ tests/
```

## GitHub Actions configuration

After pushing to GitHub, configure these repository secrets (Settings → Secrets and variables → Actions → New repository secret):

| Secret | Value |
|---|---|
| `DATABASE_URL` | Supabase **session pooler** URL (host `pooler.supabase.com`, port 5432). NOT the direct host (IPv6-only). |
| `R2_ACCOUNT_ID` | Cloudflare R2 account ID |
| `R2_ACCESS_KEY_ID` | R2 API token access key |
| `R2_SECRET_ACCESS_KEY` | R2 API token secret |
| `R2_BUCKET` | R2 bucket name (e.g. `remates-images`) |
| `R2_PUBLIC_URL` | Public R2 URL (e.g. `https://cdn.remates.cr` or `https://<id>.r2.dev`) |
| `WEBHOOK_REVALIDATE_URL` | `https://<vercel-domain>/api/revalidate` |
| `WEBHOOK_REVALIDATE_TOKEN` | Same value as the web app's `ADMIN_TOKEN` |

The `scrape` workflow runs daily at 08:00 UTC (02:00 CR). To trigger manually: Actions → scrape → Run workflow.
