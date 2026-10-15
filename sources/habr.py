import logging
import re
from datetime import datetime, timezone
from typing import List, Optional
from bs4 import BeautifulSoup
import feedparser
import httpx

from models.order import FreelanceOrder
from sources.base import BaseSource
from config.settings import settings

logger = logging.getLogger(__name__)


class HabrFreelanceSource(BaseSource):
    """
    Парсер заказов с Хабр Фриланс (freelance.habr.com) через RSS.
    """

    DEFAULT_RSS_URL = (
        "https://freelance.habr.com/tasks.rss?categories="
        "development_all_inclusive,development_backend,development_scripts,development_bots"
    )

    def __init__(self, rss_urls: Optional[List[str]] = None):
        super().__init__(name="habr")
        self.rss_urls = rss_urls or settings.HABR_RSS_URLS or [self.DEFAULT_RSS_URL]
        self._headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        }

    async def fetch_orders(self) -> List[FreelanceOrder]:
        orders: List[FreelanceOrder] = []

        async with httpx.AsyncClient(headers=self._headers, timeout=15.0, follow_redirects=True) as client:
            for url in self.rss_urls:
                try:
                    resp = await client.get(url)
                    if resp.status_code == 410:
                        logger.warning(
                            "Хабр Фриланс вернул 410 Gone (сервис freelance.habr.com официально закрыт с февраля 2025 года)."
                        )
                        continue
                    resp.raise_for_status()
                    parsed_feed = feedparser.parse(resp.text)

                    for entry in parsed_feed.entries:
                        order = self._parse_entry(entry)
                        if order:
                            orders.append(order)
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code == 410:
                        logger.warning(
                            "Хабр Фриланс вернул 410 Gone (сервис freelance.habr.com официально закрыт с февраля 2025 года)."
                        )
                    else:
                        logger.error("Ошибка HTTP Хабр Фриланс: %s", exc)
                except Exception as exc:
                    logger.error("Ошибка при получении RSS Хабр Фриланс (%s): %s", url, exc)

        logger.info("Хабр Фриланс: получено %d заказов", len(orders))
        return orders

    def _parse_entry(self, entry) -> Optional[FreelanceOrder]:
        try:
            link = getattr(entry, "link", "").strip()
            title = getattr(entry, "title", "").strip()
            if not link or not title:
                return None

            raw_desc = getattr(entry, "description", "") or getattr(entry, "summary", "")

            # Извлекаем чистый текст из HTML
            clean_desc, budget_extracted = self._clean_html_and_extract_budget(raw_desc)

            # Пробуем извлечь теги/категории
            tags = []
            if hasattr(entry, "tags"):
                tags = [t.term for t in entry.tags if hasattr(t, "term")]

            # Время публикации
            published_at = datetime.now(timezone.utc)
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                try:
                    published_at = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                except Exception:
                    pass

            order_id = FreelanceOrder.generate_id("habr", link)

            return FreelanceOrder(
                id=order_id,
                source="habr",
                title=title,
                url=link,
                description=clean_desc,
                budget_raw=budget_extracted,
                currency="RUB",
                published_at=published_at,
                tags=tags,
                raw_data={"link": link, "title": title},
            )
        except Exception as exc:
            logger.warning("Ошибка разбора записи Хабр Фриланс: %s", exc)
            return None

    def _clean_html_and_extract_budget(self, html_content: str) -> tuple[str, Optional[str]]:
        if not html_content:
            return "", None

        soup = BeautifulSoup(html_content, "html.parser")

        # Пытаемся найти строчку цены в HTML
        budget = None
        price_elem = soup.find(class_=re.compile(r"price|count|cost", re.I))
        if price_elem:
            budget = price_elem.get_text(strip=True)

        # Если не найден класс, ищем текст вида "Цена: 15 000 руб." или "Бюджет: ..."
        text = soup.get_text(separator="\n").strip()
        if not budget:
            budget_match = re.search(
                r"(?:Цена|Бюджет|Стоимость)[:\s]+(?:(?:до|от)\s+)?([\d\s]+(?:руб|₽|тенге|₸|\$|USD|EUR)?)",
                text,
                re.IGNORECASE,
            )
            if budget_match:
                budget = budget_match.group(0).strip()

        # Очищаем текст от лишних переводов строк
        clean_text = re.sub(r"\n{3,}", "\n\n", text).strip()
        return clean_text, budget
