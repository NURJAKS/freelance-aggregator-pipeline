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


class KworkSource(BaseSource):
    """
    Парсер проектов с биржи Kwork (kwork.ru) через RSS.
    """

    DEFAULT_RSS_URL = "https://kwork.ru/rss/projects.xml"

    def __init__(self, rss_urls: Optional[List[str]] = None):
        super().__init__(name="kwork")
        self.rss_urls = rss_urls or settings.KWORK_RSS_URLS or [self.DEFAULT_RSS_URL]
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
                    logger.error("Ошибка при получении RSS Kwork (%s): %s", url, exc)

        logger.info("Kwork: получено %d проектов", len(orders))
        return orders

    def _parse_entry(self, entry) -> Optional[FreelanceOrder]:
        try:
            link = getattr(entry, "link", "").strip()
            title = getattr(entry, "title", "").strip()
            if not link or not title:
                return None

            raw_desc = getattr(entry, "description", "") or getattr(entry, "summary", "")
            clean_desc, budget = self._parse_description_and_budget(raw_desc)

            published_at = datetime.now(timezone.utc)
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                try:
                    published_at = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                except Exception:
                    pass

            order_id = FreelanceOrder.generate_id("kwork", link)

            return FreelanceOrder(
                id=order_id,
                source="kwork",
                title=title,
                url=link,
                description=clean_desc,
                budget_raw=budget,
                currency="RUB",
                published_at=published_at,
                tags=["Kwork"],
                raw_data={"link": link, "title": title},
            )
        except Exception as exc:
            logger.warning("Ошибка разбора проекта Kwork: %s", exc)
            return None

    def _parse_description_and_budget(self, html_content: str) -> tuple[str, Optional[str]]:
        if not html_content:
            return "", None

        soup = BeautifulSoup(html_content, "html.parser")
        text = soup.get_text(separator="\n").strip()

        # Ищем бюджет в Kwork (обычно: "Желаемый бюджет: до 10 000 руб." или "Бюджет: 5 000 руб.")
        budget = None
        budget_match = re.search(
            r"(?:Желаемый бюджет|Допустимый бюджет|Бюджет|Цена)[:\s]+(?:(?:до|от)\s+)?([\d\s]+(?:руб|₽)?)",
            text,
            re.IGNORECASE,
        )
        if budget_match:
            budget = budget_match.group(0).strip()

        clean_text = re.sub(r"\n{3,}", "\n\n", text).strip()
        return clean_text, budget
