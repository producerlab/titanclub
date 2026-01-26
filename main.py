from __future__ import annotations
import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import CallbackQuery
from sqlalchemy import select

from config import TELEGRAM_TOKEN, DAILY_REQUEST_LIMIT
from middleware import GroupCheckMiddleware
from database import session_maker, create_db, drop_db, UserState
from keyboards import build_assistant_keyboard, ASSISTANTS
from openai_client import ask_assistant, ask_assistant_file
from rate_limit import check_rate_limit, increment_usage

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

bot = Bot(TELEGRAM_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

dp.message.middleware(GroupCheckMiddleware())


# ======================================================
#            РАБОТА С USER STATE В БД
# ======================================================
async def get_user_assistant(tg_id: int, session) -> str | None:
    """Получить выбранного ассистента из БД"""
    result = await session.execute(
        select(UserState).where(UserState.tg_id == tg_id)
    )
    state = result.scalar_one_or_none()
    return state.assistant_id if state else None


async def set_user_assistant(tg_id: int, assistant_id: str, session) -> None:
    """Сохранить выбранного ассистента в БД"""
    result = await session.execute(
        select(UserState).where(UserState.tg_id == tg_id)
    )
    state = result.scalar_one_or_none()

    if state:
        state.assistant_id = assistant_id
    else:
        state = UserState(tg_id=tg_id, assistant_id=assistant_id)
        session.add(state)

    await session.commit()


# ======================================================
#                   START COMMAND
# ======================================================
@dp.message(CommandStart())
async def start(message: types.Message):
    await message.answer(
        "Привет! 👋\n\nВыберите ассистента:",
        reply_markup=build_assistant_keyboard(None)
    )


# ======================================================
#           ВЫБОР / СМЕНА АССИСТЕНТА
# ======================================================
@dp.callback_query(F.data == "choose_assistant")
async def choose_assistant(cb: CallbackQuery):
    await bot.send_message(
        cb.from_user.id,
        "Выберите ассистента:",
        reply_markup=build_assistant_keyboard(None)
    )
    await cb.answer()


@dp.callback_query(F.data.startswith("set_assistant:"))
async def set_assistant(cb: CallbackQuery):
    tg_id = cb.from_user.id
    assistant_id = cb.data.split(":", 1)[1]

    # Валидация assistant_id
    assistant = ASSISTANTS.get(assistant_id)
    if not assistant:
        await cb.answer("❌ Неизвестный ассистент", show_alert=True)
        return

    async with session_maker() as session:
        await set_user_assistant(tg_id, assistant_id, session)

    await bot.send_message(
        chat_id=cb.from_user.id,
        text=f"🔄 Теперь вы общаетесь с {assistant['emoji']} <b>{assistant['title']}</b>",
        reply_markup=build_assistant_keyboard(assistant_id)
    )

    await cb.answer()


@dp.callback_query(F.data == "noop")
async def noop(cb: CallbackQuery):
    await cb.answer()


@dp.callback_query(F.data == "listmembers")
async def listmembers(cb: CallbackQuery):
    await cb.answer()


# ======================================================
#                   ФАЙЛЫ / ФОТО
# ======================================================
@dp.message(F.photo | F.document)
async def handle_file(message: types.Message):
    tg_id = message.from_user.id

    async with session_maker() as session:
        # Проверяем выбранного ассистента
        assistant_id = await get_user_assistant(tg_id, session)
        if not assistant_id:
            await message.answer(
                "Сначала выберите ассистента:",
                reply_markup=build_assistant_keyboard(None)
            )
            return

        # Валидация assistant_id
        assistant = ASSISTANTS.get(assistant_id)
        if not assistant:
            await message.answer(
                "Выбранный ассистент недоступен. Выберите другого:",
                reply_markup=build_assistant_keyboard(None)
            )
            return

        # Проверяем rate limit
        allowed, current_count, warning = await check_rate_limit(tg_id, session)
        if not allowed:
            await message.answer(
                f"⛔ Вы достигли лимита в {DAILY_REQUEST_LIMIT} запросов на сегодня.\n"
                "Лимит сбросится в полночь. Попробуйте завтра!"
            )
            return

    await bot.send_chat_action(message.chat.id, "upload_photo")

    try:
        # Получаем файл
        file_id = (
            message.photo[-1].file_id
            if message.photo
            else message.document.file_id
        )
        tg_file = await bot.get_file(file_id)
        downloaded = await bot.download_file(tg_file.file_path)

        filename = message.document.file_name if message.document else "image.jpg"
        with open(filename, "wb") as f:
            f.write(downloaded.read())

        # Работа с OpenAI
        async with session_maker() as session:
            # Увеличиваем счётчик использования
            await increment_usage(tg_id, session)

            reply, _ = await ask_assistant_file(
                tg_id=tg_id,
                assistant_id=assistant_id,
                filepath=filename,
                session=session
            )

        # Удаляем временный файл
        if os.path.exists(filename):
            os.remove(filename)

        response_text = f"{assistant['emoji']} <b>{assistant['title']}</b>:\n\n{reply}"

        # Добавляем предупреждение о лимите если есть
        if warning:
            response_text += f"\n\n{warning}"

        await message.answer(
            response_text,
            reply_markup=build_assistant_keyboard(assistant_id)
        )

    except Exception as e:
        logging.error(f"FILE ERROR for user {tg_id}: {e}", exc_info=True)
        await message.answer("⚠ Ошибка обработки файла")


# ======================================================
#                   ТЕКСТОВЫЕ СООБЩЕНИЯ
# ======================================================
@dp.message()
async def handle_message(message: types.Message):
    tg_id = message.from_user.id

    async with session_maker() as session:
        # Проверяем выбранного ассистента
        assistant_id = await get_user_assistant(tg_id, session)
        if not assistant_id:
            await message.answer(
                "Пожалуйста, выберите ассистента:",
                reply_markup=build_assistant_keyboard(None)
            )
            return

        # Валидация assistant_id
        assistant = ASSISTANTS.get(assistant_id)
        if not assistant:
            await message.answer(
                "Выбранный ассистент недоступен. Выберите другого:",
                reply_markup=build_assistant_keyboard(None)
            )
            return

        # Проверяем rate limit
        allowed, current_count, warning = await check_rate_limit(tg_id, session)
        if not allowed:
            await message.answer(
                f"⛔ Вы достигли лимита в {DAILY_REQUEST_LIMIT} запросов на сегодня.\n"
                "Лимит сбросится в полночь. Попробуйте завтра!"
            )
            return

    await bot.send_chat_action(message.chat.id, "typing")

    try:
        async with session_maker() as session:
            # Увеличиваем счётчик использования
            await increment_usage(tg_id, session)

            reply, _ = await ask_assistant(
                tg_id=tg_id,
                assistant_id=assistant_id,
                user_message=message.text,
                session=session
            )

        response_text = f"{assistant['emoji']} <b>{assistant['title']}</b>:\n\n{reply}"

        # Добавляем предупреждение о лимите если есть
        if warning:
            response_text += f"\n\n{warning}"

        await message.answer(
            response_text,
            reply_markup=build_assistant_keyboard(assistant_id)
        )

    except Exception as e:
        logging.error(f"ERROR for user {tg_id}: {e}", exc_info=True)
        await message.answer("⚠ Ошибка обращения к ассистенту")


# ======================================================
#               STARTUP / SHUTDOWN
# ======================================================
async def on_startup(bot: Bot):
    logging.info("Running startup...")
    await create_db()
    logging.info("DB ready")
    logging.info("Bot started")


async def on_shutdown(bot: Bot):
    logging.info("Bot shutting down...")


# ======================================================
#                    MAIN ENTRY
# ======================================================
async def main() -> None:
    logging.info("Starting bot...")

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
