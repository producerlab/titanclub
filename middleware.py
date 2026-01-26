import logging
from aiogram import BaseMiddleware
from aiogram.types import Message

from config import GROUP_ID


class GroupCheckMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: Message, data):

        # 1) Реагируем ТОЛЬКО если пользователь пишет боту в личку
        if event.chat.type != "private":
            return  # полностью игнорируем всё из групп

        # 2) Если сообщение отправлено от имени канала/группы — такого юзера нельзя проверить
        if event.sender_chat:
            return  # игнорируем

        bot = data["bot"]
        user_id = event.from_user.id

        # 3) Проверяем, что пользователь присутствует в целевой группе
        try:
            member = await bot.get_chat_member(GROUP_ID, user_id)
            allowed = member.status in ["member", "creator", "administrator"]
        except Exception as e:
            logging.warning(f"Failed to check membership for user {user_id}: {e}")
            allowed = False

        if not allowed:
            await event.answer("❌ Ассистент доступен только для резидентов закрытого клуба Titan Sellers Club\n\n"
                               "Если вы еще не резидент, напишите нам в поддержку @mpbiz_bot")
            return

        # Если всё ок → продолжаем выполнение хэндлера
        return await handler(event, data)
