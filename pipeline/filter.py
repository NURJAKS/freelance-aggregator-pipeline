import re
from typing import List, Tuple
from models.order import FreelanceOrder
from config.settings import settings


class OrderFilter:
    """
    Фильтр заказов по ключевым словам и стоп-словам.
    """

    def __init__(
        self,
        whitelist: List[str] = None,
        blacklist: List[str] = None,
    ):
        self.whitelist = [w.lower() for w in (whitelist or settings.KEYWORD_WHITELIST)]
        self.blacklist = [w.lower() for w in (blacklist or settings.KEYWORD_BLACKLIST)]

    def is_match(self, order: FreelanceOrder) -> Tuple[bool, str, List[str]]:
        """
        Проверяет заказ на соответствие фильтрам.
        Возвращает:
            - is_accepted: bool
            - reason: str (причина отклонения или одобрения)
            - matched_keywords: list[str] (список совпавших ключевых слов)
        """
        text = f"{order.title} {order.description}".lower()

        # 1. Проверка на стоп-слова
        for bad_word in self.blacklist:
            pattern = rf"\b{re.escape(bad_word)}\b"
            if re.search(pattern, text):
                return False, f"Содержит стоп-слово: '{bad_word}'", []

        # 2. Проверка на целевые ключевые слова
        matched = []
        for good_word in self.whitelist:
            pattern = rf"\b{re.escape(good_word)}\b"
            if re.search(pattern, text):
                matched.append(good_word)

        if matched:
            return True, f"Совпадение по ключевым словам: {', '.join(matched)}", matched

        return False, "Нет совпадений с целевыми ключевыми словами", []
