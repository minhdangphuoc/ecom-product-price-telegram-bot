# E-commerce Product Price Telegram Bot

Telegram bot for:

- User-specific product watch lists
- Daily price refresh on supported vendors
- Persistent price history in Supabase Postgres
- Discount discovery from official vendor pages
- On-demand price chart images in Telegram
- Vercel deployment with webhook and cron endpoints

Built-in vendors:

- Zalando
- Boozt
- Booztlet
- Lyko
- Notino
- Prisma

## Hosting shape

This repo is now designed for:

- `Vercel` for Python HTTP functions
- `Supabase` for Postgres storage
- `Telegram webhook` for incoming bot updates
- `Vercel Cron` for periodic daily refresh checks

The bot no longer depends on a long-running polling worker.

## Architecture

```mermaid
flowchart TD
    TG["Telegram"] --> WEBHOOK["Vercel Webhook Endpoint"]
    CRON["Vercel Cron"] --> DAILY["Daily Refresh Endpoint"]
    WEBHOOK --> CTRL["Controllers"]
    DAILY --> CTRL
    CTRL --> DB["Supabase Postgres"]
    CTRL --> REG["Vendor Registry"]
    REG --> GV["Generic Vendor Interface"]
    GV --> Z["Zalando Adapter"]
    GV --> B["Boozt Adapter"]
    GV --> BL["Booztlet Adapter"]
    GV --> L["Lyko Adapter"]
    GV --> N["Notino Adapter"]
    GV --> P["Prisma Adapter"]
    GV --> ADDON["Addon Vendor Modules"]
    CTRL --> CHART["PNG Chart Renderer"]
    CHART --> TG
```

More detail: [docs/ARCHITECTURE.md](/C:/WORK/SideQuests/ecom-product-price-telegram-bot/docs/ARCHITECTURE.md)

## Features

- Stores Telegram user information
- Keeps a separate watch list for each Telegram user
- Saves price history for each watched product
- Returns chart images with `/chart <id>`
- Provides a signed chart URL when `APP_BASE_URL` is configured
- Uses Supabase SQL migrations in [supabase/migrations](/C:/WORK/SideQuests/ecom-product-price-telegram-bot/supabase/migrations)

## Routes

When deployed to Vercel, these endpoints are exposed through `api/index.py`:

- `POST /telegram/webhook`
- `GET /cron/daily-refresh`
- `GET /chart`
- `GET /health`

## Telegram commands

- `/watch <url>`: add a watched product for the current Telegram user
- `/add <url>`: alias for `/watch`
- `/list`: list only your watched products
- `/remove <id|url>`: remove one of your watched products
- `/refresh`: refresh your watches and relevant discounts now
- `/discounts`: refresh discount discovery for vendors you watch
- `/chart <id>`: send a PNG chart of saved price history
- `/help`: show the command list

## Setup

1. Create a Supabase project.
2. Apply the migration in [20260415013000_init_price_bot.sql](/C:/WORK/SideQuests/ecom-product-price-telegram-bot/supabase/migrations/20260415013000_init_price_bot.sql).
3. Create a Vercel project and deploy this repo.
4. Configure environment variables from `.env.example`.
5. Set the Telegram webhook to `https://<your-domain>/telegram/webhook`.
6. Optionally set the Telegram webhook secret header token.

If `APP_BASE_URL` is set to your deployed public domain, the app also auto-syncs
the Telegram webhook to `<APP_BASE_URL>/telegram/webhook` on runtime startup.

Local run:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
Copy-Item .env.example .env
python -m ecom_price_bot.main
```

That starts a local FastAPI server on `http://127.0.0.1:8000`.

## Environment variables

```env
TELEGRAM_BOT_TOKEN=replace-me
TELEGRAM_ALLOWED_USER_IDS=
TELEGRAM_WEBHOOK_SECRET=replace-me
TELEGRAM_DAILY_TIME=09:00
DAILY_REFRESH_WINDOW_MINUTES=20
TIMEZONE=America/Los_Angeles
SUPABASE_DB_URL=postgresql://postgres.your-project:password@aws-0-region.pooler.supabase.com:6543/postgres
APP_BASE_URL=https://your-project.vercel.app
CRON_SECRET=replace-me
CHART_SIGNING_SECRET=replace-me
VENDOR_ADDON_MODULES=
```

## Vercel config

[vercel.json](/C:/WORK/SideQuests/ecom-product-price-telegram-bot/vercel.json) includes:

- the Vercel schema config
- a daily cron schedule for `/cron/daily-refresh`

The app computes each user’s local due time from `TIMEZONE` and `TELEGRAM_DAILY_TIME`, so cron can stay in UTC while user-facing notifications still follow local time.
The cron endpoint also uses a Postgres advisory lock to avoid overlapping runs.

Important:

- A 15-minute Vercel cron schedule is suitable when your Vercel plan supports that frequency.
- On Hobby, the daily cron may run later within the scheduled hour, so the bot sends the first run after the configured local time for that date.
- If you are on a plan with fewer cron runs, keep the endpoint and trigger it from another scheduler instead of changing the core app logic.

## Data model

Main tables:

- `telegram_users`
- `watched_products`
- `price_snapshots`
- `discount_snapshots`

Each watched product belongs to one Telegram user, so every user gets an isolated list and isolated history.

## Notes

- Product parsing still prefers JSON-LD and metadata before falling back to visible text.
- Discount crawling is best-effort because many stores do not expose structured coupon feeds.
- Zalando may still return anti-bot protection pages depending on network/session context.
- Lyko, Notino, and Prisma product pages currently parse with the shared generic product extractor.
- The chart endpoint is signed with `CHART_SIGNING_SECRET` so product history URLs are not guessable.
