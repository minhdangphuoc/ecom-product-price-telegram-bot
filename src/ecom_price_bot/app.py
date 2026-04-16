from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from ecom_price_bot.bootstrap import get_dependencies
from ecom_price_bot.charts import render_price_history_chart
from ecom_price_bot.security import verify_chart_token
from ecom_price_bot.telegram.webhook_handler import TelegramWebhookHandler
from ecom_price_bot.telegram.webhook_sync import sync_telegram_webhook


app = FastAPI(title="ecom-price-telegram-bot")
logger = logging.getLogger(__name__)
_webhook_sync_lock = asyncio.Lock()
_webhook_sync_completed = False


async def _ensure_runtime_webhook_sync() -> None:
    global _webhook_sync_completed
    if _webhook_sync_completed:
        return

    async with _webhook_sync_lock:
        if _webhook_sync_completed:
            return

        dependencies = get_dependencies()
        try:
            result = await sync_telegram_webhook(
                dependencies.telegram_bot,
                dependencies.settings,
            )
        except Exception:
            logger.exception("Telegram webhook auto-sync failed.")
            return

        logger.info("Telegram webhook auto-sync result: %s", result)
        _webhook_sync_completed = True


@app.middleware("http")
async def auto_sync_telegram_webhook(request: Request, call_next):
    await _ensure_runtime_webhook_sync()
    return await call_next(request)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> JSONResponse:
    dependencies = get_dependencies()
    expected_secret = dependencies.settings.telegram_webhook_secret
    if expected_secret and x_telegram_bot_api_secret_token != expected_secret:
        raise HTTPException(status_code=403, detail="Invalid Telegram webhook secret.")

    payload = await request.json()
    handler = TelegramWebhookHandler(dependencies)
    await handler.handle_update(payload)
    return JSONResponse({"ok": True})


@app.get("/cron/daily-refresh")
async def daily_refresh(request: Request) -> JSONResponse:
    dependencies = get_dependencies()
    expected_secret = dependencies.settings.cron_secret
    authorization = request.headers.get("authorization", "")
    if expected_secret and authorization != f"Bearer {expected_secret}":
        raise HTTPException(status_code=401, detail="Invalid cron secret.")

    user_agent = request.headers.get("user-agent", "")
    is_vercel_cron = user_agent.lower().startswith("vercel-cron/")
    force_send = True

    logger.info(
        "Daily refresh requested: is_vercel_cron=%s force_send=%s user_agent=%r",
        is_vercel_cron,
        force_send,
        user_agent,
    )

    with dependencies.database.advisory_lock(904215) as locked:
        if not locked:
            logger.info(
                "Daily refresh skipped: force=%s is_vercel_cron=%s reason=%s",
                force_send,
                is_vercel_cron,
                "daily refresh already running",
            )
            return JSONResponse(
                {
                    "ok": True,
                    "skipped": True,
                    "reason": "daily refresh already running",
                    "force": force_send,
                    "is_vercel_cron": is_vercel_cron,
                    "at": datetime.now(tz=UTC).isoformat(),
                }
            )

        handler = TelegramWebhookHandler(dependencies)
        result = await handler.send_daily_reports(force=force_send)
        logger.info(
            "Daily refresh result: force=%s is_vercel_cron=%s targets=%s sent=%s failed=%s",
            force_send,
            is_vercel_cron,
            result["targets"],
            result["sent"],
            result["failed"],
        )
        return JSONResponse(
            {
                "ok": True,
                "force": force_send,
                "is_vercel_cron": is_vercel_cron,
                "targets": result["targets"],
                "sent": result["sent"],
                "failed": result["failed"],
                "at": datetime.now(tz=UTC).isoformat(),
            }
        )


@app.get("/chart")
async def chart(
    telegram_user_id: int,
    watch_id: str,
    sig: str,
) -> Response:
    dependencies = get_dependencies()
    signing_secret = dependencies.settings.chart_signing_secret
    if not signing_secret:
        raise HTTPException(status_code=404, detail="Chart links are disabled.")

    if not verify_chart_token(signing_secret, telegram_user_id, watch_id, sig):
        raise HTTPException(status_code=403, detail="Invalid chart signature.")

    watch = dependencies.watchlist_controller.get_watch(telegram_user_id, watch_id)
    if watch is None:
        raise HTTPException(status_code=404, detail="Watch not found.")

    history = dependencies.watchlist_controller.get_price_history(
        telegram_user_id,
        watch_id,
        limit=180,
    )
    image_bytes = render_price_history_chart(watch, history)
    return Response(content=image_bytes, media_type="image/png")
