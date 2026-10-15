import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models.order import FreelanceOrder
from sources.habr import HabrFreelanceSource
from sources.kwork import KworkSource
from sources.upwork import UpworkSource
from sources.telegram import TelegramChannelsSource
from pipeline.scorer import OrderScorer
from pipeline.filter import OrderFilter
from storage.db import OrderStorage
from notify.telegram import TelegramNotifier
from main import process_orders

SAMPLE_HABR_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Заказы с Хабр Фриланс</title>
    <link>https://freelance.habr.com/tasks</link>
    <description>Свежие заказы</description>
    <item>
      <title>Разработка бэкенда на FastAPI для агрегатора вакансий</title>
      <link>https://freelance.habr.com/tasks/999001</link>
      <description>&lt;p&gt;Нужен опытный разработчик на Python (FastAPI, PostgreSQL, Docker). Бюджет: 80 000 руб.&lt;/p&gt;</description>
      <pubDate>Sun, 11 Oct 2026 06:00:00 +0000</pubDate>
    </item>
  </channel>
</rss>
"""

SAMPLE_KWORK_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Биржа Kwork</title>
    <link>https://kwork.ru/projects</link>
    <description>Проекты Kwork</description>
    <item>
      <title>Написать Telegram-бота для обработки заявок клиентов</title>
      <link>https://kwork.ru/projects/888002</link>
      <description>Требуется разработать Telegram бота на Python (Aiogram). Желаемый бюджет: до 15 000 руб.</description>
      <pubDate>Sun, 11 Oct 2026 06:10:00 +0000</pubDate>
    </item>
  </channel>
</rss>
"""

SAMPLE_UPWORK_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Upwork Jobs</title>
    <link>https://www.upwork.com</link>
    <description>Jobs search</description>
    <item>
      <title>Python / Web Scraping Specialist for E-commerce</title>
      <link>https://www.upwork.com/jobs/777003?source=rss</link>
      <description>&lt;b&gt;Hourly Range:&lt;/b&gt; $25.00 - $45.00&lt;br /&gt;&lt;b&gt;Skills:&lt;/b&gt; Python, Beautiful Soup, Web Scraping, FastAPI&lt;br /&gt;Need a scraper for product catalogs.</description>
      <pubDate>Sun, 11 Oct 2026 06:20:00 +0000</pubDate>
    </item>
  </channel>
</rss>
"""


async def test_all_sources():
    print("=== 1. Тест парсера Хабр Фриланс (RSS) ===")
    habr_source = HabrFreelanceSource()
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_resp = AsyncMock()
        mock_resp.text = SAMPLE_HABR_RSS
        mock_resp.status_code = 200
        mock_resp.raise_for_status = lambda: None
        mock_get.return_value = mock_resp

        orders = await habr_source.fetch_orders()
        assert len(orders) == 1
        order = orders[0]
        assert order.source == "habr"
        assert "FastAPI" in order.title
        assert "80 000 руб" in (order.budget_raw or "")
        print(f"✓ Хабр: заказ успешно распарсен, бюджет: {order.budget_raw}")

    print("\n=== 2. Тест парсера Kwork (RSS) ===")
    kwork_source = KworkSource()
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_resp = AsyncMock()
        mock_resp.text = SAMPLE_KWORK_RSS
        mock_resp.status_code = 200
        mock_resp.raise_for_status = lambda: None
        mock_get.return_value = mock_resp

        orders = await kwork_source.fetch_orders()
        assert len(orders) == 1
        order = orders[0]
        assert order.source == "kwork"
        assert "Telegram" in order.title
        assert "15 000 руб" in (order.budget_raw or "")
        print(f"✓ Kwork: проект успешно распарсен, бюджет: {order.budget_raw}")

    print("\n=== 3. Тест парсера Upwork (RSS) ===")
    upwork_source = UpworkSource()
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_resp = AsyncMock()
        mock_resp.text = SAMPLE_UPWORK_RSS
        mock_resp.status_code = 200
        mock_resp.raise_for_status = lambda: None
        mock_get.return_value = mock_resp

        orders = await upwork_source.fetch_orders()
        assert len(orders) == 1
        order = orders[0]
        assert order.source == "upwork"
        assert "$25.00 - $45.00" in (order.budget_raw or "")
        assert "Python" in order.tags or "FastAPI" in order.tags
        assert not order.url.endswith("?source=rss")  # Проверка очистки параметров ссылки
        print(f"✓ Upwork: рейт и навыки успешно извлечены: {order.budget_raw}, {order.tags}")

    print("\n=== 4. Тест парсера Telegram каналов без кредов (graceful fallback) ===")
    tg_source = TelegramChannelsSource(api_id=0, api_hash="")
    orders = await tg_source.fetch_orders()
    assert orders == []
    print("✓ Telegram: корректный безопасный пропуск при отсутствии API ключей.")

    print("\n=== 5. Тест AI Scorer (graceful fallback при отсутствии ключа) ===")
    scorer = OrderScorer(api_key="", enabled=False)
    score, verdict, tip = await scorer.score_order(order)
    assert score is None
    print("✓ Scorer: корректный пропуск при отключенном AI.")

    print("\n=== 6. Интеграционный тест сквозного пайплайна process_orders ===")
    import tempfile, shutil
    tmp_dir = tempfile.mkdtemp()
    db_path = os.path.join(tmp_dir, "test_pipeline.db")
    try:
        storage = OrderStorage(db_path=db_path)
        await storage.init_db()
        order_filter = OrderFilter()
        mock_notifier = AsyncMock()

        # Запускаем один цикл обработки
        sources = [habr_source]
        with patch("httpx.AsyncClient.get") as mock_get:
            mock_resp = AsyncMock()
            mock_resp.text = SAMPLE_HABR_RSS
            mock_resp.status_code = 200
            mock_resp.raise_for_status = lambda: None
            mock_get.return_value = mock_resp

            await process_orders(sources, storage, order_filter, scorer, mock_notifier)

            # Проверяем, что нотификатор был вызван для целевого заказа
            assert mock_notifier.send_order.call_count == 1
            print("✓ Нотификатор успешно вызван для целевого заказа.")

            # Второй запуск (проверка дедупликации)
            await process_orders(sources, storage, order_filter, scorer, mock_notifier)
            assert mock_notifier.send_order.call_count == 1
            print("✓ Повторный запуск не отправил дубликатов (дедупликация подтверждена).")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    print("\n🎉 Все тесты источников и пайплайна успешно пройдены!")


if __name__ == "__main__":
    asyncio.run(test_all_sources())
