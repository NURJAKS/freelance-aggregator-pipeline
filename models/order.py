import hashlib
from datetime import datetime, timezone
from typing import Any, Optional
from pydantic import BaseModel, Field


class FreelanceOrder(BaseModel):
    """
    Унифицированная модель заказа с фриланс-биржи или Telegram-канала.
    """
    id: str = Field(description="Уникальный идентификатор заказа (MD5/SHA256 хеш или ID источника)")
    source: str = Field(description="Название источника: habr, telegram, upwork, kwork")
    title: str = Field(description="Заголовок задачи или краткая выжимка")
    url: str = Field(description="Прямая ссылка на заказ или пост")
    description: str = Field(default="", description="Текст описания задачи")
    budget_raw: Optional[str] = Field(default=None, description="Строковое представление бюджета (например, '50 000 ₸', '$35/hr')")
    currency: Optional[str] = Field(default=None, description="Валюта заказа (RUB, KZT, USD, EUR)")
    published_at: Optional[datetime] = Field(default_factory=lambda: datetime.now(timezone.utc), description="Время публикации")
    tags: list[str] = Field(default_factory=list, description="Теги, навыки или категории")
    raw_data: dict[str, Any] = Field(default_factory=dict, description="Сырые данные источника для отладки")

    @classmethod
    def generate_id(cls, source: str, unique_key: str) -> str:
        """
        Генерирует уникальный хеш ID на основе источника и первичного ключа (URL или ID поста).
        """
        raw = f"{source.strip().lower()}:{unique_key.strip()}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
