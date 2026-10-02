"""Проверка подписи Telegram Mini App (initData) и белого списка пользователей.

https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

from . import config

MAX_AGE_SECONDS = 7 * 24 * 3600


def validate_init_data(init_data: str, bot_token: str) -> dict | None:
    """Возвращает данные пользователя, если подпись верна, иначе None."""
    if not init_data:
        return None
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        return None

    check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received_hash):
        return None

    try:
        if time.time() - int(pairs.get("auth_date", "0")) > MAX_AGE_SECONDS:
            return None
        return json.loads(pairs.get("user", "{}"))
    except ValueError:
        return None


def is_allowed(user_id: int | None) -> bool:
    return user_id is not None and user_id in config.ALLOWED_USER_IDS
