import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
import time

from db import *

load_dotenv(Path(__file__).with_name(".env"))

from classifier import (
    classify_email,
    classification_is_confident,
    classification_needs_review,
)

from imap_client import (
    open_mailbox,
)

EMAIL = os.getenv("YANDEX_EMAIL")
APP_PASSWORD = os.getenv("YANDEX_APP_PASSWORD")
ROUTERAI_API_KEY = os.getenv("ROUTERAI_API_KEY")
MODELD = os.getenv("ROUTERAI_MODEL_DEEPSEEK")

IMAP_HOST = "imap.yandex.ru"
LIMIT = 50

client = OpenAI(
    api_key=ROUTERAI_API_KEY,
    base_url="https://routerai.ru/api/v1"
)

CATEGORIES = [
    "work",
    "finance",
    "events",
    "notifications",
    "subscriptions",
    "personal",
    "spam",
    "other",
]



PROMPT = f"""
Ты анализируешь письмо пользователя и извлекаешь важные данные.

Доступные категории:
{", ".join(CATEGORIES)}

Правила:
- Выбери ровно одну наиболее подходящую категорию.
- Не придумывай категории вне списка.
- Если уверенность ниже 0.5, поставь needs_review = true.
- Даты возвращай в формате YYYY-MM-DD, время — HH:MM.
- Если данных нет, используй null.
- В description дай подробное, но краткое описание события:
  что нужно сделать, зачем, какие условия и что произойдёт при пропуске.
- В links добавляй только релевантные ссылки:
  регистрация, страница события, оплата, документ, форма, личный кабинет.
- Не добавляй ссылки на рекламу, социальные сети и нерелевантные страницы.
- Верни строго JSON без markdown и пояснений.

Формат ответа:
{{
  "category": "одна из категорий",
  "confidence": 0.0,
  "needs_review": true,
  "summary": "краткое резюме",
  "requires_reply": true,
  "urgency": "low | medium | high",
  "important_data": [],
  "events": [
    {{
      "type": "meeting | deadline | registration | payment | other",
      "title": "",
      "date": null,
      "time": null,
      "description": "",
      "links": []
    }}
  ]
}}
"""

import re
from html import unescape

URL_PATTERN = re.compile(
    r"https?://[^\s<>\"')\]]+",
    re.IGNORECASE,
)


def extract_links(text):
    if not text:
        return []

    text = unescape(text)

    urls = URL_PATTERN.findall(text)

    unique_urls = []
    seen = set()

    for url in urls:
        url = url.rstrip(".,;:!?)")

        if url not in seen:
            seen.add(url)
            unique_urls.append(url)

    return unique_urls[:10]

def extract_text(msg):
    text = msg.text or ""

    if not text and msg.html:
        text = msg.html

    return text.strip()


def analyze_email(subject, sender, text):
    response = client.chat.completions.create(
        model=MODELD,
        messages=[
            {"role": "system", "content": PROMPT},
            {
                "role": "user",
                "content": f"От: {sender}\nТема: {subject}\n\nТекст:\n{text[:12000]}"
            }
        ],
        temperature=0.1
    )

    usage = response.usage
    tokens_prompt = usage.prompt_tokens if usage else None
    tokens_completion = usage.completion_tokens if usage else None

    return response.choices[0].message.content, tokens_prompt, tokens_completion


def normalize_category(category):
    category = (category or "").strip().lower()

    if category in CATEGORIES:
        return category

    return "other"

def parse_analysis(raw_response):
    analysis = json.loads(raw_response)

    analysis["category"] = normalize_category(analysis.get("category"))

    confidence = float(analysis.get("confidence", 0.0))

    analysis["confidence"] = max(0.0, min(confidence, 1.0))
    analysis["needs_review"] = bool(
        analysis.get("needs_review")
        or analysis["confidence"] < 0.7
        or analysis["category"] == "other"
    )

    return analysis

def process_email(conn, msg):
    message_id = msg.headers.get("message-id", [""])[0].strip()

    if not message_id:
        print("Пропуск: у письма нет Message-ID")
        return

    if email_exists(conn, message_id):
        print(f"Пропуск без LLM: {msg.subject}")
        return

    text = extract_text(msg)
    email_links = extract_links(text)

    email_id = insert_email(
        conn=conn,
        message_id=message_id,
        imap_uid=str(msg.uid),
        folder="INBOX",
        sender=msg.from_,
        subject=msg.subject,
        received_at=msg.date,
        raw_text=text
    )

    category, probability, decision_raw = classify_email(
        msg.subject,
        msg.from_,
        text
    )

    print(
        f"Decision: {msg.subject} -> "
        f"{category} ({probability:.2f})"
    )

    needs_review = classification_needs_review(probability)

    update_email_classification(
        conn=conn,
        email_id=email_id,
        category=category,
        confidence=probability,
        needs_review=needs_review,
    )

    DEEPSEEK_CATEGORIES = {
    "events",
    }

    needs_deep_analysis = (
    category in DEEPSEEK_CATEGORIES
    )

    if not needs_deep_analysis:
        print("DeepSeek не требуется.")
        return

    print("обработка события: вызываем DeepSeek.")

    raw_response, tokens_prompt, tokens_completion = analyze_email(
        msg.subject,
        msg.from_,
        text
    )

    analysis = parse_analysis(raw_response)

    insert_analysis(
        conn=conn,
        email_id=email_id,
        model=MODELD,
        analysis=analysis,
        tokens_prompt=tokens_prompt,
        tokens_completion=tokens_completion
    )

    save_events_from_analysis(
        conn=conn,
        email_id=email_id,
        source_message_id=message_id,
        analysis=analysis,
        email_links=email_links,
    )
    
    insert_email_decision(
    conn=conn,
    email_id=email_id,
    model=os.getenv("ROUTERAI_DECISION_MODEL"),
    category=category,
    probability=probability,
    raw_response=decision_raw,
    )


BATCH_SIZE = int(os.getenv("MAIL_BATCH_SIZE", "20"))
MAX_EMAILS = int(os.getenv("MAIL_MAX_EMAILS", "100"))



def process_batch(mailbox, uid_batch, conn):
    messages = list(
        mailbox.fetch(
            "ALL",
            uid_list=uid_batch,
            bulk=len(uid_batch),
            mark_seen=False,
        )
    )

    for msg in messages:
        process_email(conn, msg)



def process_uid_batch(uid_batch):
    with get_connection() as conn:
        with open_mailbox() as mailbox:
            process_batch(mailbox, uid_batch, conn)


def get_uid_batches(uids, batch_size):
    for start in range(0, len(uids), batch_size):
        yield uids[start:start + batch_size]

def main():
    init_db()

    with get_connection() as conn:
        with open_mailbox() as mailbox:
            uids = mailbox.uids("ALL")[::-1]

    uids = uids[:MAX_EMAILS]

    print(f"Найдено UID: {len(uids)}")

    for number, uid_batch in enumerate(
        get_uid_batches(uids, BATCH_SIZE),
        start=1,
    ):
        print(f"Пакет {number}: {len(uid_batch)} писем")

        process_uid_batch(uid_batch)

        time.sleep(1)

    print("Готово.")


if __name__ == "__main__":
    main()


