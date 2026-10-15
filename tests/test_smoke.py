import asyncio
import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import shutil
import tempfile
from datetime import datetime, timezone
from models.order import FreelanceOrder
from storage.db import OrderStorage
from pipeline.filter import OrderFilter
from notify.telegram import TelegramNotifier


async def run_tests():
    print("=== 1. Проверка модели FreelanceOrder ===")
    order_id = FreelanceOrder.generate_id("habr", "https://freelance.habr.com/tasks/12345")
    order = FreelanceOrder(
        id=order_id,
        source="habr",
        title="Написать парсер на Python FastAPI",
        url="https://freelance.habr.com/tasks/12345",
        description="Требуется разработать асинхронный сервис сбора данных с сохранением в PostgreSQL.",
        budget_raw="50 000 ₸",
        currency="KZT",
        published_at=datetime.now(timezone.utc),
        tags=["Python", "FastAPI", "Парсинг"],
    )
    assert order.id == order_id
    assert order.source == "habr"
    print("✓ Модель FreelanceOrder успешно создана и валидирована.")

    print("\n=== 2. Проверка OrderFilter ===")
    order_filter = OrderFilter()

    # Позитивный тест
    is_match, reason, matched = order_filter.is_match(order)
    assert is_match is True
    assert "python" in matched or "fastapi" in matched
    print(f"✓ Фильтр успешно одобрил релевантный заказ: {matched}")

    # Негативный тест (стоп-слово)
    bad_order = FreelanceOrder(
        id=FreelanceOrder.generate_id("habr", "task_bad"),
        source="habr",
        title="Сделать дизайн и верстку на WordPress 1C",
        url="https://example.com/bad",
        description="Курсовая работа",
    )
    is_match_bad, reason_bad, _ = order_filter.is_match(bad_order)
    assert is_match_bad is False
    print(f"✓ Фильтр успешно отклонил нерелевантный заказ: {reason_bad}")

    print("\n=== 3. Проверка хранилища дедупликации SQLite ===")
    tmp_dir = tempfile.mkdtemp()
    db_path = os.path.join(tmp_dir, "test_freelance.db")
    try:
        storage = OrderStorage(db_path=db_path)
        await storage.init_db()

        # Первичное сохранение
        assert not await storage.is_seen(order.id)
        saved = await storage.save_order_if_new(order)
        assert saved is True
        print("✓ Заказ успешно сохранен впервые.")

        # Повторное сохранение (проверка дедупликации)
        assert await storage.is_seen(order.id)
        saved_again = await storage.save_order_if_new(order)
        assert saved_again is False
        print("✓ Дедупликация сработала: дубликат отклонен.")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    print("\n=== 4. Проверка форматирования уведомлений Telegram ===")
    notifier = TelegramNotifier()
    msg = notifier.format_order(order, matched)
    assert "⚡ Хабр Фриланс" in msg
    assert "Написать парсер" in msg
    assert "50 000 ₸" in msg
    print("✓ Карточка заказа сформирована корректно.")
    print("\nКарточка заказа предпросмотр:\n" + "-" * 40)
    print(msg)
    print("-" * 40)

    print("\n✅ Все тесты базового фундамента успешно пройдены!")


if __name__ == "__main__":
    asyncio.run(run_tests())
