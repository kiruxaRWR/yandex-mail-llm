import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg.types.json import Jsonb

load_dotenv(Path(__file__).with_name(".env"))

DSN = os.getenv("POSTGRES_DSN")


def get_connection():
    return psycopg.connect(DSN)

from datetime import date, time as dt_time


def parse_date(value):
    if not value:
        return None

    return date.fromisoformat(value)


def parse_time(value):
    if not value:
        return None

    return dt_time.fromisoformat(value)


def save_events_from_analysis(
    conn,
    email_id,
    source_message_id,
    analysis,
    email_links,
):
    events = analysis.get("events") or []

    for event in events:
        event_type = (event.get("type") or "other").strip()
        title = event.get("title")
        event_date = parse_date(event.get("date"))
        event_time = parse_time(event.get("time"))
        description = event.get("description")

        event_links = event.get("links") or []

        if not event_links:
            event_links = email_links

        links = {
            "event_links": event_links,
            "email_links": email_links,
        }

        if not event_date:
            continue

        conn.execute(
            """
            INSERT INTO events
                (email_id, source_message_id, type, title,
                 event_date, event_time, description, links)
            VALUES
                (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT
                (source_message_id, type, title, event_date, event_time)
            DO NOTHING;
            """,
            (
                email_id,
                source_message_id,
                event_type,
                title,
                event_date,
                event_time,
                description,
                Jsonb(links),
            )
        )

def init_db():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS emails (
                id BIGSERIAL PRIMARY KEY,
                message_id TEXT NOT NULL UNIQUE,
                imap_uid TEXT,
                folder TEXT NOT NULL DEFAULT 'INBOX',
                sender TEXT,
                subject TEXT,
                received_at TIMESTAMPTZ,
                raw_text TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );

            CREATE TABLE IF NOT EXISTS email_analysis (
                id BIGSERIAL PRIMARY KEY,
                email_id BIGINT NOT NULL REFERENCES emails(id) ON DELETE CASCADE,
                model TEXT NOT NULL,
                analysis JSONB NOT NULL,
                tokens_prompt INTEGER,
                tokens_completion INTEGER,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );

            ALTER TABLE emails
                ADD COLUMN IF NOT EXISTS imap_uid TEXT;

            CREATE INDEX IF NOT EXISTS idx_emails_message_id
                ON emails(message_id);

            CREATE INDEX IF NOT EXISTS idx_emails_received_at
                ON emails(received_at DESC);

            CREATE INDEX IF NOT EXISTS idx_email_analysis_email_id
                ON email_analysis(email_id);
        """)


def email_exists(conn, message_id):
    row = conn.execute(
        "SELECT 1 FROM emails WHERE message_id = %s",
        (message_id,)
    ).fetchone()

    return row is not None


def insert_email(conn, message_id, imap_uid, folder, sender, subject, received_at, raw_text):
    row = conn.execute(
        """
        INSERT INTO emails
            (message_id, imap_uid, folder, sender, subject, received_at, raw_text)
        VALUES
            (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (message_id) DO UPDATE
        SET imap_uid = EXCLUDED.imap_uid,
            folder = EXCLUDED.folder,
            sender = EXCLUDED.sender,
            subject = EXCLUDED.subject,
            received_at = EXCLUDED.received_at,
            raw_text = EXCLUDED.raw_text
        RETURNING id;
        """,
        (message_id, imap_uid, folder, sender, subject, received_at, raw_text)
    ).fetchone()

    return row[0]


def insert_analysis(conn, email_id, model, analysis, tokens_prompt, tokens_completion):
    conn.execute(
        """
        INSERT INTO email_analysis
            (email_id, model, analysis, tokens_prompt, tokens_completion)
        VALUES
            (%s, %s, %s, %s, %s);
        """,
        (
            email_id,
            model,
            Jsonb(analysis),
            tokens_prompt,
            tokens_completion
        )
    )

def update_email_classification(conn, email_id, category, confidence, needs_review):
    conn.execute(
        """
        UPDATE emails
        SET category = %s,
            category_confidence = %s,
            needs_review = %s
        WHERE id = %s;
        """,
        (category, confidence, needs_review, email_id)
    )

def insert_email_decision(
    conn,
    email_id,
    model,
    category,
    probability,
    raw_response,
):
    conn.execute(
        """
        INSERT INTO email_decisions
            (email_id, model, category, category_probability, raw_response)
        VALUES
            (%s, %s, %s, %s, %s);
        """,
        (
            email_id,
            model,
            category,
            probability,
            Jsonb(raw_response),
        )
    )