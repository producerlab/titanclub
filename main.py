from __future__ import annotations
import asyncio
import logging
import os
import uuid
import tempfile
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import CallbackQuery
from sqlalchemy import select

from config import (
    TELEGRAM_TOKEN, DAILY_REQUEST_LIMIT, MAX_FILE_SIZE, ADMIN_IDS
)
from middleware import GroupCheckMiddleware, CallbackGroupCheckMiddleware
from database import session_maker, create_db, drop_db, UserState
from keyboards import build_assistant_keyboard, ASSISTANTS
from openai_client import ask_assistant, ask_assistant_file
from rate_limit import check_rate_limit, increment_usage

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

bot = Bot(TELEGRAM_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# Защита и message, и callback_query
dp.message.middleware(GroupCheckMiddleware())
dp.callback_query.middleware(CallbackGroupCheckMiddleware())


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


def get_safe_filepath(original_filename: str) -> str:
    """Генерирует безопасный путь для временного файла"""
    # Берём только имя файла без пути (защита от path traversal)
    safe_name = os.path.basename(original_filename)
    # Добавляем уникальный префикс
    unique_name = f"{uuid.uuid4().hex}_{safe_name}"
    # Используем системную временную директорию
    return os.path.join(tempfile.gettempdir(), unique_name)


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
#                   HELP COMMAND
# ======================================================
@dp.message(Command("help"))
async def help_command(message: types.Message):
    await message.answer(
        "<b>🤖 Помощь по боту</b>\n\n"
        "Этот бот предоставляет доступ к AI-ассистентам для резидентов Titan Sellers Club.\n\n"
        "<b>Команды:</b>\n"
        "/start — выбрать ассистента\n"
        "/help — показать эту справку\n\n"
        "<b>Как пользоваться:</b>\n"
        "1. Выберите ассистента из списка\n"
        "2. Отправьте текстовое сообщение или файл\n"
        "3. Получите ответ от ассистента\n\n"
        f"<b>Лимиты:</b> {DAILY_REQUEST_LIMIT} запросов в день"
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

    # Проверка размера файла
    file_size = 0
    if message.photo:
        file_size = message.photo[-1].file_size or 0
    elif message.document:
        file_size = message.document.file_size or 0

    if file_size > MAX_FILE_SIZE:
        max_mb = MAX_FILE_SIZE // (1024 * 1024)
        await message.answer(f"⚠ Файл слишком большой. Максимум {max_mb} MB")
        return

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

    # Безопасное имя файла
    original_filename = message.document.file_name if message.document else "image.jpg"
    filepath = get_safe_filepath(original_filename)

    try:
        # Получаем файл
        file_id = (
            message.photo[-1].file_id
            if message.photo
            else message.document.file_id
        )
        tg_file = await bot.get_file(file_id)
        downloaded = await bot.download_file(tg_file.file_path)

        with open(filepath, "wb") as f:
            f.write(downloaded.read())

        # Работа с OpenAI
        async with session_maker() as session:
            # Увеличиваем счётчик использования
            await increment_usage(tg_id, session)

            reply, _ = await ask_assistant_file(
                tg_id=tg_id,
                assistant_id=assistant_id,
                filepath=filepath,
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
        logging.error(f"FILE ERROR for user {tg_id}: {type(e).__name__}: {e}")
        await message.answer("⚠ Ошибка обработки файла")

    finally:
        # Гарантированно удаляем временный файл
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except OSError:
                pass


# ======================================================
#                   ТЕКСТОВЫЕ СООБЩЕНИЯ
# ======================================================
@dp.message()
async def handle_message(message: types.Message):
    tg_id = message.from_user.id

    # Игнорируем пустые сообщения
    if not message.text:
        return

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
        logging.error(f"ERROR for user {tg_id}: {type(e).__name__}: {e}")
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
