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


class UpworkSource(BaseSource):
    """
    Парсер заказов с Upwork через RSS поиск (FastAPI, Python).
    """

    DEFAULT_RSS_URL = (
        "https://www.upwork.com/ab/feed/jobs/rss?q=FastAPI+OR+Python&paging=0%3B10&api_params=1"
    )

    def __init__(self, rss_urls: Optional[List[str]] = None):
        super().__init__(name="upwork")
        self.rss_urls = rss_urls or settings.UPWORK_RSS_URLS or [self.DEFAULT_RSS_URL]
        self._headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        }

    async def fetch_orders(self) -> List[FreelanceOrder]:
        orders: List[FreelanceOrder] = []

        async with httpx.AsyncClient(headers=self._headers, timeout=20.0, follow_redirects=True) as client:
            for url in self.rss_urls:
                try:
                    resp = await client.get(url)
                    if resp.status_code == 403:
                        logger.warning("Upwork RSS вернул 403 (защита Cloudflare/User-Agent). Пропускаем.")
                        continue
                    resp.raise_for_status()

                    parsed_feed = feedparser.parse(resp.text)
                    for entry in parsed_feed.entries:
                        order = self._parse_entry(entry)
                        if order:
                            orders.append(order)
                except Exception as exc:
                    logger.error("Ошибка при получении RSS Upwork (%s): %s", url, exc)

        logger.info("Upwork: получено %d заказов", len(orders))
        return orders

    def _parse_entry(self, entry) -> Optional[FreelanceOrder]:
        try:
            link = getattr(entry, "link", "").strip()
            # Убираем трекинговые GET-параметры из ссылки Upwork для чистой дедупликации
            clean_link = link.split("?")[0] if link else ""
            title = getattr(entry, "title", "").strip()
            if not clean_link or not title:
                return None

            raw_desc = getattr(entry, "description", "") or getattr(entry, "summary", "")
            clean_desc, budget, skills = self._parse_upwork_content(raw_desc)

            published_at = datetime.now(timezone.utc)
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                try:
                    published_at = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                except Exception:
                    pass

            order_id = FreelanceOrder.generate_id("upwork", clean_link)

            return FreelanceOrder(
                id=order_id,
                source="upwork",
                title=title,
                url=clean_link,
                description=clean_desc,
                budget_raw=budget,
                currency="USD",
                published_at=published_at,
                tags=skills or ["Upwork", "Python"],
                raw_data={"link": clean_link, "title": title},
            )
        except Exception as exc:
            logger.warning("Ошибка разбора заказа Upwork: %s", exc)
            return None

    def _parse_upwork_content(self, html_content: str) -> tuple[str, Optional[str], List[str]]:
        if not html_content:
            return "", None, []

        soup = BeautifulSoup(html_content, "html.parser")
        text = soup.get_text(separator="\n").strip()

        # Ищем Hourly Range или Budget
        budget = None
        hourly_match = re.search(r"Hourly Range:\s*([^\n<]+)", text, re.IGNORECASE)
        budget_match = re.search(r"Budget:\s*([^\n<]+)", text, re.IGNORECASE)

        if hourly_match:
            budget = f"Hourly: {hourly_match.group(1).strip()}"
        elif budget_match:
            budget = f"Budget: {budget_match.group(1).strip()}"

        # Ищем блок Skills
        skills = []
        skills_match = re.search(r"Skills:\s*([^\n<]+)", text, re.IGNORECASE)
        if skills_match:
            raw_skills = skills_match.group(1).split(",")
            skills = [s.strip() for s in raw_skills if s.strip()]

        clean_text = re.sub(r"\n{3,}", "\n\n", text).strip()
        return clean_text, budget, skills
