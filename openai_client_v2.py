"""
OpenAI клиент на базе Responses API (замена Assistants API)
Миграция в связи с deprecation Assistants API (август 2026)
"""
from __future__ import annotations
import logging
import mimetypes
import base64
from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import OPENAI_API_KEY, OPENAI_RUN_TIMEOUT
from database import Conversations

client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# Инструкции ассистентов (экспортированы из OpenAI)
ASSISTANT_INSTRUCTIONS = {
    "asst_ZMDIYhez0iMJ3ZhMScCwREil": """**РОЛЬ:**
Ты — Адвокат клиента и Промпт-Инженер для товарного бизнеса. Твоя задача — собрать информацию о продукте и аудитории клиента, а затем создать идеальный промпт для глубинного исследования болей и потребностей покупателей.

**ВАЖНО:** Ты НЕ проводишь исследование сам. Ты только создаёшь готовый, максимально точный промпт для исследования.

## АЛГОРИТМ РАБОТЫ:
1. Узнай о продукте: "Что ты продаёшь?"
2. Узнай об аудитории (по одному вопросу)
3. Уточни задачу исследования
4. Создай промпт по шаблону

Будь кратким в вопросах. Начинай с вопроса: "Что ты продаёшь?"
""",

    "asst_16FOkKPETrIKCZ4VTn5iMr3J": """Ты — опытный SEO-специалист для Wildberries.

Алгоритм:
1. Спроси: «О каком продукте пишем?»
2. Спроси: «Введите список ключевых слов»
3. Спроси: «Хочешь использовать фразы в прямом вхождении?» (ДА/НЕТ)

Создавай описания:
- Не более 2000 символов
- Ключевые слова не чаще 3 раз
- В конце призыв к действию

Описание лаконичное, ёмкое, ориентировано на преимущества.
""",

    "asst_rYvjemjJPNoTLnraZVFzZsGI": """## РОЛЬ:
Ты — сценарист и контент-ассистент для блогеров и брендов. Создаёшь продающие сценарии для рилсов, сторис и постов.

Твои тексты:
- Цепляют за 2-3 секунды
- Вызывают эмоцию
- Продают через конкретику
- Звучат естественно

## АЛГОРИТМ (по одному вопросу):
1. "Какой товар ты продаёшь?"
2. "Какие сильные стороны товара?"
3. "За счёт чего достигается эффект?"
4. "Кто целевая аудитория?"
5. "Для какой платформы?" (Reels/Stories/Пост)
6. "Какова цель?" (продажа/прогрев/вовлечение)

Начинай с вопроса: "Какой товар ты продаёшь?"
"""
}

# Модели для каждого ассистента
ASSISTANT_MODELS = {
    "asst_ZMDIYhez0iMJ3ZhMScCwREil": "gpt-4.1-mini",  # Адвокат
    "asst_16FOkKPETrIKCZ4VTn5iMr3J": "gpt-4.1-mini",  # SEO Vivaldi
    "asst_rYvjemjJPNoTLnraZVFzZsGI": "gpt-4.1-mini",  # Тарантино
}

# Ассистенты с RAG (пока используют старый API)
RAG_ASSISTANTS = {
    "asst_QfzzLwaL8JHcve4Y80IVKq9E",  # Ящик Пандоры
    "asst_K0TDVlaEvZHvh5bSxjz1iUCe",  # Куратор WB
}


async def get_last_response_id(tg_id: int, assistant_id: str, session: AsyncSession) -> str | None:
    """Получить ID последнего ответа для продолжения диалога"""
    result = await session.execute(
        select(Conversations).where(
            Conversations.tg_id == tg_id,
            Conversations.assistant_id == assistant_id
        )
    )
    conv = result.scalar_one_or_none()
    return conv.last_response_id if conv else None


async def save_response_id(tg_id: int, assistant_id: str, response_id: str, session: AsyncSession) -> None:
    """Сохранить ID ответа для продолжения диалога"""
    result = await session.execute(
        select(Conversations).where(
            Conversations.tg_id == tg_id,
            Conversations.assistant_id == assistant_id
        )
    )
    conv = result.scalar_one_or_none()

    if conv:
        conv.last_response_id = response_id
    else:
        conv = Conversations(
            tg_id=tg_id,
            assistant_id=assistant_id,
            last_response_id=response_id
        )
        session.add(conv)

    await session.commit()


async def ask_assistant_v2(
    tg_id: int,
    assistant_id: str,
    user_message: str,
    session: AsyncSession
) -> tuple[str, str]:
    """
    Отправить сообщение ассистенту через Responses API.
    Возвращает (ответ, response_id)
    """
    # Проверяем, нужен ли старый API (для RAG ассистентов)
    if assistant_id in RAG_ASSISTANTS:
        # Пока используем старый Assistants API для RAG
        from openai_client import ask_assistant
        return await ask_assistant(tg_id, assistant_id, user_message, session)

    # Получаем инструкции и модель
    instructions = ASSISTANT_INSTRUCTIONS.get(assistant_id, "Ты — полезный ассистент.")
    model = ASSISTANT_MODELS.get(assistant_id, "gpt-4.1-mini")

    # Получаем ID предыдущего ответа для продолжения диалога
    previous_response_id = await get_last_response_id(tg_id, assistant_id, session)

    # Формируем запрос
    input_messages = [
        {"role": "system", "content": instructions},
        {"role": "user", "content": user_message}
    ]

    try:
        # Вызываем Responses API
        if previous_response_id:
            response = await client.responses.create(
                model=model,
                input=input_messages,
                previous_response_id=previous_response_id
            )
        else:
            response = await client.responses.create(
                model=model,
                input=input_messages
            )

        # Извлекаем текст ответа
        reply = ""
        for output in response.output:
            if hasattr(output, 'content'):
                for content in output.content:
                    if hasattr(content, 'text'):
                        reply += content.text

        if not reply:
            reply = "Пустой ответ 🤷‍♂️"

        # Сохраняем response_id для продолжения диалога
        await save_response_id(tg_id, assistant_id, response.id, session)

        return reply, response.id

    except Exception as e:
        logging.error(f"Responses API error: {type(e).__name__}: {e}")
        raise


async def ask_assistant_file_v2(
    tg_id: int,
    assistant_id: str,
    filepath: str,
    session: AsyncSession
) -> tuple[str, str]:
    """
    Отправить файл ассистенту через Responses API.
    Возвращает (ответ, response_id)
    """
    # Проверяем, нужен ли старый API (для RAG ассистентов)
    if assistant_id in RAG_ASSISTANTS:
        from openai_client import ask_assistant_file
        return await ask_assistant_file(tg_id, assistant_id, filepath, session)

    # Определяем MIME тип
    mime, _ = mimetypes.guess_type(filepath)
    is_image = mime and mime.startswith("image/")

    instructions = ASSISTANT_INSTRUCTIONS.get(assistant_id, "Ты — полезный ассистент.")
    model = ASSISTANT_MODELS.get(assistant_id, "gpt-4.1-mini")

    previous_response_id = await get_last_response_id(tg_id, assistant_id, session)

    try:
        if is_image:
            # Для изображений — используем base64
            with open(filepath, "rb") as f:
                image_data = base64.b64encode(f.read()).decode("utf-8")

            input_messages = [
                {"role": "system", "content": instructions},
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "Проанализируй это изображение."},
                        {
                            "type": "input_image",
                            "image_url": f"data:{mime};base64,{image_data}"
                        }
                    ]
                }
            ]
        else:
            # Для документов — загружаем файл
            with open(filepath, "rb") as f:
                file = await client.files.create(file=f, purpose="assistants")

            input_messages = [
                {"role": "system", "content": instructions},
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "Проанализируй прикреплённый файл."},
                        {"type": "input_file", "file_id": file.id}
                    ]
                }
            ]

        # Вызываем Responses API
        if previous_response_id:
            response = await client.responses.create(
                model=model,
                input=input_messages,
                previous_response_id=previous_response_id
            )
        else:
            response = await client.responses.create(
                model=model,
                input=input_messages
            )

        # Извлекаем текст ответа
        reply = ""
        for output in response.output:
            if hasattr(output, 'content'):
                for content in output.content:
                    if hasattr(content, 'text'):
                        reply += content.text

        if not reply:
            reply = "Пустой ответ 🤷‍♂️"

        await save_response_id(tg_id, assistant_id, response.id, session)

        return reply, response.id

    except Exception as e:
        logging.error(f"Responses API file error: {type(e).__name__}: {e}")
        raise


async def get_conversation_history_v2(
    tg_id: int,
    assistant_id: str,
    session: AsyncSession,
    limit: int = 5
) -> list[dict]:
    """
    Получить историю диалога через Responses API.
    """
    # Для RAG ассистентов — используем старый API
    if assistant_id in RAG_ASSISTANTS:
        from openai_client import get_thread_history
        return await get_thread_history(tg_id, assistant_id, session, limit)

    last_response_id = await get_last_response_id(tg_id, assistant_id, session)

    if not last_response_id:
        return []

    try:
        # Получаем ответ с историей
        response = await client.responses.retrieve(response_id=last_response_id)

        history = []

        # Извлекаем input (вопросы пользователя)
        if response.input:
            for item in response.input:
                if isinstance(item, dict) and item.get("role") == "user":
                    content = item.get("content", "")
                    if isinstance(content, str):
                        history.append({"role": "user", "text": content})
                    elif isinstance(content, list):
                        text_parts = [c.get("text", "") for c in content if c.get("type") == "input_text"]
                        if text_parts:
                            history.append({"role": "user", "text": " ".join(text_parts)})

        # Извлекаем output (ответы ассистента)
        if response.output:
            for output in response.output:
                if hasattr(output, 'content'):
                    text_parts = []
                    for content in output.content:
                        if hasattr(content, 'text'):
                            text_parts.append(content.text)
                    if text_parts:
                        history.append({"role": "assistant", "text": "\n".join(text_parts)})

        return history[-limit * 2:]

    except Exception as e:
        logging.warning(f"Failed to get conversation history: {e}")
        return []


async def reset_conversation_v2(tg_id: int, assistant_id: str, session: AsyncSession) -> None:
    """Сбросить историю диалога (начать новый)"""
    result = await session.execute(
        select(Conversations).where(
            Conversations.tg_id == tg_id,
            Conversations.assistant_id == assistant_id
        )
    )
    conv = result.scalar_one_or_none()

    if conv:
        conv.last_response_id = None
        await session.commit()
