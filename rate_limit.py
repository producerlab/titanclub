from __future__ import annotations
from datetime import date
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import DAILY_REQUEST_LIMIT, RATE_LIMIT_WARNING_THRESHOLD
from database import UsageLog


async def get_usage_count(tg_id: int, session: AsyncSession) -> int:
    """Получить количество запросов пользователя за сегодня"""
    today = date.today()
    result = await session.execute(
        select(UsageLog).where(
            UsageLog.tg_id == tg_id,
            UsageLog.usage_date == today
        )
    )
    usage = result.scalar_one_or_none()
    return usage.request_count if usage else 0


async def increment_usage(tg_id: int, session: AsyncSession) -> int:
    """Увеличить счётчик запросов и вернуть новое значение"""
    today = date.today()
    result = await session.execute(
        select(UsageLog).where(
            UsageLog.tg_id == tg_id,
            UsageLog.usage_date == today
        )
    )
    usage = result.scalar_one_or_none()

    if usage:
        usage.request_count += 1
    else:
        usage = UsageLog(tg_id=tg_id, usage_date=today, request_count=1)
        session.add(usage)

    await session.commit()
    return usage.request_count


async def check_rate_limit(tg_id: int, session: AsyncSession) -> tuple[bool, int, str | None]:
    """
    Проверить лимит запросов.

    Возвращает:
        - allowed: можно ли делать запрос
        - current_count: текущее количество запросов
        - warning_message: предупреждение (если приближается к лимиту)
    """
    current_count = await get_usage_count(tg_id, session)

    if current_count >= DAILY_REQUEST_LIMIT:
        return False, current_count, None

    warning_message = None
    if current_count >= RATE_LIMIT_WARNING_THRESHOLD:
        remaining = DAILY_REQUEST_LIMIT - current_count
        warning_message = f"⚠️ Внимание: осталось {remaining} запросов из {DAILY_REQUEST_LIMIT} на сегодня"

    return True, current_count, warning_message
