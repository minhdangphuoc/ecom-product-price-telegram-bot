# Architecture

## Deployment model

The app is built for a serverless deployment:

- Telegram sends updates to a webhook endpoint on Vercel
- Vercel invokes Python code in `api/index.py`
- Supabase Postgres stores users, watch lists, prices, and discounts
- Vercel Cron triggers the daily refresh endpoint every 15 minutes
- The app decides which users are actually due based on timezone and last sent date

## Layers

### Layer 1: Services

Each vendor adapter implements the same contract:

- `fetch_product(url) -> Product`
- `fetch_discounts() -> list[Discount]`

Shared responsibilities:

- Browser-like HTTP fetching
- JSON-LD parsing
- HTML metadata parsing
- Promo text extraction

Built-in vendors:

- `zalando`
- `boozt`
- `booztlet`
- `lyko`
- `notino`

Addon vendors can be loaded through `VENDOR_ADDON_MODULES`.

### Layer 2: Controllers

Controllers coordinate vendor fetches with stored users and watches:

- `WatchlistController`
- `MonitoringController`

Responsibilities:

- Detect vendor by URL
- Add or remove a watch for one Telegram user
- Refresh one user’s product list
- Collect discounts
- Build per-user daily reports
- Decide which users are due for a daily message

### Layer 3: Communication

FastAPI endpoints replace the old long-running polling process:

- `/telegram/webhook`
- `/cron/daily-refresh`
- `/chart`
- `/health`

The webhook handler:

- syncs Telegram user info into the database
- parses commands
- returns watch lists only for that user
- generates and sends price charts on demand

## Data model

### TelegramUser

- `telegram_user_id`
- `chat_id`
- `username`
- `first_name`
- `last_name`
- `language_code`
- `timezone`
- `last_daily_report_on`

### WatchingProduct

- `id`
- `telegram_user_id`
- `name`
- `url`
- `vendor_id`
- `active`

### PriceSnapshot

- `watching_product_id`
- `observed_at`
- `product_name`
- `product_price`
- `currency`
- `in_stock`

### Discount

- `vendor_id`
- `code`
- `condition`
- `source_url`

## Request flow

```mermaid
sequenceDiagram
    participant User
    participant TG as Telegram
    participant WH as Webhook Endpoint
    participant CTRL as Controllers
    participant REG as Vendor Registry
    participant VEN as Vendor Adapter
    participant DB as Supabase Postgres

    User->>TG: /watch <product-url>
    TG->>WH: webhook POST
    WH->>DB: upsert telegram user
    WH->>CTRL: add_watch(user_id, url)
    CTRL->>REG: get_by_url(url)
    REG->>VEN: matching adapter
    CTRL->>VEN: fetch_product(url)
    VEN-->>CTRL: Product
    CTRL->>DB: upsert watched product
    CTRL->>DB: save first snapshot
    CTRL-->>WH: PriceUpdate
    WH-->>TG: send reply
```

## Daily refresh flow

```mermaid
sequenceDiagram
    participant Cron as Vercel Cron
    participant API as Daily Refresh Endpoint
    participant CTRL as MonitoringController
    participant DB as Supabase Postgres
    participant VEN as Vendor Adapters
    participant TG as Telegram

    Cron->>API: GET /cron/daily-refresh
    API->>CTRL: list_due_users()
    CTRL->>DB: query active users with watches
    API->>CTRL: collect_discounts()
    loop each vendor
        CTRL->>VEN: fetch_discounts()
        VEN-->>CTRL: discounts
        CTRL->>DB: save new discounts
    end
    loop each due user
        CTRL->>DB: list user's watches
        loop each watch
            CTRL->>VEN: fetch_product(url)
            VEN-->>CTRL: Product
            CTRL->>DB: save snapshot
        end
        CTRL->>DB: load today's discounts for watched vendors
        API->>TG: send report
        API->>DB: mark daily report sent
    end
```

## Chart flow

```mermaid
sequenceDiagram
    participant User
    participant TG as Telegram
    participant WH as Webhook
    participant DB as Supabase
    participant CH as Chart Renderer

    User->>TG: /chart 12
    TG->>WH: webhook POST
    WH->>DB: load watch + price history
    WH->>CH: render PNG in memory
    CH-->>WH: image bytes
    WH-->>TG: send photo
```
