<<<<<<< HEAD
# Finance AI Helper Telegram Bot

[![Python Version][python-badge]][python-link]
[![Telegram Bot API][tg-badge]][tg-link]
[![Code style: black][black-badge]][black-link]
[![License: MIT][license-badge]][license-link]

Интеллектуальный Telegram-бот для управления личными финансами и мониторинга инвестиционного портфеля в Т-Инвестициях. Бот объединяет возможности официального API Т-Банка и мощь ИИ-агентов на базе LangGraph для глубокого анализа активов.

## 🚀 Ключевые возможности

*   **Гибкий импорт данных**:
    *   Подключение через API-токен Т-Инвестиций для получения актуальных данных о портфеле.
    *   Парсинг брокерских отчетов в формате Excel (`.xlsx`) для анализа исторических данных.
*   **Финансовый AI-Агент**: Полноценный чат-бот на базе **Google Gemini**, способный отвечать на вопросы о состоянии портфеля, анализировать новости и давать рекомендации.
*   **Анализ новостей**: Автоматический сбор и суммаризация новостей по интересующим активам.
*   **Асинхронная архитектура**: Полностью асинхронный код на базе `asyncio` и `aiogram` обеспечивает высокую производительность и отзывчивость.

## 🏛️ Архитектура

Проект построен на принципах слоистой архитектуры, что обеспечивает низкую связанность модулей и легкость масштабирования.

```mermaid
graph TD
    subgraph Пользователь
        A["👨‍💻 Пользователь"]
    end

    subgraph Telegram
        B["✈️ Aiogram Bot"]
    end

    subgraph Приложение
        C["🤖 AI Агент <br>(LangGraph)"]
        D["⚙️ Сервисы"]
        E["🗃️ База данных <br>(PostgreSQL)"]
    end
    
    subgraph Внешние API
        F["📈 API Т-Инвестиций"]
        G["🧠 Google Gemini API"]
    end

    A -- "Текстовые команды" --> B
    B -- "Запросы" --> C
    C -- "Использует инструменты" --> D
    D -- "Обращается к" --> F
    D -- "Обращается к" --> G
    D -- "Сохраняет/читает" --> E
```

## 🛠️ Технологический стек

*   **Язык**: Python 3.13+
*   **Telegram Framework**: `aiogram 3.x`
*   **AI**: `langgraph`, `langchain`, `Google Gemini` / `LiteLLM`
*   **База данных**: `PostgreSQL` + `SQLAlchemy 2.0` (асинхронный драйвер `asyncpg`)
*   **Инвестиции**: `t-tech-investments` (SDK для T-Invest API)

## ⚙️ Установка и запуск

Выполните следующие шаги для локального развертывания проекта.

### 1. Предварительные требования

*   Python 3.13 или новее
*   Установленный и запущенный сервер PostgreSQL

### 2. Установка

```bash
# 1. Клонируйте репозиторий
git clone https://github.com/your_username/broker_agent.git
cd broker_agent

# 2. Создайте и активируйте виртуальное окружение
python -m venv .venv
# Для Windows:
# .venv\Scripts\activate
# Для macOS/Linux:
source .venv/bin/activate

# 3. Установите зависимости
pip install -r requirements.txt
```

### 3. Конфигурация

Проект использует файл `config.py` для хранения токенов и ключей API.

1.  Скопируйте файл-пример:
    ```bash
    cp app/core/config.py.example.txt app/core/config.py
    ```
2.  Откройте `app/core/config.py` и вставьте ваши реальные токены.

| Переменная       | Описание                                           |
| ---------------- | -------------------------------------------------- |
| `TELEGRAM_TOKEN` | Токен для вашего Telegram-бота.                    |
| `T_INVEST_TOKEN` | Токен для API Т-Инвестиций.                        |
| `GOOGLE_API_KEY` | API-ключ для Google Gemini.                        |
| `BASE_URL`       | URL для эндпоинта LiteLLM (если используется).     |
*Не забудьте также настроить подключение к базе данных в `app/database/session.py`.*

### 4. Запуск

После установки и конфигурации запустите бота:

```bash
python main.py
```

## 📁 Структура проекта

<details>
<summary>Нажмите, чтобы увидеть структуру</summary>

```text
broker_agent/
├── main.py              # Точка входа в приложение
├── requirements.txt     # Зависимости проекта 
├── app/                 # Основной пакет приложения
│   ├── agent/           # Логика AI-агента и графа LangGraph
│   ├── bot/             # Обработчики команд Telegram и FSM-состояния
│   ├── core/            # Конфигурация и глобальные настройки
│   ├── database/        # Модели таблиц, сессии и CRUD-запросы
│   ├── services/        # Бизнес-логика (API, расчеты, файлы)
│   └── utils/           # Вспомогательные утилиты
└── ...
```
</details>

[python-badge]: https://img.shields.io/badge/Python-3.13+-blue.svg
[python-link]: https://www.python.org/downloads/
[tg-badge]: https://img.shields.io/badge/Telegram-Aiogram%203.x-blue
[tg-link]: https://github.com/aiogram/aiogram
[black-badge]: https://img.shields.io/badge/code%20style-black-000000.svg
[black-link]: https://github.com/psf/black
[license-badge]: https://img.shields.io/badge/License-MIT-yellow.svg
[license-link]: https://opensource.org/licenses/MIT
```text
=======
# Valor Bot

Асинхронный Telegram-бот с единым каталогом бумаг T-Invest и MOEX и ведением пользовательского инвестиционного портфеля. Бот поддерживает интерактивный поиск бумаг, ручное добавление бумаг и синхронизацию позиций из T-Invest.

## Стек

- Python 3.13+
- aiogram 3
- PostgreSQL, SQLAlchemy 2 и asyncpg
- MOEX ISS API через aiohttp
- T-Invest API через t-tech-investments
- openpyxl для брокерских Excel-отчетов
- BeautifulSoup для разбора новостей RBC

## Структура

```text
main.py                    запуск Telegram-бота
update_instruments.py      обновление общего справочника
app/bot/                   handlers, клавиатуры и FSM
app/core/                  настройки и логирование
app/database/              ORM-модели, lifecycle БД и запросы
app/services/              единый каталог, MOEX, T-Invest, RBC и Excel
app/utils/                 форматирование и сбор новостей
tests/                     unit-тесты
```

Поток основного запроса: Telegram handler -> сервис/CRUD -> PostgreSQL или внешний API. Справочник `instruments` объединяет T-Invest и MOEX и используется для поиска и сопоставления по тикеру, ISIN, FIGI или UID.

## Поиск бумаги

В разделах «Облигации» и «Акции и фонды» пользователь вводит часть названия, тикер или ISIN. В поиск акций и фондов также входят неоактивы T-Invest с тикерами вида `NBISperpA`. Бот ищет совпадения в справочнике и показывает inline-кнопки с результатами. Результаты выдаются страницами, а после выбора бот отправляет карточку бумаги с текущей ценой и основными параметрами.

Если неоактив отсутствует в общем справочнике, бот использует сохранённый через
`/set_token` токен пользователя для поиска в T-Invest, записывает найденный
инструмент в `instruments` и повторяет поиск уже по БД. Этот же токен используется
для обновления цены перед показом карточки и портфеля; сам токен пользователю не
возвращается.

В карточке доступна кнопка «Добавить в портфель». После ее нажатия бот запрашивает среднюю цену покупки и количество бумаг в формате `985.50 10`.


## Установка

```bash
python -m venv .venv
python -m pip install -r requirements.txt
```

SDK `t-tech-investments` загружается из официального package index T-Bank,
который уже указан в `requirements.txt`.

Приложение читает конфигурацию только из окружения:

| Переменная | Назначение |
| --- | --- |
| `TELEGRAM_TOKEN` | токен Telegram-бота |
| `DATABASE_URL` | async URL PostgreSQL вида `postgresql+asyncpg://user:password@host/database` |
| `MOEX_REFRESH_INTERVAL_SECONDS` | интервал обновления данных MOEX в секундах, минимум 60, по умолчанию 900 |
| `T_INVEST_TOKEN` | необязательный read-only токен для общего каталога и актуальных цен T-Invest |
| `SSL_TBANK_VERIFY` | использовать сертификат Russian Trusted Root CA из официального SDK T-Invest; по умолчанию `true` |

Пример значений находится в `.env.example`. При запуске приложение автоматически загружает простой `.env` из корня проекта, не перезаписывая уже экспортированные переменные.

PowerShell:

```powershell
$env:TELEGRAM_TOKEN="..."
$env:DATABASE_URL="postgresql+asyncpg://postgres:password@localhost:5432/valor_bot"
$env:T_INVEST_TOKEN="..."
python main.py
```

Bash:

```bash
export TELEGRAM_TOKEN="..."
export DATABASE_URL="postgresql+asyncpg://postgres:password@localhost:5432/valor_bot"
export T_INVEST_TOKEN="..."
python main.py
```

## База данных и миграции

При старте приложения выполняется `alembic upgrade head`. Для ручного применения миграций из `.env`:

```bash
python migrate.py
```

При прямом вызове Alembic переменная `DATABASE_URL` должна быть экспортирована в окружение:

```bash
alembic -c alembic.ini upgrade head
```

Модели находятся в `app/database/models.py`, а ревизии в `migrations/versions/`. Токен и портфель связаны с `app_users`; удаление пользователя удаляет их каскадно. Инструменты, на которые ссылается портфель, удалить нельзя.

## Справочник инструментов

После первичной настройки БД и затем по расписанию запускайте:

```bash
python update_instruments.py
```

Команда параллельно получает акции, облигации, ETF и неоактивы из T-Invest и акции с
облигациями из MOEX ISS, объединяет их и выполняет upsert в `instruments`.
Совпадения объединяются прежде всего по ISIN. Для бумаг T-Invest также
сохраняются UID, FIGI, class code и биржа, поэтому в каталог попадают доступные
через брокера инструменты СПБ Биржи. Неоактивы выбираются из метода `Futures`
по тикерам `*perpA` и показываются отдельным типом в карточке.

Если T-Invest вернул цену последней сделки, она имеет приоритет. Если цены нет
или инструмент отсутствует у брокера, используется цена MOEX. При временной
ошибке одного источника refresh продолжается по данным второго. Без
`T_INVEST_TOKEN` бот работает в прежнем режиме только с MOEX.

Перед показом карточки или пользовательского портфеля бот дополнительно
запрашивает последние сделки по UID у T-Invest. Этот live-запрос не затирает
fallback: при пустом ответе или ошибке остаётся последняя сохранённая цена MOEX.

При запуске бота обновление общего справочника выполняется в фоновой задаче сразу после
инициализации базы, а затем каждые `MOEX_REFRESH_INTERVAL_SECONDS` секунд. Ошибка
одного обновления не останавливает бота. Портфель при каждом просмотре берет свежие
данные из `instruments`, поэтому новые цены становятся доступны без повторного
добавления бумаги.

Полная загрузка T-Invest включает несколько тысяч инструментов и пачки последних
цен, поэтому ей разрешено выполняться до двух минут. Бот и сохраненный справочник
остаются доступны во время этого фонового обновления.

Если в системе gRPC не доверяет цепочке сертификатов T-Invest и пишет
`CERTIFICATE_VERIFY_FAILED: self signed certificate in certificate chain`, оставьте
`SSL_TBANK_VERIFY=true`. SDK загрузит предназначенный для этого сертификат
`RussianTrustedRootCA.pem`. Проверка TLS при этом не отключается. Даже если T-Invest
временно недоступен, поиск продолжит работать по сохраненному справочнику БД, а
фоновое обновление — по данным MOEX.

## Проверки

```bash
python -m unittest discover -s tests -v
python -m compileall -q main.py update_instruments.py app tests
```

Live smoke-тест источников (читает только переменные окружения процесса и не
загружает `.env`):

```bash
python -m tests.live_api_smoke
```

Без экспортированного `T_INVEST_TOKEN` проверяется только MOEX; с токеном скрипт
также проверяет каталог T-Invest, цены и коллизии объединённого результата.

Для проверки реального PostgreSQL используйте тестовые данные с автоматической очисткой:

```powershell
$env:RUN_DB_TESTS="1"
python -m unittest tests.test_database_integration -v
```
>>>>>>> f04103d (version 1.0.0)
