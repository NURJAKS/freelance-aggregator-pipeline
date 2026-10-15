import logging
import aiosqlite
from datetime import datetime, timedelta, timezone
from typing import Optional
from models.order import FreelanceOrder

logger = logging.getLogger(__name__)


class OrderStorage:
    """
    Асинхронное SQLite хранилище для дедупликации и истории найденных заказов.
    """

    def __init__(self, db_path: str = "freelance.db"):
        self.db_path = db_path

    async def init_db(self) -> None:
        """
        Создает необходимые таблицы и индексы при запуске приложения.
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS seen_orders (
                    id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    url TEXT NOT NULL,
                    title TEXT NOT NULL,
                    budget_raw TEXT,
                    currency TEXT,
                    published_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_seen_orders_source ON seen_orders (source);"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_seen_orders_created ON seen_orders (created_at);"
            )
            await db.commit()
            logger.info("Storage initialized with SQLite at %s", self.db_path)

    async def is_seen(self, order_id: str) -> bool:
        """
        Проверяет, был ли заказ с данным ID уже обработан ранее.
        """
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT 1 FROM seen_orders WHERE id = ? LIMIT 1;", (order_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return row is not None

    async def save_order_if_new(self, order: FreelanceOrder) -> bool:
        """
        Атомарно сохраняет заказ. Возвращает True, если заказ новый, или False, если уже существует.
        """
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute(
                    """
                    INSERT INTO seen_orders (
                        id, source, url, title, budget_raw, currency, published_at, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        order.id,
                        order.source,
                        order.url,
                        order.title,
                        order.budget_raw,
                        order.currency,
                        order.published_at.isoformat() if order.published_at else None,
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
                await db.commit()
                return True
            except aiosqlite.IntegrityError:
                # Заказ с таким ID уже есть в БД
                return False

    async def cleanup_old(self, days: int = 30) -> int:
        """
        Удаляет заказы старше указанного количества дней для экономии места.
        Возвращает количество удаленных записей.
        """
        cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "DELETE FROM seen_orders WHERE created_at < ?;", (cutoff_date,)
            )
            await db.commit()
            return cursor.rowcount

    async def get_stats(self) -> dict:
        """
        Возвращает статистику по найденным заказам: общее количество, за сегодня и по источникам.
        """
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            # Всего
            async with db.execute("SELECT COUNT(*) FROM seen_orders;") as cur:
                total = (await cur.fetchone())[0]

            # За сегодня
            async with db.execute("SELECT COUNT(*) FROM seen_orders WHERE created_at >= ?;", (today_start,)) as cur:
                today = (await cur.fetchone())[0]

            # По источникам
            by_source = {}
            async with db.execute("SELECT source, COUNT(*) FROM seen_orders GROUP BY source;") as cur:
                rows = await cur.fetchall()
                for src, count in rows:
                    by_source[src] = count

            return {
                "total": total,
                "today": today,
                "by_source": by_source,
            }

    async def get_recent_orders(self, limit: int = 5) -> list:
        """
        Возвращает последние найденные заказы.
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT id, source, title, url, budget_raw, currency, created_at
                FROM seen_orders
                ORDER BY created_at DESC
                LIMIT ?;
                """,
                (limit,),
            ) as cur:
                rows = await cur.fetchall()
                return [dict(row) for row in rows]

