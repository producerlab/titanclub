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
from keyboards import (
    build_assistant_keyboard, build_assistant_selection_keyboard,
    get_assistant_card, ASSISTANTS
)
from openai_client import ask_assistant, ask_assistant_file, get_thread_history
from rate_limit import check_rate_limit, increment_usage, get_usage_count

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
    safe_name = os.path.basename(original_filename)
    unique_name = f"{uuid.uuid4().hex}_{safe_name}"
    return os.path.join(tempfile.gettempdir(), unique_name)


def format_usage_info(current: int, limit: int) -> str:
    """Форматирует информацию о лимите"""
    remaining = limit - current
    if remaining <= 20:
        return f"⚠️ Осталось запросов: {remaining}/{limit}"
    return f"📊 Запросов: {current}/{limit}"


# ======================================================
#                   START COMMAND
# ======================================================
@dp.message(CommandStart())
async def start(message: types.Message):
    await message.answer(
        "👋 <b>Добро пожаловать в Titan AI!</b>\n\n"
        "Я — ваш помощник для работы с Wildberries.\n"
        "Выберите ассистента для начала работы:",
        reply_markup=build_assistant_keyboard(None)
    )


# ======================================================
#                   HELP COMMAND
# ======================================================
@dp.message(Command("help"))
async def help_command(message: types.Message):
    assistants_list = "\n".join([
        f"{a['emoji']} <b>{a['title']}</b> — {a['desc']}"
        for a in ASSISTANTS.values()
    ])

    await message.answer(
        "<b>🤖 Помощь по боту</b>\n\n"
        "Этот бот предоставляет доступ к AI-ассистентам для резидентов Titan Sellers Club.\n\n"
        "<b>Доступные ассистенты:</b>\n"
        f"{assistants_list}\n\n"
        "<b>Команды:</b>\n"
        "/start — выбрать ассистента\n"
        "/status — показать статус и лимиты\n"
        "/help — показать эту справку\n\n"
        "<b>Как пользоваться:</b>\n"
        "1. Выберите ассистента из списка\n"
        "2. Отправьте текстовое сообщение или файл\n"
        "3. Получите ответ от ассистента\n\n"
        f"<b>Лимиты:</b> {DAILY_REQUEST_LIMIT} запросов в день"
    )


# ======================================================
#                   STATUS COMMAND
# ======================================================
@dp.message(Command("status"))
async def status_command(message: types.Message):
    tg_id = message.from_user.id

    async with session_maker() as session:
        assistant_id = await get_user_assistant(tg_id, session)
        usage = await get_usage_count(tg_id, session)

    assistant_info = "Не выбран"
    if assistant_id and assistant_id in ASSISTANTS:
        a = ASSISTANTS[assistant_id]
        assistant_info = f"{a['emoji']} {a['title']}"

    remaining = DAILY_REQUEST_LIMIT - usage

    await message.answer(
        "<b>📊 Ваш статус</b>\n\n"
        f"<b>Ассистент:</b> {assistant_info}\n"
        f"<b>Запросов сегодня:</b> {usage}\n"
        f"<b>Осталось:</b> {remaining}/{DAILY_REQUEST_LIMIT}\n\n"
        "Лимит сбрасывается в полночь.",
        reply_markup=build_assistant_keyboard(assistant_id)
    )


# ======================================================
#           ВЫБОР / СМЕНА АССИСТЕНТА
# ======================================================
@dp.callback_query(F.data == "choose_assistant")
async def choose_assistant(cb: CallbackQuery):
    await cb.message.edit_text(
        "🔄 <b>Выберите ассистента:</b>\n\n"
        "Каждый ассистент специализируется на своей области:",
        reply_markup=build_assistant_selection_keyboard()
    )
    await cb.answer()


@dp.callback_query(F.data == "cancel_selection")
async def cancel_selection(cb: CallbackQuery):
    tg_id = cb.from_user.id

    async with session_maker() as session:
        assistant_id = await get_user_assistant(tg_id, session)

    if assistant_id:
        await cb.message.edit_text(
            "Выбор отменён. Текущий ассистент сохранён.",
            reply_markup=build_assistant_keyboard(assistant_id)
        )
    else:
        await cb.message.edit_text(
            "Для работы необходимо выбрать ассистента:",
            reply_markup=build_assistant_keyboard(None)
        )
    await cb.answer()


@dp.callback_query(F.data.startswith("set_assistant:"))
async def set_assistant(cb: CallbackQuery):
    tg_id = cb.from_user.id
    assistant_id = cb.data.split(":", 1)[1]

    assistant = ASSISTANTS.get(assistant_id)
    if not assistant:
        await cb.answer("❌ Неизвестный ассистент", show_alert=True)
        return

    async with session_maker() as session:
        await set_user_assistant(tg_id, assistant_id, session)
        usage = await get_usage_count(tg_id, session)

    card_text = get_assistant_card(assistant_id)
    usage_info = format_usage_info(usage, DAILY_REQUEST_LIMIT)

    await cb.message.edit_text(
        f"{card_text}\n\n{usage_info}",
        reply_markup=build_assistant_keyboard(assistant_id)
    )
    await cb.answer()


@dp.callback_query(F.data == "noop")
async def noop(cb: CallbackQuery):
    await cb.answer()


# ======================================================
#                   SHOW STATUS
# ======================================================
@dp.callback_query(F.data == "show_status")
async def show_status(cb: CallbackQuery):
    tg_id = cb.from_user.id

    async with session_maker() as session:
        assistant_id = await get_user_assistant(tg_id, session)
        usage = await get_usage_count(tg_id, session)

    remaining = DAILY_REQUEST_LIMIT - usage

    await cb.answer(
        f"📊 Запросов: {usage}/{DAILY_REQUEST_LIMIT}\nОсталось: {remaining}",
        show_alert=True
    )


# ======================================================
#                   SHOW HISTORY
# ======================================================
@dp.callback_query(F.data == "show_history")
async def show_history(cb: CallbackQuery):
    tg_id = cb.from_user.id

    async with session_maker() as session:
        assistant_id = await get_user_assistant(tg_id, session)

    if not assistant_id:
        await cb.answer("Сначала выберите ассистента", show_alert=True)
        return

    assistant = ASSISTANTS.get(assistant_id)
    if not assistant:
        await cb.answer("Ассистент не найден", show_alert=True)
        return

    try:
        async with session_maker() as session:
            history = await get_thread_history(tg_id, assistant_id, session, limit=5)

        if not history:
            await cb.answer("История пуста. Задайте первый вопрос!", show_alert=True)
            return

        history_text = f"📜 <b>История ({assistant['emoji']} {assistant['title']})</b>\n\n"

        for i, item in enumerate(history, 1):
            role = "👤 Вы" if item["role"] == "user" else f"{assistant['emoji']} Ответ"
            text = item["text"][:200] + "..." if len(item["text"]) > 200 else item["text"]
            history_text += f"<b>{role}:</b>\n{text}\n\n"

        await cb.message.edit_text(
            history_text,
            reply_markup=build_assistant_keyboard(assistant_id)
        )

    except Exception as e:
        logging.error(f"Error getting history: {e}")
        await cb.answer("Не удалось загрузить историю", show_alert=True)

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
        await message.answer(f"⚠️ Файл слишком большой. Максимум {max_mb} MB")
        return

    async with session_maker() as session:
        assistant_id = await get_user_assistant(tg_id, session)
        if not assistant_id:
            await message.answer(
                "Сначала выберите ассистента:",
                reply_markup=build_assistant_keyboard(None)
            )
            return

        assistant = ASSISTANTS.get(assistant_id)
        if not assistant:
            await message.answer(
                "Выбранный ассистент недоступен. Выберите другого:",
                reply_markup=build_assistant_keyboard(None)
            )
            return

        allowed, current_count, _ = await check_rate_limit(tg_id, session)
        if not allowed:
            await message.answer(
                f"⛔ Вы достигли лимита в {DAILY_REQUEST_LIMIT} запросов на сегодня.\n"
                "Лимит сбросится в полночь. Попробуйте завтра!"
            )
            return

    # Отправляем сообщение о загрузке
    loading_msg = await message.answer(
        f"⏳ <b>{assistant['emoji']} {assistant['title']}</b> анализирует файл...\n\n"
        "<i>Обычно это занимает 10-60 секунд</i>"
    )

    original_filename = message.document.file_name if message.document else "image.jpg"
    filepath = get_safe_filepath(original_filename)

    try:
        file_id = (
            message.photo[-1].file_id
            if message.photo
            else message.document.file_id
        )
        tg_file = await bot.get_file(file_id)
        downloaded = await bot.download_file(tg_file.file_path)

        with open(filepath, "wb") as f:
            f.write(downloaded.read())

        async with session_maker() as session:
            await increment_usage(tg_id, session)
            new_count = current_count + 1

            reply, _ = await ask_assistant_file(
                tg_id=tg_id,
                assistant_id=assistant_id,
                filepath=filepath,
                session=session
            )

        usage_info = format_usage_info(new_count, DAILY_REQUEST_LIMIT)
        response_text = f"{assistant['emoji']} <b>{assistant['title']}</b>:\n\n{reply}\n\n{usage_info}"

        await loading_msg.delete()
        await message.answer(
            response_text,
            reply_markup=build_assistant_keyboard(assistant_id)
        )

    except TimeoutError:
        await loading_msg.delete()
        await message.answer(
            "⏱️ Ассистент не успел ответить за отведённое время.\n"
            "Попробуйте повторить запрос или отправить файл меньшего размера.",
            reply_markup=build_assistant_keyboard(assistant_id)
        )

    except Exception as e:
        logging.error(f"FILE ERROR for user {tg_id}: {type(e).__name__}: {e}")
        await loading_msg.delete()
        await message.answer(
            "⚠️ Ошибка обработки файла. Попробуйте ещё раз или обратитесь в поддержку.",
            reply_markup=build_assistant_keyboard(assistant_id)
        )

    finally:
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

    if not message.text:
        return

    async with session_maker() as session:
        assistant_id = await get_user_assistant(tg_id, session)
        if not assistant_id:
            await message.answer(
                "Пожалуйста, выберите ассистента:",
                reply_markup=build_assistant_keyboard(None)
            )
            return

        assistant = ASSISTANTS.get(assistant_id)
        if not assistant:
            await message.answer(
                "Выбранный ассистент недоступен. Выберите другого:",
                reply_markup=build_assistant_keyboard(None)
            )
            return

        allowed, current_count, _ = await check_rate_limit(tg_id, session)
        if not allowed:
            await message.answer(
                f"⛔ Вы достигли лимита в {DAILY_REQUEST_LIMIT} запросов на сегодня.\n"
                "Лимит сбросится в полночь. Попробуйте завтра!"
            )
            return

    # Отправляем сообщение о загрузке
    loading_msg = await message.answer(
        f"⏳ <b>{assistant['emoji']} {assistant['title']}</b> думает...\n\n"
        "<i>Обычно это занимает 5-30 секунд</i>"
    )

    try:
        async with session_maker() as session:
            await increment_usage(tg_id, session)
            new_count = current_count + 1

            reply, _ = await ask_assistant(
                tg_id=tg_id,
                assistant_id=assistant_id,
                user_message=message.text,
                session=session
            )

        usage_info = format_usage_info(new_count, DAILY_REQUEST_LIMIT)
        response_text = f"{assistant['emoji']} <b>{assistant['title']}</b>:\n\n{reply}\n\n{usage_info}"

        await loading_msg.delete()
        await message.answer(
            response_text,
            reply_markup=build_assistant_keyboard(assistant_id)
        )

    except TimeoutError:
        await loading_msg.delete()
        await message.answer(
            "⏱️ Ассистент не успел ответить за отведённое время.\n"
            "Попробуйте повторить запрос или сформулировать вопрос короче.",
            reply_markup=build_assistant_keyboard(assistant_id)
        )

    except Exception as e:
        logging.error(f"ERROR for user {tg_id}: {type(e).__name__}: {e}")
        await loading_msg.delete()
        await message.answer(
            "⚠️ Ошибка обращения к ассистенту. Попробуйте ещё раз.",
            reply_markup=build_assistant_keyboard(assistant_id)
        )


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
