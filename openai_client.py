import asyncio
import logging
import mimetypes
from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import OPENAI_API_KEY
from database import Threads

client = AsyncOpenAI(api_key=OPENAI_API_KEY)


async def get_or_create_thread(tg_id: int, assistant_id: str, session: AsyncSession) -> str:
    result = await session.execute(
        select(Threads).where(
            Threads.tg_id == tg_id,
            Threads.assistant_id == assistant_id
        )
    )
    thread = result.scalar_one_or_none()

    if thread:
        return thread.thread_id

    # Создаём новый THREAD в OpenAI
    new_thread = await client.beta.threads.create()
    thread_id = new_thread.id

    # Записываем в БД
    session.add(Threads(
        tg_id=tg_id,
        assistant_id=assistant_id,
        thread_id=thread_id
    ))
    await session.commit()

    return thread_id


async def ask_assistant(tg_id, assistant_id, user_message, session):
    # получаем или создаём thread
    thread_id = await get_or_create_thread(tg_id, assistant_id, session)

    # === 1. Проверяем, есть ли активные run ===
    active_runs = await client.beta.threads.runs.list(thread_id=thread_id)
    for run in active_runs.data:
        if run.status in ("queued", "in_progress", "requires_action"):
            # ждём завершения
            for _ in range(60):
                run = await client.beta.threads.runs.retrieve(
                    thread_id=thread_id,
                    run_id=run.id
                )
                if run.status == "completed":
                    break
                await asyncio.sleep(1)

            # если всё ещё активен — отменяем
            if run.status not in ("completed", "failed", "cancelled"):
                try:
                    await client.beta.threads.runs.cancel(
                        thread_id=thread_id, run_id=run.id
                    )
                except Exception as e:
                    logging.warning(f"Failed to cancel run {run.id}: {e}")

    # === 2. Теперь можно добавлять сообщение ===
    await client.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=[{"type": "text", "text": user_message}],
    )

    # === 3. Создаём новый run ===
    run = await client.beta.threads.runs.create(
        thread_id=thread_id,
        assistant_id=assistant_id,
    )

    # === 4. Ждём выполнения ===
    for _ in range(120):
        run = await client.beta.threads.runs.retrieve(
            thread_id=thread_id,
            run_id=run.id,
        )
        if run.status == "completed":
            break
        if run.status in ("failed", "cancelled", "expired"):
            raise RuntimeError(f"Run failed: {run.last_error}")
        await asyncio.sleep(1)

    # === 5. Получаем последний ответ ===
    messages = await client.beta.threads.messages.list(
        thread_id=thread_id,
        limit=1,
    )

    last_msg = messages.data[0]
    parts = [
        part.text.value for part in last_msg.content if part.type == "text"
    ]
    reply = "\n".join(parts) if parts else "Пустой ответ 🤷‍♂️"

    return reply, thread_id



async def ask_assistant_file(
    tg_id: int,
    assistant_id: str,
    filepath: str,
    session: AsyncSession
):
    # 1. Получаем или создаём thread_id
    thread_id = await get_or_create_thread(tg_id, assistant_id, session)

    # 2. Определяем MIME тип
    mime, _ = mimetypes.guess_type(filepath)

    # 3. Загружаем файл в OpenAI Files API
    with open(filepath, "rb") as f:
        file = await client.files.create(
            file=f,
            purpose="assistants"
        )

    is_image = mime and mime.startswith("image/")

    # ------- Для изображений -------
    if is_image:
        content = [
            {"type": "text", "text": "Проанализируй изображение."},
            {"type": "image_file", "image_file": {"file_id": file.id}}
        ]

        await client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=content
        )

    # ------- Для документов -------
    else:
        await client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=[{
                "type": "text",
                "text": "Проанализируй прикреплённый файл."
            }],
            attachments=[{
                "file_id": file.id,
                "tools": [{"type": "code_interpreter"}]
            }]
        )

    # 4. Запускаем ассистента
    run = await client.beta.threads.runs.create(
        thread_id=thread_id,
        assistant_id=assistant_id
    )

    # 5. Ждём выполнения
    while True:
        run = await client.beta.threads.runs.retrieve(
            thread_id=thread_id,
            run_id=run.id
        )
        if run.status == "completed":
            break
        if run.status in ("failed", "cancelled", "expired"):
            raise RuntimeError(f"Assistant error: {run.last_error}")
        await asyncio.sleep(1)

    # 6. Читаем ответ
    messages = await client.beta.threads.messages.list(
        thread_id=thread_id,
        limit=1
    )

    last_msg = messages.data[0]

    reply = ""
    for part in last_msg.content:
        if part.type == "text":
            reply += part.text.value

    return reply, thread_id