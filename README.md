# 🚀 freelance-aggregator-pipeline

Автономный асинхронный сервис сбора, фильтрации и моментальных уведомлений в Telegram о новых заказах на фрилансе и гибких контрактных подработках (15–25 ч/неделю) для **Python / Backend разработчика**.

---

## 🎯 Стек и специализация
- **Ключевые навыки:** Python, FastAPI, Django, Telegram-боты (Aiogram, Telethon), Web Scraping / Парсинг данных, API интеграции.
- **Таймзоны:** Кызылорда / Казахстан (UTC+5), СНГ (UTC+3), Европа (CET), асинхронные контракты.
- **Архитектура:** Чистый асинхронный Python 3.12+, Pydantic v2, aiosqlite, httpx, feedparser, BeautifulSoup4, Telethon, Google Gemini (Flash).

---

## 📡 Источники данных
1. **Freelancehunt** (`sources/freelancehunt.py`) — официальная RSS лента свежих заказов с парсингом бюджетов в реальном времени.
2. **Kwork** (`sources/kwork.py`) — RSS лента биржи проектов с извлечением бюджетов и описаний.
3. **Upwork** (`sources/upwork.py`) — RSS лента поиска контрактов (`FastAPI OR Python`, Hourly $20–$50, извлечение рейтов и навыков).
4. **Telegram Каналы** (`sources/telegram.py`) — MTProto Userbot на Telethon для мониторинга каналов (`@freelance_it_job`, `@forfreelance`, `@freelancedev`, `@parttime_it`).
5. **Хабр Фриланс** (`sources/habr.py`) — обработчик RSS (с корректной обработкой статуса 410 Gone в связи с закрытием платформы в 2025 г.).

---

## 🏗️ Архитектура проекта

```
freelance-aggregator-pipeline/
├── config/
│   ├── __init__.py
│   └── settings.py          # Настройки, таймауты, белые и черные списки ключевых слов
├── models/
│   ├── __init__.py
│   └── order.py             # Унифицированный датакласс FreelanceOrder
├── storage/
│   ├── __init__.py
│   └── db.py                # SQLite дедупликатор на aiosqlite
├── pipeline/
│   ├── __init__.py
│   ├── filter.py            # Фильтр стоп-слов и целевых технологий
│   └── scorer.py            # Опциональный AI-скоринг и советы по отклику на базе Gemini
├── sources/
│   ├── __init__.py
│   ├── base.py              # Базовый класс BaseSource
│   ├── freelancehunt.py     # RSS Freelancehunt
│   ├── kwork.py             # RSS Kwork
│   ├── upwork.py            # RSS Upwork
│   ├── telegram.py          # Telethon каналы
│   └── habr.py              # RSS Хабр Фриланс
├── notify/
│   ├── __init__.py
│   └── telegram.py          # Отправка структурированных HTML-карточек
├── tests/
│   ├── test_smoke.py        # Базовый smoke-тест моделей и БД
│   └── test_sources.py      # Интеграционный тест всех источников и пайплайна
├── .env.example             # Шаблон переменных окружения
├── requirements.txt         # Зависимости проекта
└── main.py                  # Главный цикл опроса
```

---

## ⚙️ Установка и запуск

### 1. Клонирование и виртуальное окружение
```bash
git clone https://github.com/NURJAKS/freelance-aggregator-pipeline.git
cd freelance-aggregator-pipeline
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Настройка `.env`
Скопируйте пример конфигурации:
```bash
cp .env.example .env
```
Заполните параметры:
- `TELEGRAM_BOT_TOKEN` и `TELEGRAM_CHAT_ID` — для получения мгновенных уведомлений.
- `TELEGRAM_API_ID` и `TELEGRAM_API_HASH` (опционально) — для чтения Telegram-каналов через Telethon.
- `GEMINI_API_KEY` (опционально) — для автоматической оценки привлекательности заказа и подсказок для первого сообщения клиенту.

### 3. Проверка тестов
```bash
.venv/bin/python tests/test_smoke.py
.venv/bin/python tests/test_sources.py
```

### 4. Запуск сервиса
```bash
.venv/bin/python main.py
```
Сервис будет непрерывно опрашивать подключенные источники (раз в 3 минуты по умолчанию), дедуплицировать в SQLite, фильтровать и присылать подходящие заказы вам в Telegram.
