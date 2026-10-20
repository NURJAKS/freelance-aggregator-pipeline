import asyncio
import logging
import signal
from typing import List
from config.settings import settings
from models.order import FreelanceOrder
from storage.db import OrderStorage
from pipeline.filter import OrderFilter
from pipeline.scorer import OrderScorer
from notify.telegram import TelegramNotifier
from notify.bot_listener import TelegramBotListener
from sources.base import BaseSource
from sources.habr import HabrFreelanceSource
from sources.kwork import KworkSource
from sources.upwork import UpworkSource
from sources.telegram import TelegramChannelsSource
from sources.freelancehunt import FreelancehuntSource

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("freelance_parser")

stop_event = asyncio.Event()


def handle_stop_signals():
    logger.info("Получен сигнал завершения. Останавливаем сервис...")
    stop_event.set()


async def process_orders(
    sources: List[BaseSource],
    storage: OrderStorage,
    order_filter: OrderFilter,
    scorer: OrderScorer,
    notifier: TelegramNotifier,
) -> int:
    """
    Один цикл опроса всех активных источников:
    1. Сбор заказов
    2. Проверка дедупликации (is_seen)
    3. Фильтрация по ключевым словам
    4. Сохранение в БД
    5. Опциональный AI-скоринг
    6. Отправка уведомления
    Возвращает количество новых отправленных заказов.
    """
    sent_count = 0
    for source in sources:
        try:
            logger.info("Опрос источника: %s...", source.name)
            orders = await source.fetch_orders()
            logger.info("Источник %s вернул %d заказов", source.name, len(orders))

            for order in orders:
                # 1. Проверяем, видели ли уже этот заказ
                if await storage.is_seen(order.id):
                    continue

                # 2. Фильтруем заказ
                is_match, reason, matched_kw = order_filter.is_match(order)
                if not is_match:
                    logger.debug("Заказ '%s' отклонен: %s", order.title, reason)
                    # Сохраняем в БД как просмотренный, чтобы не фильтровать снова
                    await storage.save_order_if_new(order)
                    continue

                # 3. Сохраняем в БД
                is_new = await storage.save_order_if_new(order)
                if not is_new:
                    continue

                logger.info(
                    "🎯 Найден целевой заказ: [%s] %s (%s)",
                    order.source,
                    order.title,
                    order.budget_raw or "Без бюджета",
                )

                # 4. Опциональный AI-скоринг
                ai_score, ai_verdict, ai_bid_tip = await scorer.score_order(order)

                # 5. Отправляем уведомление
                sent = await notifier.send_order(
                    order=order,
                    matched_keywords=matched_kw,
                    ai_score=ai_score,
                    ai_verdict=ai_verdict,
                    ai_bid_tip=ai_bid_tip,
                )
                if sent:
                    sent_count += 1

        except Exception as exc:
            logger.error("Ошибка при обработке источника %s: %s", source.name, exc, exc_info=True)

    return sent_count


async def main():
    logger.info("Запуск freelance-aggregator-pipeline...")

    storage = OrderStorage(db_path=settings.DATABASE_PATH)
    await storage.init_db()

    order_filter = OrderFilter()
    scorer = OrderScorer()
    notifier = TelegramNotifier()

    # Инициализация всех источников данных
    sources: List[BaseSource] = [
        HabrFreelanceSource(),
        KworkSource(),
        UpworkSource(),
        TelegramChannelsSource(),
        FreelancehuntSource(),
    ]

    active_names = ", ".join(s.name for s in sources)
    logger.info(
        "Сервис готов. Активные источники: [%s]. Интервал опроса: %d сек.",
        active_names,
        settings.POLL_INTERVAL_SECONDS,
    )

    # Callback для ручного запуска проверки из меню Telegram
    async def check_now_callback() -> int:
        return await process_orders(sources, storage, order_filter, scorer, notifier)

    # Инициализация интерактивного слушателя бота Telegram
    bot_listener = TelegramBotListener(
        storage=storage,
        order_filter=order_filter,
        check_now_callback=check_now_callback,
    )
    listener_task = asyncio.create_task(bot_listener.run_listener(stop_event))

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, handle_stop_signals)
        except NotImplementedError:
            pass  # Для сред без add_signal_handler

    while not stop_event.is_set():
        await process_orders(sources, storage, order_filter, scorer, notifier)

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=settings.POLL_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            pass

    # Останавливаем слушатель команд
    listener_task.cancel()
    try:
        await listener_task
    except asyncio.CancelledError:
        pass

    # Закрываем источники при остановке
    for source in sources:
        await source.close()

    logger.info("Сервис freelance-aggregator-pipeline успешно остановлен.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
