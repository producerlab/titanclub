from __future__ import annotations
from aiogram.utils.keyboard import InlineKeyboardBuilder


ASSISTANTS = {
    "asst_ZMDIYhez0iMJ3ZhMScCwREil": {
        "title": "Адвокат клиента",
        "emoji": "⚖️",
        "desc": "Промпты для изучения ЦА"
    },
    "asst_16FOkKPETrIKCZ4VTn5iMr3J": {
        "title": "SEO Vivaldi",
        "emoji": "🎼",
        "desc": "SEO-описания для WB"
    },
    "asst_QfzzLwaL8JHcve4Y80IVKq9E": {
        "title": "Ящик Пандоры",
        "emoji": "📦",
        "desc": "Реклама WB, адаптация под селлера"
    },
    "asst_rYvjemjJPNoTLnraZVFzZsGI": {
        "title": "Тарантино для блогеров",
        "emoji": "🎬",
        "desc": "Сценарии и посты"
    },
    "asst_K0TDVlaEvZHvh5bSxjz1iUCe": {
        "title": "Куратор WB",
        "emoji": "📈",
        "desc": "Эксперт с опытом на 300 млн"
    }
}

def build_assistant_keyboard(current_assistant_id: str | None = None):
    kb = InlineKeyboardBuilder()

    # Показываем текущего ассистента
    if current_assistant_id:
        a = ASSISTANTS[current_assistant_id]
        kb.button(
            text=f"🟢 Ассистент: {a['emoji']} {a['title']}",
            callback_data="noop"
        )
        kb.button(
            text="🔄 Сменить ассистента",
            callback_data="choose_assistant"
        )
        kb.adjust(1)
        return kb.as_markup()

    # Если ассистент ещё не выбран — выводим список
    for asst_id, a in ASSISTANTS.items():
        kb.button(
            text=f"{a['emoji']} {a['title']}",
            callback_data=f"set_assistant:{asst_id}"
        )

    kb.adjust(1)
    return kb.as_markup()