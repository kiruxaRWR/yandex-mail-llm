import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from html import escape
from dotenv import load_dotenv

from db import get_connection
from notifier import send_notification

load_dotenv(Path(__file__).with_name(".env"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger("scheduler")

NOTIFY_DAYS_BEFORE = int(os.getenv("NOTIFY_DAYS_BEFORE", "3"))


def format_event_message(event):
    (
        event_id,
        event_type,
        title,
        event_date,
        event_time,
        description,
        links
    ) = event

    links = links or {}

    event_links = links.get("event_links") or []
    email_links = links.get("email_links") or []

    text = (
        "🔔 Напоминание о событии\n\n"
        f"Тип: {event_type}\n"
        f"Название: {title or 'Без названия'}\n"
        f"Дата: {event_date}\n"
    )

    if event_time:
        text += f"Время: {event_time}\n"

    if description:
        text += f"\nЧто нужно сделать:\n{description}\n"

    if event_links:
        text += "\nПолезные ссылки:\n"

        for url in event_links[:5]:
            text += f"• {url}\n"

    if email_links and email_links != event_links:
        text += "\nСсылки из письма:\n"

        for url in email_links[:5]:
            text += f"• {url}\n"

    return text
def get_upcoming_events(conn):
    now = datetime.now().date()
    limit_date = now + timedelta(days=NOTIFY_DAYS_BEFORE)

    logger.info(
        "Ищу события с %s по %s",
        now,
        limit_date,
    )

    events = conn.execute(
        """
        SELECT
            e.id,
            e.type,
            e.title,
            e.event_date,
            e.event_time,
            e.description,
            e.links
        FROM events e
        WHERE e.status = 'pending'
          AND e.event_date IS NOT NULL
          AND e.event_date BETWEEN %s AND %s
        ORDER BY e.event_date, e.event_time NULLS LAST;
        """,
        (now, limit_date)
    ).fetchall()

    logger.info("Найдено событий для уведомления: %d", len(events))

    return events


def mark_notified(conn, event_id):
    conn.execute(
        """
        UPDATE events
        SET status = 'notified'
        WHERE id = %s;
        """,
        (event_id,)
    )


def notify_upcoming_events():
    logger.info("Запуск проверки событий")

    with get_connection() as conn:
        events = get_upcoming_events(conn)

        if not events:
            logger.info("Подходящих событий нет.")
            return

        for event in events:
            ( event_id, event_type, title, event_date, event_time, description, links ) = event

            logger.info(
                "Отправляю уведомление: id=%s, title=%s",
                event_id,
                title,
            )

            text = (
                f"Напоминание о событии\n"
                f"Тип: {event_type}\n"
                f"Название: {title or 'Без названия'}\n"
                f"Дата: {event_date}\n"
            )

            if event_time:
                text += f"Время: {event_time}\n"

            if description:
                text += f"\n{description}"

            if links:
                text += f"\n{links['event_links']}"
                text += f"\n{links['email_links']}"
            
            send_notification(text)

            mark_notified(conn, event_id)
            conn.commit()

            logger.info("Уведомление отправлено и событие отмечено.")


def main():
    notify_upcoming_events()
    logger.info("Проверка событий завершена.")


if __name__ == "__main__":
    main()