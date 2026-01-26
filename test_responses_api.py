"""
Тест нового клиента на Responses API.
Запуск: python test_responses_api.py
"""
import asyncio
from openai import AsyncOpenAI
from config import OPENAI_API_KEY

client = AsyncOpenAI(api_key=OPENAI_API_KEY)


async def test_basic_response():
    """Тест базового вызова Responses API"""
    print("=" * 60)
    print("ТЕСТ 1: Базовый вызов Responses API")
    print("=" * 60)

    try:
        response = await client.responses.create(
            model="gpt-4.1-mini",
            input=[
                {"role": "system", "content": "Ты — помощник. Отвечай кратко."},
                {"role": "user", "content": "Привет! Скажи 'тест пройден'."}
            ]
        )

        print(f"✅ Response ID: {response.id}")
        print(f"✅ Model: {response.model}")

        # Извлекаем текст
        for output in response.output:
            if hasattr(output, 'content'):
                for content in output.content:
                    if hasattr(content, 'text'):
                        print(f"✅ Ответ: {content.text}")

        return response.id

    except Exception as e:
        print(f"❌ Ошибка: {type(e).__name__}: {e}")
        return None


async def test_conversation_continuity(previous_id: str):
    """Тест продолжения диалога через previous_response_id"""
    print("\n" + "=" * 60)
    print("ТЕСТ 2: Продолжение диалога")
    print("=" * 60)

    try:
        response = await client.responses.create(
            model="gpt-4.1-mini",
            input=[
                {"role": "user", "content": "Какое было моё предыдущее сообщение?"}
            ],
            previous_response_id=previous_id
        )

        print(f"✅ Response ID: {response.id}")

        for output in response.output:
            if hasattr(output, 'content'):
                for content in output.content:
                    if hasattr(content, 'text'):
                        print(f"✅ Ответ: {content.text}")

        return True

    except Exception as e:
        print(f"❌ Ошибка: {type(e).__name__}: {e}")
        return False


async def test_response_structure():
    """Тест структуры ответа"""
    print("\n" + "=" * 60)
    print("ТЕСТ 3: Структура ответа")
    print("=" * 60)

    try:
        response = await client.responses.create(
            model="gpt-4.1-mini",
            input="Скажи 'привет'"
        )

        print(f"✅ response.id: {response.id}")
        print(f"✅ response.model: {response.model}")
        print(f"✅ response.output type: {type(response.output)}")
        print(f"✅ response.output length: {len(response.output)}")

        if response.output:
            output = response.output[0]
            print(f"✅ output type: {type(output)}")
            print(f"✅ output attrs: {dir(output)}")

            if hasattr(output, 'content'):
                print(f"✅ content length: {len(output.content)}")
                for c in output.content:
                    print(f"   - content type: {type(c)}")
                    if hasattr(c, 'text'):
                        print(f"   - text: {c.text}")

        return True

    except Exception as e:
        print(f"❌ Ошибка: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    print("\n🚀 ТЕСТИРОВАНИЕ RESPONSES API\n")

    # Тест 1
    response_id = await test_basic_response()

    # Тест 2 (если тест 1 успешен)
    if response_id:
        await test_conversation_continuity(response_id)

    # Тест 3
    await test_response_structure()

    print("\n" + "=" * 60)
    print("ТЕСТИРОВАНИЕ ЗАВЕРШЕНО")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
