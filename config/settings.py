from typing import List, Optional
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Конфигурация приложения, загружаемая из переменных окружения или .env файла.
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Telegram Bot
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""

    # Telethon Userbot (для парсинга каналов)
    TELEGRAM_API_ID: Optional[int] = 0
    TELEGRAM_API_HASH: str = ""
    TELEGRAM_PHONE: str = ""
    TELEGRAM_SESSION_NAME: str = "freelance_userbot"

    @field_validator("TELEGRAM_API_ID", mode="before")
    @classmethod
    def parse_api_id(cls, v):
        if v is None or v == "":
            return 0
        return int(v)

    # Telegram каналы для мониторинга
    TELEGRAM_CHANNELS: List[str] = [
        "freelance_it_job",
        "forfreelance",
        "freelancedev",
        "parttime_it",
    ]

    # RSS Источники: Хабр Фриланс
    HABR_RSS_URLS: List[str] = [
        "https://freelance.habr.com/tasks.rss?categories=development_all_inclusive,development_backend,development_scripts,development_bots",
    ]

    # RSS Источники: Kwork (категории: скрипты/боты, парсинг данных)
    KWORK_RSS_URLS: List[str] = [
        "https://kwork.ru/rss/projects.xml",
    ]

    # RSS Источники: Upwork (поиск Python/FastAPI)
    UPWORK_RSS_URLS: List[str] = [
        "https://www.upwork.com/ab/feed/jobs/rss?q=FastAPI+OR+Python&paging=0%3B10&api_params=1",
    ]

    # Gemini AI Scorer (Опционально)
    GEMINI_API_KEY: str = ""
    AI_SCORING_ENABLED: bool = False

    # Database
    DATABASE_PATH: str = "freelance.db"

    # Polling & Workers
    POLL_INTERVAL_SECONDS: int = 180
    LOG_LEVEL: str = "INFO"

    # Ключевые слова для фильтрации (положительные)
    KEYWORD_WHITELIST: List[str] = [
        "python",
        "fastapi",
        "django",
        "flask",
        "aiohttp",
        "парсинг",
        "парсер",
        "парсить",
        "scraping",
        "scraper",
        "crawler",
        "бот",
        "боты",
        "bot",
        "backend",
        "бэкенд",
        "telethon",
        "aiogram",
        "pyrogram",
        "selenium",
        "playwright",
    ]

    # Минус-слова (нерелевантные направления)
    KEYWORD_BLACKLIST: List[str] = [
        "1c",
        "1с",
        "bitrix",
        "битрикс",
        "wordpress",
        "вордпресс",
        "дизайн",
        "дизайнер",
        "figma",
        "копирайт",
        "рерайт",
        "seo",
        "таргет",
        "smm",
        "курсовая",
        "диплом",
        "контрольная",
    ]


settings = Settings()
