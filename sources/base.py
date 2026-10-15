from abc import ABC, abstractmethod
from typing import List
from models.order import FreelanceOrder


class BaseSource(ABC):
    """
    Абстрактный базовый класс для любого источника заказов (Хабр, Upwork, Telegram, Kwork).
    """

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    async def fetch_orders(self) -> List[FreelanceOrder]:
        """
        Получает свежие заказы из источника и возвращает их в виде списка FreelanceOrder.
        """
        pass

    async def close(self) -> None:
        """
        Освобождает ресурсы источника (сессии, соединения), если необходимо.
        """
        pass
