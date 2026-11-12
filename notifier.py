import asyncio
import os
from pathlib import Path
import logging
import random
import requests
from dotenv import load_dotenv
from telegram import Bot

load_dotenv(Path(__file__).with_name(".env"))

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

logger = logging.getLogger("notifier")

VK_API_URL = "https://api.vk.com/method/messages.send"
VK_API_VERSION = "5.199"

VK_GROUP_TOKEN = os.getenv("VK_GROUP_TOKEN")
VK_USER_ID = os.getenv("VK_USER_ID")


def send_vk_message(text):
    if not VK_GROUP_TOKEN or not VK_USER_ID:
        raise ValueError(
            "Не заданы VK_GROUP_TOKEN или VK_USER_ID"
        )

    response = requests.post(
        VK_API_URL,
        data={
            "access_token": VK_GROUP_TOKEN,
            "v": VK_API_VERSION,
            "user_id": VK_USER_ID,
            "random_id": random.randint(1, 2**31 - 1),
            "message": text,
        },
        timeout=30,
    )

    response.raise_for_status()
    result = response.json()

    if "error" in result:
        raise RuntimeError(result["error"].get("error_msg", result["error"]))

    logger.info("Уведомление отправлено в VK.")

def send_telegram_message(text):
    async def send():
        bot = Bot(token=BOT_TOKEN)

        async with bot:
            await bot.send_message(
                chat_id=CHAT_ID,
                text=text,
                parse_mode="HTML",
                disable_web_page_preview=False,
            )

    asyncio.run(send())

def send_notification(text):
    send_vk_message(text)