import json
import logging
from typing import Optional, Tuple
import httpx

from models.order import FreelanceOrder
from config.settings import settings

logger = logging.getLogger(__name__)


class OrderScorer:
    """
    Опциональный AI-скорер на базе Google Gemini.
    Оценивает релевантность задачи для Python/Backend разработчика и дает совет по отклику.
    """

    def __init__(self, api_key: Optional[str] = None, enabled: Optional[bool] = None):
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.enabled = enabled if enabled is not None else settings.AI_SCORING_ENABLED
        self.endpoint = (
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
            f"?key={self.api_key}"
        )

    async def score_order(self, order: FreelanceOrder) -> Tuple[Optional[int], Optional[str], Optional[str]]:
        """
        Возвращает:
            - score (1-10): оценка привлекательности проекта
            - short_verdict: краткий вердикт (почему подходит)
            - bid_tip: совет для быстрого отклика
        """
        if not self.enabled or not self.api_key:
            return None, None, None

        prompt = f"""
Ты — помощник опытного Python/Backend разработчика (стек: Python, FastAPI, Django, Telegram-боты, Web Scraping, парсинг данных).
Разработчик ищет контракты и подработки (15–25 ч/неделю) в часовых поясах UTC+5 (Казахстан) / UTC+3 (СНГ) / CET или асинхронно.

Оцени заказ:
Заголовок: {order.title}
Источник: {order.source}
Бюджет: {order.budget_raw or 'Не указан'}
Описание: {order.description[:800]}

Верни ответ СТРОГО в формате валидного JSON без markdown:
{{
  "score": <целое число от 1 до 10>,
  "verdict": "<краткий вердикт на русском до 15 слов, почему задача интересна>",
  "bid_tip": "<конкретный совет на русском до 20 слов, на что сделать упор в первом сообщении клиенту>"
}}
"""

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    self.endpoint,
                    json={
                        "contents": [
                            {"parts": [{"text": prompt}]}
                        ],
                        "generationConfig": {
                            "response_mime_type": "application/json",
                            "temperature": 0.2,
                        },
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                content = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                result = json.loads(content)
                return (
                    int(result.get("score", 7)),
                    result.get("verdict"),
                    result.get("bid_tip"),
                )
        except Exception as exc:
            logger.warning("Ошибка при вызове Gemini Scorer: %s", exc)
            return None, None, None
