from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings

# Лимитер ограничивает запросы по IP клиента
limiter = Limiter(key_func=get_remote_address, default_limits=[])

# Лимит применяется только к POST /bookings; вынесен в константу,
# чтобы легко переопределить через .env.
CREATE_LIMIT = settings.rate_limit_create
