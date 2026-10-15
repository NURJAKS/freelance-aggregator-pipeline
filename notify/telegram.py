import html
import logging
from typing import List, Optional
import httpx
from models.order import FreelanceOrder
from config.settings import settings

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """
    Отправщик уведомлений о заказах в Telegram.
    """

    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None):
        self.bot_token = bot_token or settings.TELEGRAM_BOT_TOKEN
        self.chat_id = chat_id or settings.TELEGRAM_CHAT_ID
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"

    def format_order(
        self,
        order: FreelanceOrder,
        matched_keywords: List[str] = None,
        ai_score: Optional[int] = None,
        ai_verdict: Optional[str] = None,
        ai_bid_tip: Optional[str] = None,
    ) -> str:
        """
        Форматирует карточку заказа в чистый HTML для Telegram.
        """
        source_icons = {
            "habr": "⚡ Хабр Фриланс",
            "telegram": "✈️ Telegram",
            "upwork": "🟢 Upwork",
            "kwork": "🔵 Kwork",
            "freelancehunt": "🏹 Freelancehunt",
        }
        source_label = source_icons.get(order.source.lower(), f"🌐 {order.source.capitalize()}")

        budget = order.budget_raw or "Договорная"
        safe_title = html.escape(order.title.strip())

        # Ограничиваем длину описания
        desc = order.description.strip()
        if len(desc) > 500:
            desc = desc[:497] + "..."
        safe_desc = html.escape(desc)

        kw_str = ""
        if matched_keywords:
            safe_kw = [f"#{k.replace(' ', '_')}" for k in matched_keywords[:6]]
            kw_str = f"🏷️ <b>Навыки:</b> {' '.join(safe_kw)}\n"

        lines = [
            f"<b>{source_label}</b> | <b>{html.escape(budget)}</b>",
            "",
            f"📌 <b>{safe_title}</b>",
            "",
        ]

        if safe_desc:
            lines.append(f"{safe_desc}\n")

        if kw_str:
            lines.append(kw_str)

        # Добавляем AI блок, если доступен
        if ai_score is not None:
            score_bar = "⭐" * min(max(ai_score, 1), 10)
            lines.append(f"🤖 <b>AI Скоринг:</b> {ai_score}/10 {score_bar}")
            if ai_verdict:
                lines.append(f"💡 <i>{html.escape(ai_verdict)}</i>")
            if ai_bid_tip:
                lines.append(f"🎯 <b>Совет для отклика:</b> {html.escape(ai_bid_tip)}")
            lines.append("")

        lines.append(f'🔗 <a href="{order.url}">Открыть заказ и откликнуться</a>')

        return "\n".join(lines)

    async def send_order(
        self,
        order: FreelanceOrder,
        matched_keywords: List[str] = None,
        ai_score: Optional[int] = None,
        ai_verdict: Optional[str] = None,
        ai_bid_tip: Optional[str] = None,
    ) -> bool:
        """
        Отправляет карточку заказа в Telegram-чат.
        """
        if not self.bot_token or not self.chat_id:
            logger.warning("Telegram Bot Token или Chat ID не настроены. Уведомление пропущено.")
            return False

        message_text = self.format_order(
            order,
            matched_keywords=matched_keywords,
            ai_score=ai_score,
            ai_verdict=ai_verdict,
            ai_bid_tip=ai_bid_tip,
        )
        payload = {
            "chat_id": self.chat_id,
            "text": message_text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.post(f"{self.base_url}/sendMessage", json=payload)
                resp.raise_for_status()
                return True
            except httpx.HTTPError as exc:
                logger.error("Ошибка отправки в Telegram: %s", exc)
                return False
