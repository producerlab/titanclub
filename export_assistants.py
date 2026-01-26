"""
Скрипт для выгрузки инструкций всех ассистентов из OpenAI.
Запустить ОДИН РАЗ для сохранения данных перед миграцией.

Использование:
    python export_assistants.py
"""
import asyncio
import json
from datetime import datetime
from openai import AsyncOpenAI
from config import OPENAI_API_KEY
from keyboards import ASSISTANTS

client = AsyncOpenAI(api_key=OPENAI_API_KEY)


async def export_all_assistants():
    """Выгружает все ассистенты и сохраняет в JSON"""

    print("=" * 60)
    print("ЭКСПОРТ АССИСТЕНТОВ ИЗ OPENAI")
    print("=" * 60)

    exported = []

    for assistant_id, local_data in ASSISTANTS.items():
        print(f"\n📥 Загружаю: {local_data['emoji']} {local_data['title']}...")

        try:
            # Получаем полные данные ассистента из OpenAI
            assistant = await client.beta.assistants.retrieve(assistant_id)

            data = {
                "id": assistant.id,
                "name": assistant.name,
                "model": assistant.model,
                "instructions": assistant.instructions,
                "tools": [tool.model_dump() for tool in assistant.tools] if assistant.tools else [],
                "metadata": assistant.metadata,
                "local_title": local_data["title"],
                "local_emoji": local_data["emoji"],
                "local_desc": local_data["desc"],
                "exported_at": datetime.now().isoformat()
            }

            exported.append(data)

            print(f"   ✅ Модель: {assistant.model}")
            print(f"   ✅ Инструкции: {len(assistant.instructions or '')} символов")
            print(f"   ✅ Инструменты: {len(assistant.tools or [])} шт")

        except Exception as e:
            print(f"   ❌ Ошибка: {e}")
            exported.append({
                "id": assistant_id,
                "error": str(e),
                "local_title": local_data["title"],
                "local_emoji": local_data["emoji"],
                "exported_at": datetime.now().isoformat()
            })

    # Сохраняем в файл
    filename = f"assistants_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(exported, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print(f"✅ ЭКСПОРТ ЗАВЕРШЁН")
    print(f"📁 Файл: {filename}")
    print("=" * 60)

    # Также выводим инструкции в консоль для удобства
    print("\n\n" + "=" * 60)
    print("ИНСТРУКЦИИ АССИСТЕНТОВ (для создания Prompts в дашборде)")
    print("=" * 60)

    for data in exported:
        if "error" not in data:
            print(f"\n{'='*60}")
            print(f"## {data['local_emoji']} {data['local_title']}")
            print(f"ID: {data['id']}")
            print(f"Model: {data['model']}")
            print(f"{'='*60}")
            print("\nINSTRUCTIONS:")
            print("-" * 40)
            print(data.get("instructions", "Нет инструкций"))
            print("-" * 40)

    return exported


if __name__ == "__main__":
    asyncio.run(export_all_assistants())
