import logging
import re
from datetime import datetime, timezone
from typing import List, Optional
from bs4 import BeautifulSoup
import feedparser
import httpx

from models.order import FreelanceOrder
from sources.base import BaseSource

logger = logging.getLogger(__name__)


class FreelancehuntSource(BaseSource):
    """
    Парсер проектов с популярной биржи Freelancehunt (freelancehunt.com) через официальную RSS ленту.
    Отдает свежие заказы разработки, парсинга, ботов с указанием бюджетов.
    """

    DEFAULT_RSS_URL = "https://freelancehunt.com/projects.rss"

    def __init__(self, rss_urls: Optional[List[str]] = None):
        super().__init__(name="freelancehunt")
        self.rss_urls = rss_urls or [self.DEFAULT_RSS_URL]
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
                    resp.raise_for_status()
                    parsed_feed = feedparser.parse(resp.text)

                    for entry in parsed_feed.entries:
                        order = self._parse_entry(entry)
                        if order:
                            orders.append(order)
                except Exception as exc:
                    logger.error("Ошибка при получении RSS Freelancehunt (%s): %s", url, exc)

        logger.info("Freelancehunt: получено %d проектов", len(orders))
        return orders

    def _parse_entry(self, entry) -> Optional[FreelanceOrder]:
        try:
            link = getattr(entry, "link", "").strip()
            # Очищаем трекинг utm_source из ссылки
            clean_link = link.split("?")[0] if link else ""
            raw_title = getattr(entry, "title", "").strip()
            if not clean_link or not raw_title:
                return None

            # Во Freelancehunt цена часто идет в конце заголовка: "... - 5000UAH" или "... - 15000RUB"
            title, budget = self._extract_title_and_budget(raw_title)

            raw_desc = getattr(entry, "description", "") or getattr(entry, "summary", "")
            soup = BeautifulSoup(raw_desc, "html.parser")
            clean_desc = soup.get_text(separator="\n").strip()

            published_at = datetime.now(timezone.utc)
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                try:
                    published_at = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                except Exception:
                    pass

            order_id = FreelanceOrder.generate_id("freelancehunt", clean_link)

            return FreelanceOrder(
                id=order_id,
                source="freelancehunt",
                title=title,
                url=clean_link,
                description=clean_desc,
                budget_raw=budget,
                published_at=published_at,
                tags=["Freelancehunt"],
                raw_data={"link": clean_link, "title": title},
            )
        except Exception as exc:
            logger.warning("Ошибка разбора проекта Freelancehunt: %s", exc)
            return None

    def _extract_title_and_budget(self, raw_title: str) -> tuple[str, Optional[str]]:
        budget = None
        # Проверяем суффикс вида: " - 15000UAH" или " - 500$"
        budget_match = re.search(r"\s+-\s+([\d\s]+(?:UAH|RUB|USD|EUR|грн|руб|\$|€)?)$", raw_title, re.IGNORECASE)
        if budget_match:
            budget = budget_match.group(1).strip()
            clean_title = raw_title[: budget_match.start()].strip()
            return clean_title, budget

        return raw_title, None
