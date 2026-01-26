"""
Скрипт для выгрузки информации о Vector Stores ассистентов.
"""
import asyncio
import json
from datetime import datetime
from openai import AsyncOpenAI
from config import OPENAI_API_KEY

client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# Ассистенты с file_search
ASSISTANTS_WITH_RAG = {
    "asst_QfzzLwaL8JHcve4Y80IVKq9E": "Ящик Пандоры",
    "asst_K0TDVlaEvZHvh5bSxjz1iUCe": "Куратор WB"
}


async def export_vector_stores():
    print("=" * 60)
    print("ЭКСПОРТ VECTOR STORES")
    print("=" * 60)

    all_data = []

    for assistant_id, name in ASSISTANTS_WITH_RAG.items():
        print(f"\n📦 Проверяю: {name}...")

        try:
            # Получаем ассистента
            assistant = await client.beta.assistants.retrieve(assistant_id)

            # Проверяем tool_resources
            if assistant.tool_resources:
                file_search = assistant.tool_resources.file_search
                if file_search and file_search.vector_store_ids:
                    print(f"   ✅ Найдены Vector Stores: {file_search.vector_store_ids}")

                    for vs_id in file_search.vector_store_ids:
                        # Получаем информацию о Vector Store
                        try:
                            vs = await client.vector_stores.retrieve(vs_id)
                            print(f"\n   📁 Vector Store: {vs.name or vs_id}")
                            print(f"      ID: {vs.id}")
                            print(f"      Файлов: {vs.file_counts.completed}")
                            print(f"      Статус: {vs.status}")

                            # Получаем список файлов
                            files_list = await client.vector_stores.files.list(vs_id)
                            files_info = []

                            for f in files_list.data:
                                try:
                                    # Получаем детали файла
                                    file_obj = await client.files.retrieve(f.id)
                                    files_info.append({
                                        "id": f.id,
                                        "filename": file_obj.filename,
                                        "bytes": file_obj.bytes,
                                        "created_at": file_obj.created_at,
                                        "status": f.status
                                    })
                                    print(f"      - {file_obj.filename} ({file_obj.bytes} bytes)")
                                except Exception as e:
                                    files_info.append({
                                        "id": f.id,
                                        "error": str(e)
                                    })
                                    print(f"      - {f.id} (ошибка: {e})")

                            all_data.append({
                                "assistant_id": assistant_id,
                                "assistant_name": name,
                                "vector_store_id": vs.id,
                                "vector_store_name": vs.name,
                                "file_count": vs.file_counts.completed,
                                "status": vs.status,
                                "files": files_info
                            })

                        except Exception as e:
                            print(f"   ❌ Ошибка получения VS {vs_id}: {e}")
                else:
                    print(f"   ⚠️ Нет Vector Stores")
            else:
                print(f"   ⚠️ Нет tool_resources")

        except Exception as e:
            print(f"   ❌ Ошибка: {e}")

    # Сохраняем
    filename = f"vector_stores_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2, default=str)

    print("\n" + "=" * 60)
    print(f"✅ ЭКСПОРТ ЗАВЕРШЁН: {filename}")
    print("=" * 60)

    return all_data


if __name__ == "__main__":
    asyncio.run(export_vector_stores())
