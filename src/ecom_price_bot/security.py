from __future__ import annotations

import hashlib
import hmac


def sign_chart_token(secret: str, telegram_user_id: int, watch_id: str) -> str:
    payload = f"{telegram_user_id}:{watch_id}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def verify_chart_token(
    secret: str,
    telegram_user_id: int,
    watch_id: str,
    signature: str,
) -> bool:
    expected = sign_chart_token(secret, telegram_user_id, watch_id)
    return hmac.compare_digest(expected, signature)
