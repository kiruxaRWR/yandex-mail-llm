import os
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

ROUTERAI_API_KEY = os.getenv("ROUTERAI_API_KEY")
DECISION_MODEL = os.getenv("ROUTERAI_DECISION_MODEL")

HIGH_CONFIDENCE = float(os.getenv("CLASSIFY_CONFIDENCE_HIGH", "0.80"))
REVIEW_CONFIDENCE = float(os.getenv("CLASSIFY_CONFIDENCE_REVIEW", "0.50"))

CATEGORIES = {
    "work": "Работа, учёба, задачи, переписка с коллегами",
    "finance": "Счета, оплаты, банковские уведомления, чеки",
    "events": "Хакатоны, олимпиады, стажировки, встречи, дедлайны",
    "notifications": "Регистрации, подтверждения, системные уведомления",
    "subscriptions": "Рассылки, новости, маркетинг",
    "personal": "Личная переписка",
    "spam": "Спам, фишинг, мусор",
    "other": "Всё остальное",
}

DECISIONS_URL = "https://routerai.ru/api/v1/decisions"


def classify_email(subject, sender, text):
    payload = {
        "model": DECISION_MODEL,
        "state": {
            "sender": sender,
            "subject": subject,
            "text": text[:20000],
        },
        "questions": {
            "category": {
                "type": "choice",
                "instructions": (
                    "Определи основную категорию письма. "
                    "Учитывай отправителя, тему и текст."
                ),
                "criteria": CATEGORIES,
            }
        },
    }

    response = requests.post(
        DECISIONS_URL,
        headers={
            "Authorization": f"Bearer {ROUTERAI_API_KEY}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=60,
    )

    response.raise_for_status()
    result = response.json()

    answer = result["answers"]["category"]
    category = answer["choice"]
    probability = answer["probabilities"].get(category, 0.0)

    return category, float(probability), result


def classification_is_confident(probability):
    return probability >= HIGH_CONFIDENCE


def classification_needs_review(probability):
    return REVIEW_CONFIDENCE <= probability < HIGH_CONFIDENCE