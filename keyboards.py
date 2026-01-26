from __future__ import annotations
from aiogram.utils.keyboard import InlineKeyboardBuilder


ASSISTANTS = {
    "asst_ZMDIYhez0iMJ3ZhMScCwREil": {
        "title": "Адвокат клиента",
        "emoji": "⚖️",
        "desc": "Промпты для изучения ЦА",
        "full_desc": "Помогает составить портрет целевой аудитории, определить боли и потребности клиентов",
        "examples": ["Кто моя ЦА для товара X?", "Какие боли у покупателей Y?"]
    },
    "asst_16FOkKPETrIKCZ4VTn5iMr3J": {
        "title": "SEO Vivaldi",
        "emoji": "🎼",
        "desc": "SEO-описания для WB",
        "full_desc": "Создаёт SEO-оптимизированные описания для карточек товаров на Wildberries",
        "examples": ["Напиши описание для куртки", "SEO-текст для детской игрушки"]
    },
    "asst_QfzzLwaL8JHcve4Y80IVKq9E": {
        "title": "Ящик Пандоры",
        "emoji": "📦",
        "desc": "Реклама WB, адаптация под селлера",
        "full_desc": "Настраивает рекламные кампании на Wildberries, адаптирует стратегии под вашу нишу",
        "examples": ["Как настроить рекламу?", "Какой бюджет на продвижение?"]
    },
    "asst_rYvjemjJPNoTLnraZVFzZsGI": {
        "title": "Тарантино для блогеров",
        "emoji": "🎬",
        "desc": "Сценарии и посты",
        "full_desc": "Создаёт сценарии для видео и тексты постов для продвижения товаров",
        "examples": ["Сценарий Reels для товара", "Пост для блогера о продукте"]
    },
    "asst_K0TDVlaEvZHvh5bSxjz1iUCe": {
        "title": "Куратор WB",
        "emoji": "📈",
        "desc": "Эксперт с опытом на 300 млн",
        "full_desc": "Эксперт-маркетолог с опытом продаж на 300+ млн рублей, консультирует по стратегии",
        "examples": ["Как увеличить продажи?", "Анализ конкурентов"]
    }
}


def build_assistant_keyboard(current_assistant_id: str | None = None):
    """Основная клавиатура с ассистентом"""
    kb = InlineKeyboardBuilder()

    if current_assistant_id:
        a = ASSISTANTS.get(current_assistant_id)
        if a:
            kb.button(
                text=f"🟢 {a['emoji']} {a['title']}",
                callback_data="noop"
            )
        kb.button(text="🔄 Сменить", callback_data="choose_assistant")
        kb.button(text="📜 История", callback_data="show_history")
        kb.button(text="📊 Статус", callback_data="show_status")
        kb.adjust(1, 3)
        return kb.as_markup()

    # Если ассистент не выбран — список с описаниями
    for asst_id, a in ASSISTANTS.items():
        kb.button(
            text=f"{a['emoji']} {a['title']}",
            callback_data=f"set_assistant:{asst_id}"
        )

    kb.adjust(1)
    return kb.as_markup()


def build_assistant_selection_keyboard():
    """Клавиатура выбора ассистента с описаниями"""
    kb = InlineKeyboardBuilder()

    for asst_id, a in ASSISTANTS.items():
        kb.button(
            text=f"{a['emoji']} {a['title']} — {a['desc']}",
            callback_data=f"set_assistant:{asst_id}"
        )

    kb.button(text="❌ Отмена", callback_data="cancel_selection")
    kb.adjust(1)
    return kb.as_markup()


def build_loading_keyboard():
    """Клавиатура при загрузке (без кнопок)"""
    return None


def get_assistant_card(assistant_id: str) -> str:
    """Форматирует карточку ассистента"""
    a = ASSISTANTS.get(assistant_id)
    if not a:
        return "Ассистент не найден"

    examples_text = "\n".join([f"• {ex}" for ex in a.get("examples", [])])

    return (
        f"✅ <b>Вы выбрали: {a['emoji']} {a['title']}</b>\n\n"
        f"{a['full_desc']}\n\n"
        f"<b>Примеры вопросов:</b>\n{examples_text}\n\n"
        f"Просто отправьте ваш вопрос или загрузите файл!"
    )
