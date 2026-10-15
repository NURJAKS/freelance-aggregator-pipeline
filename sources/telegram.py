import logging
import re
from datetime import datetime, timezone
from typing import List, Optional
from telethon import TelegramClient
from telethon.tl.types import Message

from models.order import FreelanceOrder
from sources.base import BaseSource
from config.settings import settings

logger = logging.getLogger(__name__)


class TelegramChannelsSource(BaseSource):
    """
    Парсер Telegram-каналов фриланса и подработок через Telethon (MTProto).
    """

    def __init__(
        self,
        channels: Optional[List[str]] = None,
        api_id: Optional[int] = None,
        api_hash: Optional[str] = None,
        session_name: Optional[str] = None,
    ):
        super().__init__(name="telegram")
        self.channels = channels or settings.TELEGRAM_CHANNELS
        self.api_id = api_id or settings.TELEGRAM_API_ID
        self.api_hash = api_hash or settings.TELEGRAM_API_HASH
        self.session_name = session_name or settings.TELEGRAM_SESSION_NAME
        self._client: Optional[TelegramClient] = None
        self._is_ready = False

    async def _get_client(self) -> Optional[TelegramClient]:
        if not self.api_id or not self.api_hash:
            logger.info(
                "Telegram Userbot: TELEGRAM_API_ID или TELEGRAM_API_HASH не настроены в .env. "
                "Мониторинг TG-каналов временно пропущен."
            )
            return None

        if self._client is None:
            self._client = TelegramClient(self.session_name, self.api_id, self.api_hash)
            await self._client.connect()
            if not await self._client.is_user_authorized():
                logger.warning(
                    "Telegram Userbot: сессия '%s' не авторизована. "
                    "Необходимо выполнить вход по номеру телефона.",
                    self.session_name,
                )
                return None
            self._is_ready = True

        return self._client

    async def fetch_orders(self) -> List[FreelanceOrder]:
        client = await self._get_client()
        if not client or not self._is_ready:
            return []

        orders: List[FreelanceOrder] = []

        for channel_name in self.channels:
            try:
                clean_name = channel_name.lstrip("@")
                entity = await client.get_entity(clean_name)
                messages = await client.get_messages(entity, limit=15)

                for msg in messages:
                    order = self._parse_message(clean_name, msg)
                    if order:
                        orders.append(order)

            except Exception as exc:
                logger.error("Ошибка при чтении Telegram канала @%s: %s", channel_name, exc)

        logger.info("Telegram каналы: получено %d сообщений", len(orders))
        return orders

    def _parse_message(self, channel_name: str, msg: Message) -> Optional[FreelanceOrder]:
        if not msg.text or len(msg.text.strip()) < 20:
            return None

        text = msg.text.strip()
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        if not lines:
            return None

        # Заголовок — первая осмысленная строка (до 100 символов)
        first_line = lines[0]
        title = first_line[:100] + ("..." if len(first_line) > 100 else "")

        msg_url = f"https://t.me/{channel_name}/{msg.id}"
        order_id = FreelanceOrder.generate_id("telegram", f"{channel_name}:{msg.id}")

        # Поиск бюджета/оплаты
        budget = self._extract_budget(text)

        pub_date = msg.date
        if pub_date and pub_date.tzinfo is None:
            pub_date = pub_date.replace(tzinfo=timezone.utc)

        return FreelanceOrder(
            id=order_id,
            source="telegram",
            title=f"@{channel_name}: {title}",
            url=msg_url,
            description=text,
            budget_raw=budget,
            currency="RUB",
            published_at=pub_date or datetime.now(timezone.utc),
            tags=[f"@{channel_name}"],
            raw_data={"channel": channel_name, "message_id": msg.id},
        )

    def _extract_budget(self, text: str) -> Optional[str]:
        # Поиск строчек с ценой/оплатой/рейтом
        budget_match = re.search(
            r"(?:ЗП|Оплата|Бюджет|Вилка|Рейт|Ставка)[:\s]+([\d\s]+(?:руб|₽|\$|USD|EUR|тенге|₸|k|к|т\.р\.?)?)",
            text,
            re.IGNORECASE,
        )
        if budget_match:
            return budget_match.group(0).strip()
        return None

    async def close(self) -> None:
        if self._client and self._client.is_connected():
            await self._client.disconnect()
            logger.info("Telegram client отключен.")
