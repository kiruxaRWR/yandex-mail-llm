# yandex-mail-llm

Локальный конвейер умного анализа входящей почты Яндекса: письма забираются по IMAP,
классифицируются LLM-моделями через [RouterAI](https://routerai.ru), важные события
(дедлайны, встречи, регистрации, оплаты) сохраняются в PostgreSQL, а напоминания о них
отправляются в VK / Telegram.

## Как это работает

```
IMAP (imap.yandex.ru) ──> mail-analyzer.py ──> PostgreSQL ──> scheduler.py ──> notifier.py ──> VK/Telegram
                                   │
                                   ├── classifier.py   — категория письма (RouterAI Decisions API)
                                   └── DeepSeek        — глубокий анализ для категории `events`
```

1. **`mail-analyzer.py`** — основной конвейер:
   - забирает последние письма из INBOX пачками (`MAIL_BATCH_SIZE`, не больше `MAIL_MAX_EMAILS`);
   - сохраняет каждое письмо в таблицу `emails` (дедупликация по `Message-ID`);
   - быстро классифицирует письмо через RouterAI Decisions API
     (категории: работа, финансы, события, уведомления, рассылки, личное, спам);
   - для категории `events` запускает глубокий анализ
     через DeepSeek (OpenAI-совместимый API RouterAI): извлекает события с датами,
     описаниями и ссылками;
   - найденные события кладёт в таблицу `events`.
2. **`scheduler.py`** — находит события со статусом `pending` на ближайшие
   `NOTIFY_DAYS_BEFORE` дней и отправляет напоминания, после чего помечает их `notified`.
3. **`notifier.py`** — отправка уведомлений в VK (API `messages.send`); там же есть
   отправка через Telegram Bot API (`python-telegram-bot`).
4. **`imap_client.py`** — подключение к IMAP (открытие INBOX). Собственной логики
   повторов нет: обрывы соединения обрабатываются перезапусками на уровне конвейера.
5. **`run-mail-pipeline.ps1`** — запускает анализ и рассылку последовательно, ведёт лог
   в `pipeline.log`; упавший шаг перезапускает до 3 раз с увеличивающимися интервалами
   (30 → 60 → 120 сек). Удобно вешать на Планировщик Windows.

## Структура проекта

| Файл | Назначение |
|---|---|
| `mail-analyzer.py` | Основной конвейер: IMAP → классификация → глубокий анализ → БД |
| `classifier.py` | Быстрая классификация писем (RouterAI Decisions API) |
| `imap_client.py` | IMAP-подключение (открытие INBOX) |
| `db.py` | Схема БД и работа с PostgreSQL (psycopg 3) |
| `scheduler.py` | Выборка предстоящих событий и напоминания |
| `notifier.py` | Отправка уведомлений в VK / Telegram |
| `SQL/Table Creation.sql` | Базовая схема: `emails`, `email_analysis` |
| `.env.example` | Шаблон переменных окружения |

## Установка

Требуется Python 3.10+ и PostgreSQL.

```powershell
git clone <url-репозитория>
cd yandex-mail-llm
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Настройка

1. Создайте базу данных:

```sql
CREATE DATABASE "mail-agent";
```

2. Скопируйте `.env.example` в `.env` и заполните значения:

```powershell
Copy-Item .env.example .env
```

- `YANDEX_EMAIL` / `YANDEX_APP_PASSWORD` — почта Яндекса и **пароль приложения**
  (Настройки → «Безопасность» → «Пароли приложений», обычный пароль не подойдёт);
- `ROUTERAI_API_KEY`, `ROUTERAI_MODEL_DEEPSEEK`, `ROUTERAI_DECISION_MODEL` — ключ и модели RouterAI;
- `POSTGRES_DSN` — строка подключения к PostgreSQL;
- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`, `VK_GROUP_TOKEN` / `VK_USER_ID` — каналы уведомлений;
- необязательные: `MAIL_BATCH_SIZE` / `MAIL_MAX_EMAILS` (размер пачки и лимит писем за
  запуск), `CLASSIFY_CONFIDENCE_HIGH` / `CLASSIFY_CONFIDENCE_REVIEW` (пороги уверенности
  классификации), `NOTIFY_DAYS_BEFORE` (за сколько дней напоминать о событии).

3. Создайте таблицы. Базовые (`emails`, `email_analysis`) создаются автоматически при
   первом запуске (`init_db`) или вручную из `SQL/Table Creation.sql`.
   Колонки классификации и таблицы `events` / `email_decisions` нужно создать отдельно:

```sql
ALTER TABLE emails
    ADD COLUMN IF NOT EXISTS category TEXT,
    ADD COLUMN IF NOT EXISTS category_confidence REAL,
    ADD COLUMN IF NOT EXISTS needs_review BOOLEAN;

CREATE TABLE IF NOT EXISTS events (
    id BIGSERIAL PRIMARY KEY,
    email_id BIGINT REFERENCES emails(id) ON DELETE CASCADE,
    source_message_id TEXT,
    type TEXT,
    title TEXT,
    event_date DATE,
    event_time TIME,
    description TEXT,
    links JSONB,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_events UNIQUE (source_message_id, type, title, event_date, event_time)
);

CREATE TABLE IF NOT EXISTS email_decisions (
    id BIGSERIAL PRIMARY KEY,
    email_id BIGINT NOT NULL REFERENCES emails(id) ON DELETE CASCADE,
    model TEXT,
    category TEXT,
    category_probability REAL,
    raw_response JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

## Запуск

```powershell
.venv\Scripts\python.exe mail-analyzer.py   # анализ почты
.venv\Scripts\python.exe scheduler.py       # напоминания о событиях
```

или одной командой (с логом в `pipeline.log`):

```powershell
powershell -ExecutionPolicy Bypass -File .\run-mail-pipeline.ps1
```

> В `run-mail-pipeline.ps1` прописан абсолютный путь к проекту — замените его на свой.

## Планировщик Windows и обработка сбоев

Задача Планировщика запускает скрипт конвейера:

```text
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "<путь к проекту>\run-mail-pipeline.ps1"
```

- В действии задачи укажите **рабочую папку** (Working Directory) — путь к проекту.
  Без неё дочерние процессы Python стартуют в `C:\Windows\system32` и не находят скрипты.
  (`Set-Location` в PowerShell этот каталог не меняет, поэтому скрипт дополнительно
  выставляет `[Environment]::CurrentDirectory`.)
- Python-скрипты не перехватывают исключения: любая ошибка (IMAP, БД, RouterAI)
  завершает шаг с ненулевым кодом выхода.
- `run-mail-pipeline.ps1` перезапускает упавший шаг до 3 раз с увеличивающимися
  интервалами 30 / 60 / 120 сек (настраивается переменными `$MaxRestarts` и
  `$RetryDelays` в начале скрипта) и пишет всё в `pipeline.log`, включая трейсбеки.
- Детерминированные ошибки (например, невалидный JSON в ответе LLM) перезапусками
  не лечатся — причину смотрите в `pipeline.log`.

## Безопасность

- Файл `.env` с реальными секретами **не хранится в репозитории** (см. `.gitignore`).
- Шаблон переменных — `.env.example`.
- Если секрет всё же попал в историю репозитория — немедленно перевыпустите его
  (пароль приложения Яндекса, ключи RouterAI/VK, токен Telegram-бота).
