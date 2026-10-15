import asyncio
import html
import logging
from typing import Callable, Optional
import httpx

from config.settings import settings
from storage.db import OrderStorage
from pipeline.filter import OrderFilter

logger = logging.getLogger(__name__)


class TelegramBotListener:
    """
    Интерактивный слушатель команд и кнопочного меню в Telegram.
    Позволяет управлять парсером прямо из чата Telegram.
    """

    def __init__(
        self,
        storage: OrderStorage,
        order_filter: OrderFilter,
        check_now_callback: Callable,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
    ):
        self.storage = storage
        self.order_filter = order_filter
        self.check_now_callback = check_now_callback
        self.bot_token = bot_token or settings.TELEGRAM_BOT_TOKEN
        self.chat_id = str(chat_id or settings.TELEGRAM_CHAT_ID)
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.offset = 0

    async def setup_bot_commands(self) -> None:
        """
        Устанавливает официальное меню команд Telegram (кнопка 'Меню' в нижнем углу).
        """
        commands = [
            {"command": "start", "description": "🏠 Главное меню и клавиатура"},
            {"command": "check", "description": "🔄 Проверить биржи прямо сейчас"},
            {"command": "stats", "description": "📊 Статистика найденных заказов"},
            {"command": "last", "description": "📋 Последние 5 найденных заказов"},
            {"command": "filters", "description": "⚙️ Активные фильтры и минус-слова"},
        ]
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                await client.post(
                    f"{self.base_url}/setMyCommands",
                    json={"commands": commands},
                )
                logger.info("Команды меню Telegram успешно зарегистрированы.")
            except Exception as exc:
                logger.warning("Не удалось зарегистрировать команды меню Telegram: %s", exc)

    def _get_keyboard_markup(self) -> dict:
        """
        Удобная постоянная клавиатура с кнопками быстрого доступа.
        """
        return {
            "keyboard": [
                [{"text": "📊 Статистика"}, {"text": "🔄 Проверить сейчас"}],
                [{"text": "📋 Последние заказы"}, {"text": "⚙️ Мои фильтры"}],
            ],
            "resize_keyboard": True,
            "persistent": True,
        }

    async def send_message(self, text: str, reply_markup: Optional[dict] = None) -> None:
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        else:
            payload["reply_markup"] = self._get_keyboard_markup()

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                await client.post(f"{self.base_url}/sendMessage", json=payload)
            except Exception as exc:
                logger.error("Ошибка отправки ответа в Telegram: %s", exc)

    async def handle_update(self, update: dict) -> None:
        message = update.get("message")
        if not message:
            return

        from_id = str(message.get("chat", {}).get("id", ""))
        text = (message.get("text") or "").strip()

        # Защита: реагируем только на авторизованного пользователя
        if from_id != self.chat_id:
            logger.warning("Получено сообщение от неавторизованного ID: %s", from_id)
            return

        cmd = text.lower()

        if cmd in ["/start", "меню", "start"]:
            welcome_text = (
                "👋 <b>Добро пожаловать в панель управления auto_freelance-parser!</b>\n\n"
                "Я постоянно сканирую фриланс-биржи и присылаю новые задачи по вашему стеку.\n\n"
                "Используйте кнопки меню ниже для управления:"
            )
            await self.send_message(welcome_text)

        elif cmd in ["📊 статистика", "/stats", "stats", "статистика"]:
            stats = await self.storage.get_stats()
            by_src_lines = [f"  • {src.capitalize()}: <b>{cnt}</b>" for src, cnt in stats["by_source"].items()]
            by_src_str = "\n".join(by_src_lines) if by_src_lines else "  • Пока нет данных"

            msg = (
                "📊 <b>Статистика работы парсера:</b>\n\n"
                f"• Всего заказов в базе: <b>{stats['total']}</b>\n"
                f"• Заказов за сегодня: <b>{stats['today']}</b>\n\n"
                f"<b>По источникам:</b>\n{by_src_str}\n\n"
                f"⏱️ Интервал авто-опроса: <b>{settings.POLL_INTERVAL_SECONDS} сек.</b>\n"
                "🟢 Статус: <b>Работает в фоне</b>"
            )
            await self.send_message(msg)

        elif cmd in ["🔄 проверить сейчас", "/check", "check", "проверить"]:
            await self.send_message("🔍 <i>Запускаю внеочередное сканирование всех бирж...</i>")
            try:
                new_count = await self.check_now_callback()
                if new_count > 0:
                    await self.send_message(f"✅ Сканирование завершено! Найдено новых заказов: <b>{new_count}</b>.")
                else:
                    await self.send_message("✅ Сканирование завершено. Новых заказов пока нет, дедупликатор активен.")
            except Exception as exc:
                logger.error("Ошибка ручной проверки: %s", exc)
                await self.send_message(f"⚠️ Ошибка при опросе источников: {exc}")

        elif cmd in ["📋 последние заказы", "/last", "last", "заказы"]:
            orders = await self.storage.get_recent_orders(limit=5)
            if not orders:
                await self.send_message("📋 В базе пока нет сохраненных заказов.")
                return

            lines = ["📋 <b>Последние 5 заказов из базы:</b>\n"]
            for i, ord_data in enumerate(orders, 1):
                src = ord_data.get("source", "").capitalize()
                title = html.escape(ord_data.get("title", ""))
                url = ord_data.get("url", "#")
                budget = ord_data.get("budget_raw") or "Договорная"
                lines.append(f"{i}. <b>[{src}]</b> <a href=\"{url}\">{title}</a> — <i>{budget}</i>")

            await self.send_message("\n\n".join(lines))

        elif cmd in ["⚙️ мои фильтры", "/filters", "filters", "фильтры"]:
            kw_white = ", ".join([f"<code>{k}</code>" for k in settings.KEYWORD_WHITELIST[:15]])
            kw_black = ", ".join([f"<code>{k}</code>" for k in settings.KEYWORD_BLACKLIST[:10]])
            msg = (
                "⚙️ <b>Текущие настройки фильтрации:</b>\n\n"
                f"✅ <b>Ключевые технологии (White-list):</b>\n{kw_white} и др.\n\n"
                f"🚫 <b>Минус-слова (Black-list):</b>\n{kw_black} и др.\n\n"
                f"🎯 <b>Целевой профиль:</b> Python / Backend / Парсинг / Telegram-боты\n"
                f"⏱️ <b>Интервал опроса:</b> {settings.POLL_INTERVAL_SECONDS} секунд"
            )
            await self.send_message(msg)

        else:
            await self.send_message("ℹ️ Выберите действие в меню ниже или отправьте /start.")

    async def run_listener(self, stop_event: asyncio.Event) -> None:
        """
        Фоновый цикл получения входящих обновлений от Telegram (long polling).
        """
        if not self.bot_token or not self.chat_id:
            logger.info("Telegram Bot Token или Chat ID не заданы. Слушатель команд отключен.")
            return

        await self.setup_bot_commands()
        logger.info("Слушатель интерактивного меню Telegram запущен.")

        async with httpx.AsyncClient(timeout=25.0) as client:
            while not stop_event.is_set():
                try:
                    resp = await client.get(
                        f"{self.base_url}/getUpdates",
                        params={"offset": self.offset, "timeout": 20},
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        updates = data.get("result", [])
                        for update in updates:
                            self.offset = update["update_id"] + 1
                            await self.handle_update(update)
                    elif resp.status_code == 409:
                        # Конфликт сессий (другой инстанс)
                        await asyncio.sleep(5)
                    else:
                        await asyncio.sleep(2)

                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    logger.debug("Ошибка в цикле getUpdates: %s", exc)
                    await asyncio.sleep(3)

        logger.info("Слушатель интерактивного меню Telegram остановлен.")
